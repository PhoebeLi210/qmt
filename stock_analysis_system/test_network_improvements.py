#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络错误修复测试脚本

测试改进后的网络错误处理机制的效果
"""

import time
import logging
from datetime import datetime
from data_collector import StockDataCollector

def setup_test_logger():
    """设置测试日志"""
    logger = logging.getLogger('network_test')
    logger.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    return logger

def test_network_error_handling():
    """测试网络错误处理效果"""
    logger = setup_test_logger()
    logger.info("=== 网络错误处理测试开始 ===")
    
    start_time = datetime.now()
    
    try:
        # 初始化数据收集器
        collector = StockDataCollector()
        
        logger.info("数据收集器初始化成功")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 测试获取少量股票数据
        test_codes = [
            'sh.600036',  # 招商银行
            'sz.300059',  # 东方财富
            'sh.600519',  # 贵州茅台
            'sz.000858',  # 五粮液
            'sh.600309'   # 万华化学
        ]
        
        success_count = 0
        error_count = 0
        
        logger.info(f"开始测试 {len(test_codes)} 只股票的获取")
        
        for i, stock_code in enumerate(test_codes, 1):
            try:
                logger.info(f"正在获取第 {i} 只股票: {stock_code}")
                stock_data = collector._get_stock_detail_akshare(stock_code)
                
                if stock_data:
                    success_count += 1
                    logger.info(f"✓ {stock_code} 获取成功: {len(stock_data['kline_data'])} 天K线数据")
                    logger.info(f"  最新价格: {stock_data['latest_price']:.2f}")
                    logger.info(f"  涨跌幅: {stock_data['change_pct']:.2f}%")
                    if stock_data['pe'] > 0:
                        logger.info(f"  PE: {stock_data['pe']:.2f}")
                    if stock_data['pb'] > 0:
                        logger.info(f"  PB: {stock_data['pb']:.2f}")
                else:
                    error_count += 1
                    logger.warning(f"✗ {stock_code} 获取失败或数据不完整")
                
                # 显示统计信息
                logger.info(f"当前统计 - 成功: {success_count}, 失败: {error_count}, 成功率: {success_count/(success_count+error_count)*100:.1f}%")
                logger.info(f"请求统计 - 总请求: {collector.request_count}, 成功: {collector.success_count}, 失败: {collector.error_count}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"✗ {stock_code} 获取异常: {str(e)}")
                logger.info(f"当前统计 - 成功: {success_count}, 失败: {error_count}, 成功率: {success_count/(success_count+error_count)*100:.1f}%")
        
        # 最终统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=== 网络错误处理测试完成 ===")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"总耗时: {duration:.1f} 秒")
        logger.info(f"测试股票数: {len(test_codes)}")
        logger.info(f"成功获取: {success_count}")
        logger.info(f"失败获取: {error_count}")
        logger.info(f"成功率: {success_count/len(test_codes)*100:.1f}%")
        logger.info(f"平均耗时: {duration/len(test_codes):.1f} 秒/股票")
        
        # 请求统计详情
        logger.info("=== 请求统计详情 ===")
        logger.info(f"总请求次数: {collector.request_count}")
        logger.info(f"成功请求: {collector.success_count}")
        logger.info(f"失败请求: {collector.error_count}")
        if collector.request_count > 0:
            logger.info(f"请求成功率: {collector.success_count/collector.request_count*100:.1f}%")
            logger.info(f"请求错误率: {collector.error_count/collector.request_count*100:.1f}%")
        
        # 网络错误类型分析
        logger.info("=== 网络错误处理效果评估 ===")
        if collector.error_count > 0:
            logger.info(f"检测到 {collector.error_count} 个网络错误")
            logger.info("网络错误处理机制已自动重试和优化")
        else:
            logger.info("未检测到网络错误，网络状况良好")
        
        return success_count, error_count, duration
        
    except Exception as e:
        logger.error(f"测试执行失败: {str(e)}")
        return 0, len(test_codes), 0

if __name__ == "__main__":
    test_network_error_handling()