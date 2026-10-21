#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指数数据采集器测试文件

功能：
1. 测试指数实时数据获取功能
2. 测试指数历史数据获取功能
3. 测试常用指数列表获取功能
4. 测试所有指数列表获取功能
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_index_collector')

from index_collector import IndexCollector

def test_index_realtime():
    """测试指数实时数据获取"""
    logger.info("=== 测试指数实时数据获取 ===")
    
    collector = IndexCollector()
    
    # 测试上证指数
    logger.info("测试上证指数(sh000001)")
    sh_index = collector.get_index_realtime('sh000001')
    assert sh_index is not None
    assert sh_index['code'] == 'sh000001'
    assert 'latest_price' in sh_index
    assert 'change' in sh_index
    assert 'change_pct' in sh_index
    logger.info(f"✓ 上证指数实时数据测试通过: {sh_index['name']} - {sh_index['latest_price']}")
    
    # 测试深证成指
    logger.info("测试深证成指(sz399001)")
    sz_index = collector.get_index_realtime('sz399001')
    assert sz_index is not None
    assert sz_index['code'] == 'sz399001'
    assert 'latest_price' in sz_index
    assert 'change' in sz_index
    assert 'change_pct' in sz_index
    logger.info(f"✓ 深证成指实时数据测试通过: {sz_index['name']} - {sz_index['latest_price']}")
    
    # 测试创业板指
    logger.info("测试创业板指(sz399006)")
    cyb_index = collector.get_index_realtime('sz399006')
    assert cyb_index is not None
    assert cyb_index['code'] == 'sz399006'
    assert 'latest_price' in cyb_index
    assert 'change' in cyb_index
    assert 'change_pct' in cyb_index
    logger.info(f"✓ 创业板指实时数据测试通过: {cyb_index['name']} - {cyb_index['latest_price']}")
    
    logger.info("✓ 所有指数实时数据测试通过")
    return True

def test_index_history():
    """测试指数历史数据获取"""
    logger.info("\n=== 测试指数历史数据获取 ===")
    
    collector = IndexCollector()
    
    # 测试上证指数历史数据
    logger.info("测试上证指数(sh000001)历史数据")
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    
    sh_history = collector.get_index_history('sh000001', start_date=start_date, end_date=end_date)
    assert sh_history is not None
    assert isinstance(sh_history, list)
    assert len(sh_history) > 0
    
    # 检查历史数据字段
    for item in sh_history:
        assert 'date' in item
        assert 'open' in item
        assert 'high' in item
        assert 'low' in item
        assert 'close' in item
        assert 'volume' in item
        assert 'amount' in item
    
    logger.info(f"✓ 上证指数历史数据测试通过，获取到 {len(sh_history)} 条数据")
    
    # 测试深证成指历史数据
    logger.info("测试深证成指(sz399001)历史数据")
    sz_history = collector.get_index_history('sz399001', start_date=start_date, end_date=end_date)
    assert sz_history is not None
    assert isinstance(sz_history, list)
    assert len(sz_history) > 0
    logger.info(f"✓ 深证成指历史数据测试通过，获取到 {len(sz_history)} 条数据")
    
    logger.info("✓ 所有指数历史数据测试通过")
    return True

def test_common_indices():
    """测试常用指数列表获取"""
    logger.info("\n=== 测试常用指数列表获取 ===")
    
    collector = IndexCollector()
    common_indices = collector.get_common_indices()
    
    assert common_indices is not None
    assert isinstance(common_indices, dict)
    assert len(common_indices) > 0
    
    # 检查常用指数是否包含关键指数
    key_indices = ['sh000001', 'sz399001', 'sz399006', 'sh000300']
    for code in key_indices:
        assert code in common_indices
        assert 'name' in common_indices[code]
        assert 'source' in common_indices[code]
    
    logger.info(f"✓ 常用指数列表测试通过，共 {len(common_indices)} 个常用指数")
    return True

def test_all_indices():
    """测试所有指数列表获取"""
    logger.info("\n=== 测试所有指数列表获取 ===")
    
    collector = IndexCollector()
    all_indices = collector.get_all_indices()
    
    assert all_indices is not None
    assert isinstance(all_indices, list)
    assert len(all_indices) > 0
    
    # 检查指数列表字段
    for item in all_indices[:5]:  # 只检查前5个
        assert 'code' in item
        assert 'name' in item
        assert 'source' in item
    
    logger.info(f"✓ 所有指数列表测试通过，共 {len(all_indices)} 个指数")
    return True

def test_cache_mechanism():
    """测试缓存机制"""
    logger.info("\n=== 测试缓存机制 ===")
    
    collector = IndexCollector()
    collector.set_update_interval(10)  # 设置较短的更新间隔以便测试
    
    # 第一次获取数据（应该从网络获取）
    import time
    start_time = time.time()
    sh_index1 = collector.get_index_realtime('sh000001')
    time1 = time.time() - start_time
    
    # 第二次获取数据（应该从缓存获取）
    start_time = time.time()
    sh_index2 = collector.get_index_realtime('sh000001')
    time2 = time.time() - start_time
    
    # 检查缓存是否生效（第二次获取应该更快）
    assert time2 < time1 * 0.1, f"缓存机制未生效，第一次耗时: {time1:.4f}s, 第二次耗时: {time2:.4f}s"
    
    # 检查两次获取的数据是否相同
    assert sh_index1['latest_price'] == sh_index2['latest_price']
    
    logger.info(f"✓ 缓存机制测试通过，第一次耗时: {time1:.4f}s, 第二次耗时: {time2:.4f}s")
    return True

def test_mock_data():
    """测试模拟数据功能"""
    logger.info("\n=== 测试模拟数据功能 ===")
    
    # 临时禁用akshare模块来测试模拟数据
    import sys
    original_ak = None
    if 'akshare' in sys.modules:
        original_ak = sys.modules['akshare']
        del sys.modules['akshare']
    
    try:
        # 重新导入index_collector，此时应该使用模拟数据
        import importlib
        if 'index_collector' in sys.modules:
            importlib.reload(sys.modules['index_collector'])
        from index_collector import IndexCollector
        
        collector = IndexCollector()
        
        # 测试获取模拟实时数据
        sh_index = collector.get_index_realtime('sh000001')
        assert sh_index is not None
        assert 'latest_price' in sh_index
        assert 'change' in sh_index
        assert 'change_pct' in sh_index
        logger.info(f"✓ 模拟实时数据测试通过: {sh_index['name']} - {sh_index['latest_price']}")
        
        # 测试获取模拟历史数据
        sh_history = collector.get_index_history('sh000001', start_date='2025-12-01', end_date='2025-12-10')
        assert sh_history is not None
        assert len(sh_history) > 0
        logger.info(f"✓ 模拟历史数据测试通过，获取到 {len(sh_history)} 条数据")
        
    finally:
        # 恢复akshare模块
        if original_ak is not None:
            sys.modules['akshare'] = original_ak
    
    logger.info("✓ 模拟数据功能测试通过")
    return True

def main():
    """主测试函数"""
    logger.info("开始测试指数采集器")
    
    tests = [
        test_index_realtime,
        test_index_history,
        test_common_indices,
        test_all_indices,
        test_cache_mechanism,
        test_mock_data
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                logger.error(f"测试失败: {test_func.__name__}")
        except Exception as e:
            failed += 1
            logger.error(f"测试异常: {test_func.__name__} - {str(e)}", exc_info=True)
    
    logger.info(f"\n=== 测试结果 ===")
    logger.info(f"通过: {passed}")
    logger.info(f"失败: {failed}")
    logger.info(f"总测试数: {passed + failed}")
    
    if failed == 0:
        logger.info("✓ 所有测试通过")
        return True
    else:
        logger.error("✗ 部分测试失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
