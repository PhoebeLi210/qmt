#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试优化后的股票分析系统
"""

import sys
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("测试优化后的股票分析系统...")
    
    try:
        # 1. 股票数据采集
        logger.info("1. 开始采集股票数据...")
        from data_collector import StockDataCollector
        collector = StockDataCollector()
        # 使用正确的方法名和参数
        stocks = collector.get_all_stocks(limit=1000)  # 减少到1000只有效股票
        logger.info(f"共采集到 {len(stocks)} 只有效股票")
        
        if not stocks:
            logger.error("未采集到有效股票数据")
            return
        
        # 2. 股票筛选（通过K线形态）
        logger.info("2. 开始筛选股票...")
        from stock_selector import StockSelector
        selector = StockSelector(stocks)
        selected_stocks = selector.select_by_kline_pattern()
        logger.info(f"筛选后剩余 {len(selected_stocks)} 只股票")
        
        if not selected_stocks:
            logger.error("筛选后无有效股票")
            return
        
        # 3. 股票分析与推荐
        logger.info("3. 开始分析股票并生成推荐清单...")
        from stock_analyzer import StockAnalyzer
        # 使用正确的初始化方式和方法
        analyzer = StockAnalyzer(selected_stocks)
        analyzed_stocks = analyzer.analyze_stocks()
        logger.info(f"分析完成 {len(analyzed_stocks)} 只股票")
        
        # 生成推荐列表（按综合评分排序，取前10只）
        recommendations = sorted(analyzed_stocks, key=lambda x: x['score'], reverse=True)[:10]
        
        if recommendations:
            logger.info("推荐股票清单:")
            for stock in recommendations:
                logger.info(f"  - {stock['name']}({stock['code']}): 得分 {stock['score']:.2f}, 行业: {stock.get('industry', '未知')}, "
                          f"PE: {stock.get('pe', '未知')}, 积极指标: {', '.join(stock.get('positive_indicators', []))}")
        else:
            logger.info("未找到符合推荐条件的股票")
              
    except Exception as e:
        logger.error(f"程序运行异常: {e}", exc_info=True)
    finally:
        # 确保关闭连接
        try:
            import baostock as bs
            bs.logout()
        except Exception as e:
            logger.warning(f"关闭baostock连接时发生错误: {e}")

if __name__ == "__main__":
    main()