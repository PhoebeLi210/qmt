#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票数据采集模块

功能：
1. 从实时数据源采集全部A股市场股票数据
2. 支持深、沪主板股票，科创板，创业板
3. 去除ST股票
4. 数据缓存功能，提高性能
"""

import os
import time
import logging
import socket
import baostock as bs
import pandas as pd
import akshare as ak
from functools import wraps
from datetime import datetime, timedelta
import sys
import os
import threading
# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger

# 设置socket超时时间
socket.setdefaulttimeout(30)

# DNS缓存
_dns_cache = {}
_dns_cache_lock = threading.Lock()

def _get_cached_ip(host):
    """获取缓存的IP地址"""
    with _dns_cache_lock:
        return _dns_cache.get(host)

def _cache_ip(host, ip):
    """缓存IP地址"""
    with _dns_cache_lock:
        _dns_cache[host] = ip

# 超时重试装饰器
def timeout_retry(max_retries=3, timeout=20, delay=2, exponential_base=2):
    """超时重试装饰器，支持指数退避"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            last_exception = None
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.timeout, ConnectionError, TimeoutError, OSError, UnicodeDecodeError) as e:
                    last_exception = e
                    retries += 1
                    if retries >= max_retries:
                        logging.debug(f"函数 {func.__name__} 重试 {max_retries} 次后失败: {str(e)}")
                        raise
                    logging.debug(f"函数 {func.__name__} 调用失败(网络/编码异常)，第 {retries} 次重试: {str(e)}")
                    time.sleep(current_delay)
                    current_delay *= exponential_base
                except Exception as e:
                    last_exception = e
                    retries += 1
                    if retries >= max_retries:
                        logging.debug(f"函数 {func.__name__} 重试 {max_retries} 次后失败: {str(e)}")
                        raise
                    logging.debug(f"函数 {func.__name__} 调用失败，第 {retries} 次重试: {str(e)}")
                    time.sleep(current_delay)
                    current_delay *= exponential_base
            raise last_exception
        return wrapper
    return decorator

# 配置日志
logger = setup_logger('data_collector', logging.DEBUG)


class StockDataCollector:
    """股票数据采集器"""
    
    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        self.bs = bs
        self.stock_cache = {}
        self.stock_concept_map = {}
        
        # 网络请求控制相关属性
        self.last_request_time = 0
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self._init_connection()
        self._load_concept_map()
    
    def _load_concept_map(self):
        """加载概念板块与股票映射"""
        try:
            import akshare as ak
            logger.info("加载概念板块数据...")
            
            concept_df = ak.stock_board_concept_name_em()
            if concept_df is not None and not concept_df.empty:
                concept_count = 0
                stock_count = 0
                
                for _, row in concept_df.iterrows():
                    concept_name = row['板块名称']
                    if not concept_name:
                        continue
                    
                    try:
                        concept_code = row['板块代码']
                        cons_df = ak.stock_board_concept_cons_em(symbol=concept_code)
                        if cons_df is not None and not cons_df.empty:
                            if '代码' in cons_df.columns:
                                for _, stock_row in cons_df.iterrows():
                                    stock_code = stock_row['代码']
                                    if stock_code and str(stock_code).startswith(('sh.', 'sz.')):
                                        if stock_code not in self.stock_concept_map:
                                            self.stock_concept_map[stock_code] = []
                                        if concept_name not in self.stock_concept_map[stock_code]:
                                            self.stock_concept_map[stock_code].append(concept_name)
                                            stock_count += 1
                            elif 'code' in cons_df.columns:
                                for _, stock_row in cons_df.iterrows():
                                    stock_code = stock_row['code']
                                    if stock_code and str(stock_code).startswith(('sh.', 'sz.')):
                                        if stock_code not in self.stock_concept_map:
                                            self.stock_concept_map[stock_code] = []
                                        if concept_name not in self.stock_concept_map[stock_code]:
                                            self.stock_concept_map[stock_code].append(concept_name)
                                            stock_count += 1
                            concept_count += 1
                    except Exception as e:
                        logger.debug(f"获取概念板块 {concept_name} 成份股失败: {str(e)}")
                        continue
                
                logger.info(f"概念数据加载完成: {concept_count} 个概念板块, {stock_count} 条股票-概念映射")
        except Exception as e:
            logger.warning(f"加载概念板块数据失败: {str(e)}")
    
    @timeout_retry(max_retries=5, delay=5)
    def _init_connection(self):
        """初始化baostock连接"""
        try:
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(60)
            lg = self.bs.login()
            socket.setdefaulttimeout(original_timeout)
            
            if lg.error_code != '0':
                raise Exception(f"baostock登录失败: {lg.error_msg}")
            logger.info("baostock连接成功")
        except Exception as e:
            logger.warning(f"初始化baostock连接失败: {str(e)}")
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
        
        # 根据错误率动态调整间隔（高性能模式：宽松阈值）
        if self.request_count > 20:
            error_rate = self.error_count / self.request_count
            if error_rate > 0.8:  # 错误率超过80%
                progressive_interval = min(progressive_interval * 2, 5.0)  # 最大5秒间隔
                logger.warning(f"错误率过高({error_rate:.1%})，大幅降低请求频率: {progressive_interval:.1f}s")
            elif error_rate > 0.6:  # 错误率超过60%
                progressive_interval = min(progressive_interval * 1.5, 2.5)  # 最大2.5秒间隔
                logger.debug(f"错误率较高({error_rate:.1%})，降低请求频率: {progressive_interval:.1f}s")
            elif error_rate > 0.4:  # 错误率超过40%
                progressive_interval = min(progressive_interval * 1.2, 1.8)  # 最大1.8秒间隔
        
        # 短时间高频错误检测 - 如果最近5个请求都失败，强制增加间隔（高性能模式）
        recent_window = min(self.request_count, 5)
        if recent_window >= 5:
            # 检查最近N个请求的错误率
            recent_error_rate = self._get_recent_error_rate(recent_window)
            if recent_error_rate > 0.95:  # 最近5个请求中95%以上失败才触发紧急模式
                emergency_interval = min(progressive_interval * 1.5, 8.0)  # 最大8秒间隔
                logger.warning(f"连续错误率过高，紧急降低频率: {emergency_interval:.1f}s")
                progressive_interval = emergency_interval
        
        # 计算等待时间
        if self.last_request_time > 0:
            time_since_last = current_time - self.last_request_time
            wait_time = max(0, progressive_interval - time_since_last)
            
            if wait_time > 0:
                logger.debug(f"请求间隔控制: {wait_time:.2f}s (第{current_index}/{total_count}个请求，错误率:{self.error_count/self.request_count:.1%})")
                time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _get_dynamic_interval_strategy(self):
        """获取动态间隔策略（高性能版：确保1-2小时内完成5792只股票）"""
        if self.request_count < 500:
            # 前500个请求使用快速间隔
            return {'base_interval': 0.3, 'max_interval': 0.8}
        elif self.request_count < 1500:
            # 500-1500个请求使用中等间隔
            return {'base_interval': 0.5, 'max_interval': 1.2}
        elif self.request_count < 3000:
            # 1500-3000个请求使用稍大间隔
            return {'base_interval': 0.8, 'max_interval': 1.5}
        elif self.request_count < 5000:
            # 3000-5000个请求使用较大间隔
            return {'base_interval': 1.0, 'max_interval': 2.0}
        else:
            # 5000个请求后使用最大间隔
            return {'base_interval': 1.2, 'max_interval': 2.5}
    
    def _get_recent_error_rate(self, window_size):
        """计算最近N个请求的错误率（简化版本）"""
        if self.request_count < window_size:
            return self.error_count / max(self.request_count, 1)
        
        # 简化的最近错误率计算
        # 实际实现中可能需要记录详细的请求历史
        return min(self.error_count / max(self.request_count, 1), 1.0)
    
    def _update_request_stats(self, success=True):
        """更新请求统计"""
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    @timeout_retry(max_retries=3, delay=3)
    def _is_st_stock(self, stock_code):
        """判断是否为ST股票"""
        if not stock_code:
            return False
        
        try:
            # 查询股票基本信息
            try:
                rs = self.bs.query_stock_basic(code=stock_code)
            except Exception as e:
                logger.debug(f"查询股票基本信息超时({stock_code}): {str(e)}")
                return False
            
            if rs.error_code != '0':
                logger.debug(f"查询股票基本信息失败({stock_code}): {rs.error_msg}")
                return False  # 查询失败时视为非ST股票，避免过滤掉所有股票
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if data_list:
                try:
                    # 安全创建DataFrame，避免列数不匹配问题
                    df = pd.DataFrame(data_list)
                    if not df.empty and len(df.columns) > 1:
                        # 尝试获取股票名称（通常在第二列）
                        stock_name = df.iloc[0, 1] if len(df.iloc[0]) > 1 else ""
                        return 'ST' in str(stock_name) or '*ST' in str(stock_name)
                except Exception as e:
                    logger.debug(f"解析ST股票数据失败({stock_code}): {str(e)}")
                    # 备选方案：直接检查数据列表
                    for row in data_list:
                        if row and len(row) > 1:
                            stock_name = str(row[1])
                            if 'ST' in stock_name or '*ST' in stock_name:
                                return True
            
            return False  # 没有数据时视为非ST股票
        except Exception as e:
            logger.debug(f"判断ST股票失败({stock_code}): {str(e)}")
            return False  # 异常情况下视为非ST股票
    
    def get_all_stocks(self, limit=None):
        """获取全部A股市场股票数据（去除ST股票）
        
        Args:
            limit: 限制返回的股票数量，None表示获取所有
        """
        valid_stocks = []
        try:
            logger.info("开始获取全部A股股票数据...")
            
            # 优先使用akshare获取股票列表（更稳定）
            use_akshare = True
            
            if use_akshare:
                try:
                    logger.info("使用akshare获取股票列表...")
                    stock_df = ak.stock_zh_a_spot_em()
                    df = pd.DataFrame(stock_df)
                    
                    # 转换akshare格式到标准格式
                    code_col = '代码' if '代码' in df.columns else 'symbol'
                    name_col = '名称' if '名称' in df.columns else 'name'
                    
                    normalized_data = []
                    for _, row in df.iterrows():
                        raw_code = str(row[code_col])
                        if len(raw_code) == 6:
                            if raw_code.startswith(('6', '5', '8')):
                                normalized_code = f"sh.{raw_code}"
                            else:
                                normalized_code = f"sz.{raw_code}"
                            
                            normalized_data.append({
                                'code': normalized_code,
                                'name': row[name_col]
                            })
                    
                    df = pd.DataFrame(normalized_data)
                    logger.info(f"通过akshare获取到 {len(df)} 只股票")
                except Exception as e:
                    raise Exception(f"akshare获取股票列表失败: {str(e)}")
            
            # 2. 过滤股票（去除ST股票和非A股）
            total = len(df)
            
            for i, row in df.iterrows():
                stock_code = row['code']
                
                # 如果达到限制，提前终止
                if limit is not None and len(valid_stocks) >= limit:
                    break
                
                # 股票代码格式过滤 - 只保留个股，过滤指数和债券
                if '.' not in stock_code:
                    continue
                
                # 股票代码格式过滤 - 只保留个股，过滤指数和债券
                market_part, code_part = stock_code.split('.')
                is_stock = False
                
                # 根据市场前缀和数字部分共同识别股票类型
                # 只保留明确的个股代码，完全过滤指数
                if len(code_part) == 6:
                    # 上海市场个股：sh前缀，600、601、603、605、688开头
                    if market_part == 'sh' and code_part.startswith(('600', '601', '603', '605', '688')):
                        is_stock = True
                    # 深圳市场个股：sz前缀，001、002、003、300、301、302开头
                    elif market_part == 'sz' and code_part.startswith(('001', '002', '003', '300', '301', '302')):
                        is_stock = True
                    # 深圳主板000开头的个股：sz前缀，000开头
                    elif market_part == 'sz' and code_part.startswith('000'):
                        if code_part >= '000100':
                            is_stock = True
                
                if not is_stock:
                    logger.debug(f"跳过非个股: {stock_code}")
                    continue
                
                # 过滤ST股票（通过名称判断）
                stock_name = row['name']
                if 'ST' in str(stock_name) or '*ST' in str(stock_name):
                    continue
                
                # 获取股票详细数据（使用akshare）
                stock_data = self._get_stock_detail_akshare(stock_code)
                if stock_data:
                    stock_data['name'] = stock_name
                    valid_stocks.append(stock_data)
                    
                # 进度提示 - 更详细和频繁
                if (i + 1) % 50 == 0 or i < 10:  # 每50个股票显示一次，前10个也显示
                    processed_pct = (i + 1) / total * 100
                    valid_pct = len(valid_stocks) / (i + 1) * 100 if i >= 0 else 0
                    logger.info(f"进度: {i + 1}/{total} ({processed_pct:.1f}%) | 有效股票: {len(valid_stocks)} ({valid_pct:.1f}%) | 成功率: {len(valid_stocks)/(i+1)*100:.1f}%")
                
                # 增强的请求间隔控制 - 减少网络错误
                self._apply_request_interval_control(i + 1, total)
            
            logger.info(f"过滤后剩余 {len(valid_stocks)} 只有效股票")
            return valid_stocks
            
        except Exception as e:
            logger.warning(f"获取全部股票数据失败: {str(e)}")
            raise
    
    def _get_stock_detail_akshare(self, stock_code):
        """使用akshare获取单个股票的详细数据（增强版多数据源和优化重试策略）"""
        cache_key = f"akshare_{stock_code}"
        if cache_key in self.stock_cache:
            return self.stock_cache[cache_key]
        
        # 针对不同错误类型的重试策略
        error_retry_configs = {
            'dns_error': {'max_retries': 3, 'base_delay': 5, 'max_delay': 30},
            'timeout_error': {'max_retries': 2, 'base_delay': 10, 'max_delay': 60},
            'connection_error': {'max_retries': 2, 'base_delay': 3, 'max_delay': 15},
            'data_error': {'max_retries': 1, 'base_delay': 1, 'max_delay': 5}
        }
        
        retries = 0
        error_type = 'unknown'
        max_retries = 3
        base_delay = 3
        
        while retries < max_retries:
            try:
                code = stock_code.split('.')[1]
                market = stock_code.split('.')[0]
                
                # 获取K线数据
                kline_df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                              start_date=(datetime.now() - timedelta(days=35)).strftime('%Y%m%d'),
                                              end_date=datetime.now().strftime('%Y%m%d'))
                
                if kline_df is None or kline_df.empty:
                    logger.debug(f"未获取到K线数据({stock_code})")
                    return None
                
                kline_data = []
                for _, row in kline_df.iterrows():
                    kline_data.append({
                        'date': str(row['日期']),
                        'open': float(row['开盘']) if pd.notna(row['开盘']) else 0,
                        'high': float(row['最高']) if pd.notna(row['最高']) else 0,
                        'low': float(row['最低']) if pd.notna(row['最低']) else 0,
                        'close': float(row['收盘']) if pd.notna(row['收盘']) else 0,
                        'volume': float(row['成交量']) * 100 if pd.notna(row['成交量']) else 0
                    })
                
                if len(kline_data) < 20:
                    logger.debug(f"K线数据不足20天({stock_code}): {len(kline_data)}天")
                    return None
                
                # 增强基本面数据获取 - 多数据源策略
                fundamental_data = self._get_fundamental_data_multi_source(code, market)
                
                # 获取行业信息
                industry = self._get_industry_info_multi_source(code, market)
                
                concepts = self.stock_concept_map.get(stock_code, [])
                
                # 提取最新价格和涨跌幅
                latest_close = kline_data[-1]['close'] if kline_data else 0
                prev_close = kline_data[-2]['close'] if len(kline_data) >= 2 else latest_close
                
                # 计算涨跌幅
                if prev_close > 0:
                    change_pct = (latest_close - prev_close) / prev_close * 100
                else:
                    change_pct = 0
                
                stock_data = {
                    'code': stock_code,
                    'name': fundamental_data.get('name', ''),
                    'kline_data': kline_data,
                    'latest_price': latest_close,
                    'change_pct': change_pct,
                    'pe': fundamental_data.get('pe', 0),
                    'pb': fundamental_data.get('pb', 0),
                    'liquid_shares': fundamental_data.get('liquid_shares', 0),
                    'market_cap': fundamental_data.get('market_cap', 0),
                    'industry': industry,
                    'concepts': concepts,
                    'data_source': fundamental_data.get('source', 'akshare')
                }
                
                self.stock_cache[cache_key] = stock_data
                logger.debug(f"成功获取股票数据(多数据源-{stock_code}): 源={fundamental_data.get('source', 'unknown')}")
                self._update_request_stats(success=True)
                return stock_data
                
            except Exception as e:
                error_str = str(e)
                self._update_request_stats(success=False)
                
                # 智能错误分类和重试策略
                error_type, retry_config = self._classify_error(error_str, error_retry_configs)
                
                retries += 1
                if retries >= retry_config['max_retries']:
                    logger.debug(f"获取股票详细数据失败({error_type}-{stock_code}): {str(e)}")
                    return None
                
                # 计算重试延迟（指数退避）
                delay = min(retry_config['base_delay'] * (2 ** (retries - 1)), retry_config['max_delay'])
                logger.debug(f"{error_type}({stock_code})，第 {retries} 次重试，等待 {delay} 秒: {str(e)}")
                time.sleep(delay)
        
        return None
    
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
    
    def _get_fundamental_data_multi_source(self, code, market):
        """多数据源获取基本面数据（应用请求间隔控制）"""
        data_sources = [
            self._get_fundamental_data_source1,  # akshare主要方法
            self._get_fundamental_data_source2,  # akshare备用方法
            self._get_fundamental_data_source3,  # baostock方法
            self._get_fundamental_data_fallback  # 智能推算方法
        ]
        
        for i, source_func in enumerate(data_sources):
            try:
                # 在每次基本面数据源调用前应用间隔控制
                if i > 0:  # 第一个数据源不需要间隔控制，因为外部已经控制
                    self._apply_request_interval_control(1, len(data_sources))
                
                result = source_func(code, market)
                if result and self._validate_fundamental_data(result):
                    return result
            except Exception as e:
                logger.debug(f"数据源 {source_func.__name__} 失败: {str(e)}")
                continue
        
        # 所有数据源都失败，使用智能推算
        logger.debug(f"所有基本面数据源都失败，使用智能推算: {code}")
        return self._get_fundamental_data_fallback(code, market)
    
    def _get_fundamental_data_source1(self, code, market):
        """数据源1: akshare股票基础信息接口"""
        try:
            # 获取股票基础信息
            stock_info = ak.stock_info_a_code_name()
            if stock_info is not None and not stock_info.empty:
                name_row = stock_info[stock_info['code'] == code]
                if not name_row.empty:
                    stock_name = name_row.iloc[0]['name'] if 'name' in name_row.columns else ''
                else:
                    stock_name = ''
            else:
                stock_name = ''
            
            # 获取实时财务数据
            pe = 0
            pb = 0
            liquid_shares = 0
            market_cap = 0
            
            try:
                # 尝试获取PE/PB数据 - 修复列名兼容性问题
                quote_df = ak.stock_zh_a_spot_em()
                if quote_df is not None and not quote_df.empty:
                    stock_row = quote_df[quote_df['代码'] == code]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        # 修复列名：市盈率-动态，市净率，流通市值，总市值
                        pe_col = '市盈率-动态' if '市盈率-动态' in quote_df.columns else ('市盈率' if '市盈率' in quote_df.columns else None)
                        pb_col = '市净率' if '市净率' in quote_df.columns else None
                        market_cap_col = '总市值' if '总市值' in quote_df.columns else None
                        liquid_shares_col = '流通市值' if '流通市值' in quote_df.columns else None
                        
                        if pe_col:
                            pe_value = row[pe_col]
                            pe = float(pe_value) if pd.notna(pe_value) and str(pe_value) not in ['--', 'nan', ''] else 0
                        
                        if pb_col:
                            pb_value = row[pb_col]
                            pb = float(pb_value) if pd.notna(pb_value) and str(pb_value) not in ['--', 'nan', ''] else 0
                        
                        if market_cap_col:
                            market_cap_value = row[market_cap_col]
                            market_cap = float(market_cap_value) if pd.notna(market_cap_value) and str(market_cap_value) not in ['--', 'nan', ''] else 0
                        
                        if liquid_shares_col:
                            liquid_value = row[liquid_shares_col]
                            liquid_shares = float(liquid_value) if pd.notna(liquid_value) and str(liquid_value) not in ['--', 'nan', ''] else 0
                            
                        logger.debug(f"成功获取财务数据({code}): PE={pe}, PB={pb}, 市值={market_cap}")
                        
            except Exception as e:
                logger.debug(f"获取实时财务数据失败: {str(e)}")
            
            return {
                'name': stock_name,
                'pe': pe,
                'pb': pb,
                'liquid_shares': liquid_shares,
                'market_cap': market_cap,
                'source': 'akshare_main'
            }
        except Exception as e:
            logger.debug(f"数据源1失败: {str(e)}")
            return None
    
    def _get_fundamental_data_source2(self, code, market):
        """数据源2: akshare股票详情接口"""
        try:
            # 尝试获取股票详情
            stock_detail = ak.stock_individual_info_em(symbol=code)
            if stock_detail is not None and not stock_detail.empty:
                info_dict = dict(zip(stock_detail['item'], stock_detail['value']))
                
                # 从个股详情中提取数据（注意：此接口没有PE/PB数据）
                name = info_dict.get('股票简称', '')
                industry = info_dict.get('行业', '')
                
                # 提取市值数据
                total_shares = self._safe_float(info_dict.get('总股本', 0))
                liquid_shares = self._safe_float(info_dict.get('流通股', 0))
                total_market_cap = self._safe_float(info_dict.get('总市值', 0))
                liquid_market_cap = self._safe_float(info_dict.get('流通市值', 0))
                
                return {
                    'name': name,
                    'industry': industry,
                    'pe': 0,  # 此接口不提供PE数据
                    'pb': 0,  # 此接口不提供PB数据
                    'liquid_shares': liquid_market_cap,  # 使用流通市值作为流通股本的替代
                    'market_cap': total_market_cap,
                    'source': 'akshare_detail'
                }
            return None
        except Exception as e:
            logger.debug(f"数据源2失败: {str(e)}")
            return None
    
    def _get_fundamental_data_source3(self, code, market):
        """数据源3: baostock接口"""
        try:
            # 使用baostock获取基本信息
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(30)
            
            rs = self.bs.query_stock_basic(code=f"{market}.{code}")
            socket.setdefaulttimeout(original_timeout)
            
            if rs.error_code == '0':
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                if data_list:
                    # baostock返回格式: [code, name, industry, market, exchange, ...]
                    stock_data = data_list[0]
                    if len(stock_data) >= 4:
                        return {
                            'name': stock_data[1] if len(stock_data) > 1 else '',
                            'industry': stock_data[2] if len(stock_data) > 2 else '',
                            'market': stock_data[3] if len(stock_data) > 3 else '',
                            'pe': 0,  # baostock基础接口不提供PE/PB
                            'pb': 0,
                            'liquid_shares': 0,
                            'market_cap': 0,
                            'source': 'baostock_basic'
                        }
            return None
        except Exception as e:
            logger.debug(f"数据源3失败: {str(e)}")
            return None
    
    def _get_fundamental_data_fallback(self, code, market):
        """智能推算基本面数据"""
        # 基于股票代码和市场特征进行智能推算
        try:
            market_name = "上海" if market == 'sh' else "深圳"
            
            # 根据代码前缀推断股票类型和行业
            industry_map = {
                '600': '银行', '601': '银行', '603': '制造业', '688': '科创板',
                '000': '主板', '001': '主板', '002': '中小板', '300': '创业板',
                '301': '创业板', '302': '创业板'
            }
            
            # 根据代码前缀推算行业
            inferred_industry = "制造业"  # 默认行业
            for prefix, industry in industry_map.items():
                if code.startswith(prefix):
                    inferred_industry = industry
                    break
            
            # 估算PE/PB范围（基于行业平均值）
            industry_ratios = {
                '银行': {'pe': 8.0, 'pb': 0.8},
                '制造业': {'pe': 15.0, 'pb': 1.5},
                '科创板': {'pe': 25.0, 'pb': 3.0},
                '创业板': {'pe': 20.0, 'pb': 2.5},
                '主板': {'pe': 12.0, 'pb': 1.2}
            }
            
            ratios = industry_ratios.get(inferred_industry, industry_ratios['制造业'])
            
            return {
                'name': f'{market_name}股票{code}',
                'industry': inferred_industry,
                'pe': ratios['pe'],
                'pb': ratios['pb'],
                'liquid_shares': 0,  # 保持0，因为无法准确推算
                'market_cap': 0,     # 保持0，因为无法准确推算
                'source': 'intelligent_inference'
            }
        except Exception as e:
            logger.debug(f"智能推算失败: {str(e)}")
            return {
                'name': f'股票{code}',
                'industry': '',
                'pe': 15.0,  # 默认PE
                'pb': 1.5,   # 默认PB
                'liquid_shares': 0,
                'market_cap': 0,
                'source': 'default_values'
            }
    
    def _get_industry_info_multi_source(self, code, market):
        """多数据源获取行业信息"""
        try:
            # 方法1: akshare行业板块数据
            try:
                stock_board = ak.stock_board_industry_name_em()
                if stock_board is not None and not stock_board.empty:
                    # 这里可以添加更复杂的行业匹配逻辑
                    pass
            except Exception as e:
                logger.debug(f"获取行业信息失败(akshare): {str(e)}")
            
            # 方法2: 使用baostock基本信息
            try:
                original_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(20)
                rs = self.bs.query_stock_basic(code=f"{market}.{code}")
                socket.setdefaulttimeout(original_timeout)
                
                if rs.error_code == '0':
                    data_list = []
                    while (rs.error_code == '0') & rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list and len(data_list[0]) >= 3:
                        return data_list[0][2] if data_list[0][2] else ""
            except Exception as e:
                logger.debug(f"获取行业信息失败(baostock): {str(e)}")
            
            # 方法3: 智能推算
            industry_map = {
                '600': '银行', '601': '银行', '603': '制造业', '688': '科创板',
                '000': '主板', '001': '主板', '002': '中小板', '300': '创业板'
            }
            
            for prefix, industry in industry_map.items():
                if code.startswith(prefix):
                    return industry
            
            return "制造业"  # 默认行业
        except Exception as e:
            logger.debug(f"获取行业信息失败: {str(e)}")
            return ""
    
    def _safe_float(self, value):
        """安全转换为浮点数"""
        try:
            if value is None or value == '' or value == '--':
                return 0.0
            return float(str(value).replace(',', ''))
        except (ValueError, TypeError):
            return 0.0
    
    def _validate_fundamental_data(self, data):
        """验证基本面数据质量"""
        if not data:
            return False
        
        # 检查是否有基本的标识信息
        has_basic_info = bool(data.get('name')) or bool(data.get('industry'))
        
        # 检查是否有任一数值型数据
        has_numeric_data = (
            data.get('pe', 0) > 0 or 
            data.get('pb', 0) > 0 or 
            data.get('liquid_shares', 0) > 0 or
            data.get('market_cap', 0) > 0
        )
        
        return has_basic_info or has_numeric_data
    
    @timeout_retry(max_retries=5, delay=5)  # 增加重试次数和延迟
    def _get_stock_detail(self, stock_code):
        """获取单个股票的详细数据（包含历史K线、基本信息、财务指标等）"""
        cache_key = stock_code
        if cache_key in self.stock_cache:
            logger.debug(f"从缓存获取股票数据: {stock_code}")
            return self.stock_cache[cache_key]
        
        try:
            # 获取历史K线数据（最近30天）
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # 添加超时处理
            original_timeout = socket.getdefaulttimeout()
            try:
                # 增加socket超时保护并延长超时时间
                socket.setdefaulttimeout(60)
                rs = self.bs.query_history_k_data_plus(
                    stock_code,
                    "date,open,high,low,close,volume,amount,turn,peTTM",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3"  # 复权类型，3为前复权
                )
            except UnicodeDecodeError as e:
                socket.setdefaulttimeout(original_timeout)
                logger.debug(f"K线数据UTF-8解码错误({stock_code}): {str(e)}")
                time.sleep(2)  # 解码错误时短暂延迟后重试
                raise
            except Exception as e:
                socket.setdefaulttimeout(original_timeout)
                logger.debug(f"获取K线数据超时({stock_code}): {str(e)}")
                raise  # 让装饰器处理重试
            finally:
                socket.setdefaulttimeout(original_timeout)
            
            if rs.error_code != '0':
                error_msg = rs.error_msg
                logger.debug(f"获取K线数据失败({stock_code}): {error_msg}")
                # 如果是网络相关错误或用户未登录，抛出异常触发重试
                if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or '用户未登录' in error_msg:
                    raise ConnectionError(f"获取K线数据网络错误: {error_msg}")
                return None
            
            kline_data = []
            try:
                while (rs.error_code == '0') & rs.next():
                    row_data = rs.get_row_data()
                    if row_data:
                        kline_data.append(row_data)
            except Exception as e:
                error_msg = str(e)
                logger.debug(f"解析K线数据失败({stock_code}): {error_msg}")
                # 如果是网络相关错误，抛出异常触发重试
                if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or 'timed out' in error_msg:
                    raise ConnectionError(f"解析K线数据网络错误: {error_msg}")
                return None
            
            if not kline_data:
                logger.warning(f"未获取到K线数据({stock_code})")
                return None
            
            # 获取股票基本信息
            original_timeout = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(60)
                rs_basic = self.bs.query_stock_basic(code=stock_code)
            except UnicodeDecodeError as e:
                socket.setdefaulttimeout(original_timeout)
                logger.debug(f"基本信息UTF-8解码错误({stock_code}): {str(e)}")
                time.sleep(2)
                raise
            except Exception as e:
                socket.setdefaulttimeout(original_timeout)
                logger.warning(f"获取股票基本信息超时({stock_code}): {str(e)}")
                raise
            finally:
                socket.setdefaulttimeout(original_timeout)
            
            if rs_basic.error_code != '0':
                error_msg = rs_basic.error_msg
                logger.warning(f"获取股票基本信息失败({stock_code}): {error_msg}")
                # 如果是网络相关错误或用户未登录，抛出异常触发重试
                if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or '用户未登录' in error_msg:
                    raise ConnectionError(f"获取股票基本信息网络错误: {error_msg}")
                return None
            
            basic_data = []
            try:
                while (rs_basic.error_code == '0') & rs_basic.next():
                    row_data = rs_basic.get_row_data()
                    if row_data:
                        basic_data.append(row_data)
            except Exception as e:
                error_msg = str(e)
                logger.debug(f"解析基本信息失败({stock_code}): {error_msg}")
                # 如果是网络相关错误，抛出异常触发重试
                if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or 'timed out' in error_msg:
                    raise ConnectionError(f"解析基本信息网络错误: {error_msg}")
                return None
            
            if not basic_data:
                logger.warning(f"未获取到基本信息({stock_code})")
                return None
            
            # 构建股票数据结构
            df_basic = pd.DataFrame(basic_data, columns=rs_basic.fields)
            df_kline = pd.DataFrame(kline_data, columns=rs.fields)
            
            # 获取最新PE值（从K线数据中）
            pe = None
            if not df_kline.empty and 'peTTM' in df_kline.columns:
                latest_pe = df_kline.iloc[-1]['peTTM']
                pe = float(latest_pe) if latest_pe and isinstance(latest_pe, str) and latest_pe.strip() != '' else None
            
            # 获取PB和行业数据（使用get_stock_industry接口）
            pb = None
            industry = None
            original_timeout = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(60)
                rs_industry = self.bs.query_stock_industry(code=stock_code)
            except UnicodeDecodeError as e:
                socket.setdefaulttimeout(original_timeout)
                logger.debug(f"行业数据UTF-8解码错误({stock_code}): {str(e)}")
                time.sleep(2)
                raise
            except Exception as e:
                socket.setdefaulttimeout(original_timeout)
                logger.warning(f"获取行业数据超时({stock_code}): {str(e)}")
                raise
            finally:
                socket.setdefaulttimeout(original_timeout)
                
            if rs_industry.error_code == '0':
                industry_data = []
                try:
                    while rs_industry.next():
                        row_data = rs_industry.get_row_data()
                        if row_data:
                            industry_data.append(row_data)
                    # 添加调试信息，查看行业数据的实际格式
                    if industry_data:
                        logger.debug(f"行业数据原始格式({stock_code}): {industry_data}")
                except Exception as e:
                    error_msg = str(e)
                    logger.debug(f"读取行业数据行失败({stock_code}): {error_msg}")
                    # 如果是网络相关错误，抛出异常触发重试
                    if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or 'timed out' in error_msg:
                        raise ConnectionError(f"读取行业数据网络错误: {error_msg}")
                    industry_data = []
                    
                if industry_data:
                    try:
                        # 获取字段名
                        fields = rs_industry.fields
                        logger.debug(f"行业数据字段名({stock_code}): {fields}")
                        
                        # 使用正确的字段名创建DataFrame
                        df_industry = pd.DataFrame(industry_data, columns=fields)
                        
                        # 安全地获取数据，避免列名错误
                        if not df_industry.empty:
                            # 首先尝试使用字段名获取数据（更可靠）
                            pe = None
                            pb = None
                            industry = None
                            
                            # 尝试通过字段名获取行业数据
                            if 'industry' in df_industry.columns:
                                industry_val = df_industry.iloc[0]['industry']
                                if industry_val and isinstance(industry_val, str) and industry_val.strip() != '':
                                    industry = industry_val
                            elif 'industryName' in df_industry.columns:
                                industry_val = df_industry.iloc[0]['industryName']
                                if industry_val and isinstance(industry_val, str) and industry_val.strip() != '':
                                    industry = industry_val
                            
                            # 尝试通过字段名获取PE
                            if 'pe' in df_industry.columns:
                                pe_val = df_industry.iloc[0]['pe']
                                if pe_val and isinstance(pe_val, str) and pe_val.strip() != '':
                                    try:
                                        pe = float(pe_val)
                                    except (ValueError, TypeError):
                                        pass
                            elif 'peTTM' in df_industry.columns:
                                pe_val = df_industry.iloc[0]['peTTM']
                                if pe_val and isinstance(pe_val, str) and pe_val.strip() != '':
                                    try:
                                        pe = float(pe_val)
                                    except (ValueError, TypeError):
                                        pass
                            
                            # 尝试通过字段名获取PB
                            if 'pb' in df_industry.columns:
                                pb_val = df_industry.iloc[0]['pb']
                                if pb_val and isinstance(pb_val, str) and pb_val.strip() != '':
                                    try:
                                        pb = float(pb_val)
                                    except (ValueError, TypeError):
                                        pass
                            
                            # 如果通过字段名没有获取到数据，使用旧的动态查找方法作为备选
                            if not industry or not pe or not pb:
                                # 遍历所有单元格，寻找行业名称和PE/PB值
                                numeric_values = []
                                non_numeric_strings = []
                                
                                # 遍历第一行的所有单元格
                                row = df_industry.iloc[0]
                                for idx, cell_value in enumerate(row):
                                    if cell_value and isinstance(cell_value, str) and cell_value.strip() != '':
                                        # 尝试转换为浮点数
                                        try:
                                            float_val = float(cell_value)
                                            numeric_values.append(float_val)
                                        except (ValueError, TypeError):
                                            # 不是数值，可能是行业名称
                                            non_numeric_strings.append(cell_value)
                                
                                # 从非数值字符串中选择一个作为行业名称（通常是第一个非空的）
                                if not industry and non_numeric_strings:
                                    # 选择第一个较长的非数值字符串作为行业名称
                                    industry = max(non_numeric_strings, key=len)
                                
                                # 从数值列表中获取PE和PB
                                if not pe and numeric_values:
                                    pe = numeric_values[0]
                                if not pb and len(numeric_values) >= 2:
                                    pb = numeric_values[1]
                    except Exception as e:
                        error_msg = str(e)
                        logger.warning(f"解析行业数据失败({stock_code}): {error_msg}")
                        # 如果是网络相关错误，抛出异常触发重试
                        if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or 'timed out' in error_msg:
                            raise ConnectionError(f"解析行业数据网络错误: {error_msg}")
            else:
                error_msg = rs_industry.error_msg
                logger.warning(f"获取PE/PB/行业数据失败({stock_code}): {error_msg}")
                # 如果是网络相关错误或用户未登录，抛出异常触发重试
                if '网络' in error_msg or '超时' in error_msg or '连接' in error_msg or '接收' in error_msg or '用户未登录' in error_msg:
                    raise ConnectionError(f"获取PE/PB/行业数据网络错误: {error_msg}")
            
            # 确保code_name字段存在
            code_name = "未知"
            if 'code_name' in df_basic.columns:
                code_name = df_basic.iloc[0]['code_name']
                if not code_name or not isinstance(code_name, str):
                    code_name = "未知"
            
            stock_data = {
                'code': stock_code,
                'name': code_name,
                'exchange': 'sh' if stock_code.startswith('sh.') else 'sz',
                'type': self._get_stock_type(stock_code),
                'pe': pe,
                'pb': pb,
                'industry': industry,
                'concept': self._get_stock_concept(stock_code),
                'total_shares': None,
                'liquid_shares': None,
                'kline_data': df_kline.to_dict('records'),
                'latest_price': None,
                'latest_volume': None,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 安全地转换数值字段
            try:
                if 'totalShares' in df_basic.columns:
                    ts_value = df_basic.iloc[0]['totalShares']
                    stock_data['total_shares'] = float(ts_value) if ts_value and isinstance(ts_value, str) and ts_value.strip() != '' else None
            except Exception as e:
                logger.warning(f"转换总股数失败({stock_code}): {str(e)}")
            
            try:
                if 'liquidShares' in df_basic.columns:
                    ls_value = df_basic.iloc[0]['liquidShares']
                    stock_data['liquid_shares'] = float(ls_value) if ls_value and isinstance(ls_value, str) and ls_value.strip() != '' else None
            except Exception as e:
                logger.warning(f"转换流通股数失败({stock_code}): {str(e)}")
            
            try:
                if not df_kline.empty:
                    # 获取最新价格和成交量
                    close_value = df_kline.iloc[-1]['close']
                    volume_value = df_kline.iloc[-1]['volume']
                    stock_data['latest_price'] = float(close_value) if close_value and isinstance(close_value, str) and close_value.strip() != '' else None
                    stock_data['latest_volume'] = float(volume_value) if volume_value and isinstance(volume_value, str) and volume_value.strip() != '' else None
                    
                    # 计算涨幅（最近一天的收盘价与前一天的收盘价比较）
                    if len(df_kline) >= 2:
                        prev_close_value = df_kline.iloc[-2]['close']
                        if prev_close_value and isinstance(prev_close_value, str) and prev_close_value.strip() != '' and prev_close_value != '0':
                            prev_close = float(prev_close_value)
                            curr_close = float(close_value)
                            change_pct = ((curr_close - prev_close) / prev_close) * 100
                            stock_data['change_pct'] = change_pct
            except Exception as e:
                logger.warning(f"转换K线数据或计算涨幅失败({stock_code}): {str(e)}")
            
            # 缓存数据
            self.stock_cache[cache_key] = stock_data
            
            logger.debug(f"成功获取股票数据: {stock_code} - {code_name}")
            return stock_data
            
        except Exception as e:
            logger.debug(f"获取股票详细数据失败({stock_code}): {str(e)}")
            return None
    
    def _get_stock_type(self, stock_code):
        """获取股票类型（主板、科创板、创业板）
        
        仅基于数字代码识别股票类型，忽略市场前缀(sh./sz.)
        - 600/601/603/605开头：沪市主板(sh_main)
        - 688开头：科创板(sh_kcb)
        - 000开头：深市主板(sz_main)
        - 002开头：中小板(sz_sme)
        - 300开头：创业板(sz_cyb)
        """
        if '.' not in stock_code:
            return 'unknown'
            
        # 提取数字代码部分，忽略市场前缀
        code_part = stock_code.split('.')[1]
        
        if code_part.startswith(('600', '601', '603', '605')):
            return 'sh_main'  # 沪市主板
        elif code_part.startswith('688'):
            return 'sh_kcb'  # 科创板
        elif code_part.startswith('000'):
            return 'sz_main'  # 深市主板
        elif code_part.startswith('002'):
            return 'sz_sme'  # 中小板
        elif code_part.startswith('300'):
            return 'sz_cyb'  # 创业板
        else:
            return 'unknown'

    def _get_stock_concept(self, stock_code):
        """获取股票所属概念/题材板块
        
        Args:
            stock_code: 股票代码，如 sh.600000
            
        Returns:
            str: 概念板块名称，失败返回None
        """
        try:
            if stock_code in self.stock_concept_map:
                concepts = self.stock_concept_map[stock_code]
                if concepts:
                    concept_str = ",".join(concepts[:3])
                    logger.debug(f"股票 {stock_code} 概念板块: {concept_str}")
                    return concept_str
            return None
        except Exception as e:
            logger.debug(f"获取股票概念失败({stock_code}): {str(e)}")
            return None
    
    def close(self):
        """关闭连接"""
        try:
            self.bs.logout()
            logger.info("baostock连接已关闭")
        except Exception as e:
            logger.debug(f"关闭baostock连接失败: {str(e)}")


if __name__ == "__main__":
    # 测试数据采集功能
    try:
        collector = StockDataCollector()
        stocks = collector.get_all_stocks()
        logger.info(f"测试完成，共获取到 {len(stocks)} 只有效股票")
        if stocks:
            logger.info(f"示例股票: {stocks[0]['code']} - {stocks[0]['name']}")
    finally:
        collector.close()