#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""持仓盯盘扩展数据：资金流 + 筹码分布（展示与预警用）。

- 资金流复用 lab.fund_flow 的全市场日缓存（全进程每天 1 次 HTTP）。
- 筹码用新浪日K（含换手率）本地计算，按 (代码, 自然日) 进程内缓存：
  日K每天只更新一次，持仓数量很少，单股一次 HTTP，线程安全。
- 任何失败只丢该只股票的数据，绝不影响持仓页与盯盘主流程。

注意与采集器口径一致：新浪 turnover 是小数，入库前 ×100 转百分数。
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger('webapp.lab.holdings')

from webapp.lab import fund_flow, chip

_lock = threading.Lock()
_kline_cache = {}  # (digits, date) -> {'bars': list|None, 'ts': monotonic}
_last_fetch_ts = None  # 上次真实 HTTP 拉K线时刻，用于突发节流
_FAIL_TTL = 600    # K线拉取失败只缓存 10 分钟，避免早盘一次抖动全天无数据
_KLINE_GAP = 0.3  # 连续拉K线的最小间隔（秒），避免被新浪突发节流


def _now():
    return time.monotonic()


def _fetch_bars(digits, market):
    """新浪日K（含换手率），取最近 120 个交易日；失败返回 None。"""
    import akshare as ak
    df = ak.stock_zh_a_daily(symbol=f'{market}{digits}', adjust='')
    if df is None or df.empty or 'turnover' not in df.columns:
        return None
    df = df.tail(120)
    bars = []
    for _, r in df.iterrows():
        try:
            t = r['turnover']
            t = float(t) * 100 if t == t else None  # NaN 判断 + 小数转百分数
            if t is not None and not (0 <= t <= 100):
                t = None
            bars.append({
                'date': str(r['date']),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'turnover': t,
            })
        except (TypeError, ValueError):
            continue
    return bars or None


def _bars_for(code):
    """成功按自然日缓存，失败仅短冷却（10 分钟）。"""
    global _last_fetch_ts
    try:
        market, digits = code.split('.')
    except (AttributeError, ValueError):
        return None
    if market not in ('sh', 'sz'):
        return None
    today = datetime.now().strftime('%Y-%m-%d')
    key = (digits, today)
    with _lock:
        ent = _kline_cache.get(key)
        if ent is not None:
            if ent['bars'] is not None or _now() - ent['ts'] < _FAIL_TTL:
                return ent['bars']
        last = _last_fetch_ts
    if last is not None:
        wait = _KLINE_GAP - (_now() - last)
        if wait > 0:
            time.sleep(wait)
    bars = None
    try:
        bars = _fetch_bars(digits, market)
    except Exception:
        logger.debug('持仓扩展K线拉取失败 %s', code, exc_info=True)
    with _lock:
        _last_fetch_ts = _now()
        _kline_cache[key] = {'bars': bars, 'ts': _now()}
        # 简单防膨胀：超过上限先清失败冷却项，再清旧日期项
        if len(_kline_cache) > 200:
            for k, v in list(_kline_cache.items()):
                if v['bars'] is None:
                    _kline_cache.pop(k, None)
            for k in [k for k in _kline_cache if k[1] != today]:
                _kline_cache.pop(k, None)
    return bars


def get_ext_map(codes):
    """批量取持仓股扩展数据。

    返回 {sh.xxxxxx: {'fund': dict|None, 'chip': dict|None,
                      'close': float|None}}。
    """
    codes = [c for c in codes if c]
    if not codes:
        return {}
    try:
        fund_map = fund_flow.fetch_market_fund_map()
    except Exception:
        logger.debug('资金流快照不可用', exc_info=True)
        fund_map = {}

    out = {}
    for code in dict.fromkeys(codes):  # 去重保序
        entry = {'fund': None, 'chip': None, 'close': None}
        try:
            entry['fund'] = fund_flow.get_fund_factor(code, fund_map)
        except Exception:
            entry['fund'] = None
        bars = _bars_for(code)
        if bars:
            entry['close'] = bars[-1]['close']
            try:
                entry['chip'] = chip.compute_chip(bars)
            except Exception:
                logger.debug('持仓筹码计算失败 %s', code, exc_info=True)
        out[code] = entry
    return out


def get_main_outflow_map(codes):
    """盘中预警专用：返回 {code: 资金流因子 dict}（仅含比率可得的标的），
    失败返回 {}，不触发K线请求。"""
    if not codes:
        return {}
    try:
        fund_map = fund_flow.fetch_market_fund_map()
    except Exception:
        return {}
    out = {}
    for code in codes:
        f = fund_flow.get_fund_factor(code, fund_map)
        if f and f.get('mf_main_ratio') is not None:
            out[code] = f
    return out


def reset_cache():
    global _last_fetch_ts
    with _lock:
        _kline_cache.clear()
        _last_fetch_ts = None
    fund_flow.reset_cache()


def enrich_stocks_with_fund_chip(stock_list):
    """批量给 stock dict 填充 fund/chip，供评分使用（全量扫描/自选分析共用）。

    - 资金流：一次全市场 HTTP（日缓存），按代码 map 查找，零额外请求。
    - 筹码：直接用 stock['kline_data']（采集器已含 turnover 百分数）本地计算，
      零额外 HTTP。
    - 原地修改 stock dict，stock['fund']/stock['chip'] 无数据时为 None。
    - 任何单股失败只丢该只数据，绝不抛异常。
    """
    if not stock_list:
        return
    try:
        fund_map = fund_flow.fetch_market_fund_map()
    except Exception:
        logger.debug('资金流快照不可用', exc_info=True)
        fund_map = {}

    for stock in stock_list:
        try:
            code = stock.get('code', '')
            stock['fund'] = fund_flow.get_fund_factor(code, fund_map)
        except Exception:
            stock['fund'] = None
        try:
            stock['chip'] = chip.compute_chip(stock.get('kline_data'))
        except Exception:
            stock['chip'] = None
