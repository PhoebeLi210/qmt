#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票交易量化系统测试脚本

用于快速验证系统的核心功能
"""

import logging
import sys
import pandas as pd
from utils.logger import setup_logger
from data_collector import StockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine

# 配置日志
logger = setup_logger('test_system', logging.INFO)

def main():
    try:
        logger.info("=== 股票交易量化系统测试启动 ===")
        
        # 1. 测试数据采集模块（只采集少量股票）
        logger.info("1. 测试数据采集模块...")
        collector = StockDataCollector()
        
        # 获取股票列表但只处理前10只股票
        rs = collector.bs.query_all_stock(day='2025-12-19')
        if rs.error_code != '0':
            raise Exception(f"获取股票列表失败: {rs.error_msg}")
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            stock_code = rs.get_row_data()[0]  # code字段是第一列
            # 只收集个股数据，过滤指数
            # 从股票代码中提取数字部分，忽略市场前缀
            if '.' in stock_code:
                code_part = stock_code.split('.')[1]
            else:
                code_part = stock_code
                
            # 根据数字代码前缀识别股票类型，不受市场前缀影响
            if (code_part.startswith(('600', '601', '603', '605')) or  # 上海主板
                code_part.startswith('688') or                          # 上海科创板
                code_part.startswith('000') or                          # 深圳主板
                code_part.startswith('002') or                          # 深圳中小板
                code_part.startswith('300')):                           # 深圳创业板
                data_list.append(rs.get_row_data())
                if len(data_list) >= 50:  # 只测试前50只股票
                    break
        
        df = pd.DataFrame(data_list, columns=rs.fields)
        logger.info(f"共获取到 {len(df)} 只个股用于测试")
        
        valid_stocks = []
        for i, row in df.iterrows():
            stock_code = row['code']
            
            # 过滤ST股票
            if collector._is_st_stock(stock_code):
                continue
            
            # 获取股票详细数据
            stock_data = collector._get_stock_detail(stock_code)
            if stock_data:
                valid_stocks.append(stock_data)
                logger.info(f"获取股票数据成功: {stock_code} - {stock_data['name']}")
            
            # 避免请求过快
            import time
            time.sleep(0.1)
        
        logger.info(f"过滤后剩余 {len(valid_stocks)} 只有效股票")
        
        # 2. 测试股票选择模块
        logger.info("2. 测试股票选择模块...")
        selector = StockSelector(valid_stocks)
        selected_stocks = selector.select_by_kline_pattern()
        logger.info(f"根据形态选择出 {len(selected_stocks)} 只股票")
        
        # 3. 测试股票分析模块
        logger.info("3. 测试股票分析模块...")
        analyzer = StockAnalyzer(selected_stocks)
        analyzed_stocks = analyzer.analyze_stocks()
        logger.info(f"完成分析 {len(analyzed_stocks)} 只股票")
        
        # 4. 测试推荐引擎模块
        logger.info("4. 测试推荐引擎模块...")
        engine = RecommendationEngine(analyzed_stocks)
        recommendations = engine.generate_recommendations()
        logger.info(f"生成 {len(recommendations)} 只股票推荐")
        
        # 5. 输出推荐结果
        logger.info("5. 输出推荐结果...")
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                logger.info(f"[{i}] {rec['code']} - {rec['name']} (评分: {rec['score']:.2f})")
                logger.info(f"   推荐理由: {rec['recommendation_reason']}")
        else:
            logger.info("未生成任何推荐股票")
        
        logger.info("=== 系统测试完成 ===")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        return 1
    finally:
        # 确保关闭连接
        if 'collector' in locals():
            collector.close()
    
    return 0

if __name__ == "__main__":
    import pandas as pd
    sys.exit(main())
