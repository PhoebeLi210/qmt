#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化网络错误修复测试脚本

跳过概念板块数据加载，直接测试网络错误处理机制
"""

import time
import logging
from datetime import datetime
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

class SimplifiedDataCollector:
    """简化的数据收集器，专注于测试网络错误修复"""
    
    def __init__(self):
        # 网络请求控制相关属性
        self.last_request_time = 0
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0
        
        import baostock as bs
        import akshare as ak
        import pandas as pd
        from datetime import datetime, timedelta
        
        self.bs = bs
        self.ak = ak
        self.pd = pd
        self.datetime = datetime
        self.timedelta = timedelta
        
        self._init_baostock()
    
    def _init_baostock(self):
        """初始化baostock连接"""
        try:
            import socket
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(30)
            lg = self.bs.login()
            socket.setdefaulttimeout(original_timeout)
            
            if lg.error_code != '0':
                raise Exception(f"baostock登录失败: {lg.error_msg}")
            print("baostock连接成功")
        except Exception as e:
            print(f"初始化baostock连接失败: {str(e)}")
            raise
    
    def _apply_request_interval_control(self, current_index, total_count):
        """应用增强的请求间隔控制，减少网络错误"""
        current_time = time.time()
        
        # 记录请求
        self.request_count += 1
        
        # 动态频率限制
        interval_strategy = self._get_dynamic_interval_strategy()
        base_interval = interval_strategy['base_interval']
        max_interval = interval_strategy['max_interval']
        
        # 基础间隔：随着请求数量递增
        progressive_interval = min(base_interval + (current_index // 10) * 0.1, max_interval)
        
        # 根据错误率动态调整间隔
        if self.request_count > 10:
            error_rate = self.error_count / self.request_count
            if error_rate > 0.5:  # 错误率超过50%
                progressive_interval = min(progressive_interval * 3, 10.0)  # 最大10秒间隔
                print(f"错误率过高({error_rate:.1%})，大幅降低请求频率: {progressive_interval:.1f}s")
            elif error_rate > 0.3:  # 错误率超过30%
                progressive_interval = min(progressive_interval * 2, 5.0)  # 最大5秒间隔
                print(f"错误率较高({error_rate:.1%})，降低请求频率: {progressive_interval:.1f}s")
            elif error_rate > 0.1:  # 错误率超过10%
                progressive_interval = min(progressive_interval * 1.5, 3.0)  # 最大3秒间隔
        
        # 短时间高频错误检测 - 如果最近5个请求都失败，强制增加间隔
        recent_window = min(self.request_count, 5)
        if recent_window >= 5:
            # 检查最近N个请求的错误率
            recent_error_rate = self._get_recent_error_rate(recent_window)
            if recent_error_rate > 0.8:  # 最近5个请求中80%以上失败
                emergency_interval = min(progressive_interval * 2, 15.0)  # 最大15秒间隔
                print(f"连续错误率过高，紧急降低频率: {emergency_interval:.1f}s")
                progressive_interval = emergency_interval
        
        # 计算等待时间
        if self.last_request_time > 0:
            time_since_last = current_time - self.last_request_time
            wait_time = max(0, progressive_interval - time_since_last)
            
            if wait_time > 0:
                print(f"请求间隔控制: {wait_time:.2f}s (第{current_index}/{total_count}个请求，错误率:{self.error_count/self.request_count:.1%})")
                time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _get_dynamic_interval_strategy(self):
        """获取动态间隔策略"""
        if self.request_count < 50:
            # 前50个请求使用较小间隔
            return {'base_interval': 0.2, 'max_interval': 1.5}
        elif self.request_count < 200:
            # 50-200个请求使用中等间隔
            return {'base_interval': 0.5, 'max_interval': 2.5}
        elif self.request_count < 500:
            # 200-500个请求使用较大间隔
            return {'base_interval': 1.0, 'max_interval': 4.0}
        else:
            # 500个请求后使用最大间隔
            return {'base_interval': 1.5, 'max_interval': 6.0}
    
    def _get_recent_error_rate(self, window_size):
        """计算最近N个请求的错误率（简化版本）"""
        if self.request_count < window_size:
            return self.error_count / max(self.request_count, 1)
        
        # 简化的最近错误率计算
        return min(self.error_count / max(self.request_count, 1), 1.0)
    
    def _update_request_stats(self, success=True):
        """更新请求统计"""
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def _classify_error(self, error_str, retry_configs):
        """智能错误分类"""
        error_str_lower = error_str.lower()
        
        # DNS解析错误
        if any(keyword in error_str_lower for keyword in ['name resolution error', 'failed to resolve', 'getaddrinfo failed', 'dns', 'cannot resolve']):
            return 'dns_error', retry_configs['dns_error']
        
        # 连接超时错误
        elif any(keyword in error_str_lower for keyword in ['timeout', 'timed out', 'read timeout', 'connect timeout']):
            return 'timeout_error', retry_configs['timeout_error']
        
        # 连接错误
        elif any(keyword in error_str_lower for keyword in ['connection', 'connection refused', 'connection reset', 'winerror 10054']):
            return 'connection_error', retry_configs['connection_error']
        
        # 数据错误（通常不重试）
        elif any(keyword in error_str_lower for keyword in ['no data', 'empty', 'invalid', '接收数据异常']):
            return 'data_error', retry_configs['data_error']
        
        # 默认其他错误
        else:
            return 'unknown_error', retry_configs['connection_error']
    
    def get_stock_data(self, stock_code):
        """获取股票数据（带网络错误处理）"""
        # 针对不同错误类型的重试策略
        error_retry_configs = {
            'dns_error': {'max_retries': 3, 'base_delay': 5, 'max_delay': 30},
            'timeout_error': {'max_retries': 2, 'base_delay': 10, 'max_delay': 60},
            'connection_error': {'max_retries': 2, 'base_delay': 3, 'max_delay': 15},
            'data_error': {'max_retries': 1, 'base_delay': 1, 'max_delay': 5}
        }
        
        retries = 0
        max_retries = 3
        base_delay = 3
        
        while retries < max_retries:
            try:
                code = stock_code.split('.')[1]
                
                # 获取K线数据
                kline_df = self.ak.stock_zh_a_hist(symbol=code, period="daily", 
                                                  start_date=(self.datetime.now() - self.timedelta(days=35)).strftime('%Y%m%d'),
                                                  end_date=self.datetime.now().strftime('%Y%m%d'))
                
                if kline_df is None or kline_df.empty:
                    print(f"未获取到K线数据({stock_code})")
                    return None
                
                # 提取基本数据
                latest_close = float(kline_df.iloc[-1]['收盘']) if len(kline_df) > 0 else 0
                prev_close = float(kline_df.iloc[-2]['收盘']) if len(kline_df) >= 2 else latest_close
                
                # 计算涨跌幅
                if prev_close > 0:
                    change_pct = (latest_close - prev_close) / prev_close * 100
                else:
                    change_pct = 0
                
                stock_data = {
                    'code': stock_code,
                    'latest_price': latest_close,
                    'change_pct': change_pct,
                    'kline_days': len(kline_df)
                }
                
                self._update_request_stats(success=True)
                return stock_data
                
            except Exception as e:
                error_str = str(e)
                self._update_request_stats(success=False)
                
                # 智能错误分类和重试策略
                error_type, retry_config = self._classify_error(error_str, error_retry_configs)
                
                retries += 1
                if retries >= retry_config['max_retries']:
                    print(f"获取股票详细数据失败({error_type}-{stock_code}): {str(e)}")
                    return None
                
                # 计算重试延迟（指数退避）
                delay = min(retry_config['base_delay'] * (2 ** (retries - 1)), retry_config['max_delay'])
                print(f"{error_type}({stock_code})，第 {retries} 次重试，等待 {delay} 秒: {str(e)}")
                time.sleep(delay)
        
        return None

def test_network_error_handling():
    """测试网络错误处理效果"""
    logger = setup_test_logger()
    logger.info("=== 简化网络错误处理测试开始 ===")
    
    start_time = datetime.now()
    
    try:
        # 初始化简化数据收集器
        collector = SimplifiedDataCollector()
        
        logger.info("简化数据收集器初始化成功")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 测试获取少量股票数据
        test_codes = [
            '600036',  # 招商银行
            '300059',  # 东方财富
            '600519',  # 贵州茅台
            '000858',  # 五粮液
            '600309'   # 万华化学
        ]
        
        success_count = 0
        error_count = 0
        
        print(f"开始测试 {len(test_codes)} 只股票的获取")
        
        for i, stock_code in enumerate(test_codes, 1):
            try:
                print(f"正在获取第 {i} 只股票: {stock_code}")
                
                # 应用请求间隔控制
                collector._apply_request_interval_control(i, len(test_codes))
                
                # 加上市场前缀
                full_code = f"sh.{stock_code}" if stock_code.startswith('6') else f"sz.{stock_code}"
                stock_data = collector.get_stock_data(full_code)
                
                if stock_data:
                    success_count += 1
                    print(f"✓ {stock_code} 获取成功:")
                    print(f"  最新价格: {stock_data['latest_price']:.2f}")
                    print(f"  涨跌幅: {stock_data['change_pct']:.2f}%")
                    print(f"  K线数据: {stock_data['kline_days']} 天")
                else:
                    error_count += 1
                    print(f"✗ {stock_code} 获取失败或数据不完整")
                
                # 显示统计信息
                total_requests = collector.request_count
                success_rate = collector.success_count / max(total_requests, 1) * 100
                print(f"当前统计 - 成功: {success_count}, 失败: {error_count}, 成功率: {success_count/(success_count+error_count)*100:.1f}%")
                print(f"请求统计 - 总请求: {total_requests}, 成功: {collector.success_count}, 失败: {collector.error_count}, 成功率: {success_rate:.1f}%")
                print("-" * 50)
                
            except Exception as e:
                error_count += 1
                print(f"✗ {stock_code} 获取异常: {str(e)}")
                print(f"当前统计 - 成功: {success_count}, 失败: {error_count}, 成功率: {success_count/(success_count+error_count)*100:.1f}%")
                print("-" * 50)
        
        # 最终统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("=== 网络错误处理测试完成 ===")
        print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总耗时: {duration:.1f} 秒")
        print(f"测试股票数: {len(test_codes)}")
        print(f"成功获取: {success_count}")
        print(f"失败获取: {error_count}")
        print(f"成功率: {success_count/len(test_codes)*100:.1f}%")
        print(f"平均耗时: {duration/len(test_codes):.1f} 秒/股票")
        
        # 请求统计详情
        print("=== 请求统计详情 ===")
        print(f"总请求次数: {collector.request_count}")
        print(f"成功请求: {collector.success_count}")
        print(f"失败请求: {collector.error_count}")
        if collector.request_count > 0:
            print(f"请求成功率: {collector.success_count/collector.request_count*100:.1f}%")
            print(f"请求错误率: {collector.error_count/collector.request_count*100:.1f}%")
        
        # 网络错误类型分析
        print("=== 网络错误处理效果评估 ===")
        if collector.error_count > 0:
            print(f"检测到 {collector.error_count} 个网络错误")
            print("网络错误处理机制已自动重试和优化")
        else:
            print("未检测到网络错误，网络状况良好")
        
        return success_count, error_count, duration
        
    except Exception as e:
        print(f"测试执行失败: {str(e)}")
        return 0, len(test_codes), 0

if __name__ == "__main__":
    test_network_error_handling()