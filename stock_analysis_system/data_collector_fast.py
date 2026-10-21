#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高性能股票数据采集模块

特点：
1. 只使用akshare单一数据源，避免网络延迟累积
2. 简化数据处理流程，专注于核心指标
3. 优化请求间隔，平衡速度与稳定性
4. 减少数据量，提高处理效率
"""

import os
import time
import logging
import pandas as pd
import akshare as ak
from datetime import datetime, timedelta
import sys
import threading
import socket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.logger import setup_logger

logger = setup_logger('data_collector_fast', logging.INFO)

class FastStockDataCollector:
    """高性能股票数据采集器"""
    
    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0
        self.last_request_time = 0
        
        # 预加载所有股票列表，避免重复查询
        self._preload_stock_list()
        
    def _get_dynamic_interval(self):
        """获取动态请求间隔（高性能版：目标1-2小时完成5792只股票）"""
        self.request_count += 1
        
        if self.request_count < 500:
            return 0.2  # 前500个请求：极快间隔
        elif self.request_count < 1500:
            return 0.3  # 500-1500：快间隔
        elif self.request_count < 3000:
            return 0.5  # 1500-3000：中等间隔
        else:
            return 0.8  # 3000后：稍慢间隔（但仍然很快）
    
    def _wait_for_rate_limit(self):
        """速率限制"""
        current_time = time.time()
        interval = self._get_dynamic_interval()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < interval:
            sleep_time = interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _preload_stock_list(self):
        """预加载股票列表"""
        logger.info("正在预加载A股股票列表...")
        try:
            # 获取所有A股股票列表
            stock_df = ak.stock_zh_a_spot_em()
            
            # 标准化股票代码格式
            stock_list = []
            for _, row in stock_df.iterrows():
                code = str(row['代码'])
                if len(code) == 6:
                    if code.startswith(('6', '5', '8')):
                        normalized_code = f"sh.{code}"
                    else:
                        normalized_code = f"sz.{code}"
                    
                    # 过滤ST股票
                    name = str(row['名称'])
                    if 'ST' not in name and '*ST' not in name:
                        stock_list.append({
                            'code': normalized_code,
                            'name': name,
                            'current_price': float(row['最新价']) if pd.notna(row['最新价']) else 0,
                            'change_pct': float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else 0
                        })
            
            self.stock_list = stock_list
            logger.info(f"预加载完成: 共{len(stock_list)}只有效股票")
            
        except Exception as e:
            logger.error(f"预加载股票列表失败: {str(e)}")
            self.stock_list = []
    
    def get_all_stocks_fast(self, limit=None):
        """快速获取全部股票数据（高性能版本）"""
        if not self.stock_list:
            logger.error("股票列表未加载")
            return []
        
        valid_stocks = []
        total_stocks = len(self.stock_list)
        limit = limit or total_stocks
        
        logger.info(f"开始快速数据采集: {limit}/{total_stocks} 只股票")
        
        for i, stock in enumerate(self.stock_list[:limit]):
            self._wait_for_rate_limit()
            
            try:
                # 只获取基本数据，避免复杂的多数据源查询
                stock_data = self._get_fast_stock_data(stock['code'])
                
                if stock_data:
                    stock_data.update({
                        'name': stock['name'],
                        'current_price': stock['current_price'],
                        'change_pct': stock['change_pct']
                    })
                    valid_stocks.append(stock_data)
                    self.success_count += 1
                else:
                    self.error_count += 1
                
                # 每100只股票显示一次进度
                if (i + 1) % 100 == 0 or i < 10:
                    success_rate = self.success_count / (i + 1) * 100
                    logger.info(f"快速采集进度: {i + 1}/{limit} ({((i + 1)/limit*100):.1f}%) | "
                              f"成功: {self.success_count} | 成功率: {success_rate:.1f}% | "
                              f"当前: {stock['code']}")
                
            except Exception as e:
                logger.debug(f"获取股票数据失败({stock['code']}): {str(e)}")
                self.error_count += 1
                continue
        
        logger.info(f"快速采集完成: {len(valid_stocks)}/{limit} 只有效股票")
        return valid_stocks
    
    def _get_fast_stock_data(self, stock_code):
        """快速获取单个股票数据（仅核心指标）"""
        try:
            code = stock_code.split('.')[1]
            
            # 只获取最基础的数据，避免复杂计算
            # 1. 获取基本信息（简化版）
            try:
                basic_info = ak.stock_individual_info_em(symbol=code)
                if basic_info is None or basic_info.empty:
                    return None
                
                # 提取关键指标
                pe_ratio = None
                pb_ratio = None
                market_cap = None
                
                for _, row in basic_info.iterrows():
                    item = str(row.get('项目', ''))
                    value = str(row.get('值', ''))
                    
                    if '市盈率' in item and value != '--':
                        try:
                            pe_ratio = float(value)
                        except:
                            pass
                    elif '市净率' in item and value != '--':
                        try:
                            pb_ratio = float(value)
                        except:
                            pass
                    elif '总市值' in item and value != '--':
                        try:
                            # 处理市值单位
                            if '万' in value:
                                market_cap = float(value.replace('万', '')) * 10000
                            elif '亿' in value:
                                market_cap = float(value.replace('亿', '')) * 100000000
                            else:
                                market_cap = float(value)
                        except:
                            pass
                
                if pe_ratio is None or pb_ratio is None:
                    return None
                
                # 2. 获取简单的K线数据（最近30天）
                kline_data = []
                try:
                    end_date = datetime.now().strftime('%Y%m%d')
                    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
                    
                    kline_df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                                 start_date=start_date, end_date=end_date)
                    
                    if kline_df is not None and not kline_df.empty and len(kline_df) >= 20:
                        for _, row in kline_df.iterrows():
                            kline_data.append({
                                'date': str(row['日期']),
                                'open': float(row['开盘']) if pd.notna(row['开盘']) else 0,
                                'high': float(row['最高']) if pd.notna(row['最高']) else 0,
                                'low': float(row['最低']) if pd.notna(row['最低']) else 0,
                                'close': float(row['收盘']) if pd.notna(row['收盘']) else 0,
                                'volume': float(row['成交量']) if pd.notna(row['成交量']) else 0
                            })
                    else:
                        return None
                        
                except Exception as e:
                    logger.debug(f"获取K线数据失败({stock_code}): {str(e)}")
                    return None
                
                # 返回简化数据结构
                return {
                    'code': stock_code,
                    'pe': pe_ratio,
                    'pb': pb_ratio,
                    'market_cap': market_cap,
                    'kline_data': kline_data,
                    'latest_price': kline_data[-1]['close'] if kline_data else 0,
                    'volume_avg': sum([d['volume'] for d in kline_data]) / len(kline_data) if kline_data else 0
                }
                
            except Exception as e:
                logger.debug(f"获取基本面数据失败({stock_code}): {str(e)}")
                return None
                
        except Exception as e:
            logger.debug(f"处理股票数据失败({stock_code}): {str(e)}")
            return None
    
    def get_statistics(self):
        """获取采集统计信息"""
        total_requests = self.request_count
        success_rate = (self.success_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_requests': total_requests,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate': success_rate
        }


if __name__ == "__main__":
    # 测试高性能采集器
    collector = FastStockDataCollector()
    
    # 测试获取前10只股票
    stocks = collector.get_all_stocks_fast(limit=10)
    
    stats = collector.get_statistics()
    print(f"\n=== 性能测试结果 ===")
    print(f"获取股票数量: {len(stocks)}")
    print(f"总请求数: {stats['total_requests']}")
    print(f"成功率: {stats['success_rate']:.1f}%")
    
    if stocks:
        print(f"\n示例股票: {stocks[0]['code']} - PE: {stocks[0]['pe']:.2f}, PB: {stocks[0]['pb']:.2f}")