#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试报告生成和评分修复效果
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine
import logging
from utils.logger import setup_logger

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = setup_logger('quick_test', logging.INFO)

def test_quick_recommendation():
    """快速测试推荐引擎和评分系统"""
    print("=== 快速测试推荐引擎和评分修复效果 ===\n")
    
    # 创建少量测试股票
    test_stocks = [
        {
            'code': 'sh.600519',
            'name': '贵州茅台',
            'latest_price': 1800.0,
            'change_pct': 2.5,
            'turnover_rate': 0.8,
            'pe': 35.0,
            'pb': 8.5,
            'liquid_shares': 1000000000,  # 10亿
            'industry': '白酒',
            'concept': '消费升级',
            'kline_data': [
                {'date': '2024-12-01', 'open': 1750, 'high': 1820, 'low': 1740, 'close': 1800, 'volume': 500000},
                {'date': '2024-12-02', 'open': 1800, 'high': 1830, 'low': 1790, 'close': 1820, 'volume': 600000},
                {'date': '2024-12-03', 'open': 1820, 'high': 1840, 'low': 1810, 'close': 1830, 'volume': 550000}
            ]
        },
        {
            'code': 'sz.000858',
            'name': '五粮液',
            'latest_price': 150.0,
            'change_pct': 1.8,
            'turnover_rate': 1.2,
            'pe': 25.0,
            'pb': 4.2,
            'liquid_shares': 800000000,  # 8亿
            'industry': '白酒',
            'concept': '消费升级',
            'kline_data': [
                {'date': '2024-12-01', 'open': 148, 'high': 152, 'low': 147, 'close': 150, 'volume': 800000},
                {'date': '2024-12-02', 'open': 150, 'high': 153, 'low': 149, 'close': 151, 'volume': 900000},
                {'date': '2024-12-03', 'open': 151, 'high': 154, 'low': 150, 'close': 152, 'volume': 850000}
            ]
        },
        {
            'code': 'sz.300136',
            'name': '信维通信',
            'latest_price': 25.0,
            'change_pct': -1.2,
            'turnover_rate': 2.5,
            'pe': 45.0,
            'pb': 3.8,
            'liquid_shares': 200000000,  # 2亿
            'industry': '电子元件',
            'concept': '5G概念',
            'kline_data': [
                {'date': '2024-12-01', 'open': 26, 'high': 27, 'low': 25, 'close': 25, 'volume': 1200000},
                {'date': '2024-12-02', 'open': 25, 'high': 26, 'low': 24, 'close': 24, 'volume': 1500000},
                {'date': '2024-12-03', 'open': 24, 'high': 25, 'low': 23, 'close': 23, 'volume': 1800000}
            ]
        }
    ]
    
    # 分析股票
    logger.info("开始分析测试股票...")
    analyzer = StockAnalyzer(test_stocks)
    analyzed_stocks = analyzer.analyze_stocks()
    
    logger.info(f"分析完成，共通过 {len(analyzed_stocks)} 只股票")
    
    # 生成推荐
    if analyzed_stocks:
        logger.info("开始生成推荐...")
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(analyzed_stocks, top_n=3)
        
        logger.info("推荐结果:")
        for i, stock in enumerate(recommendations, 1):
            score = stock.get('score', 0.0)
            position_sizing = stock.get('position_sizing', '未提供')
            logger.info(f"{i}. {stock['name']}({stock['code']}) - 评分: {score:.2f}分 - {position_sizing}")
        
        # 验证评分是否有区分度
        scores = [stock.get('score', 0.0) for stock in recommendations]
        if len(set(scores)) > 1:
            logger.info("✅ 修复成功！股票评分具有区分度")
            logger.info(f"评分范围: {min(scores):.2f} - {max(scores):.2f}")
        else:
            logger.warning("⚠️ 仍存在问题：股票评分相同")
            
    else:
        logger.warning("没有通过分析的股票")

if __name__ == "__main__":
    test_quick_recommendation()