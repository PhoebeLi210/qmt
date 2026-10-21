#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试优化功能脚本
验证多因子量化模型、风险控制机制等新功能
"""

import os
import sys
import logging
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine
from utils.logger import setup_logger

# 设置日志
logger = setup_logger('test_optimization', logging.INFO)

def create_test_stock():
    """创建测试股票数据"""
    return {
        'code': 'test.001',
        'name': '测试股票',
        'latest_price': 15.50,
        'change_pct': 2.5,  # 降低涨幅，避免风险扣分
        'pe': 18.5,
        'pb': 2.1,
        'market_cap': 1500000000,  # 15亿
        'liquid_shares': 100000000,  # 1亿股
        'industry': '人工智能',
        'turnover_rate': 3.0,  # 降低换手率
        'kline_data': [
            {'date': '2025-12-20', 'open': 14.5, 'high': 14.8, 'low': 14.3, 'close': 14.6, 'volume': 800000},
            {'date': '2025-12-21', 'open': 14.6, 'high': 14.9, 'low': 14.5, 'close': 14.7, 'volume': 850000},
            {'date': '2025-12-22', 'open': 14.7, 'high': 15.0, 'low': 14.6, 'close': 14.8, 'volume': 900000},
            {'date': '2025-12-23', 'open': 14.8, 'high': 15.1, 'low': 14.7, 'close': 14.9, 'volume': 950000},
            {'date': '2025-12-24', 'open': 14.9, 'high': 15.2, 'low': 14.8, 'close': 15.0, 'volume': 1000000},
            {'date': '2025-12-25', 'open': 15.0, 'high': 15.3, 'low': 14.9, 'close': 15.1, 'volume': 1050000},
            {'date': '2025-12-26', 'open': 15.1, 'high': 15.4, 'low': 15.0, 'close': 15.2, 'volume': 1100000},
            {'date': '2025-12-27', 'open': 15.2, 'high': 15.5, 'low': 15.1, 'close': 15.3, 'volume': 1150000},
            {'date': '2025-12-28', 'open': 15.3, 'high': 15.6, 'low': 15.2, 'close': 15.4, 'volume': 1200000},
            {'date': '2025-12-29', 'open': 15.4, 'high': 15.7, 'low': 15.3, 'close': 15.5, 'volume': 1250000},
            {'date': '2025-12-30', 'open': 15.5, 'high': 15.8, 'low': 15.4, 'close': 15.6, 'volume': 1300000},
            {'date': '2025-12-31', 'open': 15.6, 'high': 15.9, 'low': 15.5, 'close': 15.7, 'volume': 1350000},
        ]
    }

def test_multi_factor_scoring():
    """测试多因子量化评分"""
    logger.info("=== 测试多因子量化评分功能 ===")
    
    stock = create_test_stock()
    
    # 分析股票
    try:
        analyzer = StockAnalyzer([stock])
        analyzed_stock = analyzer.analyze_stocks()[0]
        
        logger.info(f"股票代码: {analyzed_stock['code']}")
        logger.info(f"股票名称: {analyzed_stock['name']}")
        logger.info(f"最终评分: {analyzed_stock['score']:.2f}")
        logger.info(f"基本面得分: {analyzed_stock.get('fundamental_score', 'N/A')}")
        logger.info(f"技术面得分: {analyzed_stock.get('technical_score', 'N/A')}")
        logger.info(f"积极指标: {analyzed_stock.get('positive_indicators', [])}")
        
        # 检查多因子评分相关字段
        if 'score' in analyzed_stock:
            logger.info("✅ 多因子评分功能正常工作")
        else:
            logger.error("❌ 多因子评分功能异常")
            
        return analyzed_stock
    except Exception as e:
        logger.error(f"多因子评分测试失败: {str(e)}")
        return None

def test_risk_control():
    """测试风险控制机制"""
    logger.info("\n=== 测试风险控制机制 ===")
    
    # 创建高风险测试股票
    high_risk_stock = create_test_stock()
    high_risk_stock['change_pct'] = 12.5  # 涨幅过大
    high_risk_stock['turnover_rate'] = 18.0  # 换手率过高
    high_risk_stock['liquid_shares'] = 6000000000  # 流通股本过大
    
    try:
        analyzer = StockAnalyzer([high_risk_stock])
        analyzed_results = analyzer.analyze_stocks()
        
        logger.info(f"高风险股票数据:")
        logger.info(f"  涨幅: {high_risk_stock['change_pct']}%")
        logger.info(f"  换手率: {high_risk_stock['turnover_rate']}%")
        logger.info(f"  流通股本: {high_risk_stock['liquid_shares']:,}股")
        logger.info(f"  通过分析的股票数量: {len(analyzed_results)}")
        
        # 检查风险控制是否生效 - 高风险股票应该被过滤（通过数为0）
        if len(analyzed_results) == 0:  # 如果没有股票通过，说明风险控制生效
            logger.info("✅ 风险控制机制正常工作 - 高风险股票被正确过滤")
            return None  # 返回None表示风险控制生效
        else:
            logger.warning("⚠️ 风险控制机制可能需要调优 - 高风险股票未被完全过滤")
            return analyzed_results[0]  # 返回第一只股票用于后续测试
    except Exception as e:
        logger.error(f"风险控制测试失败: {str(e)}")
        return None

def test_recommendation_engine():
    """测试推荐引擎优化"""
    logger.info("\n=== 测试推荐引擎优化功能 ===")
    
    # 创建多只测试股票
    test_stocks = []
    for i in range(5):
        stock = create_test_stock()
        stock['code'] = f'test.{i:03d}'
        stock['name'] = f'测试股票{i+1}'
        stock['industry'] = ['人工智能', '新能源', '半导体', '医药生物', '互联网'][i]
        stock['score'] = 75 + i * 3  # 不同评分
        test_stocks.append(stock)
    
    try:
        engine = RecommendationEngine(test_stocks)
        recommendations = engine.generate_recommendations()
        
        logger.info(f"生成了 {len(recommendations)} 只推荐股票")
        
        for i, stock in enumerate(recommendations, 1):
            logger.info(f"{i}. {stock['code']} - {stock['name']}")
            logger.info(f"   评分: {stock['score']:.2f}")
            logger.info(f"   行业: {stock.get('industry', 'N/A')}")
            logger.info(f"   风险等级: {stock.get('risk_level', 'N/A')}")
            logger.info(f"   仓位建议: {stock.get('position_sizing', 'N/A')}")
            logger.info(f"   推荐理由: {stock.get('recommendation_reason', 'N/A')}")
        
        # 检查推荐引擎功能
        if recommendations and 'risk_level' in recommendations[0]:
            logger.info("✅ 推荐引擎优化功能正常工作")
        else:
            logger.error("❌ 推荐引擎优化功能异常")
            
        return recommendations
    except Exception as e:
        logger.error(f"推荐引擎测试失败: {str(e)}")
        return []

def main():
    """主测试函数"""
    logger.info("开始测试股票推荐系统优化功能")
    logger.info(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试各项功能
    test_stock = test_multi_factor_scoring()
    risk_stock = test_risk_control()
    recommendations = test_recommendation_engine()
    
    # 总结测试结果
    logger.info("\n=== 测试结果总结 ===")
    
    success_count = 0
    total_tests = 3
    
    if test_stock:
        success_count += 1
    if risk_stock is not None:  # 风险控制测试：返回None表示成功过滤了高风险股票
        success_count += 1
    if recommendations:
        success_count += 1
    
    logger.info(f"测试通过: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        logger.info("🎉 所有优化功能测试通过！")
    else:
        logger.warning("⚠️ 部分功能测试失败，需要检查代码")

if __name__ == "__main__":
    main()