#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化版股票数据采集模块

特点：
1. 基于原版本优化，保持数据结构兼容性
2. 改进错误处理，提高成功率
3. 严格数据校验：不使用模拟数据和默认值，数据缺失时保留None并放弃无效股票
4. 优化请求间隔和重试策略
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

logger = setup_logger('data_collector_optimized', logging.INFO)

class OptimizedStockDataCollector:
    """优化版股票数据采集器"""
    
    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        self.stock_cache = {}
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0
        self.last_request_time = 0
        # 行业映射表（v2.1新增）：code -> industry_name，懒加载
        self._industry_map = None
        self._industry_map_loading = False

        os.makedirs(self.cache_dir, exist_ok=True)

        # 全局网络超时：防止任何未显式设置 timeout 的请求永久挂起
        socket.setdefaulttimeout(30)
        # 单股采集硬超时（秒）：超过即放弃该股，继续下一只
        self.per_stock_timeout = 90

    def _build_industry_map(self):
        """构建"6位代码->行业"映射表（v2.1新增，v2.6 多级回退）

        数据源顺序：东财板块 → baostock 证监会行业（批量一次）→ 申万二级 → 新浪
        缓存 cache/industry_map.json 按日；当日构建失败时沿用最近缓存
        （行业归属极少变动，过期缓存仍远好于空值）。
        """
        import json
        import glob
        cache_file = os.path.join(self.cache_dir, 'industry_map.json')
        today = datetime.now().strftime('%Y-%m-%d')

        # 1. 优先读当日缓存
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                if cached.get('date') == today and cached.get('map'):
                    logger.info(f"行业映射表加载自缓存（{cached.get('src', '?')}源，"
                                f"{len(cached['map'])}只）")
                    return cached['map']
            except Exception as e:
                logger.debug(f"行业映射缓存读取失败: {e}")

        # 2. 依次尝试各数据源；取覆盖足够广的第一个
        industry_map, src = {}, '-'
        for builder, src_name, need in (
            (lambda: self._build_industry_map_em()[0], 'em', 4000),
            (self._build_industry_map_baostock, 'baostock', 4000),
            (self._build_industry_map_sw, 'sw', 4000),
            (self._build_industry_map_sina, 'sina', 1000),
        ):
            try:
                candidate = builder()
            except Exception:
                logger.exception(f"{src_name} 行业映射构建异常")
                candidate = {}
            if len(candidate) >= need:
                industry_map, src = candidate, src_name
                break
            if len(candidate) > len(industry_map):
                industry_map, src = candidate, src_name
            logger.warning(f"{src_name} 行业映射覆盖 {len(candidate)} 只"
                           f"（阈值 {need}），尝试下一数据源")

        # 3. 全部失败/覆盖不足：沿用最近缓存（行业归属极少变动）
        if not industry_map:
            stale = self._load_latest_industry_cache()
            if stale:
                logger.warning(f"行业数据源均不可用，沿用 {stale[1]} 的缓存"
                               f"（{stale[2]}源，{len(stale[0])}只）")
                return stale[0]
            logger.error("行业映射表构建失败：全部数据源不可用且无历史缓存")
            return {}

        # 4. 写缓存（同时备份一份带日期的副本供过期回退）
        try:
            payload = {'date': today, 'src': src, 'map': industry_map}
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            hist = os.path.join(self.cache_dir, f'industry_map_{today}.json')
            with open(hist, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            for old in glob.glob(os.path.join(self.cache_dir, 'industry_map_2*.json'))[:-10]:
                try:
                    os.remove(old)
                except OSError:
                    pass
            logger.info(f"行业映射表已缓存（{src}源，{len(industry_map)}只）")
        except Exception as e:
            logger.debug(f"行业映射缓存写入失败: {e}")

        return industry_map

    def _load_latest_industry_cache(self):
        """读取最近一份行业缓存（不限日期），返回 (map, date, src)"""
        import json
        import glob
        candidates = sorted(glob.glob(os.path.join(
            self.cache_dir, 'industry_map_2*.json')), reverse=True)
        if os.path.exists(os.path.join(self.cache_dir, 'industry_map.json')):
            candidates.insert(0, os.path.join(self.cache_dir, 'industry_map.json'))
        for path in candidates:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                if cached.get('map'):
                    return cached['map'], cached.get('date', '?'), cached.get('src', '?')
            except Exception:
                continue
        return None

    def _build_industry_map_baostock(self):
        """baostock 证监会行业分类：一次查询返回全 A（约5500只，4-5秒）。

        机房登录较慢且偶发网络错误，最多重试 4 轮。
        """
        import re
        logger.info("开始构建行业映射表（baostock 证监会行业，回退源1）...")
        try:
            import baostock as bs
        except ImportError:
            logger.warning("未安装 baostock，跳过该源")
            return {}

        logged_in = False
        # 注意：采集器全局 socket 超时 30s，而 baostock 首次登录可能需要 2-3 分钟，
        # 登录期间必须临时放开超时，否则必然"网络接收错误"
        import socket as _socket
        _old_timeout = _socket.getdefaulttimeout()
        try:
            _socket.setdefaulttimeout(None)
            for attempt in range(4):
                try:
                    lg = bs.login()
                    if lg.error_code == '0':
                        logged_in = True
                        break
                    logger.warning(f"baostock 登录失败（第{attempt+1}次）: {lg.error_msg}")
                except Exception as e:
                    logger.warning(f"baostock 登录异常（第{attempt+1}次）: {e}")
                time.sleep(5.0)
        finally:
            _socket.setdefaulttimeout(_old_timeout)
        if not logged_in:
            logger.warning("baostock 多次登录失败，放弃该源")
            return {}

        industry_map = {}
        try:
            rs = bs.query_stock_industry()
            if rs.error_code != '0':
                logger.warning(f"baostock 行业查询失败: {rs.error_msg}")
                return {}
            while rs.next():
                row = rs.get_row_data()
                # 字段: updateDate, code(sh.600000), code_name, industry, classification
                code = row[1]
                industry = (row[3] or '').strip()
                if not industry:
                    continue
                digits = ''.join(ch for ch in code if ch.isdigit())
                if len(digits) != 6:
                    continue
                # 去掉证监会门类代码前缀，如 "J66货币金融服务" -> "货币金融服务"
                industry = re.sub(r'^[A-Z]\d+', '', industry)
                industry_map[digits] = industry
            logger.info(f"baostock 行业映射构建完成: {len(industry_map)} 只股票")
        except Exception as e:
            logger.error(f"baostock 行业映射构建失败: {e}")
        finally:
            try:
                bs.logout()
            except Exception:
                pass
        return industry_map

    def _build_industry_map_em(self):
        """东财行业板块成分股反向映射，返回 (map, 'em')；异常时返回 ({}, 'em')"""
        logger.info("开始构建行业映射表（东财板块成分股反向映射）...")
        industry_map = {}
        try:
            board_df = ak.stock_board_industry_name_em()
            if board_df is None or board_df.empty:
                logger.warning("东财行业板块列表为空")
                return {}, 'em'
            board_names = board_df['板块名称'].tolist()
            logger.info(f"共 {len(board_names)} 个行业板块，开始遍历成分股...")

            success_count = 0
            for i, board_name in enumerate(board_names):
                try:
                    cons_df = ak.stock_board_industry_cons_em(symbol=board_name)
                    if cons_df is None or cons_df.empty:
                        continue
                    code_col = '代码' if '代码' in cons_df.columns else cons_df.columns[1]
                    for code in cons_df[code_col].astype(str):
                        if len(code) == 6:
                            industry_map[code] = board_name
                    success_count += 1
                    if (i + 1) % 50 == 0:
                        logger.info(f"行业映射构建进度: {i + 1}/{len(board_names)} 板块, "
                                   f"累计 {len(industry_map)} 只股票")
                    # 板块间小延迟避免限流
                    time.sleep(0.1)
                except Exception as e:
                    logger.debug(f"板块 {board_name} 成分股获取失败: {e}")
                    # 前3个板块就连续失败，基本是被限流/封 IP，提前放弃整源
                    if success_count == 0 and i >= 2:
                        logger.warning("东财板块成分股连续失败，提前终止东财源")
                        return {}, 'em'
                    continue

            logger.info(f"东财行业映射构建完成: {success_count}/{len(board_names)} 板块, "
                       f"{len(industry_map)} 只股票")
        except Exception as e:
            logger.error(f"东财行业映射表构建失败: {e}")
            return {}, 'em'

        return industry_map, 'em'

    def _build_industry_map_sw(self):
        """申万二级行业成分反向映射（乐咕乐股，131个行业，全A含创业板/科创板）

        乐咕乐股对高频请求会返回反爬页（read_html 报 NoneType.find_all），
        因此逐板块容错、失败退避，连续失败过多时提前终止保留已有部分。
        """
        logger.info("开始构建行业映射表（申万二级行业成分，回退源1）...")
        industry_map = {}

        # 行业列表本身也要重试（可能命中反爬页）
        board_df = None
        for attempt in range(3):
            try:
                board_df = ak.sw_index_second_info()
                if board_df is not None and not board_df.empty:
                    break
            except Exception as e:
                logger.warning(f"申万二级行业列表获取失败（第{attempt+1}次）: {e}")
            time.sleep(3.0)
        if board_df is None or board_df.empty:
            logger.warning("申万二级行业列表获取失败，放弃申万源")
            return {}

        boards = list(zip(board_df['行业代码'], board_df['行业名称']))
        logger.info(f"申万二级共 {len(boards)} 个行业，开始遍历成分股...")

        success_count = 0
        consec_fail = 0
        for i, (sw_code, board_name) in enumerate(boards):
            cons_df = None
            for attempt in range(3):
                try:
                    cons_df = ak.sw_index_third_cons(symbol=sw_code)
                    break
                except Exception:
                    time.sleep(2.0 + attempt * 2.0)  # 2s/4s/6s 退避
            if cons_df is None or cons_df.empty:
                consec_fail += 1
                logger.debug(f"申万行业 {board_name} 成分股获取失败（连续{consec_fail}）")
                if consec_fail >= 10:
                    logger.warning("申万源连续10个行业失败（疑似反爬限制），提前终止")
                    break
                continue
            consec_fail = 0
            for raw in cons_df['股票代码'].astype(str):
                digits = ''.join(ch for ch in raw if ch.isdigit())
                if len(digits) == 6:
                    industry_map[digits] = board_name
            success_count += 1
            if (i + 1) % 20 == 0:
                logger.info(f"申万行业映射进度: {i + 1}/{len(boards)} 行业, "
                           f"累计 {len(industry_map)} 只股票")
            time.sleep(1.0)  # 乐咕乐股节流（高频会触发反爬页）

        logger.info(f"申万二级行业映射构建完成: {success_count}/{len(boards)} 行业, "
                   f"{len(industry_map)} 只股票")
        return industry_map

    def _build_industry_map_sina(self):
        """新浪行业板块成分股反向映射（49个行业，机房可用回退源）"""
        logger.info("开始构建行业映射表（新浪行业板块回退源）...")
        industry_map = {}
        try:
            board_df = ak.stock_sector_spot(indicator='新浪行业')
            if board_df is None or board_df.empty:
                logger.warning("新浪行业板块列表为空")
                return {}
            boards = list(zip(board_df['label'], board_df['板块']))
            logger.info(f"新浪共 {len(boards)} 个行业板块，开始遍历成分股...")

            success_count = 0
            for i, (label, board_name) in enumerate(boards):
                try:
                    cons_df = ak.stock_sector_detail(sector=label)
                    if cons_df is None or cons_df.empty:
                        continue
                    for code in cons_df['code'].astype(str):
                        if len(code) == 6:
                            industry_map[code] = board_name
                    success_count += 1
                    if (i + 1) % 10 == 0:
                        logger.info(f"新浪行业映射进度: {i + 1}/{len(boards)} 板块, "
                                   f"累计 {len(industry_map)} 只股票")
                    time.sleep(0.3)  # 新浪节流
                except Exception as e:
                    logger.debug(f"新浪板块 {board_name} 成分股获取失败: {e}")
                    time.sleep(0.5)
                    continue

            logger.info(f"新浪行业映射构建完成: {success_count}/{len(boards)} 板块, "
                       f"{len(industry_map)} 只股票")
        except Exception as e:
            logger.error(f"新浪行业映射表构建失败: {e}")
            return {}

        return industry_map

    def _get_industry_from_map(self, code):
        """从映射表查询行业（懒加载）"""
        if self._industry_map is None:
            if self._industry_map_loading:
                return None  # 避免递归构建
            self._industry_map_loading = True
            try:
                self._industry_map = self._build_industry_map()
            finally:
                self._industry_map_loading = False
        # code 格式为 "sh.600000"，取6位数字
        digits = ''.join(ch for ch in code if ch.isdigit())
        if len(digits) == 6:
            return self._industry_map.get(digits)
        return None
        
    def _get_dynamic_interval(self):
        """根据请求次数动态调整间隔时间
        
        Args:
            request_count: 请求次数
            
        Returns:
            float: 间隔时间（秒）
        """
        if self.request_count < 500:
            return 0.3  # 0-500：最快
        elif self.request_count < 1500:
            return 0.8  # 600-1500：中等
        elif self.request_count < 3000:
            return 1.0  # 1500-3000：稍慢
        else:
            return 1.2  # 3000后：稳定

    def _wait_for_rate_limit(self):
        """速率限制（优化版）"""
        current_time = time.time()
        interval = self._get_dynamic_interval()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < interval:
            sleep_time = interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1  # 记录请求次数，用于动态间隔与统计
        self.request_count += 1  # 统计请求次数（用于动态间隔调整）
    
    def get_all_stocks(self, limit=None):
        """获取全部A股市场股票数据（优化版）"""
        valid_stocks = []
        
        try:
            logger.info("开始获取全部A股股票数据...")
            
            # 使用akshare获取股票列表（更稳定）
            use_akshare = True
            
            if use_akshare:
                max_retries = 3
                retry_count = 0
                success = False
                
                while retry_count < max_retries and not success:
                    try:
                        logger.info(f"使用akshare获取股票列表 (尝试 {retry_count + 1}/{max_retries})...")
                        stock_df = ak.stock_zh_a_spot_em()
                        
                        if stock_df is not None and not stock_df.empty:
                            df = pd.DataFrame(stock_df)
                            
                            # 转换akshare格式到标准格式
                            code_col = '代码' if '代码' in df.columns else 'symbol'
                            name_col = '名称' if '名称' in df.columns else 'name'
                            
                            normalized_data = []
                            for _, row in df.iterrows():
                                raw_code = str(row[code_col])
                                if len(raw_code) == 6:
                                    # 判断板块类型
                                    if raw_code.startswith(('688', '689')):
                                        # 科创板
                                        market_segment = '科创板'
                                        normalized_code = f"sh.{raw_code}"
                                    elif raw_code.startswith('6'):
                                        # 沪市主板（600/601/603/605等）
                                        market_segment = '沪市主板'
                                        normalized_code = f"sh.{raw_code}"
                                    elif raw_code.startswith(('000', '001', '002', '003')):
                                        # 深市主板（含原中小板002/003）
                                        market_segment = '深市主板'
                                        normalized_code = f"sz.{raw_code}"
                                    elif raw_code.startswith(('300', '301')):
                                        # 创业板
                                        market_segment = '创业板'
                                        normalized_code = f"sz.{raw_code}"
                                    else:
                                        # 跳过北交所等其他板块
                                        continue
                                    
                                    normalized_data.append({
                                        'code': normalized_code,
                                        'name': row[name_col],
                                        'market_segment': market_segment  # 添加板块分类
                                    })
                            
                            df = pd.DataFrame(normalized_data)
                            logger.info(f"通过akshare获取到 {len(df)} 只股票")
                            success = True
                        else:
                            logger.error("akshare获取股票列表失败: 数据为空")
                            retry_count += 1
                            time.sleep(2)
                    except Exception as e:
                        logger.error(f"akshare获取股票列表失败: {str(e)}")
                        retry_count += 1
                        time.sleep(2)
                
                if not success:
                    logger.error(f"akshare(东财)获取失败: 尝试 {max_retries} 次后仍然失败，切换至新浪源股票列表")
                    # 回退源1：新浪 stock_zh_a_spot（含代码+名称+实时行情，代码格式如 sh600000）
                    try:
                        df_spot = ak.stock_zh_a_spot()
                        if df_spot is not None and not df_spot.empty:
                            normalized_data = []
                            code_col = '代码' if '代码' in df_spot.columns else 'code'
                            name_col = '名称' if '名称' in df_spot.columns else 'name'
                            for _, row in df_spot.iterrows():
                                raw_code = str(row.get(code_col, ''))
                                # 新浪格式可能为 sh600000 / sz000001 / bj920000，提取6位数字代码
                                digits = ''.join(ch for ch in raw_code if ch.isdigit())
                                if len(digits) != 6:
                                    continue
                                if digits.startswith(('688', '689')):
                                    market_segment = '科创板'
                                    normalized_code = f"sh.{digits}"
                                elif digits.startswith('6'):
                                    market_segment = '沪市主板'
                                    normalized_code = f"sh.{digits}"
                                elif digits.startswith(('000', '001', '002', '003')):
                                    market_segment = '深市主板'
                                    normalized_code = f"sz.{digits}"
                                elif digits.startswith(('300', '301')):
                                    market_segment = '创业板'
                                    normalized_code = f"sz.{digits}"
                                else:
                                    continue  # 跳过北交所等
                                normalized_data.append({
                                    'code': normalized_code,
                                    'name': row.get(name_col, ''),
                                    'market_segment': market_segment
                                })
                            df = pd.DataFrame(normalized_data)
                            logger.info(f"通过新浪行情源获取到 {len(df)} 只股票")
                            success = True
                    except Exception as e:
                        logger.error(f"新浪行情源股票列表获取失败: {str(e)}")

                if not success:
                    # 回退源2：stock_info_a_code_name（仅代码+名称）
                    try:
                        df_list = ak.stock_info_a_code_name()
                        if df_list is not None and not df_list.empty:
                            normalized_data = []
                            for _, row in df_list.iterrows():
                                raw_code = str(row.get('code', ''))
                                if len(raw_code) != 6:
                                    continue
                                if raw_code.startswith(('688', '689')):
                                    market_segment = '科创板'
                                    normalized_code = f"sh.{raw_code}"
                                elif raw_code.startswith('6'):
                                    market_segment = '沪市主板'
                                    normalized_code = f"sh.{raw_code}"
                                elif raw_code.startswith(('000', '001', '002', '003')):
                                    market_segment = '深市主板'
                                    normalized_code = f"sz.{raw_code}"
                                elif raw_code.startswith(('300', '301')):
                                    market_segment = '创业板'
                                    normalized_code = f"sz.{raw_code}"
                                else:
                                    continue
                                normalized_data.append({
                                    'code': normalized_code,
                                    'name': row.get('name', ''),
                                    'market_segment': market_segment
                                })
                            df = pd.DataFrame(normalized_data)
                            logger.info(f"通过 stock_info_a_code_name 获取到 {len(df)} 只股票")
                            success = True
                    except Exception as e:
                        logger.error(f"stock_info_a_code_name 获取失败: {str(e)}")

                if not success:
                    logger.error("所有在线股票列表源均失败，尝试从本地股票列表文件读取...")
                    
                    # 尝试从本地文件读取股票列表
                    local_stock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_stock_list.csv')
                    if os.path.exists(local_stock_file):
                        try:
                            df = pd.read_csv(local_stock_file)
                            logger.info(f"从本地文件获取到 {len(df)} 只股票")
                            success = True
                        except Exception as e:
                            logger.error(f"读取本地股票列表失败: {str(e)}")
                            return valid_stocks
                    else:
                        logger.error("本地股票列表文件不存在")
                        return valid_stocks
            
            # 过滤股票（去除ST股票和非A股）
            total = len(df)
            if limit:
                df = df.head(limit)
            
            logger.info(f"开始处理 {len(df)} 只股票...")

            # v2.1：预先构建行业映射表（批量调用，避免单股懒加载阻塞）
            if self._industry_map is None:
                logger.info("预构建行业映射表（批量调用东财板块成分股，约1-2分钟）...")
                self._industry_map = self._build_industry_map()
                logger.info(f"行业映射表就绪：覆盖 {len(self._industry_map)} 只股票")

            for i, row in df.iterrows():
                stock_code = row['code']
                stock_name = row['name']
                market_segment = row.get('market_segment', '未知')
                
                # 进度提示
                if (i + 1) % 100 == 0 or i < 20:
                    progress_pct = (i + 1) / len(df) * 100
                    logger.info(f"处理进度: {i + 1}/{len(df)} ({progress_pct:.1f}%) | 有效股票: {len(valid_stocks)} | 当前: {stock_code}")
                
                # 过滤ST股票
                if 'ST' in str(stock_name) or '*ST' in str(stock_name):
                    continue
                
                try:
                    self._wait_for_rate_limit()

                    # 获取股票详细数据（独立守护线程+硬超时，网络挂起不阻塞全量运行）
                    result_box = {}
                    def _fetch():
                        try:
                            result_box['data'] = self._get_stock_detail_optimized(stock_code)
                        except Exception as ex:
                            result_box['error'] = ex
                    t = threading.Thread(target=_fetch, daemon=True)
                    t.start()
                    t.join(timeout=self.per_stock_timeout)

                    if t.is_alive():
                        logger.warning(f"获取股票数据超时({stock_code})，跳过")
                        self.error_count += 1
                        continue
                    if 'error' in result_box:
                        logger.warning(f"获取股票数据失败({stock_code}): {str(result_box['error'])}")
                        self.error_count += 1
                        continue
                    stock_data = result_box.get('data')
                    if stock_data:
                        stock_data['name'] = stock_name
                        stock_data['market_segment'] = market_segment  # 添加板块信息
                        valid_stocks.append(stock_data)
                        self.success_count += 1
                    else:
                        self.error_count += 1
                except Exception as e:
                    logger.warning(f"处理股票时发生异常({stock_code}): {str(e)}")
                    self.error_count += 1
                    continue
            
            logger.info(f"数据采集完成: {len(valid_stocks)}/{len(df)} 只有效股票")
            total_processed = self.success_count + self.error_count
            if total_processed > 0:
                logger.info(f"成功率: {self.success_count / total_processed * 100:.1f}%")

            return valid_stocks
            
        except Exception as e:
            logger.error(f"获取股票数据失败: {str(e)}")
            return valid_stocks
    
    def _get_stock_detail_optimized(self, stock_code):
        """优化版股票详细数据获取（严格校验，不使用模拟数据和默认值）

        规则：
        1. 基本面字段缺失或解析失败时保留None，由分析模块的数据完整性检查处理
        2. K线数据为空、不足20个交易日或包含无效价格时，放弃该股票（返回None）
        3. 异常值过滤：换手率有效范围0%-50%，涨跌幅绝对值>50%视为异常
        """
        try:
            cache_key = f"optimized_{stock_code}"
            if cache_key in self.stock_cache:
                return self.stock_cache[cache_key]

            code = stock_code.split('.')[1]

            # 1. 获取基本面数据（缺失/解析失败时保留None，不使用默认值）
            pe_ratio = None
            pb_ratio = None
            market_cap = None
            liquid_shares = None
            industry = None
            turnover_rate = None

            # v2.1：优先从行业映射表取（496次批量构建，比单股快10倍）
            industry = self._get_industry_from_map(stock_code)

            try:
                basic_info = ak.stock_individual_info_em(symbol=code)
                if basic_info is not None and not basic_info.empty:
                    for _, row in basic_info.iterrows():
                        item = str(row.get('item', ''))
                        value = str(row.get('value', ''))

                        if value in ('--', 'nan', 'None', ''):
                            continue

                        if pe_ratio is None and '市盈率' in item:
                            try:
                                pe_ratio = float(value)
                            except ValueError:
                                pe_ratio = None
                        elif pb_ratio is None and '市净率' in item:
                            try:
                                pb_ratio = float(value)
                            except ValueError:
                                pb_ratio = None
                        elif market_cap is None and '总市值' in item:
                            try:
                                if '万' in value:
                                    market_cap = float(value.replace('万', '')) * 10000
                                elif '亿' in value:
                                    market_cap = float(value.replace('亿', '')) * 100000000
                                else:
                                    market_cap = float(value)
                            except ValueError:
                                market_cap = None
                        elif liquid_shares is None and ('流通股' in item or ('流通' in item and '股本' in item)):
                            try:
                                if '万' in value:
                                    liquid_shares = float(value.replace('万', '')) * 10000
                                elif '亿' in value:
                                    liquid_shares = float(value.replace('亿', '')) * 100000000
                                else:
                                    liquid_shares = float(value)
                            except ValueError:
                                liquid_shares = None
                        elif industry is None and ('行业' in item or '所属' in item):
                            industry = value
                        elif turnover_rate is None and ('换手率' in item or '换手' in item):
                            try:
                                tr = float(value.replace('%', ''))
                                turnover_rate = tr if 0 <= tr <= 50 else None  # 有效范围0%-50%
                            except ValueError:
                                turnover_rate = None
            except Exception as e:
                logger.debug(f"获取基本面数据失败({stock_code}): {str(e)}")

            # 2. 获取K线数据（严格校验，不生成模拟数据）
            #    优先东财 stock_zh_a_hist，失败回退新浪 stock_zh_a_daily（同时提供流通股本/换手率）
            kline_data = []
            sina_outstanding = None  # 新浪K线附带的流通股本
            sina_turnover = None     # 新浪K线附带的换手率
            try:
                logger.debug(f"正在获取股票 {stock_code} K线数据")
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=40)).strftime('%Y%m%d')  # 40天确保20个交易日

                kline_df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                              start_date=start_date, end_date=end_date)

                if kline_df is not None and not kline_df.empty:
                    for _, row in kline_df.iterrows():
                        try:
                            o = float(row['开盘']) if pd.notna(row['开盘']) else None
                            h = float(row['最高']) if pd.notna(row['最高']) else None
                            l = float(row['最低']) if pd.notna(row['最低']) else None
                            c = float(row['收盘']) if pd.notna(row['收盘']) else None
                            v = float(row['成交量']) if pd.notna(row['成交量']) else None
                            # 换手率（%），筹码分布计算需要；老数据源无此列时为 None
                            t = None
                            if '换手率' in kline_df.columns and pd.notna(row['换手率']):
                                t = float(row['换手率'])
                                if not (0 <= t <= 100):
                                    t = None
                        except (TypeError, ValueError):
                            continue

                        # 严格校验：价格必须为正数，成交量必须>=0
                        if (o is None or h is None or l is None or c is None or v is None
                                or o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0):
                            continue

                        kline_data.append({
                            'date': str(row['日期']),
                            'open': o,
                            'high': h,
                            'low': l,
                            'close': c,
                            'volume': v,
                            'turnover': t
                        })
            except Exception as e:
                logger.debug(f"东财K线获取失败({stock_code}): {str(e)}，尝试腾讯源")

            # 回退源2：腾讯财经 stock_zh_a_hist_tx（机房实测可用，含换手率，北交所不支持）
            if len(kline_data) < 20 and not stock_code.startswith('bj'):
                try:
                    tx_symbol = f"{'sh' if stock_code.startswith('sh') else 'sz'}{code}"
                    tx_df = ak.stock_zh_a_hist_tx(symbol=tx_symbol,
                                                  start_date=start_date,
                                                  end_date=end_date,
                                                  adjust="")
                    if tx_df is not None and not tx_df.empty:
                        kline_data = []
                        # 腾讯 turnover 是换手率小数（0.003=0.3%），统一换算为百分数
                        has_tx_turnover = 'turnover' in tx_df.columns
                        for _, row in tx_df.iterrows():
                            try:
                                o = float(row['open']) if pd.notna(row['open']) else None
                                h = float(row['high']) if pd.notna(row['high']) else None
                                l = float(row['low']) if pd.notna(row['low']) else None
                                c = float(row['close']) if pd.notna(row['close']) else None
                                v = float(row['volume']) if pd.notna(row['volume']) else None
                                t = None
                                if has_tx_turnover and pd.notna(row['turnover']):
                                    t = float(row['turnover']) * 100
                                    if not (0 <= t <= 100):
                                        t = None
                            except (TypeError, ValueError):
                                continue
                            if (o is None or h is None or l is None or c is None or v is None
                                    or o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0):
                                continue
                            kline_data.append({
                                'date': str(row['date']),
                                'open': o,
                                'high': h,
                                'low': l,
                                'close': c,
                                'volume': v,
                                'turnover': t
                            })
                        if kline_data:
                            logger.info(f"腾讯兜底K线成功({stock_code}): {len(kline_data)}条")
                except Exception as e:
                    logger.debug(f"腾讯K线获取失败({stock_code}): {str(e)}，尝试新浪源")

            # 回退源3：新浪 stock_zh_a_daily
            if len(kline_data) < 20:
                try:
                    sina_symbol = f"{'sh' if stock_code.startswith('sh') else 'sz'}{code}"
                    sina_df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust="")
                    if sina_df is not None and not sina_df.empty:
                        kline_data = []
                        has_sina_turnover = 'turnover' in sina_df.columns
                        # 只取最近40天数据
                        sina_df = sina_df.tail(40).reset_index(drop=True)
                        for _, row in sina_df.iterrows():
                            try:
                                o = float(row['open']) if pd.notna(row['open']) else None
                                h = float(row['high']) if pd.notna(row['high']) else None
                                l = float(row['low']) if pd.notna(row['low']) else None
                                c = float(row['close']) if pd.notna(row['close']) else None
                                v = float(row['volume']) if pd.notna(row['volume']) else None
                                t = None
                                if has_sina_turnover and pd.notna(row['turnover']):
                                    # 新浪 turnover 是换手率小数（0.0016=0.16%），
                                    # 统一换算为百分数，与东财"换手率"列口径一致
                                    t = float(row['turnover']) * 100
                                    if not (0 <= t <= 100):
                                        t = None
                            except (TypeError, ValueError):
                                continue
                            if (o is None or h is None or l is None or c is None or v is None
                                    or o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0):
                                continue
                            kline_data.append({
                                'date': str(row['date']),
                                'open': o,
                                'high': h,
                                'low': l,
                                'close': c,
                                'volume': v,
                                'turnover': t
                            })
                        # 新浪K线附带流通股本与换手率（取最新一行）
                        if 'outstanding_share' in sina_df.columns:
                            last_os = sina_df['outstanding_share'].iloc[-1]
                            if pd.notna(last_os) and float(last_os) > 0:
                                sina_outstanding = float(last_os)
                        if 'turnover' in sina_df.columns:
                            last_to = sina_df['turnover'].iloc[-1]
                            if pd.notna(last_to):
                                tr = float(last_to)
                                sina_turnover = tr if 0 <= tr <= 50 else None
                except Exception as e:
                    logger.debug(f"新浪K线获取失败({stock_code}): {str(e)}")

            # 兜底源4：AlphaFeed（免费额度窄，仅东财/腾讯/新浪均失败时启用，
            # 进程内有预算上限，全市场扫描大面积故障时不会被拖死）
            if len(kline_data) < 20:
                try:
                    import alphafeed_source
                    af_rows = alphafeed_source.get_daily_kline(stock_code, count=40)
                    if af_rows:
                        kline_data = af_rows
                        logger.info(f"AlphaFeed 兜底K线成功({stock_code}): {len(af_rows)}条")
                except Exception as e:
                    logger.debug(f"AlphaFeed K线获取失败({stock_code}): {str(e)}")

            # K线数据完整性校验：至少20个交易日的真实数据，否则放弃该股票
            if len(kline_data) < 20:
                logger.debug(f"股票 {stock_code} 有效K线数据不足20个交易日({len(kline_data)}条)，放弃采集")
                return None

            # 新浪源补充流通股本与换手率（东财未取到时使用）
            if liquid_shares is None and sina_outstanding is not None:
                liquid_shares = sina_outstanding
            if turnover_rate is None and sina_turnover is not None:
                turnover_rate = sina_turnover

            # 3. PE/PB 回退源：百度 stock_zh_valuation_baidu（东财未取到时使用）
            if pe_ratio is None or pb_ratio is None:
                try:
                    for indicator, attr in (('市盈率(TTM)', 'pe'), ('市净率', 'pb')):
                        if (attr == 'pe' and pe_ratio is not None) or (attr == 'pb' and pb_ratio is not None):
                            continue
                        val_df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period='近一月')
                        if val_df is not None and not val_df.empty:
                            last_val = val_df['value'].iloc[-1]
                            if pd.notna(last_val):
                                fval = float(last_val)
                                if attr == 'pe':
                                    pe_ratio = fval if fval > 0 else None
                                else:
                                    pb_ratio = fval if fval > 0 else None
                except Exception as e:
                    logger.debug(f"百度估值获取失败({stock_code}): {str(e)}")

            # 计算涨幅数据
            latest_price = kline_data[-1]['close']
            previous_price = kline_data[-2]['close']
            price_change_pct = None
            if previous_price > 0:
                price_change_pct = (latest_price - previous_price) / previous_price * 100
                if abs(price_change_pct) > 50:  # 异常涨跌幅过滤
                    price_change_pct = None

            # 构建返回数据（与原版本兼容）
            stock_data = {
                'code': stock_code,
                'pe': pe_ratio,
                'pb': pb_ratio,
                'market_cap': market_cap,
                'liquid_shares': liquid_shares,
                'industry': industry,
                'turnover_rate': turnover_rate,
                'kline_data': kline_data,
                'latest_price': latest_price,
                'volume_avg': sum(d['volume'] for d in kline_data) / len(kline_data),
                'change_pct': price_change_pct,
                'market_segment': None  # 由调用方根据板块分类补充
            }

            self.stock_cache[cache_key] = stock_data
            return stock_data

        except Exception as e:
            logger.debug(f"处理股票数据失败({stock_code}): {str(e)}")
            return None
    
    def get_statistics(self):
        """获取采集统计信息"""
        total_requests = self.success_count + self.error_count
        success_rate = (self.success_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'request_count': self.request_count,
            'total_requests': total_requests,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate': success_rate
        }


if __name__ == "__main__":
    # 测试优化版采集器
    collector = OptimizedStockDataCollector()
    
    # 测试获取前20只股票
    stocks = collector.get_all_stocks(limit=20)
    
    stats = collector.get_statistics()
    print(f"\n=== 性能测试结果 ===")
    print(f"获取股票数量: {len(stocks)}")
    print(f"总请求数: {stats['total_requests']}")
    print(f"成功率: {stats['success_rate']:.1f}%")
    
    if stocks:
        s0 = stocks[0]
        print(f"\n示例股票: {s0['code']} - PE: {s0['pe']}, PB: {s0['pb']}, 板块: {s0['market_segment']}")