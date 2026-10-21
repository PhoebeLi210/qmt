#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试数据采集器"""

import sys
sys.path.insert(0, '.')

from data_collector import StockDataCollector

# 测试获取单只股票数据
collector = StockDataCollector()
test_stocks = ['sh.600000', 'sz.000001', 'sz.002594', 'sz.000889']
for code in test_stocks:
    data = collector._get_stock_detail_akshare(code)
    if data:
        print(f'{code}: latest_price={data.get("latest_price")}, change_pct={data.get("change_pct")}, kline_count={len(data.get("kline_data", []))}')
        if data.get('kline_data'):
            print(f'  最新收盘价: {data["kline_data"][-1]["close"]}')
            print(f'  前一天收盘价: {data["kline_data"][-2]["close"]}')
    else:
        print(f'{code}: 获取失败')
