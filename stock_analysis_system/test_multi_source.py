#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多数据源基本面数据收集测试脚本

功能：
1. 测试多数据源机制能否有效解决基本面数据缺失问题
2. 验证不同数据源的数据质量
3. 对比改进前后的数据完整性
"""

import sys
import os
import logging
from datetime import datetime, timedelta
import time

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_collector import StockDataCollector
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('test_multi_source', logging.INFO)

def test_fundamental_data_collection():
    """测试多数据源基本面数据收集"""
    print("=== 多数据源基本面数据收集测试 ===")
    
    # 初始化数据收集器（跳过概念板块加载以加速测试）
    collector = StockDataCollector(cache_dir="test_cache")
    collector.stock_concept_map = {}  # 跳过概念板块加载
    
    # 测试股票列表（不同市场、不同代码前缀）
    test_stocks = [
        ('sh.600036', '招商银行'),
        ('sh.600519', '贵州茅台'), 
        ('sz.000001', '平安银行'),
        ('sz.002415', '海康威视'),
        ('sz.300059', '东方财富'),
        ('sh.688036', '传音控股')
    ]
    
    print(f"开始测试 {len(test_stocks)} 只股票的多数据源收集机制...")
    print("-" * 80)
    
    successful_collections = 0
    data_source_stats = {}
    
    for stock_code, stock_name in test_stocks:
        print(f"\n测试股票: {stock_code} ({stock_name})")
        print("-" * 40)
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 获取股票数据
            stock_data = collector._get_stock_detail_akshare(stock_code)
            
            # 记录结束时间
            end_time = time.time()
            duration = end_time - start_time
            
            if stock_data:
                successful_collections += 1
                data_source = stock_data.get('data_source', 'unknown')
                data_source_stats[data_source] = data_source_stats.get(data_source, 0) + 1
                
                print(f"✓ 数据收集成功")
                print(f"  数据源: {data_source}")
                print(f"  耗时: {duration:.2f}秒")
                print(f"  股票名称: {stock_data.get('name', 'N/A')}")
                print(f"  行业: {stock_data.get('industry', 'N/A')}")
                print(f"  PE: {stock_data.get('pe', 0)}")
                print(f"  PB: {stock_data.get('pb', 0)}")
                print(f"  流通市值: {stock_data.get('liquid_shares', 0):,.0f}")
                print(f"  总市值: {stock_data.get('market_cap', 0):,.0f}")
                
                # 检查数据完整性
                data_fields = ['pe', 'pb', 'liquid_shares', 'market_cap', 'industry', 'name']
                non_zero_fields = [field for field in data_fields if stock_data.get(field, 0) != 0 or stock_data.get(field) != '']
                completeness = len(non_zero_fields) / len(data_fields) * 100
                print(f"  数据完整性: {completeness:.1f}%")
                
            else:
                print(f"✗ 数据收集失败")
                
        except Exception as e:
            print(f"✗ 发生异常: {str(e)}")
    
    # 输出统计结果
    print("\n" + "="*80)
    print("测试结果统计:")
    print(f"成功收集: {successful_collections}/{len(test_stocks)} ({successful_collections/len(test_stocks)*100:.1f}%)")
    print(f"失败数量: {len(test_stocks) - successful_collections}")
    
    if data_source_stats:
        print("\n数据源使用统计:")
        for source, count in data_source_stats.items():
            print(f"  {source}: {count}次 ({count/successful_collections*100:.1f}%)")
    
    return successful_collections, len(test_stocks)

def test_data_source_fallback():
    """测试数据源降级机制"""
    print("\n=== 数据源降级机制测试 ===")
    
    collector = StockDataCollector(cache_dir="test_cache")
    collector.stock_concept_map = {}
    
    # 测试一个特定股票，观察数据源降级过程
    test_code = "600036"
    market = "sh"
    
    print(f"测试降级机制: {market}.{test_code}")
    print("-" * 40)
    
    try:
        # 手动调用多数据源方法
        fundamental_data = collector._get_fundamental_data_multi_source(test_code, market)
        
        if fundamental_data:
            print(f"✓ 最终数据源: {fundamental_data.get('source', 'unknown')}")
            print(f"  股票名称: {fundamental_data.get('name', 'N/A')}")
            print(f"  行业: {fundamental_data.get('industry', 'N/A')}")
            print(f"  PE: {fundamental_data.get('pe', 0)}")
            print(f"  PB: {fundamental_data.get('pb', 0)}")
            
            # 验证数据质量
            is_valid = collector._validate_fundamental_data(fundamental_data)
            print(f"  数据质量验证: {'通过' if is_valid else '失败'}")
            
        else:
            print("✗ 所有数据源都失败")
            
    except Exception as e:
        print(f"✗ 测试异常: {str(e)}")

def test_intelligent_inference():
    """测试智能推算功能"""
    print("\n=== 智能推算功能测试 ===")
    
    collector = StockDataCollector(cache_dir="test_cache")
    
    # 测试不同代码前缀的智能推算
    test_cases = [
        ('600036', 'sh', '银行股'),
        ('000001', 'sz', '深圳主板'),
        ('002415', 'sz', '中小板'),
        ('300059', 'sz', '创业板'),
        ('688036', 'sh', '科创板')
    ]
    
    print("测试股票代码智能推算:")
    print("-" * 40)
    
    for code, market, description in test_cases:
        try:
            inferred_data = collector._get_fundamental_data_fallback(code, market)
            
            print(f"\n{description} - {market}.{code}:")
            print(f"  推算行业: {inferred_data.get('industry', 'N/A')}")
            print(f"  推算PE: {inferred_data.get('pe', 0)}")
            print(f"  推算PB: {inferred_data.get('pb', 0)}")
            print(f"  数据源: {inferred_data.get('source', 'unknown')}")
            
        except Exception as e:
            print(f"  推算失败: {str(e)}")

if __name__ == "__main__":
    print("开始多数据源机制测试...")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    try:
        # 主要测试：多数据源收集
        success_count, total_count = test_fundamental_data_collection()
        
        # 降级机制测试
        test_data_source_fallback()
        
        # 智能推算测试
        test_intelligent_inference()
        
        # 总结
        print("\n" + "="*80)
        print("测试总结:")
        if success_count >= total_count * 0.8:  # 80%成功率
            print("✓ 多数据源机制工作正常，基本面数据缺失问题得到显著改善")
        elif success_count >= total_count * 0.6:  # 60%成功率
            print("⚠ 多数据源机制部分工作，需要进一步优化")
        else:
            print("✗ 多数据源机制需要重大改进")
            
        print(f"数据收集成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
        
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        logger.exception("测试过程异常")
    
    print("\n测试完成!")