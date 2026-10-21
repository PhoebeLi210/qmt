#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试报告生成修复
"""

import os
import sys
import logging
from datetime import datetime

# 添加当前目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock_analysis_system'))

from report_generator import ReportGenerator

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_report_generation():
    """测试报告生成"""
    logger.info("开始测试报告生成...")
    
    # 创建报告生成器实例
    report_generator = ReportGenerator('reports')
    
    # 创建模拟数据
    mock_stock_rankings = [
        {
            'code': '600000',
            'name': '浦发银行',
            'industry': '银行',
            'score': 4.5,
            'current_price': 9.50,
            'total_return': 5.23,
            'technical_signals': {'ma_signal': '多头', 'macd_signal': '金叉'},
            'trading_opportunity': '积极买入'
        },
        {
            'code': '600001',
            'name': '邯郸钢铁',
            'industry': '钢铁',
            'score': 4.2,
            'current_price': 3.80,
            'total_return': 3.15,
            'technical_signals': {'ma_signal': '多头', 'macd_signal': '金叉'},
            'trading_opportunity': '超卖低吸'
        }
    ]
    
    mock_industry_performance = [
        {
            'industry': '银行',
            'avg_return': 4.56,
            'stock_count': 10
        },
        {
            'industry': '钢铁',
            'avg_return': 3.89,
            'stock_count': 8
        }
    ]
    
    mock_daily_focus_stocks = {
        'super_short_term_stocks': [
            {
                'code': '600000',
                'name': '浦发银行',
                'industry': '银行',
                'current_price': 9.50,
                'technical_signals': {'ma_signal': '多头', 'macd_signal': '金叉'},
                'trading_opportunity': '积极买入',
                'support': 9.20,
                'resistance': 9.80,
                'stop_loss': 9.10,
                'target_price': 10.00,
                'buy_price_range': {'low': 9.30, 'high': 9.60}
            }
        ],
        'recommended_buy_stocks': [
            {
                'code': '600000',
                'name': '浦发银行',
                'industry': '银行',
                'score': 4.5,
                'current_price': 9.50,
                'total_return': 5.23,
                'technical_signals': {'ma_signal': '多头', 'macd_signal': '金叉'},
                'trading_opportunity': '积极买入',
                'support': 9.20,
                'resistance': 9.80,
                'stop_loss': 9.10,
                'target_price': 10.00,
                'buy_price_range': {'low': 9.30, 'high': 9.60}
            },
            {
                'code': '600001',
                'name': '邯郸钢铁',
                'industry': '钢铁',
                'score': 4.2,
                'current_price': 3.80,
                'total_return': 3.15,
                'technical_signals': {'ma_signal': '多头', 'macd_signal': '金叉'},
                'trading_opportunity': '超卖低吸',
                'support': 3.60,
                'resistance': 4.00,
                'stop_loss': 3.50,
                'target_price': 4.20,
                'buy_price_range': {'low': 3.70, 'high': 3.90}
            }
        ]
    }
    
    try:
        # 生成每日报告
        report_path = report_generator.generate_daily_report(
            mock_stock_rankings,
            mock_industry_performance,
            mock_daily_focus_stocks
        )
        
        if report_path:
            logger.info(f"✓ 报告生成成功！文件路径: {report_path}")
            
            # 验证报告内容
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if "A股市场每日分析报告" in content:
                logger.info("✓ 报告包含正确的标题")
            else:
                logger.error("✗ 报告缺少正确的标题")
            
            if "推荐买入股票" in content:
                logger.info("✓ 报告包含推荐买入股票部分")
            else:
                logger.error("✗ 报告缺少推荐买入股票部分")
            
            if "超短线推荐股票" in content:
                logger.info("✓ 报告包含超短线推荐股票部分")
            else:
                logger.error("✗ 报告缺少超短线推荐股票部分")
            
            return True
        else:
            logger.error("✗ 报告生成失败")
            return False
            
    except Exception as e:
        logger.error(f"✗ 报告生成过程中发生异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    logger.info("====================================")
    logger.info("          测试报告生成修复")
    logger.info("====================================")
    
    success = test_report_generation()
    
    logger.info("\n====================================")
    logger.info("          测试完成")
    logger.info("====================================")
    
    if success:
        logger.info("✅ 测试通过！报告生成修复有效。")
        sys.exit(0)
    else:
        logger.info("❌ 测试失败！报告生成修复无效。")
        sys.exit(1)
