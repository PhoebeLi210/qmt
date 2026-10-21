#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试运行脚本：限流80只股票验证端到端管线"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_collector_optimized import OptimizedStockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine

LIMIT = 80

def main():
    print(f"=== 试运行（限流 {LIMIT} 只）===")
    start = time.time()

    # 1. 采集
    collector = OptimizedStockDataCollector()
    stocks = collector.get_all_stocks(limit=LIMIT)
    print(f"[1/4] 采集完成: {len(stocks)} 只")
    if not stocks:
        print("无股票数据，退出")
        return

    # 2. K线形态筛选
    selector = StockSelector(stocks)
    selected = selector.select_by_kline_pattern()
    print(f"[2/4] 形态筛选: {len(selected)} 只 (通过率 {len(selected)/len(stocks)*100:.1f}%)")
    if not selected:
        print("无股票通过形态筛选")
        return

    # 3. 多因子分析
    analyzer = StockAnalyzer(selected)
    analyzed = analyzer.analyze_stocks()
    print(f"[3/4] 多因子分析: {len(analyzed)} 只 (通过率 {len(analyzed)/len(selected)*100:.1f}%)")
    if not analyzed:
        print("无股票通过分析")
        return

    # 4. 推荐
    engine = RecommendationEngine(analyzed)
    recs = engine.generate_recommendations()
    print(f"[4/4] 推荐: {len(recs)} 只")

    print("\n" + "=" * 60)
    for i, s in enumerate(recs, 1):
        print(f"{i}. {s['code']} {s['name']}  score={s.get('score', 0):.1f}  "
              f"风险={s.get('risk_level', '-')}  仓位={s.get('position_sizing', '-')}")
        print(f"   理由: {s.get('recommendation_reason', '-')}")
    print("=" * 60)
    print(f"总耗时: {time.time()-start:.1f}s")

if __name__ == "__main__":
    main()
