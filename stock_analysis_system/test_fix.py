#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试日志颜色修复和价格数据获取"""

import sys

from stock_analysis_system.data_collector import StockDataCollector
from stock_analysis_system.utils.logger import setup_logger

def test_log_colors():
    """测试日志颜色是否正常（不应该有红色）"""
    print("=" * 50)
    print("测试日志颜色输出")
    print("=" * 50)
    
    logger = setup_logger('test_color')
    
    # 测试不同级别的日志
    logger.debug('DEBUG - 调试信息 (不应该显示)')
    logger.info('INFO - 普通信息')
    logger.warning('WARNING - 警告信息')
    logger.error('ERROR - 错误信息')
    
    print("\n注意：如果以上日志没有红色高亮，说明颜色修复成功")
    print()

def test_price_data():
    """测试价格数据获取"""
    print("=" * 50)
    print("测试价格数据获取")
    print("=" * 50)
    
    collector = StockDataCollector()
    stock_list = collector.get_all_stocks()[:5]
    
    print(f"获取到 {len(stock_list)} 只股票")
    
    for stock in stock_list:
        code = stock['code']
        print(f"\n测试股票: {code}")
        data = collector._get_stock_detail_akshare(code)
        if data:
            price = data.get('latest_price', '缺失')
            change = data.get('change_pct', '缺失')
            kline_count = len(data.get('kline_data', []))
            print(f"  最新价格: {price}")
            print(f"    涨跌幅: {change}")
            print(f"  K线数据量: {kline_count}")
        else:
            print(f"  获取数据失败")
    print()

def test_full_pipeline():
    """测试完整数据处理管道"""
    print("=" * 50)
    print("测试完整数据管道")
    print("=" * 50)
    
    from stock_analysis_system.stock_selector import StockSelector
    from stock_analysis_system.stock_analyzer import StockAnalyzer
    from stock_analysis_system.recommendation_engine import RecommendationEngine
    
    # 1. 采集数据
    collector = StockDataCollector()
    stock_list = collector.get_all_stocks()[:20]
    print(f"步骤1: 采集数据 - 获取 {len(stock_list)} 只股票")
    
    # 2. 筛选形态
    selector = StockSelector(stock_list)
    selected_stocks = selector.select_by_kline_pattern()
    print(f"步骤2: 筛选形态 - 通过 {len(selected_stocks)} 只")
    
    # 3. 分析
    analyzer = StockAnalyzer(selected_stocks)
    analyzed_stocks = analyzer.analyze_stocks()
    print(f"步骤3: 技术分析 - 分析 {len(analyzed_stocks)} 只")
    
    # 4. 生成推荐
    engine = RecommendationEngine(analyzed_stocks)
    recommendations = engine.generate_recommendations()
    print(f"步骤4: 生成推荐 - 推荐 {len(recommendations)} 只")
    
    # 5. 打印推荐结果
    print("\n" + "=" * 50)
    print("股票推荐结果")
    print("=" * 50)
    
    for i, stock in enumerate(recommendations[:10], 1):
        print(f"\n{i}. {stock.get('code', 'N/A')} - {stock.get('name', 'N/A')}")
        price = stock.get('latest_price', 0)
        change = stock.get('change_pct', 0)
        industry = stock.get('industry', 'N/A')
        concepts = ', '.join(stock.get('concepts', [])) or '无'
        
        if price and price > 0:
            print(f"   价格: {price:.2f} 元")
        else:
            print(f"   价格: 数据缺失")
            
        if change:
            print(f"   涨幅: {change:.2f}%")
        else:
            print(f"   涨幅: 数据缺失")
            
        print(f"   行业: {industry}")
        print(f"   概念: {concepts}")
    
    print("\n" + "=" * 50)

if __name__ == '__main__':
    test_log_colors()
    test_price_data()
    test_full_pipeline()
