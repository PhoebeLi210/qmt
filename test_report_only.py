#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专门测试报告生成模块的脚本
"""

import os
import sys
import logging

# 设置日志配置
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录和stock_analysis_system目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# 测试报告生成模块
try:
    logger.info("=== 测试报告生成模块 ===")
    
    # 修复导入问题
    sys.path.append(os.path.join(project_root, 'stock_analysis_system'))
    
    from stock_analysis_system.report_generator import ReportGenerator
    
    # 检查ReportGenerator的初始化参数
    import inspect
    sig = inspect.signature(ReportGenerator.__init__)
    logger.info(f"ReportGenerator构造函数签名: {sig}")
    
    # 根据签名创建实例
    if len(sig.parameters) == 1:  # 只有self参数
        report_generator = ReportGenerator()
        logger.info("[SUCCESS] 创建ReportGenerator实例成功（无参数）")
    else:
        # 假设需要report_path参数
        report_path = os.path.join(project_root, 'test_reports')
        if not os.path.exists(report_path):
            os.makedirs(report_path)
        report_generator = ReportGenerator(report_path)
        logger.info(f"[SUCCESS] 创建ReportGenerator实例成功（带report_path参数）")
    
    # 创建模拟数据
    stock_rankings = [
        {
            'code': '600036', 'name': '招商银行', 
            'industry': '银行',
            'score': 4.5, 'rating': '优秀', 'current_price': 35.20,
            'change_pct': 2.15, 
            'technical_signals': ['短期均线多头'],
            'operation_timing': '积极买入'
        }
    ]
    
    industry_performance = [
        {'industry': '银行', 'avg_score': 4.2, 'stock_count': 20, 'performance': '优秀'}
    ]
    
    daily_focus_stocks = {
        'super_short_term_stocks': [
            {
                'code': '600519', 'name': '贵州茅台', 'industry': '酿酒',
                'current_price': 1850.00, 'change_pct': 3.20,
                'super_short_score': 28, 'technical_signals': ['放量突破'],
                'operation_timing': '积极买入'
            }
        ]
    }
    
    # 测试生成报告
    logger.info("测试生成报告...")
    report_path = report_generator.generate_daily_report(
        stock_rankings=stock_rankings,
        industry_performance=industry_performance,
        daily_focus_stocks=daily_focus_stocks
    )
    
    if report_path and os.path.exists(report_path):
        logger.info(f"[SUCCESS] 报告生成成功: {report_path}")
        logger.info(f"报告内容:")
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.info(content[:500] + "..." if len(content) > 500 else content)
        logger.info("✅ 报告生成模块测试通过")
    else:
        logger.error("[ERROR] 报告生成失败")
        
except Exception as e:
    logger.error(f"[ERROR] 报告生成模块测试出错: {e}")
    import traceback
    traceback.print_exc()
