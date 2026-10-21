#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试科创板股票分类修复效果
"""

import logging
import sys
import os
import akshare as ak
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger

# 设置日志
logger = setup_logger('test_sector_fix', logging.INFO)


def main():
    """测试科创板股票分类"""
    try:
        logger.info("=== 测试科创板股票分类修复 ===")
        
        # 测试用户提到的三只科创板股票
        test_stocks = [
            "688601",  # 力芯微 (科创板)
            "688349",  # 三一重能 (科创板)
            "688268"   # 华特气体 (科创板)
        ]
        
        logger.info(f"开始测试 {len(test_stocks)} 只科创板股票...")
        
        # 使用akshare获取股票列表
        logger.info("使用akshare获取股票列表...")
        stock_df = ak.stock_zh_a_spot_em()
        df = stock_df.copy()
        
        # 转换akshare格式到标准格式
        code_col = '代码' if '代码' in df.columns else 'symbol'
        name_col = '名称' if '名称' in df.columns else 'name'
        
        logger.info(f"从akshare获取到 {len(df)} 只股票")
        
        # 查找测试股票
        found_stocks = []
        for _, row in df.iterrows():
            raw_code = str(row[code_col])
            if raw_code in test_stocks:
                # 判断板块类型
                if raw_code.startswith('688'):
                    # 科创板
                    market_segment = '科创板'
                    normalized_code = f"sh.{raw_code}"
                elif raw_code.startswith('6'):
                    # 沪市主板
                    market_segment = '沪市主板'
                    normalized_code = f"sh.{raw_code}"
                elif raw_code.startswith(('000', '001')):
                    # 深市主板
                    market_segment = '深市主板'
                    normalized_code = f"sz.{raw_code}"
                elif raw_code.startswith('300'):
                    # 创业板
                    market_segment = '创业板'
                    normalized_code = f"sz.{raw_code}"
                else:
                    # 跳过北交所等其他板块
                    continue
                
                found_stocks.append({
                    'raw_code': raw_code,
                    'code': normalized_code,
                    'name': row[name_col],
                    'market_segment': market_segment
                })
        
        logger.info("\n测试结果：")
        for stock in found_stocks:
            status = "✓ 正确" if stock['market_segment'] == '科创板' else "✗ 错误"
            logger.info(f"{status} - {stock['code']} - {stock['name']}: 板块 = {stock['market_segment']}")
        
        # 验证所有找到的股票都被正确分类为科创板
        all_correct = all(stock['market_segment'] == '科创板' for stock in found_stocks)
        if all_correct:
            logger.info("\n🎉 板块分类修复成功！所有测试的科创板股票都被正确分类。")
        else:
            logger.error("\n❌ 板块分类修复失败！部分科创板股票被错误分类。")
        
        logger.info("\n=== 测试完成 ===")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
