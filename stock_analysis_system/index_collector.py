#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票指数数据采集模块

功能：
1. 从实时数据源（东方财富、新浪财经、同花顺等）获取股票指数数据
2. 支持多种指数类型（上证指数、深证成指、创业板指等）
3. 提供实时和历史指数数据获取接口
"""

import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('index_collector', logging.INFO)

# 动态导入akshare库，避免没有安装时影响系统运行
try:
    import akshare as ak
except ImportError:
    logger.warning("akshare库未安装，将使用模拟数据")
    ak = None

class IndexCollector:
    """指数数据采集器"""
    
    def __init__(self):
        """初始化指数采集器"""
        self.index_cache = {}
        self.last_update_time = {}
        self.update_interval = 60  # 默认更新间隔为60秒
        
        # 定义常用指数列表
        self.common_indices = {
            'sh000001': {'name': '上证指数', 'source': 'eastmoney'},
            'sz399001': {'name': '深证成指', 'source': 'eastmoney'},
            'sz399006': {'name': '创业板指', 'source': 'eastmoney'},
            'sh000300': {'name': '沪深300', 'source': 'eastmoney'},
            'sh000016': {'name': '上证50', 'source': 'eastmoney'},
            'sh000905': {'name': '中证500', 'source': 'eastmoney'},
            'sh000005': {'name': '上证基金指数', 'source': 'eastmoney'},
            'sh000006': {'name': '上证国债指数', 'source': 'eastmoney'},
            'sz399005': {'name': '中小板指', 'source': 'eastmoney'},
            'sh000852': {'name': '中证1000', 'source': 'eastmoney'}
        }
    
    def get_index_realtime(self, index_code):
        """获取指数实时数据
        
        Args:
            index_code: 指数代码，如'sh000001'（上证指数）
            
        Returns:
            dict: 指数实时数据
        """
        if not ak:
            return self._get_mock_index_realtime(index_code)
            
        try:
            # 检查缓存是否有效
            if index_code in self.index_cache and index_code in self.last_update_time:
                elapsed = time.time() - self.last_update_time[index_code]
                if elapsed < self.update_interval:
                    logger.debug(f"从缓存获取指数实时数据: {index_code}")
                    return self.index_cache[index_code]
            
            logger.info(f"获取指数实时数据: {index_code}")
            
            # 根据指数代码选择数据源
            if index_code.startswith('sh') or index_code.startswith('sz'):
                # 使用东方财富数据源获取指数实时数据
                index_data = ak.stock_zh_index_spot_em()
                index_info = index_data[index_data['代码'] == index_code]
                
                if not index_info.empty:
                    index_info = index_info.iloc[0].to_dict()
                    
                    # 构建指数数据结构
                    result = {
                        'code': index_code,
                        'name': index_info['名称'],
                        'latest_price': index_info['最新价'],
                        'change': index_info['涨跌额'],
                        'change_pct': index_info['涨跌幅'],
                        'open': index_info['今开'],
                        'high': index_info['最高'],
                        'low': index_info['最低'],
                        'volume': index_info['成交量'],
                        'amount': index_info['成交额'],
                        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # 更新缓存
                    self.index_cache[index_code] = result
                    self.last_update_time[index_code] = time.time()
                    
                    return result
                else:
                    logger.warning(f"未找到指数数据: {index_code}")
                    return self._get_mock_index_realtime(index_code)
            else:
                logger.warning(f"不支持的指数代码格式: {index_code}")
                return self._get_mock_index_realtime(index_code)
                
        except Exception as e:
            logger.error(f"获取指数实时数据失败({index_code}): {str(e)}")
            return self._get_mock_index_realtime(index_code)
    
    def get_index_history(self, index_code, start_date=None, end_date=None):
        """获取指数历史数据
        
        Args:
            index_code: 指数代码
            start_date: 开始日期，格式'YYYY-MM-DD'
            end_date: 结束日期，格式'YYYY-MM-DD'
            
        Returns:
            list: 指数历史数据列表
        """
        if not ak:
            return self._get_mock_index_history(index_code, start_date, end_date)
            
        try:
            logger.info(f"获取指数历史数据: {index_code}, {start_date} 至 {end_date}")
            
            # 设置默认日期
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # 使用东方财富数据源获取指数历史数据
            index_data = ak.stock_zh_index_daily_em(symbol=index_code)
            
            # 过滤日期范围
            index_data['date'] = pd.to_datetime(index_data['date'])
            index_data = index_data[(index_data['date'] >= start_date) & (index_data['date'] <= end_date)]
            
            # 转换为字典列表
            result = index_data.to_dict('records')
            
            # 格式化日期
            for item in result:
                item['date'] = item['date'].strftime('%Y-%m-%d')
            
            logger.debug(f"获取到 {len(result)} 条指数历史数据: {index_code}")
            return result
            
        except Exception as e:
            logger.error(f"获取指数历史数据失败({index_code}): {str(e)}")
            return self._get_mock_index_history(index_code, start_date, end_date)
    
    def get_common_indices(self):
        """获取常用指数列表
        
        Returns:
            dict: 常用指数列表
        """
        return self.common_indices
    
    def get_all_indices(self, source='eastmoney'):
        """获取所有指数列表
        
        Args:
            source: 数据源，默认为'eastmoney'
            
        Returns:
            list: 指数列表
        """
        if not ak:
            return list(self.common_indices.values())
            
        try:
            logger.info(f"获取所有指数列表，数据源: {source}")
            
            if source == 'eastmoney':
                index_data = ak.stock_zh_index_spot_em()
                result = []
                for _, row in index_data.iterrows():
                    result.append({
                        'code': row['代码'],
                        'name': row['名称'],
                        'source': source
                    })
                return result
            else:
                logger.warning(f"不支持的数据源: {source}")
                return list(self.common_indices.values())
                
        except Exception as e:
            logger.error(f"获取所有指数列表失败: {str(e)}")
            return list(self.common_indices.values())
    
    def _get_mock_index_realtime(self, index_code):
        """获取模拟指数实时数据（当akshare不可用时）"""
        logger.debug(f"使用模拟指数实时数据: {index_code}")
        
        # 获取指数名称
        index_name = self.common_indices.get(index_code, {}).get('name', f'指数{index_code}')
        
        # 生成模拟数据
        base_price = 3000 if index_code.startswith('sh000001') else 10000 if index_code.startswith('sz399001') else 2000
        
        # 随机生成价格波动
        import random
        change_pct = random.uniform(-2, 2)
        latest_price = base_price * (1 + change_pct / 100)
        change = latest_price - base_price
        
        return {
            'code': index_code,
            'name': index_name,
            'latest_price': round(latest_price, 2),
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
            'open': round(base_price * (1 + random.uniform(-1, 1) / 100), 2),
            'high': round(max(base_price * (1 + random.uniform(0, 2) / 100), latest_price), 2),
            'low': round(min(base_price * (1 + random.uniform(-2, 0) / 100), latest_price), 2),
            'volume': random.randint(1000000, 10000000),
            'amount': random.randint(100000000, 10000000000),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _get_mock_index_history(self, index_code, start_date=None, end_date=None):
        """获取模拟指数历史数据（当akshare不可用时）"""
        logger.debug(f"使用模拟指数历史数据: {index_code}")
        
        # 设置默认日期
        if not end_date:
            end_date = datetime.now()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        if not start_date:
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        
        # 生成日期序列
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # 生成模拟数据
        import random
        base_price = 3000 if index_code.startswith('sh000001') else 10000 if index_code.startswith('sz399001') else 2000
        
        result = []
        current_price = base_price
        
        for date in date_range:
            # 跳过周末
            if date.weekday() >= 5:
                continue
            
            # 随机生成价格波动
            change_pct = random.uniform(-2, 2)
            open_price = current_price
            close_price = current_price * (1 + change_pct / 100)
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 1) / 100)
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 1) / 100)
            volume = random.randint(1000000, 10000000)
            amount = random.randint(100000000, 10000000000)
            
            result.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume,
                'amount': amount
            })
            
            current_price = close_price
        
        return result
    
    def set_update_interval(self, interval):
        """设置更新间隔
        
        Args:
            interval: 更新间隔（秒）
        """
        self.update_interval = interval
        logger.info(f"指数数据更新间隔已设置为 {interval} 秒")
    
    def clear_cache(self):
        """清除缓存"""
        self.index_cache.clear()
        self.last_update_time.clear()
        logger.info("指数数据缓存已清除")

# 测试代码
if __name__ == "__main__":
    """测试指数采集器"""
    try:
        collector = IndexCollector()
        
        # 测试获取实时指数数据
        logger.info("=== 测试获取实时指数数据 ===")
        sh_index = collector.get_index_realtime('sh000001')
        logger.info(f"上证指数实时数据: {sh_index}")
        
        sz_index = collector.get_index_realtime('sz399001')
        logger.info(f"深证成指实时数据: {sz_index}")
        
        # 测试获取历史指数数据
        logger.info("\n=== 测试获取历史指数数据 ===")
        sh_history = collector.get_index_history('sh000001', start_date='2025-12-01', end_date='2025-12-20')
        logger.info(f"上证指数历史数据数量: {len(sh_history)}")
        if sh_history:
            logger.info(f"最新一条历史数据: {sh_history[-1]}")
        
        # 测试获取常用指数列表
        logger.info("\n=== 测试获取常用指数列表 ===")
        common_indices = collector.get_common_indices()
        logger.info(f"常用指数数量: {len(common_indices)}")
        for code, info in common_indices.items():
            logger.info(f"{code}: {info['name']}")
            
    except Exception as e:
        logger.error(f"测试指数采集器失败: {str(e)}", exc_info=True)
