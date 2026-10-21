#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证9月9日推荐股票的实际走势"""

import os
import sys

# 添加依赖路径
deps = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.deps')
if os.path.isdir(deps):
    sys.path.insert(0, deps)

import akshare as ak
import pandas as pd
from datetime import datetime

stocks = [
    ('000012', '南玻A', 3.80),
    ('603867', '新化股份', 30.56),
    ('688136', '科兴制药', 21.61),
    ('601900', '南方传媒', 12.90),
    ('600731', '湖南海利', 6.11),
    ('000900', '现代投资', 3.71),
    ('300993', '玉马科技', 10.29),
    ('002267', '陕天然气', 7.53),
    ('002204', '大连重工', 5.31),
    ('002330', '得利斯', 4.38),
    ('000860', '顺鑫农业', 11.24),
    ('300080', '易成新能', 3.84),
    ('600713', '南京医药', 5.38),
    ('002375', '亚厦股份', 3.93),
    ('002540', '亚太科技', 5.26),
]

start = '20260909'
end = '20260921'

print(f'=== 推荐后走势分析 (2026-09-09 至 2026-09-21) ===')
print(f'{"代码":<8} {"名称":<8} {"推荐价":>8} {"最新价":>8} {"涨跌幅":>8} {"最高价":>8} {"最大涨幅":>8} {"最低价":>8} {"最大回撤":>8} 评价')
print('-' * 110)

results = []
for code, name, rec_price in stocks:
    try:
        df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date=start, end_date=end, adjust='qfq')
        if df is None or len(df) == 0:
            print(f'{code:<8} {name:<8} {rec_price:>8.2f}  N/A')
            continue
        
        latest = df.iloc[-1]
        latest_price = float(latest['收盘'])
        high = float(df['最高'].max())
        low = float(df['最低'].min())
        change_pct = (latest_price - rec_price) / rec_price * 100
        max_gain = (high - rec_price) / rec_price * 100
        max_drawdown = (low - rec_price) / rec_price * 100
        
        if change_pct > 5:
            eval_str = '盈利'
        elif change_pct > 0:
            eval_str = '微赚'
        elif change_pct > -5:
            eval_str = '微亏'
        else:
            eval_str = '亏损'
        
        print(f'{code:<8} {name:<8} {rec_price:>8.2f} {latest_price:>8.2f} {change_pct:>+7.2f}% {high:>8.2f} {max_gain:>+7.2f}% {low:>8.2f} {max_drawdown:>+7.2f}% {eval_str}')
        results.append((code, name, rec_price, latest_price, change_pct, max_gain, max_drawdown, eval_str))
    except Exception as e:
        print(f'{code:<8} {name:<8} {rec_price:>8.2f}  ERROR: {e}')

print()
if results:
    avg_change = sum(r[4] for r in results) / len(results)
    avg_gain = sum(r[5] for r in results) / len(results)
    avg_dd = sum(r[6] for r in results) / len(results)
    win_count = sum(1 for r in results if r[4] > 0)
    big_win = sum(1 for r in results if r[4] > 5)
    big_loss = sum(1 for r in results if r[4] < -5)
    
    print(f'=== 汇总统计 ===')
    print(f'平均涨跌幅: {avg_change:+.2f}%')
    print(f'平均最大涨幅: {avg_gain:+.2f}%')
    print(f'平均最大回撤: {avg_dd:+.2f}%')
    print(f'盈利数: {win_count}/{len(results)} (胜率{win_count/len(results)*100:.0f}%)')
    print(f'大赚(>5%): {big_win}只  大亏(<-5%): {big_loss}只')
    
    # 上证指数对比
    print()
    print(f'=== 大盘对比 ===')
    try:
        sh = ak.stock_zh_index_daily_em(symbol='sh000001')
        sh_909 = float(sh[sh['date']>='2026-09-09'].iloc[0]['close'])
        sh_latest = float(sh.iloc[-1]['close'])
        sh_change = (sh_latest - sh_909) / sh_909 * 100
        print(f'上证指数 9/9={sh_909:.2f} 最新={sh_latest:.2f} 涨跌幅={sh_change:+.2f}%')
        print(f'推荐组合 vs 大盘: {avg_change:+.2f}% vs {sh_change:+.2f}%  超额收益={avg_change-sh_change:+.2f}%')
    except Exception as e:
        print(f'获取上证指数失败: {e}')
