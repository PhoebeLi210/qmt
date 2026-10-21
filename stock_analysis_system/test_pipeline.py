#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试完整的数据处理链路"""

import sys
sys.path.insert(0, '.')

from data_collector import StockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine

# 1. 采集数据
print("="*60)
print("1. 数据采集")
print("="*60)
collector = StockDataCollector()
stock_list = collector.get_all_stocks()[:50]  # 只取前50只测试
print(f"采集到 {len(stock_list)} 只股票")
if stock_list:
    print(f"示例股票: {stock_list[0]['code']}")
    print(f"  latest_price: {stock_list[0].get('latest_price')}")
    print(f"  change_pct: {stock_list[0].get('change_pct')}")

# 2. 筛选形态
print("\n" + "="*60)
print("2. K线形态筛选")
print("="*60)
selector = StockSelector(stock_list)
selected_stocks = selector.select_by_kline_pattern()
print(f"筛选出 {len(selected_stocks)} 只符合形态的股票")
if selected_stocks:
    print(f"示例股票: {selected_stocks[0]['code']}")
    print(f"  latest_price: {selected_stocks[0].get('latest_price')}")
    print(f"  change_pct: {selected_stocks[0].get('change_pct')}")
    print(f"  pattern: {selected_stocks[0].get('pattern')}")

# 3. 分析
print("\n" + "="*60)
print("3. 股票分析")
print("="*60)
analyzer = StockAnalyzer(selected_stocks)
analyzed_stocks = analyzer.analyze_stocks()
print(f"完成 {len(analyzed_stocks)} 只股票的分析")
if analyzed_stocks:
    print(f"示例股票: {analyzed_stocks[0]['code']}")
    print(f"  latest_price: {analyzed_stocks[0].get('latest_price')}")
    print(f"  change_pct: {analyzed_stocks[0].get('change_pct')}")
    print(f"  score: {analyzed_stocks[0].get('score')}")

# 4. 生成推荐
print("\n" + "="*60)
print("4. 生成推荐")
print("="*60)
engine = RecommendationEngine(analyzed_stocks)
recommendations = engine.generate_recommendations()
print(f"生成 {len(recommendations)} 只推荐股票")
if recommendations:
    print(f"示例股票: {recommendations[0]['code']}")
    print(f"  latest_price: {recommendations[0].get('latest_price')}")
    print(f"  change_pct: {recommendations[0].get('change_pct')}")
    print(f"  score: {recommendations[0].get('score')}")
    print(f"  所有字段: {list(recommendations[0].keys())}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
