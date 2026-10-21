#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中监控引擎（二期 + 三期）

数据：东财实时行情快照（一次请求取全市场，进程内短时缓存）。
节奏：交易时段（9:30-11:30 / 13:00-15:00，交易日历校验）约每 2 分钟一轮。

二期：
- 持仓静态止损（价 <= 成本*(1-止损%)）/ 静态止盈（>= 成本*(1+止盈%)）
- 自选股"买点提醒"：最近一次分析通过、当前价回到买点参考价附近（未持仓）

三期：
- 移动止损状态机：维护持仓以来盘中最高价 peak_price，
  动态止损线 = max(硬止损, peak*(1-移动回撤%))，跌破即预警
- 盘中见顶近似预警：盘中曾明显冲高（最高较昨收 >=4%）后
  自最高点回落 >=2%（可选叠加放量），提示"冲高回落"

预警一律落 alerts 表（用户+股+日+类型唯一），天然当日去重，
同一用户一轮内的多条预警聚合为一条推送，避免轰炸。
"""

import re
import time
import logging
import threading
from datetime import datetime, date, time as dtime

from webapp import db, push as push_mod

logger = logging.getLogger('webapp.monitor')

# ---------------- 参数（集中可调） ----------------
SPOT_CACHE_SECONDS = 75          # 快照缓存；监控周期 120s，页面也复用
QUOTE_CACHE_SECONDS = 70         # 兜底行情缓存
BUY_BAND = 0.005                 # 买点提醒：现价 <= 参考价 * 1.005
TOP_SURGE_MIN = 0.04             # 见顶近似：最高较昨收至少 +4%
TOP_PULLBACK_MIN = 0.02          # 见顶近似：现价自最高点回落至少 2%
TOP_VOL_RATIO = 1.5              # 见顶近似：量比参考阈值（仅写入说明，不做硬门槛）
SOURCE_WARN_GAP = 300            # 主源失败日志节流秒数（避免每 2 分钟刷屏）
FUND_OUTFLOW_RATIO = -0.08       # 主力净占比 ≤ -8% 触发大幅流出预警
FUND_MIN_AMOUNT = 2e7            # 成交额低于 2000 万的比率噪音大，不预警

MORNING_START, MORNING_END = dtime(9, 30), dtime(11, 30)
AFTERNOON_START, AFTERNOON_END = dtime(13, 0), dtime(15, 0)

# ---------------- 实时快照 ----------------
_spot_lock = threading.Lock()
_spot_cache = {'ts': 0.0, 'map': None}
_quote_lock = threading.Lock()
_quote_cache = {'ts': 0.0, 'map': {}}
_last_warn_ts = 0.0


def _to_float(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN 过滤
    except (TypeError, ValueError):
        return None


def get_spot_map(force=False):
    """返回 {6位代码: {price,pct,high,low,open,preclose,vol_ratio}}；失败返回 None。"""
    import time
    now_ts = time.time()
    with _spot_lock:
        if (not force and _spot_cache['map'] is not None
                and now_ts - _spot_cache['ts'] < SPOT_CACHE_SECONDS):
            return _spot_cache['map']
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return _spot_cache['map']
        col = {c: c for c in df.columns}

        def pick(*names):
            for n in names:
                if n in col:
                    return n
            return None

        c_code = pick('代码')
        c_price = pick('最新价')
        c_pct = pick('涨跌幅')
        c_high = pick('最高')
        c_low = pick('最低')
        c_open = pick('今开')
        c_pre = pick('昨收')
        c_vr = pick('量比')
        if not c_code or not c_price:
            return _spot_cache['map']

        spot = {}
        for _, row in df.iterrows():
            price = _to_float(row[c_price])
            if price is None or price <= 0:
                continue
            spot[str(row[c_code]).zfill(6)] = {
                'price': price,
                'pct': _to_float(row[c_pct]) if c_pct else None,
                'high': _to_float(row[c_high]) if c_high else None,
                'low': _to_float(row[c_low]) if c_low else None,
                'open': _to_float(row[c_open]) if c_open else None,
                'preclose': _to_float(row[c_pre]) if c_pre else None,
                'vol_ratio': _to_float(row[c_vr]) if c_vr else None,
            }
        with _spot_lock:
            _spot_cache['ts'] = now_ts
            _spot_cache['map'] = spot
        return spot
    except Exception:
        global _last_warn_ts
        if now_ts - _last_warn_ts > SOURCE_WARN_GAP:
            logger.warning('东财全市场快照获取失败，将对所需股票走新浪兜底行情')
            _last_warn_ts = now_ts
        return _spot_cache['map']


_SINA_LINE = re.compile(r'hq_str_(sh|sz)(\d{6})="([^"]*)"')


def _sina_quotes(codes):
    """新浪批量实时行情兜底。codes 为 sh.xxxxxx/sz.xxxxxx 列表，返回 {6位代码: quote}。"""
    import requests
    syms = []
    for c in codes:
        market, digits = c.split('.')
        if market in ('sh', 'sz'):
            syms.append(f'{market}{digits}')
    if not syms:
        return {}
    url = 'https://hq.sinajs.cn/list=' + ','.join(syms)
    resp = requests.get(
        url, timeout=8,
        headers={'Referer': 'https://finance.sina.com.cn'})
    resp.encoding = 'gbk'
    out = {}
    for market, digits, body in _SINA_LINE.findall(resp.text):
        parts = body.split(',')
        if len(parts) < 32 or not parts[3]:
            continue  # 停牌或无数据
        price = _to_float(parts[3])
        preclose = _to_float(parts[2])
        pct = ((price / preclose - 1) * 100) if price and preclose else None
        out[digits] = {
            'price': price,
            'pct': pct,
            'high': _to_float(parts[4]),
            'low': _to_float(parts[5]),
            'open': _to_float(parts[1]),
            'preclose': preclose,
            'vol_ratio': None,
        }
    return out


def get_quotes(codes, force=False):
    """获取指定股票（sh./sz. 前缀）实时行情：先东财全市场快照，缺失走新浪兜底。

    返回 {6位代码: quote}，可能只包含部分股票（停牌/源故障）。
    """
    codes = list(codes)
    digits = {c.split('.')[-1] for c in codes}
    full = get_spot_map(force=force)
    result = {}
    if full:
        result.update({d: full[d] for d in digits if d in full})

    missing = [c for c in codes if c.split('.')[-1] not in result]
    if not missing:
        return result

    now_ts = time.time()
    with _quote_lock:
        fresh = (not force) and now_ts - _quote_cache['ts'] < QUOTE_CACHE_SECONDS
        cached = dict(_quote_cache['map']) if fresh else {}
    # 缓存里已有的直接用，其余的重新批量取
    still_missing = [c for c in missing if c.split('.')[-1] not in cached]
    if still_missing:
        try:
            fresh_map = _sina_quotes(still_missing)
        except Exception:
            logger.warning('新浪兜底行情也获取失败，缺失股票本轮跳过: %s',
                           ','.join(still_missing[:10]))
            fresh_map = {}
        cached.update(fresh_map)

        # 新浪仍缺失的少量股票，最后走 AlphaFeed（免费版5标的/次，仅小名单兜底）
        af_missing = [c for c in still_missing
                      if c.split('.')[-1] not in fresh_map]
        if af_missing:
            try:
                import alphafeed_source
                cached.update(alphafeed_source.get_quotes(af_missing))
            except Exception:
                logger.debug('AlphaFeed 兜底行情失败: %s',
                             ','.join(af_missing[:10]))

        with _quote_lock:
            _quote_cache['ts'] = now_ts
            _quote_cache['map'] = cached
    result.update({d: cached[d] for d in digits if d in cached})
    return result


# ---------------- 交易日 / 交易时段 ----------------
_calendar_lock = threading.Lock()
_calendar = {'day': None, 'dates': None}


def is_trading_day(day=None):
    """akshare 交易日历；获取失败时降级为工作日判断。"""
    day = day or date.today()
    with _calendar_lock:
        if _calendar['day'] == day:
            dates = _calendar['dates']
        else:
            dates = None
            try:
                import akshare as ak
                df = ak.tool_trade_date_hist_sina()
                if df is not None and not df.empty and 'trade_date' in df.columns:
                    dates = {d.date() if hasattr(d, 'date') else d
                             for d in df['trade_date']}
            except Exception:
                logger.warning('交易日历获取失败，降级为周一至周五判断')
            _calendar['day'] = day
            _calendar['dates'] = dates
    if dates is not None:
        return day in dates
    return day.weekday() < 5


def in_session(now=None):
    now = now or datetime.now()
    if not is_trading_day(now.date()):
        return False
    t = now.time()
    return ((MORNING_START <= t <= MORNING_END)
            or (AFTERNOON_START <= t <= AFTERNOON_END))


# ---------------- 预警评估 ----------------

def _emit(per_user, uid, code, trade_date, atype, price, ref, detail, push_title):
    """落库去重；新预警才加入待推送集合。"""
    alert_id = db.add_alert(uid, code, trade_date, atype,
                            price=price, ref_price=ref, detail=detail)
    if alert_id is not None:
        per_user.setdefault(uid, []).append((push_title, price, ref, detail, alert_id))
        logger.info(f'新预警 uid={uid} {code} {atype} price={price} ref={ref}')
    return alert_id


def _check_positions(spot, trade_date, per_user, fund_map=None):
    fund_map = fund_map or {}
    for p in db.list_all_open_positions():
        s = spot.get(p['code'].split('.')[-1])
        if not s:
            continue
        price, high = s['price'], s['high'] or s['price']
        cost = p['cost']
        name = p['name'] or p['code']

        hard_stop = cost * (1 - p['stop_pct'])
        take_line = cost * (1 + p['take_pct'])

        # ---- 二期：静态止损 / 止盈 ----
        if price <= hard_stop:
            detail = (f'成本 {cost:.2f}，止损线 {hard_stop:.2f}'
                      f'（-{p["stop_pct"] * 100:.1f}%），现价 {price:.2f}')
            _emit(per_user, p['user_id'], p['code'], trade_date,
                  'stop_loss', price, hard_stop, detail,
                  f'⛔ 止损提醒：{name}')
        if price >= take_line:
            detail = (f'成本 {cost:.2f}，止盈线 {take_line:.2f}'
                      f'（+{p["take_pct"] * 100:.1f}%），现价 {price:.2f}')
            _emit(per_user, p['user_id'], p['code'], trade_date,
                  'take_profit', price, take_line, detail,
                  f'🎯 止盈提醒：{name}')

        # ---- 三期：移动止损状态机 ----
        # 未产生足够浮盈前不激活（否则会把用户自设的宽止损偷偷收紧）；
        # 激活条件：峰值涨幅 >= 移动回撤幅度，此时回撤线 >= 成本，保本优先。
        if p['trail_pct'] and p['trail_pct'] > 0:
            peak_prev = p['peak_price'] or cost
            peak = max(peak_prev, high, price)
            if peak > peak_prev:
                db.update_position_peak(p['id'], peak)
            armed = peak / cost - 1 >= p['trail_pct']
            if armed:
                trail_line = peak * (1 - p['trail_pct'])
                dyn_stop = max(hard_stop, trail_line)
                if price <= dyn_stop:
                    detail = (f'持仓最高价 {peak:.2f}，移动止损线 {dyn_stop:.2f}'
                              f'（自高点回撤 {p["trail_pct"] * 100:.1f}%），现价 {price:.2f}')
                    _emit(per_user, p['user_id'], p['code'], trade_date,
                          'trailing_stop', price, dyn_stop, detail,
                          f'📉 移动止损：{name}')

        # ---- 三期：盘中见顶近似（冲高回落） ----
        preclose = s['preclose']
        if preclose and preclose > 0:
            surge = high / preclose - 1
            pullback = (high - price) / high if high > 0 else 0
            if surge >= TOP_SURGE_MIN and pullback >= TOP_PULLBACK_MIN:
                vr = s.get('vol_ratio')
                vr_txt = f'，量比 {vr:.1f}' if vr else ''
                if vr and vr >= TOP_VOL_RATIO:
                    vr_txt += '（明显放量）'
                detail = (f'盘中最高 {high:.2f}（较昨收 {surge * 100:+.1f}%），'
                          f'现价 {price:.2f}，自高点回落 {pullback * 100:.1f}%{vr_txt}')
                _emit(per_user, p['user_id'], p['code'], trade_date,
                      'top_warning', price, high, detail,
                      f'⚠️ 冲高回落：{name}')

        # ---- 大资金流向：主力（超大单+大单）大幅净流出 ----
        f = fund_map.get(p['code'])
        if f:
            ratio = f.get('mf_main_ratio')
            amount = f.get('mf_amount')
            if (ratio is not None and ratio <= FUND_OUTFLOW_RATIO
                    and (amount is None or amount >= FUND_MIN_AMOUNT)):
                net_yi = (f.get('mf_main_net') or 0) / 1e8
                detail = (f'今日主力（超大单+大单）净占比 {ratio * 100:.1f}%'
                          f'（净额 {net_yi:+.2f} 亿元），现价 {price:.2f}，'
                          f'资金显著流出，注意兑现/减仓风险')
                _emit(per_user, p['user_id'], p['code'], trade_date,
                      'fund_outflow', price, None, detail,
                      f'💸 主力大幅流出：{name}')


def _needed_codes():
    """本轮监控需要行情的全部股票（去重，sh./sz. 前缀）。"""
    codes = {p['code'] for p in db.list_all_open_positions()}
    with db.get_db() as conn:
        user_ids = [r['id'] for r in conn.execute('SELECT id FROM users').fetchall()]
    for uid in user_ids:
        codes.update(db.get_latest_passed_map(uid).keys())
    return codes, user_ids


def _check_buy_points(spot, trade_date, per_user, user_ids=None):
    """所有用户：自选股最近一次分析通过、且当前价回到买点参考价附近。"""
    if user_ids is None:
        with db.get_db() as conn:
            user_ids = [r['id'] for r in conn.execute('SELECT id FROM users').fetchall()]
    for uid in user_ids:
        passed_map = db.get_latest_passed_map(uid)
        for code, row in passed_map.items():
            ref = row['latest_price']
            s = spot.get(code.split('.')[-1])
            if not s or not ref or ref <= 0:
                continue
            price = s['price']
            if price <= ref * (1 + BUY_BAND):
                name = row['name'] or code
                detail = (f'买点参考价 {ref:.2f}（{row["trade_date"]} 分析通过，'
                          f'形态 {row["pattern"] or "—"}），现价 {price:.2f}')
                _emit(per_user, uid, code, trade_date, 'buy_point',
                      price, ref, detail, f'🔔 买点提醒：{name}')


def run_cycle(force=False):
    """执行一轮盘中检查。force=True 时忽略交易时段（测试用）。返回本轮新预警数。"""
    now = datetime.now()
    trade_date = now.strftime('%Y-%m-%d')
    if not force and not in_session(now):
        return 0

    codes, user_ids = _needed_codes()
    if not codes:
        return 0
    spot = get_quotes(codes, force=force)
    if not spot:
        logger.info('无可用实时行情，本轮跳过')
        return 0

    per_user = {}
    # 主力资金流（日缓存，全市场一次请求；失败返回空映射，不影响价格类预警）
    try:
        from webapp.lab.holdings import get_main_outflow_map
        fund_map = get_main_outflow_map(codes)
    except Exception:
        logger.debug('盘中资金流快照获取失败，本轮跳过资金流预警', exc_info=True)
        fund_map = {}
    _check_positions(spot, trade_date, per_user, fund_map=fund_map)
    _check_buy_points(spot, trade_date, per_user, user_ids=user_ids)

    # 按用户聚合：一轮一条推送
    for uid, items in per_user.items():
        user = db.get_user_by_id(uid)
        lines = []
        for title, price, ref, detail, alert_id in items:
            lines.append(f'{title}\n{detail}')
        body = '\n\n'.join(lines) + '\n\n（预警仅为模型规则触发的机械提醒，非投资建议）'
        ok, _msg = push_mod.push_to_user(user, f'chaogu 盘中预警（{len(items)}条）', body)
        if ok:
            for _, _, _, _, alert_id in items:
                db.mark_alert_pushed(alert_id)
        else:
            logger.warning(f'uid={uid} 预警推送失败，预警已落库，页面仍可查看')

    total = sum(len(v) for v in per_user.values())
    logger.info(f'盘中监控一轮完成: 新预警 {total} 条')
    return total
