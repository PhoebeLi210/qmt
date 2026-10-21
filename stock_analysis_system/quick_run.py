#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票分析系统快速运行版本
只处理前200只股票，用于快速演示完整流程
"""

import logging
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_collector import StockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 设置为DEBUG级别以查看详细日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('quick_run.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    logger.info("=== 股票交易量化系统快速运行版本 ===")
    
    try:
        # 1. 数据采集
        logger.info("1. 开始采集股票数据...")
        collector = StockDataCollector()
        logger.info("   正在获取股票列表...")
        
        try:
            # 修改：只获取前200只股票
            stock_list = collector.get_all_stocks(limit=200)
            logger.info(f"   共采集到 {len(stock_list)} 只股票数据")
            
            if not stock_list:
                logger.error("   未获取到任何股票数据")
                return
        except Exception as e:
            logger.error(f"   获取股票列表失败: {str(e)}")
            return
        
        # 2. 股票选择
        logger.info("2. 开始股票形态选择...")
        selector = StockSelector(stock_list)
        selected_stocks = selector.select_by_kline_pattern()
        logger.info(f"   根据形态选择出 {len(selected_stocks)} 只股票")
        
        if not selected_stocks:
            logger.warning("   未选择出符合条件的股票")
            return
        
        # 3. 股票分析
        logger.info("3. 开始股票深度分析...")
        analyzer = StockAnalyzer(selected_stocks)
        analyzed_stocks = analyzer.analyze_stocks()
        logger.info(f"   完成分析 {len(analyzed_stocks)} 只股票")
        
        if not analyzed_stocks:
            logger.warning("   分析过程中未产生有效结果")
            return
        
        # 4. 生成推荐
        logger.info("4. 开始生成投资推荐...")
        engine = RecommendationEngine(analyzed_stocks)
        recommendations = engine.generate_recommendations()
        logger.info(f"   生成 {len(recommendations)} 只股票推荐")
        
        # 5. 输出结果
        logger.info("5. 输出推荐结果...")
        if recommendations:
            logger.info("\n=== 最终推荐股票列表 ===")
            for rec in recommendations:
                logger.info(f"股票代码: {rec['code']}, 股票名称: {rec['name']}")
                logger.info(f"   推荐理由: {rec['recommendation_reason']}")
                logger.info(f"   推荐日期: {rec['recommendation_date']}")
                logger.info("---")
        else:
            logger.info("未生成任何推荐股票")
            
    except Exception as e:
        logger.error(f"系统运行失败: {str(e)}", exc_info=True)
    finally:
        # 确保资源释放
        if 'collector' in locals():
            collector.close()

if __name__ == "__main__":
    main()
