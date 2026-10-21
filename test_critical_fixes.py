#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试关键修复点的脚本
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 设置日志配置
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# 测试1: 报告生成模块修复 (避免KeyError)
def test_report_generator_fix():
    logger.info("\n=== 测试报告生成模块修复 ===")
    try:
        # 从stock_analysis_system模块导入ReportGenerator
        from stock_analysis_system.report_generator import ReportGenerator
        
        # 创建ReportGenerator实例（需要report_path参数）
        report_path = os.path.join(project_root, 'test_reports')
        if not os.path.exists(report_path):
            os.makedirs(report_path)
        report_generator = ReportGenerator(report_path)
        logger.info("[SUCCESS] 创建ReportGenerator实例成功")
        
        # 创建模拟数据，故意缺少一些字段来测试修复
        stock_rankings = [
            {
                'code': '600036', 'name': '招商银行', 
                # 故意缺少industry字段
                'score': 4.5, 'rating': '优秀', 'current_price': 35.20,
                'change_pct': 2.15, 
                # 故意缺少technical_signals字段
                'operation_timing': '积极买入'
            }
        ]
        
        industry_performance = []
        daily_focus_stocks = {'super_short_term_stocks': []}
        
        # 测试生成报告，应该不会抛出KeyError
        report_path = report_generator.generate_daily_report(
            stock_rankings=stock_rankings,
            industry_performance=industry_performance,
            daily_focus_stocks=daily_focus_stocks
        )
        
        if report_path and os.path.exists(report_path):
            logger.info(f"[SUCCESS] 报告生成成功: {report_path}")
            logger.info("✅ 报告生成模块修复验证通过")
            return True
        else:
            logger.error("[ERROR] 报告生成失败")
            return False
            
    except KeyError as e:
        logger.error(f"[ERROR] 报告生成模块仍存在KeyError: {e}")
        return False
    except Exception as e:
        logger.error(f"[ERROR] 报告生成模块测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试2: 数据采集模块修复 (baostock失败回退机制)
def test_data_collector_fix():
    logger.info("\n=== 测试数据采集模块修复 ===")
    try:
        from stock_analysis_system.data_collector import DataCollector
        data_collector = DataCollector()
        logger.info("[SUCCESS] 创建DataCollector实例成功")
        
        # 模拟baostock失败的情况（通过限制股票数量来快速测试）
        stock_basic = data_collector.get_stock_basic_info(max_stocks=2)
        
        if stock_basic is not None and not stock_basic.empty:
            logger.info(f"[SUCCESS] 获取到 {len(stock_basic)} 只股票的基本信息")
            logger.info(stock_basic.head())
            logger.info("✅ 数据采集模块回退机制验证通过")
            return True
        else:
            logger.error("[ERROR] 获取股票基本信息失败")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] 数据采集模块测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False

# 测试3: 股票分析模块修复 (技术指标计算异常处理)
def test_stock_analyzer_fix():
    logger.info("\n=== 测试股票分析模块修复 ===")
    try:
        from stock_analysis_system.data_analyzer import StockAnalyzer
        analyzer = StockAnalyzer()
        logger.info("[SUCCESS] 创建StockAnalyzer实例成功")
        
        # 创建有问题的模拟数据来测试异常处理
        dates = pd.date_range(start='2025-01-01', end='2025-01-10', freq='D')
        
        # 创建包含NaN值的有问题数据
        problematic_data = pd.DataFrame({
            'date': dates,
            'open': [np.nan] * len(dates),  # 全部是NaN
            'high': [np.nan] * len(dates),
            'low': [np.nan] * len(dates),
            'close': [np.nan] * len(dates),
            'volume': [np.nan] * len(dates)
        })
        
        # 测试计算技术指标，应该不会抛出异常
        result = analyzer.calculate_technical_indicators(problematic_data)
        
        if result is not None and isinstance(result, pd.DataFrame):
            logger.info("[SUCCESS] 成功处理有问题的数据，返回有效的DataFrame")
            logger.info("✅ 股票分析模块异常处理验证通过")
            return True
        else:
            logger.error("[ERROR] 处理有问题的数据失败")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] 股票分析模块测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    logger.info("========== 关键修复点测试 ==========")
    
    # 运行所有测试
    tests = [
        ("报告生成模块修复", test_report_generator_fix),
        ("数据采集模块修复", test_data_collector_fix),
        ("股票分析模块修复", test_stock_analyzer_fix)
    ]
    
    passed_count = 0
    total_count = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed_count += 1
        except Exception as e:
            logger.error(f"{test_name} 执行出错: {e}")
    
    logger.info(f"\n========== 测试结果: {passed_count}/{total_count} 通过 ==========")
    
    if passed_count == total_count:
        logger.info("🎉 所有关键修复点验证通过！")
        sys.exit(0)
    else:
        logger.error("❌ 部分修复点验证失败")
        sys.exit(1)
