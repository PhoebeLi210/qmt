#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票代码识别逻辑
验证000001、000002等股票能被正确处理
"""

import sys
import os
import logging
import baostock as bs
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_stock_identification.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('test_stock_identification')

# 导入StockDataCollector
from stock_analysis_system.data_collector import StockDataCollector

def test_stock_identification():
    """测试股票代码识别逻辑"""
    logger.info("开始测试股票代码识别逻辑...")
    
    # 创建数据采集器实例
    collector = StockDataCollector()
    
    # 测试用例：包含个股和指数，特别增加前缀错误的股票
    test_codes = [
        'sz.000001',  # 平安银行（个股）
        'sh.000001',  # 平安银行（个股，但前缀错误）
        'sz.000002',  # 万科A（个股）
        'sh.000002',  # 万科A（个股，但前缀错误）
        'sh.000003',  # 上证B股指数（指数）
        'sh.000300',  # 沪深300指数（指数）
        'sh.600000',  # 浦发银行（个股）
        'sz.000016',  # 深康佳A（个股）
        'sh.000016',  # 深康佳A（个股，但前缀错误）
        'sz.399001',  # 深证成指（指数）
        'sz.300001',  # 特锐德（个股，创业板）
        'sh.688001',  # 华兴源创（个股，科创板）
        'sz.000993',  # 闽东电力（个股，深市主板）
        'sh.000993',  # 闽东电力（个股，但前缀错误）
    ]
    
    # 测试识别逻辑
    for stock_code in test_codes:
        logger.info(f"\n测试股票代码: {stock_code}")
        
        # 解析代码部分
        if '.' in stock_code:
            code_part = stock_code.split('.')[1]
        else:
            code_part = stock_code
        
        # 模拟代码识别逻辑
        is_stock = False
        
        # 上海主板、科创板股票：600、601、603、605、688开头
        if code_part.startswith(('600', '601', '603', '605', '688')):
            if len(code_part) == 6:
                is_stock = True
        # 深圳主板、中小板、创业板股票：000、001、002、003、300、301、302开头
        elif code_part.startswith(('000', '001', '002', '003', '300', '301', '302')):
            if len(code_part) == 6:
                # 排除主要指数
                exclude_patterns = ['000003', '000300', '000905', '399001', '399006']
                if code_part not in exclude_patterns:
                    is_stock = True
        
        logger.info(f"  代码部分: {code_part}")
        logger.info(f"  识别结果: {'个股' if is_stock else '非个股/指数'}")
        
        # 验证_get_stock_type函数
        logger.info(f"  调用_get_stock_type函数:")
        stock_type = collector._get_stock_type(stock_code)
        logger.info(f"  股票类型: {stock_type}")
        
        # 预期股票类型（基于数字代码）
        expected_type = 'unknown'
        if code_part.startswith(('600', '601', '603', '605')):
            expected_type = 'sh_main'
        elif code_part.startswith('688'):
            expected_type = 'sh_kcb'
        elif code_part.startswith('000'):
            expected_type = 'sz_main'
        elif code_part.startswith('002'):
            expected_type = 'sz_sme'
        elif code_part.startswith('300'):
            expected_type = 'sz_cyb'
        
        if stock_type == expected_type:
            logger.info(f"  ✅ 股票类型识别正确")
        else:
            logger.info(f"  ❌ 股票类型识别错误，预期: {expected_type}，实际: {stock_type}")
            
        # 如果是个股，尝试获取详细数据
        if is_stock:
            logger.info(f"  尝试获取股票详细数据...")
            try:
                stock_data = collector._get_stock_detail(stock_code)
                if stock_data:
                    logger.info(f"  ✅ 成功获取股票数据")
                    logger.info(f"  股票名称: {stock_data.get('name', '未知')}")
                    logger.info(f"  行业: {stock_data.get('industry', '未知')}")
                    logger.info(f"  PE: {stock_data.get('pe', '未知')}")
                    logger.info(f"  PB: {stock_data.get('pb', '未知')}")
                    logger.info(f"  股票类型: {stock_data.get('type', '未知')}")
                else:
                    logger.info(f"  ❌ 获取股票数据失败")
            except Exception as e:
                logger.error(f"  ❌ 获取股票数据时发生异常: {str(e)}")
                logger.exception(e)
    
    # 登出baostock
    try:
        bs.logout()
    except Exception as e:
        logger.warning(f"关闭baostock连接失败: {str(e)}")
    
    logger.info("\n测试完成！")

if __name__ == '__main__':
    test_stock_identification()
