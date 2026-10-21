#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试系统是否能生成10只股票的推荐报告
"""

import os
import sys
import time
import logging
from datetime import datetime

# 设置系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入系统模块
from data_collector import StockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('test_10_stocks', logging.INFO)

# 导入main.py中的报告生成函数
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import output_recommendations


def main():
    """测试主函数"""
    try:
        logger.info("=== 测试系统能否生成10只股票推荐报告 ===")
        start_time = time.time()
        
        # 1. 数据采集（只获取200只股票，加速测试）
        logger.info("1. 开始采集股票数据...")
        collector = StockDataCollector()
        logger.info("   正在获取部分A股股票列表...")
        stock_list = collector.get_all_stocks(limit=200)
        logger.info(f"   共采集到 {len(stock_list)} 只股票数据")
        
        # 检查是否有指数被过滤掉
        logger.info("   检查采集到的股票是否包含指数...")
        has_index = False
        for stock in stock_list:
            stock_code = stock['code']
            # 提取数字代码部分，忽略市场前缀
            if '.' in stock_code:
                code_part = stock_code.split('.')[1]
            else:
                code_part = stock_code
            # 基于数字代码判断是否为指数，不受市场前缀影响
            if (code_part.startswith('000') or code_part.startswith('399')):
                has_index = True
                logger.warning(f"   发现指数: {stock_code}")
        if not has_index:
            logger.info("   ✅ 所有指数都已被过滤掉")
        
        # 2. 股票筛选（根据K线形态）
        logger.info("2. 开始根据K线形态筛选股票...")
        selector = StockSelector(stock_list)
        selected_stocks = selector.select_by_kline_pattern()
        logger.info(f"   筛选出 {len(selected_stocks)} 只符合形态的股票")
        
        if not selected_stocks:
            logger.warning("未筛选出符合条件的股票")
            return
        
        # 3. 股票分析（基本面和技术面）
        logger.info("3. 开始进行基本面和技术面分析...")
        analyzer = StockAnalyzer(selected_stocks)
        analyzed_stocks = analyzer.analyze_stocks()
        logger.info(f"   完成 {len(analyzed_stocks)} 只股票的分析")
        
        if not analyzed_stocks:
            logger.warning("未分析出符合条件的股票")
            return
        
        # 4. 生成推荐清单
        logger.info("4. 开始生成股票推荐清单...")
        engine = RecommendationEngine(analyzed_stocks)
        recommendations = engine.generate_recommendations()
        logger.info(f"   生成了 {len(recommendations)} 只推荐股票")
        
        # 5. 输出结果并生成报告
        logger.info("5. 输出推荐结果并生成报告...")
        output_recommendations(recommendations)
        
        # 验证是否达到10只推荐
        if len(recommendations) >= 10:
            logger.info("✅ 测试成功！推荐股票数量达到10只或以上")
        else:
            logger.warning(f"⚠️  测试结果：推荐股票数量为 {len(recommendations)} 只，未达到10只")
        
        end_time = time.time()
        logger.info(f"=== 测试完成，耗时 {end_time - start_time:.2f} 秒 ===")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()