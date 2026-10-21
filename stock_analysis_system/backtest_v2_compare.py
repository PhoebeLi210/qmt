#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 优化回测对比：以 2026-09-09 为决策点，检验 v2 规则对 v1 推荐的改进

两部分：
A. 入场前过滤（优化1/5/6）：用截至9/9的K线检验 v2 严格底反弹 / 相对强度 / 前瞻信号
B. 出场规则（优化4）：对9/9买入仓位模拟 -5%止损、+5%减半/+10%清仓、5日时间止损
   对比持有到9/21的买入持有收益

数据源：新浪（stock_zh_a_daily，前复权）
"""

import os
import sys
import time

deps = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.deps')
if os.path.isdir(deps):
    sys.path.insert(0, deps)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import akshare as ak
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine

engine = RecommendationEngine([])

# (新浪代码, 代码, 名称, 9/9推荐价, v1形态)
STOCKS = [
    ('sz000012', '000012', '南玻A',   3.80,  'bottom_rebound'),
    ('sh603867', '603867', '新化股份', 30.56, 'bottom_rebound'),
    ('sh688136', '688136', '科兴制药', 21.61, 'bottom_rebound'),
    ('sh601900', '601900', '南方传媒', 12.90, 'bottom_rebound'),
    ('sh600731', '600731', '湖南海利', 6.11,  'upward_trend'),
    ('sz000900', '000900', '现代投资', 3.71,  'bottom_rebound'),
    ('sz300993', '300993', '玉马科技', 10.29, 'bottom_rebound'),
    ('sz002267', '002267', '陕天然气', 7.53,  'bottom_rebound'),
    ('sz002204', '002204', '大连重工', 5.31,  'bottom_rebound'),
    ('sz002330', '002330', '得利斯',   4.38,  'bottom_rebound'),
    ('sz000860', '000860', '顺鑫农业', 11.24, 'bottom_rebound'),
    ('sz300080', '300080', '易成新能', 3.84,  'bottom_rebound'),
    ('sh600713', '600713', '南京医药', 5.38,  'upward_trend'),
    ('sz002375', '002375', '亚厦股份', 3.93,  'bottom_rebound'),
    ('sz002540', '002540', '亚太科技', 5.26,  'bottom_rebound'),
]

ENTRY_DATE = '2026-09-09'
END_DATE = '2026-09-21'

selector = StockSelector([])
analyzer = StockAnalyzer([])


def simulate_exit(entry, future_df, sl_pct=5.0):
    """优化4出场模拟。返回 (策略收益率%, 出场原因)

    规则：
    - 止损：当日最低价 <= -sl_pct% → 全部按止损价卖出（当日先判止损，保守）
    - 止盈：最高 >= +10% → 半仓+5%、半仓+10%；最高 >= +5% → 半仓+5%卖出
    - 时间止损：第5个交易日收盘仍不涨（<=入场价）→ 收盘清仓
    - 其余持有到期末按收盘价估值
    """
    stop_price = entry * (1 - sl_pct / 100)
    tp1 = entry * 1.05
    tp2 = entry * 1.10
    half_sold = False
    realized = 0.0  # 已实现收益（占总仓位比例的收益率）

    for d, (_, row) in enumerate(future_df.iterrows(), start=1):
        low = float(row['low'])
        high = float(row['high'])
        close = float(row['close'])

        # 1) 止损优先
        if low <= stop_price:
            if half_sold:
                total = realized + 0.5 * ((stop_price - entry) / entry * 100)
            else:
                total = (stop_price - entry) / entry * 100
            return total, f'止损(-{sl_pct:.0f}%)第{d}日'

        # 2) 止盈
        if high >= tp2:
            r = 0.5 * 5.0 + 0.5 * 10.0
            if half_sold:
                # 之前已在tp1卖过半仓（理论上同日处理已涵盖，这里做容错）
                total = realized + 0.5 * 10.0
            else:
                total = r
            return total, f'止盈(+5%/+10%)第{d}日'
        if high >= tp1 and not half_sold:
            realized = 0.5 * 5.0
            half_sold = True

        # 3) 时间止损：第5日收盘不涨
        if d == 5 and close <= entry:
            if half_sold:
                total = realized + 0.5 * ((close - entry) / entry * 100)
            else:
                total = (close - entry) / entry * 100
            return total, f'时间止损第5日'

    # 4) 持有到期末
    final_close = float(future_df.iloc[-1]['close'])
    if half_sold:
        total = realized + 0.5 * ((final_close - entry) / entry * 100)
        return total, '半仓止盈后持有到期'
    return (final_close - entry) / entry * 100, '持有到期'


def main():
    rows = []
    print(f'=== v2 回测对比（决策日 {ENTRY_DATE}，验证至 {END_DATE}）===\n')

    for sina_code, code, name, rec_price, v1_pattern in STOCKS:
        try:
            df = ak.stock_zh_a_daily(symbol=sina_code,
                                     start_date='20260601', end_date='20260921',
                                     adjust='qfq')
            time.sleep(0.3)
            if df is None or len(df) == 0:
                print(f'{code} {name}: 无数据')
                continue

            df = df.reset_index(drop=True)
            df['date'] = df['date'].astype(str)
            entry_idx_list = df.index[df['date'] <= ENTRY_DATE].tolist()
            if not entry_idx_list:
                print(f'{code} {name}: 9/9前无K线')
                continue
            ei = entry_idx_list[-1]
            hist = df.iloc[:ei + 1].copy()
            future = df.iloc[ei + 1:].copy()

            entry = float(hist['close'].iloc[-1])

            # ---- A. 入场前 v2 检验 ----
            # 优化5：相对强度（20日跌幅>15%排除）
            ret20 = None
            opt5_pass = True
            if len(hist) >= 21:
                c20 = float(hist['close'].iloc[-21])
                ret20 = (entry - c20) / c20 * 100
                opt5_pass = ret20 >= -15

            # 优化1：v2 严格触底反弹（仅对v1以bottom_rebound入选的股票有意义）
            kline_data = hist.rename(columns={
                'date': 'date', 'open': 'open', 'high': 'high',
                'low': 'low', 'close': 'close', 'volume': 'volume'
            }).to_dict('records')
            stock_dict = {'code': code, 'kline_data': kline_data}
            v2_bottom, bottom_detail = selector._is_bottom_rebound(stock_dict, return_detail=True)
            if v1_pattern == 'bottom_rebound':
                opt1_pass = v2_bottom
            else:
                opt1_pass = True  # 上涨趋势形态不受底反弹重构影响

            # 优化6：前瞻信号
            div_score, div_sig = analyzer._analyze_macd_divergence(hist)
            brk_score, brk_sig = analyzer._analyze_volume_breakout(hist)
            fwd_signal = '；'.join([s for s in [div_sig, brk_sig] if s]) or '无'

            v2_enter = opt1_pass and opt5_pass

            # ---- B. 出场对比 ----
            bh_ret = (float(df.iloc[-1]['close']) - entry) / entry * 100
            # v2.1 ATR自适应止损（2×ATR，夹在4%-8%）
            atr = engine._calculate_atr(kline_data)
            if atr:
                atr_pct = min(max(2.0 * atr / entry * 100, 4.0), 8.0)
            else:
                atr_pct = 5.0
            if len(future) > 0:
                strat_ret, exit_reason = simulate_exit(entry, future, sl_pct=atr_pct)
                exit_reason = f'{exit_reason}[止损{atr_pct:.1f}%]'
            else:
                strat_ret, exit_reason = 0.0, '无后续数据'

            rows.append({
                'code': code, 'name': name, 'pattern': v1_pattern,
                'entry': entry, 'ret20': ret20,
                'opt5': opt5_pass, 'v2_bottom': v2_bottom,
                'opt1': opt1_pass, 'fwd': fwd_signal, 'v2_enter': v2_enter,
                'bh': bh_ret, 'strat': strat_ret, 'exit': exit_reason,
                'detail': bottom_detail if v1_pattern == 'bottom_rebound' else None,
            })
            tag5 = '通过' if opt5_pass else '排除'
            tag1 = '通过' if opt1_pass else '排除'
            print(f'{code} {name:<6} | 20日{ret20 if ret20 is None else round(ret20,1)}% 强度{tag5} '
                  f'| v2底反弹{tag1} | 前瞻:{fwd_signal} '
                  f'| 持有{bh_ret:+.2f}% → v2出场{strat_ret:+.2f}% ({exit_reason})')
        except Exception as e:
            print(f'{code} {name}: ERROR {str(e)[:60]}')

    if not rows:
        print('无有效结果')
        return

    n = len(rows)
    bh_avg = sum(r['bh'] for r in rows) / n
    st_avg = sum(r['strat'] for r in rows) / n
    bh_win = sum(1 for r in rows if r['bh'] > 0) / n * 100
    st_win = sum(1 for r in rows if r['strat'] > 0) / n * 100

    survivors = [r for r in rows if r['v2_enter']]
    rejected = [r for r in rows if not r['v2_enter']]

    print('\n' + '=' * 80)
    print('=== B. 出场规则对比（v2.1 ATR自适应止损，全部15只）===')
    print(f'v1 买入持有：平均 {bh_avg:+.2f}%，胜率 {bh_win:.0f}%')
    print(f'v2.1 ATR止损止盈：平均 {st_avg:+.2f}%，胜率 {st_win:.0f}%')
    print(f'出场规则贡献：{st_avg - bh_avg:+.2f} 个百分点')

    print('\n=== A. 入场过滤对比（优化1+5）===')
    def reject_reason(r):
        tags = []
        if not r['opt5']:
            tags.append('相对强度')
        if not r['opt1']:
            tags.append('严格底反弹')
        return f"{r['name']}({'+'.join(tags)})"
    print(f'v2 将排除 {len(rejected)} 只：' + '、'.join(reject_reason(r) for r in rejected))
    if survivors:
        sv_bh = sum(r['bh'] for r in survivors) / len(survivors)
        sv_st = sum(r['strat'] for r in survivors) / len(survivors)
        sv_win = sum(1 for r in survivors if r['bh'] > 0) / len(survivors) * 100
        print(f'v2 保留 {len(survivors)} 只 → 买入持有平均 {sv_bh:+.2f}%，胜率 {sv_win:.0f}%')
        print(f'v2 保留 {len(survivors)} 只 → 叠加v2出场平均 {sv_st:+.2f}%')
    if rejected:
        rj_bh = sum(r['bh'] for r in rejected) / len(rejected)
        print(f'被排除 {len(rejected)} 只 持有到期平均 {rj_bh:+.2f}%（排除的实际避损/踏空效果）')

    print('\n=== 优化1诊断：13只v1底反弹股在v2八条件上的失败分布 ===')
    detail_rows = [(r['name'], r['detail']) for r in rows if r['detail']]
    if detail_rows:
        for cn in list(detail_rows[0][1].keys()):
            fails = [(name, d[cn][1]) for name, d in detail_rows if not d[cn][0]]
            extra = '  ' + '；'.join(f'{n}:{v}' for n, v in fails) if fails else ''
            print(f'  {cn}: 失败 {len(fails)}/{len(detail_rows)}{extra}')

    print('\n=== 优化6：9/9时点前瞻信号分布 ===')
    has_fwd = [r for r in rows if r['fwd'] != '无']
    for r in has_fwd:
        print(f"  {r['code']} {r['name']}: {r['fwd']} → 持有{r['bh']:+.2f}%")
    if not has_fwd:
        print('  15只在9/9均无底背离/放量突破信号（前瞻信号不会给这批股票加分）')


if __name__ == '__main__':
    main()
