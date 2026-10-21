#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据采集器脚本，用于快速验证数据采集问题
"""

import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_collector_optimized import OptimizedStockDataCollector
from utils.logger import setup_logger

# 设置日志级别为DEBUG以查看详细信息
logger = setup_logger('test_data_collector', logging.DEBUG)


def main():
    """测试数据采集器"""
    try:
        logger.info("=== 测试数据采集器 ===")
        
        # 创建数据采集器实例
        collector = OptimizedStockDataCollector()
        
        # 只测试几只股票，快速验证问题
        test_stocks = [
            "sh.688601",  # 力芯微 (科创板)
            "sh.688349",  # 三一重能 (科创板)
            "sh.688268",  # 华特气体 (科创板)
            "sh.600000",  # 浦发银行 (沪市主板)
            "sz.000001"   # 平安银行 (深市主板)
        ]
        
        logger.info(f"开始测试 {len(test_stocks)} 只股票...")
        
        # 获取这几只股票的详细数据
        for stock_code in test_stocks:
            logger.info(f"\n--- 测试股票: {stock_code} ---")
            stock_data = collector._get_stock_detail_optimized(stock_code)
            
            if stock_data:
                logger.info(f"✓ 成功获取股票数据: {stock_data['code']} - {stock_data.get('name', '未知')}")
                logger.info(f"  板块: {stock_data.get('market_segment', '未知')}")
                logger.info(f"  行业: {stock_data.get('industry', '未知')}")
                logger.info(f"  市盈率: {stock_data.get('pe', '未知')}")
                logger.info(f"  K线数据条数: {len(stock_data.get('kline_data', []))}")
            else:
                logger.info(f"✗ 无法获取股票数据: {stock_code}")
        
        logger.info("\n=== 测试完成 ===")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
