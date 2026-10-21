# -*- coding: utf-8 -*-
"""AlphaFeed 备用数据源（免费版：日K 10次/分·单标的，快照 10次/分·5标的/次）

仅作"兜底的兜底"：
- K线：东财 hist → 新浪 daily 均失败后才使用（data_collector_optimized）
- 报价：东财全市场快照 → 新浪批量行情 均缺失后才使用（webapp.monitor）

设计约束（免费额度很窄）：
1. API key 只从环境变量 ALPHAFEED_API_KEY 读取，代码/日志中绝不出现
2. 各端点独立限频（最小调用间隔），命中 RateLimit 后冷却
3. K线有进程内预算（默认60次），防止全市场扫描时在该源上耗数小时
4. 鉴权失败（401/403）本进程永久禁用；未安装 SDK / 无 key 时静默禁用
5. 日K不返回历史换手率，turnover 置 None（筹码因子降级，不影响形态/资金评分）

内部代码格式 sh.600000/sz.000001；AlphaFeed 格式 600000.SH/000001.SZ；北交所不支持。
"""
import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

_MIN_KLINE_INTERVAL = 6.2   # 10次/分 → 至少间隔6.2s
_MIN_QUOTE_INTERVAL = 6.2
_QUOTE_BATCH = 5            # 免费版快照单次最多5标的
_KLINE_BUDGET = int(os.environ.get('CHAOGU_AF_KLINE_BUDGET', '60'))
_QUOTE_BUDGET = int(os.environ.get('CHAOGU_AF_QUOTE_BUDGET', '200'))

_lock = threading.Lock()
_client = None
_client_override = None     # 测试注入
_init_done = False
_last_kline_ts = 0.0
_last_quote_ts = 0.0
_kline_calls = 0
_quote_calls = 0
_disabled_until = 0.0       # 限频冷却截止时间戳；0=未冷却
_permanently_disabled = ''  # 非空表示永久禁用原因


def reset_for_tests():
    """测试用：重置模块状态"""
    global _client, _init_done, _last_kline_ts, _last_quote_ts
    global _kline_calls, _quote_calls, _disabled_until, _permanently_disabled
    global _client_override
    with _lock:
        _client = None
        _client_override = None
        _init_done = False
        _last_kline_ts = 0.0
        _last_quote_ts = 0.0
        _kline_calls = 0
        _quote_calls = 0
        _disabled_until = 0.0
        _permanently_disabled = ''


def set_client_for_tests(client):
    """测试用：注入假客户端（传 None 恢复自动初始化）"""
    global _client_override, _client, _init_done
    with _lock:
        _client_override = client
        _client = client
        _init_done = client is not None


def status():
    """返回当前可用性状态（供日志/诊断）"""
    if _permanently_disabled:
        return f'disabled:{_permanently_disabled}'
    if _disabled_until:
        left = _disabled_until - time.time()
        if left > 0:
            return f'cooling:{left:.0f}s'
    if _client is not None:
        return 'ready'
    if not os.environ.get('ALPHAFEED_API_KEY'):
        return 'no-key'
    return 'unavailable' if _init_done else 'uninitialized'


def to_af_symbol(code):
    """sh.600000 -> 600000.SH；不支持的板块返回 None"""
    try:
        market, digits = code.split('.')
    except (ValueError, AttributeError):
        return None
    if market in ('sh', 'sz') and len(digits) == 6 and digits.isdigit():
        return f'{digits}.{market.upper()}'
    return None


def _get_client():
    """懒加载 AlphaFeed 客户端；不可用时返回 None"""
    global _client, _init_done, _permanently_disabled
    if _client_override is not None:
        return _client_override
    with _lock:
        if _init_done:
            return _client
        _init_done = True
        api_key = os.environ.get('ALPHAFEED_API_KEY', '').strip()
        if not api_key:
            logger.info('AlphaFeed 备用源未启用（未设置 ALPHAFEED_API_KEY）')
            return None
        try:
            from alphafeed import AlphaFeed
            _client = AlphaFeed(api_key=api_key)
            logger.info('AlphaFeed 备用源已启用（仅在主数据源失败时兜底）')
        except ImportError:
            logger.info('AlphaFeed SDK 未安装，备用源不可用')
        except Exception as e:
            logger.warning('AlphaFeed 客户端初始化失败: %s', type(e).__name__)
        return _client


def _is_auth_error(exc):
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return ('auth' in name or 'permission' in name
            or '401' in text or '403' in text or 'invalid api key' in text
            or 'unauthorized' in text)


def _is_rate_error(exc):
    name = type(exc).__name__.lower()
    return 'ratelimit' in name or 'rate limit' in str(exc).lower() or '429' in str(exc)


def _apply_failure(exc, where):
    """根据异常类型更新熔断器，返回 None"""
    global _disabled_until, _permanently_disabled, _client, _init_done
    if _is_auth_error(exc):
        _permanently_disabled = 'auth'
        logger.warning('AlphaFeed 鉴权失败（%s），本进程永久禁用备用源', where)
    elif _is_rate_error(exc):
        m = re.search(r'[Rr]etry after (\d+)', str(exc))
        wait_ms = int(m.group(1)) if m else 60000
        _disabled_until = max(_disabled_until, time.time() + wait_ms / 1000.0)
        logger.warning('AlphaFeed 触发限频（%s），冷却 %.0f 秒', where, wait_ms / 1000.0)
    else:
        # 普通网络/服务错误：短冷却，避免在坏源上反复重试
        _disabled_until = max(_disabled_until, time.time() + 30)
        logger.debug('AlphaFeed 调用失败（%s）: %s %s',
                     where, type(exc).__name__, str(exc)[:120])


def _gate(kind):
    """调用前检查：返回 True 放行。kind='kline'/'quote'"""
    global _kline_calls, _quote_calls, _last_kline_ts, _last_quote_ts
    if _permanently_disabled:
        return False
    # 冷却期不放行
    if _disabled_until and time.time() < _disabled_until:
        return False
    # 预算 + 最小间隔（sleep 在锁外，避免阻塞另一端点）
    with _lock:
        if kind == 'kline':
            if _kline_calls >= _KLINE_BUDGET:
                return False
            last = _last_kline_ts
            interval = _MIN_KLINE_INTERVAL
        else:
            if _quote_calls >= _QUOTE_BUDGET:
                return False
            last = _last_quote_ts
            interval = _MIN_QUOTE_INTERVAL
    wait = interval - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    with _lock:
        if kind == 'kline':
            _last_kline_ts = time.time()
            _kline_calls += 1
        else:
            _last_quote_ts = time.time()
            _quote_calls += 1
    return True


def get_daily_kline(code, count=40):
    """获取日K，返回与采集器内部一致的 list[dict]：
    {date,open,high,low,close,volume,turnover(None)}；不可用时返回 []。
    """
    client = _get_client()
    if client is None:
        return []
    symbol = to_af_symbol(code)
    if symbol is None:
        return []
    if not _gate('kline'):
        return []
    try:
        df = client.klines.get(symbol, count=count, to_dataframe=True)
    except Exception as e:
        _apply_failure(e, f'kline {code}')
        return []
    if df is None or len(df) == 0:
        return []
    rows = []
    for _, r in df.iterrows():
        try:
            o, h, l, c, v = (float(r['open']), float(r['high']), float(r['low']),
                             float(r['close']), float(r['volume']))
        except (KeyError, TypeError, ValueError):
            continue
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
            continue
        rows.append({
            'date': str(r['trade_date'])[:10],
            'open': o, 'high': h, 'low': l, 'close': c,
            'volume': v, 'turnover': None,  # AlphaFeed 日K无历史换手率
        })
    return rows


def get_quotes(codes):
    """批量实时行情兜底。codes 为 sh./sz. 前缀列表，
    返回 {6位代码: {price,pct,high,low,open,preclose,vol_ratio(None)}}。
    """
    client = _get_client()
    if client is None:
        return {}
    sym_map = {}
    for code in codes:
        sym = to_af_symbol(code)
        if sym:
            sym_map[sym] = code.split('.')[-1]
    if not sym_map:
        return {}

    out = {}
    syms = list(sym_map.keys())
    for i in range(0, len(syms), _QUOTE_BATCH):
        batch = syms[i:i + _QUOTE_BATCH]
        if not _gate('quote'):
            break
        try:
            df = client.quotes.get(symbols=batch, to_dataframe=True)
        except Exception as e:
            _apply_failure(e, 'quotes')
            break
        if df is None or len(df) == 0:
            continue
        for _, r in df.iterrows():
            try:
                price = float(r['last_price'])
            except (KeyError, TypeError, ValueError):
                continue
            if price <= 0:
                continue
            digits = sym_map.get(str(r.get('symbol', '')))
            if not digits:
                continue

            def _f(name):
                try:
                    v = float(r[name])
                    return v if v == v else None
                except (KeyError, TypeError, ValueError):
                    return None

            pct = _f('ext.change_pct')
            out[digits] = {
                'price': price,
                'pct': pct * 100 if pct is not None else None,
                'high': _f('high'),
                'low': _f('low'),
                'open': _f('open'),
                'preclose': _f('prev_close'),
                'vol_ratio': None,  # 快照无量比字段
            }
    return out
