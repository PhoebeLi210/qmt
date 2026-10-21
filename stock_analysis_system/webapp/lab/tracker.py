#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号结果回填与路径判定

交易口径（与推荐清单"次日验证、不追涨停"的实际用法一致）：
- T 日收盘出信号，T+1 开盘买入；T+1 开盘相对 T 收盘涨停（主板≥9.5%、
  创业板/科创板≥19.5%、北交所≥29.5%）记 no_entry，剔除样本
- 路径口径：T+1 起 20 个交易日内，先触 tp2 计胜、先触 sl 计负；
  同一天都触到按保守原则计 sl；先触 tp1 再触 sl 按半仓止盈复合计收益；
  20 日到期未触任何边界计 neutral
- 窗口口径：T+3/5/10/20 收盘相对买入价的收益，并对比上证综指算超额
- 成本：路径实现收益统一扣 0.2%（佣金+印花税+滑点近似）
"""

import re
import json
import logging
from datetime import datetime, timedelta

from webapp import db

logger = logging.getLogger('webapp.lab.tracker')

HORIZON_DAYS = 20                 # 路径判定的最长交易日
ROUND_TRIP_COST = 0.002
WINDOWS = (3, 5, 10, 20)
TREND_PATTERNS = ('breakout', 'pullback', 'acceleration', 'upward_trend', '上涨趋势')
REBOUND_PATTERNS = ('v_rebound', 'double_bottom', 'consolidation_breakout',
                    'bottom_rebound', '底反弹')

# 每轮回填的拉取上限（akshare 单股单次调用，控制总耗时）
NEW_LIMIT = 300
PENDING_LIMIT = 300


# ---------------- 纯函数：路径判定（单测覆盖） ----------------

def limit_up_threshold(code):
    """按板块返回开盘涨停判定阈值（小数）。"""
    digits = (code or '').split('.')[-1]
    if digits.startswith(('30', '68')):
        return 0.195
    if digits.startswith(('8', '4')):
        return 0.295
    return 0.095


def default_exit_by_pattern(pattern):
    """ATR 缺失分支的默认止损止盈（与 recommendation_engine 同口径）。"""
    import strategy_params
    p = strategy_params.get_exit_params()
    is_trend = any(x in (pattern or '') for x in TREND_PATTERNS)
    is_rebound = any(x in (pattern or '') for x in REBOUND_PATTERNS)
    if is_trend and 'breakout' in (pattern or ''):
        tp1, tp2, tstop = p['tp_breakout']
    elif is_trend:
        tp1, tp2, tstop = p['tp_trend']
    elif is_rebound:
        tp1, tp2, tstop = p['tp_rebound']
    else:
        tp1, tp2, tstop = p['tp_default']
    sl = p['fallback_sl_rebound'] if is_rebound else p['fallback_sl_trend']
    return sl, tp1, tp2, tstop


def evaluate(signal_close, sl_pct, tp1_pct, tp2_pct, bars, bench=None,
             code=None):
    """对一条信号的未来 K 线做路径+窗口判定。

    bars: 信号日之后的日 K（升序），元素含 date/open/high/low/close
    bench: {date: 上证收盘}，可选
    返回 dict（字段对齐 db.upsert_outcome），至少包含 status。
    """
    result = {'status': 'pending', 'entry_date': None, 'entry_price': None,
              'exit_date': None, 'exit_price': None, 'exit_reason': None,
              'path_result': None, 'tp1_touched': 0, 'hold_days': None,
              'realized_ret': None, 'ret_3d': None, 'ret_5d': None,
              'ret_10d': None, 'ret_20d': None, 'bench_ret_20d': None,
              'excess_20d': None, 'max_gain': None, 'max_loss': None}

    if not signal_close or signal_close <= 0 or not bars:
        return result
    if not sl_pct or not tp2_pct:
        return result

    entry_bar = bars[0]
    entry = entry_bar['open']
    if not entry or entry <= 0:
        return result
    result['entry_date'] = entry_bar['date']
    result['entry_price'] = round(entry, 4)

    # T+1 开盘涨停 → 买不进
    if entry / signal_close - 1 >= limit_up_threshold(code):
        result['status'] = 'no_entry'
        return result

    sl_price = entry * (1 - sl_pct / 100)
    tp1_price = entry * (1 + tp1_pct / 100)
    tp2_price = entry * (1 + tp2_pct / 100)

    path = bars[:HORIZON_DAYS]
    tp1_touched = False

    for i, bar in enumerate(path):
        high, low = bar.get('high'), bar.get('low')
        if high is None or low is None:
            continue
        if not tp1_touched and high >= tp1_price:
            tp1_touched = True
        # 同日都触到：保守按止损先到
        if low <= sl_price:
            result.update(status='closed', exit_date=bar['date'],
                          exit_price=round(sl_price, 4),
                          exit_reason='sl_after_tp1' if tp1_touched else 'sl',
                          path_result='loss', tp1_touched=int(tp1_touched),
                          hold_days=i + 1)
            if tp1_touched:
                ret = 0.5 * tp1_pct / 100 + 0.5 * (-sl_pct / 100)
            else:
                ret = -sl_pct / 100
            result['realized_ret'] = round(ret - ROUND_TRIP_COST, 5)
            break
        if high >= tp2_price:
            # 简化：半仓 tp1 + 半仓 tp2（比"全部 tp2"更保守，见方案说明）
            ret = 0.5 * tp1_pct / 100 + 0.5 * tp2_pct / 100
            result.update(status='closed', exit_date=bar['date'],
                          exit_price=round(tp2_price, 4), exit_reason='tp2',
                          path_result='win', tp1_touched=int(tp1_touched),
                          hold_days=i + 1,
                          realized_ret=round(ret - ROUND_TRIP_COST, 5))
            break

    # 窗口收益（按收盘价，不含费用）
    for n in WINDOWS:
        if len(path) >= n and path[n - 1].get('close'):
            result[f'ret_{n}d'] = round(path[n - 1]['close'] / entry - 1, 5)

    highs = [b['high'] for b in path if b.get('high')]
    lows = [b['low'] for b in path if b.get('low')]
    if highs:
        result['max_gain'] = round(max(highs) / entry - 1, 5)
    if lows:
        result['max_loss'] = round(min(lows) / entry - 1, 5)

    if result['status'] != 'closed':
        if len(bars) >= HORIZON_DAYS:
            last = path[-1]
            result.update(status='closed', exit_date=last['date'],
                          exit_price=last.get('close'),
                          exit_reason='neutral', path_result='neutral',
                          tp1_touched=int(tp1_touched), hold_days=HORIZON_DAYS)
            if last.get('close'):
                result['realized_ret'] = round(
                    last['close'] / entry - 1 - ROUND_TRIP_COST, 5)
        # else: 仍在追踪窗口内，保持 pending

    # 基准超额（T+20 口径；entry_date 取实际 T+1 日期）
    if bench and result.get('ret_20d') is not None:
        ed = result['entry_date']
        xd = path[HORIZON_DAYS - 1]['date']
        b0, b1 = bench.get(ed), bench.get(xd)
        if b0 and b1:
            result['bench_ret_20d'] = round(b1 / b0 - 1, 5)
            result['excess_20d'] = round(result['ret_20d'] - (b1 / b0 - 1), 5)

    return result


# ---------------- 行情拉取（带进程内缓存） ----------------

class MarketFetcher:

    def __init__(self):
        self._stock_cache = {}
        self._bench = None

    def stock_bars(self, code, start_date, end_date):
        """拉个股日线（升序），东财失败回退新浪。返回 [{date,open,high,low,close}]。"""
        key = (code, start_date, end_date)
        if key in self._stock_cache:
            return self._stock_cache[key]
        bars = []
        try:
            import akshare as ak
            digits = code.split('.')[-1]
            try:
                df = ak.stock_zh_a_hist(
                    symbol=digits, period='daily',
                    start_date=start_date.replace('-', ''),
                    end_date=end_date.replace('-', ''))
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        bars.append({
                            'date': str(r['日期'])[:10],
                            'open': float(r['开盘']), 'high': float(r['最高']),
                            'low': float(r['最低']), 'close': float(r['收盘'])})
            except Exception:
                prefix = 'sh' if code.startswith('sh') else 'sz'
                df = ak.stock_zh_a_daily(symbol=f'{prefix}{digits}', adjust='')
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        d = str(r['date'])[:10]
                        if start_date <= d <= end_date:
                            bars.append({
                                'date': d, 'open': float(r['open']),
                                'high': float(r['high']),
                                'low': float(r['low']),
                                'close': float(r['close'])})
        except Exception as e:
            logger.debug('行情拉取失败 %s: %s', code, e)
        bars.sort(key=lambda b: b['date'])
        self._stock_cache[key] = bars
        return bars

    def benchmark(self):
        if self._bench is not None:
            return self._bench
        bench = {}
        try:
            import akshare as ak
            df = ak.stock_zh_index_daily(symbol='sh000001')
            if df is not None and not df.empty:
                bench = {str(r['date'])[:10]: float(r['close'])
                         for _, r in df.iterrows()}
        except Exception as e:
            logger.warning('基准指数拉取失败: %s', e)
        self._bench = bench
        return bench


# ---------------- 编排 ----------------

def _future_bars(bars, signal_date):
    return [b for b in bars if b['date'] > signal_date]


def _seeded_exit(snapshot):
    """快照缺止损止盈数值时（history/watch），按形态给默认值。"""
    sl = snapshot['sl_pct']
    tp1, tp2 = snapshot['tp1_pct'], snapshot['tp2_pct']
    tstop = snapshot['time_stop_days']
    if sl and tp1 and tp2:
        return sl, tp1, tp2, tstop
    d_sl, d_tp1, d_tp2, d_tstop = default_exit_by_pattern(snapshot['pattern'])
    return (sl or d_sl, tp1 or d_tp1, tp2 or d_tp2, tstop or d_tstop)


def _process_snapshot(snapshot, fetcher, today=None):
    today = today or datetime.now().strftime('%Y-%m-%d')
    start = (datetime.strptime(snapshot['signal_date'], '%Y-%m-%d')
             - timedelta(days=5)).strftime('%Y-%m-%d')
    bars = fetcher.stock_bars(snapshot['code'], start, today)
    future = _future_bars(bars, snapshot['signal_date'])
    if not future:
        return False  # 还没有 T+1 数据，下次再试
    sl, tp1, tp2, _ = _seeded_exit(snapshot)
    out = evaluate(snapshot['ref_price'], sl, tp1, tp2, future,
                   bench=fetcher.benchmark(), code=snapshot['code'])
    out['path_json'] = json.dumps(future[:HORIZON_DAYS], ensure_ascii=False)
    db.upsert_outcome(snapshot['id'], **out)
    return True


def run_daily(new_limit=NEW_LIMIT, pending_limit=PENDING_LIMIT):
    """盘后回填：新信号建 outcome + pending 信号续追踪。返回 (新建, 更新, 跳过)。"""
    fetcher = MarketFetcher()
    today = datetime.now().strftime('%Y-%m-%d')
    created = updated = skipped = 0

    # 至少有 T+1：信号日早于今天的才处理
    for snap in db.list_signals_without_outcome(new_limit, max_signal_date=today):
        try:
            if _process_snapshot(snap, fetcher, today):
                created += 1
            else:
                skipped += 1
        except Exception:
            logger.exception('回填失败 snapshot=%s', snap['id'])
            skipped += 1

    for row in db.list_pending_outcomes(pending_limit, stale_hours=20):
        try:
            if _process_snapshot(row, fetcher, today):
                updated += 1
            else:
                skipped += 1
        except Exception:
            logger.exception('续追踪失败 snapshot=%s', row['id'])
            skipped += 1

    logger.info('lab 回填完成: 新建 %d, 更新 %d, 跳过 %d',
                created, updated, skipped)
    return created, updated, skipped


# ---------------- 历史推荐回填基线 ----------------

_SL_RE = re.compile(r'(-?\d+(?:\.\d+)?)\s*%')
_PX_RE = re.compile(r'(\d+(?:\.\d+)?)\s*元')
_DAYS_RE = re.compile(r'(\d+)\s*个交易日')


def seed_history_snapshots():
    """把 daily_recommendations 里的历史推荐转成 source=history 信号快照。

    止损止盈从文本解析；解析不出按形态默认值。返回新增条数。
    """
    import strategy_params
    version = strategy_params.active_version()
    n = 0
    with db.get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM daily_recommendations ORDER BY trade_date, rank_no'
        ).fetchall()
        existed = {(r['signal_date'], r['code']) for r in conn.execute(
            "SELECT signal_date, code FROM signal_snapshots WHERE source='history'"
        ).fetchall()}

    for r in rows:
        if (r['trade_date'], r['code']) in existed:
            continue
        ref = r['latest_price'] or 0
        sl_pct = None
        m = _SL_RE.search(r['stop_loss'] or '')
        if m:
            sl_pct = abs(float(m.group(1)))
        tp1_pct = tp2_pct = None
        prices = _PX_RE.findall(r['take_profit'] or '')
        if ref > 0 and prices:
            tps = [float(x) for x in prices[:2]]
            if len(tps) >= 1:
                tp1_pct = round((tps[0] / ref - 1) * 100, 2)
            if len(tps) >= 2:
                tp2_pct = round((tps[1] / ref - 1) * 100, 2)
        tstop = None
        m2 = _DAYS_RE.search(r['time_stop'] or '')
        if m2:
            tstop = int(m2.group(1))
        if not sl_pct or not tp2_pct:
            d_sl, d_tp1, d_tp2, d_tstop = default_exit_by_pattern(r['pattern'])
            sl_pct = sl_pct or d_sl
            tp1_pct = tp1_pct or d_tp1
            tp2_pct = tp2_pct or d_tp2
            tstop = tstop or d_tstop

        db.save_signal_snapshot(
            r['trade_date'], r['code'], 'history',
            name=r['name'], pattern=r['pattern'], score=r['score'],
            final_score=r['score'], risk_score=None,
            market_regime=r['market_regime'], ref_price=ref,
            sl_pct=sl_pct, tp1_pct=tp1_pct, tp2_pct=tp2_pct,
            time_stop_days=tstop, recommended=True, rank_no=r['rank_no'],
            param_version=version,
            factors_json=None)
        n += 1
    logger.info('历史推荐信号快照新增 %d 条', n)
    return n


if __name__ == '__main__':
    import sys
    db.init_db()
    if '--seed-history' in sys.argv:
        added = seed_history_snapshots()
        print(f'历史快照新增 {added} 条')
    run_daily()
    print('回填完成')
