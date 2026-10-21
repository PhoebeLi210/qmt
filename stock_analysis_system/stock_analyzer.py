#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票分析模块

功能：
1. 对选取的股票进行基本面分析
2. 对选取的股票进行技术面分析
3. 支持MACD金叉、放量、多头、超卖等积极指标
"""

import logging
import sys
import pandas as pd
import numpy as np
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('stock_analyzer', logging.INFO)

# 负面技术信号（一票否决项，出现任意一项即不通过分析）
NEGATIVE_INDICATORS = ['超买', '价格偏离过大', '趋势向下', '放量下跌', '过高换手率(需谨慎)']

# 中性信号（不加分、不否决、不计入积极指标数量）
NEUTRAL_INDICATORS = ['量价齐跌', '过低换手率', '缩量下跌', '放量顶下跌',
                      '看跌吞没', '黄昏之星', '巨量长上影']  # v2.5 见顶信号仅用于离场收紧


# 动态导入akshare库，避免没有安装时影响系统运行
try:
    import akshare as ak
except ImportError:
    logger.warning("akshare库未安装，将使用模拟热门题材数据")
    ak = None

class StockAnalyzer:
    """股票分析师"""

    # 市场环境因子缓存（类级，同一交易日只拉取一次真实指数数据）
    # date: 缓存所属交易日; factor: 当日因子值; retry_after: 拉取失败后的重试时间戳
    _market_env_cache = {'date': None, 'factor': None, 'retry_after': 0.0}

    def __init__(self, stock_list):
        self.stock_list = stock_list
        self.hot_sectors = self._get_hot_sectors()  # 获取热门题材板块
    
    def _get_hot_sectors(self):
        """获取当前市场热门题材板块
        
        Returns:
            list: 热门题材板块列表
        """
        hot_sectors = []
        try:
            logger.info("获取热门题材板块数据...")
            
            # 尝试使用akshare获取热门题材
            if 'akshare' in sys.modules:
                try:
                    # 尝试不同的akshare函数名
                    if hasattr(ak, 'stock_board_industry'):
                        df = ak.stock_board_industry()
                    elif hasattr(ak, 'stock_board_concept_name_em'):
                        df = ak.stock_board_concept_name_em()
                    elif hasattr(ak, 'stock_concept_em'):
                        df = ak.stock_concept_em()
                    else:
                        # 使用默认热门板块
                        logger.warning("akshare版本不支持获取热门题材，使用默认热门板块")
                        return ["人工智能", "新能源", "半导体", "医药生物", "数字经济"]
                    
                    # 提取热门板块名称
                    if not df.empty:
                        # 尝试不同的列名
                        if '板块名称' in df.columns:
                            hot_sectors = df['板块名称'].tolist()[:10]  # 取前10个热门板块
                        elif 'name' in df.columns:
                            hot_sectors = df['name'].tolist()[:10]
                        elif 'concept_name' in df.columns:
                            hot_sectors = df['concept_name'].tolist()[:10]
                except Exception as e:
                    logger.debug(f"获取热门题材失败: {str(e)}")
                    
            # 如果没有获取到数据，使用默认热门板块
            if not hot_sectors:
                hot_sectors = ["人工智能", "新能源", "半导体", "医药生物", "数字经济"]
                
            logger.info(f"当前热门题材板块: {hot_sectors}")
            return hot_sectors
            
        except Exception as e:
            logger.debug(f"获取热门题材失败: {str(e)}")
            # 发生异常时返回默认热门板块
            return ["人工智能", "新能源", "半导体", "医药生物", "数字经济"]
    
    def analyze_stocks(self):
        """分析股票列表"""
        analyzed_stocks = []
        total_stocks = len(self.stock_list)
        
        logger.info(f"开始分析 {total_stocks} 只股票")
        
        for i, stock in enumerate(self.stock_list):
            try:
                # 进度提示 - 更详细和频繁
                processed_pct = (i + 1) / total_stocks * 100
                passed_pct = len(analyzed_stocks) / (i + 1) * 100 if i >= 0 else 0
                
                if (i + 1) % 200 == 0 or i < 20:  # 每200个股票显示一次，前20个也显示（减少I/O开销）
                    logger.info(f"分析进度: {i + 1}/{total_stocks} ({processed_pct:.1f}%) | 已通过: {len(analyzed_stocks)} ({passed_pct:.1f}%) | 当前: {stock['code']}")
                
                logger.debug(f"正在分析股票: {stock['code']} - {stock['name']}")
                
                # 基本面分析
                fundamental_score = self._analyze_fundamental(stock)
                logger.debug(f"股票 {stock['code']} 基本面得分: {fundamental_score}")
                
                # 技术面分析
                technical_score, positive_indicators = self._analyze_technical(stock)
                logger.debug(f"股票 {stock['code']} 技术面得分: {technical_score}")
                logger.debug(f"股票 {stock['code']} 积极指标: {positive_indicators}")
                
                # 多因子量化评分优化
                total_score = self._calculate_multi_factor_score(stock, fundamental_score, technical_score, positive_indicators)
                logger.debug(f"股票 {stock['code']} 多因子综合得分: {total_score}")
                
                # 增强的风险控制机制
                risk_score = self._calculate_risk_score(stock, positive_indicators)
                logger.debug(f"股票 {stock['code']} 风险得分: {risk_score}")
                
                # 最终评分：综合得分 - 风险调整
                final_score = max(0, total_score - risk_score)
                logger.debug(f"股票 {stock['code']} 最终得分: {final_score}")
                
                # 动态门槛：根据市场环境调整
                dynamic_threshold = self._get_dynamic_threshold()

                # 负面指标过滤（一票否决）
                has_negative = any(indicator in positive_indicators for indicator in NEGATIVE_INDICATORS)

                # 数据完整性检查：基本面数据至少一项 + 积极技术指标至少2个（两者须同时满足）
                has_basic_data = bool(stock.get('pe')) or bool(stock.get('pb')) or bool(stock.get('liquid_shares')) or bool(stock.get('industry'))
                truly_positive = [i for i in positive_indicators if i not in NEGATIVE_INDICATORS and i not in NEUTRAL_INDICATORS]
                has_technical_indicators = len(truly_positive) >= 2

                # 通过条件：动态门槛 + 无负面指标 + 有数据支撑（三个条件同时满足）
                if (final_score >= dynamic_threshold and not has_negative
                        and has_basic_data and has_technical_indicators):
                    stock['fundamental_score'] = fundamental_score
                    stock['technical_score'] = technical_score
                    stock['score'] = total_score
                    stock['risk_score'] = risk_score
                    stock['final_score'] = final_score
                    stock['positive_indicators'] = positive_indicators
                    analyzed_stocks.append(stock)
                    logger.debug(f"股票 {stock['code']} 通过分析，综合评分={total_score:.2f}，最终评分={final_score:.2f}，积极指标: {positive_indicators}")
                else:
                    logger.debug(f"股票 {stock['code']} 未通过分析：最终评分={final_score:.2f}(门槛{dynamic_threshold}分) 或存在负面指标或缺少数据支撑")
                    
            except Exception as e:
                logger.debug(f"分析股票失败({stock['code']}): {str(e)}")
                continue
        
        logger.info(f"分析完成，共 {len(analyzed_stocks)} 只股票通过分析")
        return analyzed_stocks
    
    def _analyze_fundamental(self, stock):
        """基本面分析"""
        score = 0
        
        # 市盈率（PE）分析（12分）- 降低权重
        if stock['pe'] and 0 < stock['pe'] < 30:
            score += 12
        elif stock['pe'] and 30 <= stock['pe'] < 50:
            score += 8
        elif stock['pe'] and 50 <= stock['pe'] < 100:
            score += 4
        
        # 市净率（PB）分析（12分）
        if stock['pb'] and 0 < stock['pb'] < 2:
            score += 12
        elif stock['pb'] and 2 <= stock['pb'] < 3:
            score += 8
        elif stock['pb'] and 3 <= stock['pb'] < 5:
            score += 4
        
        # 流通股本分析（8分）- 降低权重
        if stock['liquid_shares'] and stock['liquid_shares'] < 1000000000:  # 小于10亿
            score += 8
        elif stock['liquid_shares'] and stock['liquid_shares'] < 2000000000:  # 小于20亿
            score += 4
        
        # 行业分析（20分）- 大幅增加权重
        if stock['industry']:
            # 基础行业分数
            score += 10
            
            # 热门题材加分
            if stock['industry'] in self.hot_sectors:
                score += 10
                logger.debug(f"股票 {stock['code']} 属于热门题材 {stock['industry']}，加分10分")
            elif any(sector in stock['industry'] for sector in self.hot_sectors):
                # 部分匹配热门题材
                score += 5
                logger.debug(f"股票 {stock['code']} 部分匹配热门题材 {stock['industry']}，加分5分")
        
        # 添加基本数据完整性分数（8分）
        data_count = 0
        if stock['pe']:
            data_count += 1
        if stock['pb']:
            data_count += 1
        if stock['liquid_shares']:
            data_count += 1
        if stock['industry']:
            data_count += 1
        
        # 数据完整性最多加8分
        score += min(data_count * 2, 8)
        
        return score
    
    def _analyze_technical(self, stock):
        """技术面分析"""
        score = 0
        positive_indicators = []
        
        try:
            df_kline = pd.DataFrame(stock['kline_data'])
            logger.debug(f"股票 {stock['code']} 有 {len(df_kline)} 天K线数据")
            
            if len(df_kline) < 20:  # 需要至少20天完整K线数据
                logger.debug(f"股票 {stock['code']} K线数据不足20天，跳过技术分析")
                return score, positive_indicators
            
            # 将价格转换为浮点数，安全处理空值
            df_kline['close'] = pd.to_numeric(df_kline['close'], errors='coerce')
            df_kline['open'] = pd.to_numeric(df_kline['open'], errors='coerce')
            df_kline['high'] = pd.to_numeric(df_kline['high'], errors='coerce')
            df_kline['low'] = pd.to_numeric(df_kline['low'], errors='coerce')
            df_kline['volume'] = pd.to_numeric(df_kline['volume'], errors='coerce')
            
            # 检查是否有转换失败的空值，如果有则返回
            if df_kline[['close', 'open', 'high', 'low', 'volume']].isnull().any().any():
                logger.debug(f"股票 {stock['code']} 价格数据包含无效值，跳过技术分析")
                return score, positive_indicators
            
            # 获取最近20天数据
            recent_data = df_kline.tail(20).reset_index(drop=True)
            
            # 1. MACD分析（20分）
            try:
                macd_golden, macd_signal = self._calculate_macd(recent_data)
                if macd_golden:
                    score += 20
                    positive_indicators.append('MACD金叉')
                    logger.debug(f"股票 {stock['code']} MACD金叉，得分+20")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} MACD分析失败: {str(e)}")
            
            # 2. 成交量分析（15分）
            try:
                volume_score, volume_signal = self._analyze_volume(recent_data)
                score += volume_score
                if volume_signal:
                    positive_indicators.append(volume_signal)
                    logger.debug(f"股票 {stock['code']} 成交量分析得分+{volume_score}: {volume_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 成交量分析失败: {str(e)}")
            
            # 3. 换手率分析（15分）
            try:
                turnover_score, turnover_signal = self._analyze_turnover_rate(stock)
                score += turnover_score
                if turnover_signal:
                    positive_indicators.append(turnover_signal)
                    logger.debug(f"股票 {stock['code']} 换手率分析得分+{turnover_score}: {turnover_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 换手率分析失败: {str(e)}")
            
            # 4. 趋势强度分析（15分）
            try:
                trend_score, trend_signal = self._analyze_trend_strength(recent_data)
                score += trend_score
                if trend_signal:
                    positive_indicators.append(trend_signal)
                    logger.debug(f"股票 {stock['code']} 趋势强度分析得分+{trend_score}: {trend_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 趋势强度分析失败: {str(e)}")
            
            # 5. 量价配合分析（15分）
            try:
                price_volume_score, price_volume_signal = self._analyze_price_volume_relation(recent_data)
                score += price_volume_score
                if price_volume_signal:
                    positive_indicators.append(price_volume_signal)
                    logger.debug(f"股票 {stock['code']} 量价配合分析得分+{price_volume_score}: {price_volume_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 量价配合分析失败: {str(e)}")
            
            # 6. 均线多头排列分析（20分）
            try:
                ma_signal = self._analyze_ma_arrangement(recent_data)
                if ma_signal:
                    score += 20
                    positive_indicators.append(ma_signal)
                    logger.debug(f"股票 {stock['code']} 均线多头排列，得分+20")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 均线分析失败: {str(e)}")
            
            # 7. RSI分析（15分）
            try:
                rsi_score, rsi_signal = self._analyze_rsi(recent_data)
                score += rsi_score
                if rsi_signal:
                    positive_indicators.append(rsi_signal)
                    logger.debug(f"股票 {stock['code']} RSI分析得分+{rsi_score}: {rsi_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} RSI分析失败: {str(e)}")
            
            # 8. KDJ分析（15分）
            try:
                kdj_score, kdj_signal = self._analyze_kdj(recent_data)
                score += kdj_score
                if kdj_signal:
                    positive_indicators.append(kdj_signal)
                    logger.debug(f"股票 {stock['code']} KDJ分析得分+{kdj_score}: {kdj_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} KDJ分析失败: {str(e)}")
            
            # 9. 价格形态分析（15分）
            try:
                pattern_score, pattern_signal = self._analyze_price_pattern(recent_data)
                score += pattern_score
                if pattern_signal:
                    positive_indicators.append(pattern_signal)
                    logger.debug(f"股票 {stock['code']} 价格形态分析得分+{pattern_score}: {pattern_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 价格形态分析失败: {str(e)}")
            
            # 10. 均线偏离度分析（10分）
            try:
                ma_deviation_score, ma_deviation_signal = self._analyze_ma_deviation(recent_data)
                score += ma_deviation_score
                if ma_deviation_signal:
                    positive_indicators.append(ma_deviation_signal)
                    logger.debug(f"股票 {stock['code']} 均线偏离度分析得分+{ma_deviation_score}: {ma_deviation_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 均线偏离度分析失败: {str(e)}")
            
            # 11. 技术分析口诀分析（20分）
            try:
                adage_score, adage_signals = self._analyze_technical_adages(recent_data)
                score += adage_score
                for signal in adage_signals:
                    if signal not in positive_indicators:
                        positive_indicators.append(signal)
                logger.debug(f"股票 {stock['code']} 口诀分析得分+{adage_score}: {adage_signals}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 口诀分析失败: {str(e)}")

            # 12. 【v2新增】MACD底背离检测（15分，前瞻信号）
            try:
                divergence_score, divergence_signal = self._analyze_macd_divergence(recent_data)
                score += divergence_score
                if divergence_signal:
                    positive_indicators.append(divergence_signal)
                    logger.debug(f"股票 {stock['code']} MACD底背离得分+{divergence_score}: {divergence_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} MACD底背离分析失败: {str(e)}")

            # 13. 【v2新增】放量突破检测（15分，前瞻信号）
            try:
                breakout_score, breakout_signal = self._analyze_volume_breakout(recent_data)
                score += breakout_score
                if breakout_signal:
                    positive_indicators.append(breakout_signal)
                    logger.debug(f"股票 {stock['code']} 放量突破得分+{breakout_score}: {breakout_signal}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 放量突破分析失败: {str(e)}")

            # 14. 【v2.5新增】K线组合加分（基于 selector 的 pattern_detail）
            try:
                combo_score, combo_signals = self._analyze_kline_combos(stock)
                score += combo_score
                for sig in combo_signals:
                    if sig not in positive_indicators:
                        positive_indicators.append(sig)
                if combo_signals:
                    logger.debug(f"股票 {stock['code']} K线组合加分+{combo_score}: {combo_signals}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} K线组合分析失败: {str(e)}")

            # 15. 【v2.5新增】见顶K线组合标记（供推荐引擎收紧离场）
            try:
                bearish_combos = self._analyze_bearish_combos(stock)
                for sig in bearish_combos:
                    if sig not in positive_indicators:
                        positive_indicators.append(sig)
                if bearish_combos:
                    logger.debug(f"股票 {stock['code']} 见顶K线组合标记: {bearish_combos}")
            except Exception as e:
                logger.debug(f"股票 {stock['code']} 见顶组合分析失败: {str(e)}")

            logger.debug(f"股票 {stock['code']} 技术面分析总得分: {score}")
            logger.debug(f"股票 {stock['code']} 积极指标: {positive_indicators}")
            # 确保技术面得分不超过100分的上限
            score = min(100, score)
            return score, positive_indicators
        except Exception as e:
            logger.debug(f"股票 {stock['code']} 技术面分析失败: {str(e)}")
            return score, positive_indicators
    
    def _calculate_macd(self, df, fast_period=12, slow_period=26, signal_period=9):
        """计算MACD指标"""
        df['ema12'] = df['close'].ewm(span=fast_period, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=slow_period, adjust=False).mean()
        df['dif'] = df['ema12'] - df['ema26']
        df['dea'] = df['dif'].ewm(span=signal_period, adjust=False).mean()
        df['macd'] = 2 * (df['dif'] - df['dea'])
        
        # 检查金叉
        golden_cross = df['dif'].iloc[-2] < df['dea'].iloc[-2] and df['dif'].iloc[-1] > df['dea'].iloc[-1]
        
        return golden_cross, 'MACD'
    
    def _analyze_volume(self, df):
        """成交量分析"""
        score = 0
        signal = None
        
        # 最近一天成交量是前5天平均量的1.3倍以上（用户要求的30%增长）
        avg_volume = df['volume'].iloc[-6:-1].mean()
        latest_volume = df['volume'].iloc[-1]
        
        if latest_volume >= avg_volume * 2:
            score = 15
            signal = '放量'
        elif latest_volume >= avg_volume * 1.3:
            score = 10
            signal = '温和放量'
        elif latest_volume >= avg_volume:
            score = 5
        
        return score, signal
    
    def _analyze_turnover_rate(self, stock):
        """换手率分析（最优区间3%-8%）"""
        score = 0
        signal = None

        # 从股票数据中获取换手率
        turnover_rate = stock.get('turnover_rate', 0.0) or 0.0

        # 换手率评分：适中3-8%满分，较低1-3%得8分，较高8-10%得5分，其余0分
        if 3.0 <= turnover_rate < 8.0:  # 适中换手率 - 健康活跃
            score = 15
            signal = '适中换手率'
        elif 1.0 <= turnover_rate < 3.0:  # 较低换手率
            score = 8
            signal = '较低换手率'
        elif 8.0 <= turnover_rate < 10.0:  # 较高换手率
            score = 5
            signal = '较高换手率'
        elif turnover_rate >= 10.0:  # 过高换手率 - 投机风险（负面信号，参与一票否决）
            score = 0
            signal = '过高换手率(需谨慎)'
        else:  # 过低换手率（<1%）或缺失
            score = 0
            signal = '过低换手率'

        return score, signal
    
    def _analyze_trend_strength(self, df):
        """趋势强度分析（基于5日涨幅）"""
        score = 0
        signal = None

        closes = df['close'].values
        if len(closes) < 5:
            return score, signal

        # 最近5天涨跌幅
        price_increase_pct = (closes[-1] - closes[-5]) / closes[-5] * 100

        # 趋势强度评分：≥10%强势，≥5%稳健，≥0%小幅，下跌0分
        if price_increase_pct >= 10:
            score = 15
            signal = '强势上涨'
        elif price_increase_pct >= 5:
            score = 10
            signal = '稳健上涨'
        elif price_increase_pct >= 0:
            score = 5
            signal = '小幅上涨'

        return score, signal

    def _analyze_price_volume_relation(self, df):
        """量价配合分析（理想状态：量价齐升）"""
        score = 0
        signal = None

        if len(df) < 2:
            return score, signal

        # 最近一个交易日的价格与成交量变化
        price_change = df['close'].iloc[-1] - df['close'].iloc[-2]
        prev_volume = df['volume'].iloc[-2]
        if prev_volume <= 0:
            return score, signal
        volume_change = df['volume'].iloc[-1] - prev_volume

        # 量价齐升15分 / 价升量缩10分 / 价跌量升5分 / 量价齐跌0分
        if price_change > 0 and volume_change > 0:
            score = 15
            signal = '量价齐升'
        elif price_change > 0 and volume_change < 0:
            score = 10
            signal = '价升量缩'
        elif price_change < 0 and volume_change > 0:
            score = 5
            signal = '价跌量升'
        elif price_change < 0 and volume_change < 0:
            score = 0
            signal = '量价齐跌'

        return score, signal
    
    def _analyze_ma_arrangement(self, df):
        """均线多头排列分析"""
        # 计算5日、10日、20日均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()

        # 多头排列：MA5 > MA10 > MA20，且5日均线比20日均线高出2%以上
        if (df['ma5'].iloc[-1] > df['ma10'].iloc[-1] > df['ma20'].iloc[-1] and
                df['ma5'].iloc[-1] >= df['ma20'].iloc[-1] * 1.02):
            return '多头排列'

        return None
    
    def _analyze_rsi(self, df, window=14):
        """RSI分析"""
        score = 0
        signal = None
        
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        latest_rsi = rsi.iloc[-1]
        
        # RSI在30-70之间为正常，70以上超买，30以下超卖
        if 50 < latest_rsi < 70:
            score = 15
            signal = 'RSI正常'
        elif 30 < latest_rsi <= 50:
            score = 10
            signal = 'RSI偏低'  # 偏低不是负面，可能反弹
        elif latest_rsi <= 30:
            score = 8
            signal = '超卖'  # 超卖是机会信号，可能反弹
        elif latest_rsi >= 70:
            score = 0
            signal = '超买'
        
        return score, signal
    
    def _analyze_kdj(self, df, n=9, m1=3, m2=3):
        """KDJ分析"""
        score = 0
        signal = None
        
        # 计算KDJ
        low_min = df['low'].rolling(window=n).min()
        high_max = df['high'].rolling(window=n).max()
        rsv = (df['close'] - low_min) / (high_max - low_min) * 100
        
        k = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d = k.ewm(alpha=1/m2, adjust=False).mean()
        j = 3 * k - 2 * d
        
        # 检查KDJ金叉
        kdj_golden = k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]
        
        if kdj_golden:
            score = 15
            signal = 'KDJ金叉'
        elif 20 < k.iloc[-1] < 80 and k.iloc[-1] < d.iloc[-1]:
            score = 5
        
        return score, signal
    
    def _analyze_price_pattern(self, df):
        """价格形态分析（基于5日价格变化）"""
        score = 0
        signal = None

        closes = df['close'].values
        if len(closes) < 5:
            return score, signal

        # 检查是否有上升趋势
        if closes[-1] > closes[-5] * 1.05:  # 最近5天上涨超过5%
            score = 15
            signal = '上涨趋势'
        elif closes[-1] > closes[-5]:  # 最近5天上涨
            score = 10
            signal = '小幅上涨'

        # 趋势向下负面信号：连续5个交易日收盘价逐日下跌（一票否决项）
        if all(closes[i] < closes[i - 1] for i in range(len(closes) - 4, len(closes))):
            score = 0
            signal = '趋势向下'

        return score, signal
    
    def _analyze_ma_deviation(self, df):
        """均线偏离度分析（避免追高）"""
        score = 0
        signal = None
        
        # 计算5日均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        
        latest_close = df['close'].iloc[-1]
        latest_ma5 = df['ma5'].iloc[-1]
        
        if not pd.isna(latest_ma5):
            # 计算收盘价与5日均线的偏离度
            deviation = (latest_close - latest_ma5) / latest_ma5 * 100
            
            # 偏离度控制在合理范围内
            if deviation < 5:  # 收盘价偏离5日均线不超过5%
                score = 10
                signal = '价格合理'
            elif deviation < 8:
                score = 5
                signal = '价格小幅偏离'
            else:
                # 偏离度过大，避免追高
                score = -5
                signal = '价格偏离过大'
        
        return score, signal
    
    def _analyze_technical_adages(self, df):
        """技术分析口诀分析（20分）
        
        根据8条量价口诀进行技术分析：
        一、放量上涨，必然回调 - 放量涨预示回调风险
        二、放量下跌，必然反弹 - 放量跌预示反弹机会
        三、缩量上涨，继续上涨 - 缩量涨是强势信号
        四、缩量下跌，继续下跌 - 缩量跌是弱势信号
        五、放量不涨，顶点已现 - 放量不涨是出货信号
        六、缩量不跌，底部已现 - 缩量不跌是筑底信号
        七、无量顶下跌，后市会大涨 - 无量顶跌是主力吸筹
        八、放量顶下跌，后市调整长 - 放量顶跌是主力出货
        """
        score = 0
        signals = []
        
        if len(df) < 10:
            return score, signals
        
        df = df.copy()
        
        # 计算必要指标
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        df['volume_ma3'] = df['volume'].rolling(window=3).mean()
        df['close_ma5'] = df['close'].rolling(window=5).mean()
        
        # 最近3天和前3天的平均成交量
        recent_volume = df['volume'].tail(3).mean()
        before_volume = df['volume'].iloc[-6:-3].mean()
        avg_volume = df['volume'].tail(5).mean()
        
        # 最近3天和前3天的平均价格
        recent_price = df['close'].tail(3).mean()
        before_price = df['close'].iloc[-6:-3].mean()
        
        # 计算量比和涨幅
        volume_ratio = recent_volume / before_volume if before_volume > 0 else 1
        price_change = (recent_price - before_price) / before_price * 100 if before_price > 0 else 0
        
        # 判断量价状态（量比区分无量/缩量/放量三档，使8条口诀均可独立触发）
        is_no_volume = volume_ratio < 0.5        # 无量
        is_volume_shrink = 0.5 <= volume_ratio < 0.7  # 缩量
        is_volume_increase = volume_ratio > 1.3  # 放量
        is_price_rise = price_change > 2  # 上涨
        is_price_fall = price_change < -2  # 下跌
        is_price_stable = abs(price_change) <= 2  # 价格稳定

        # 口诀判断（8条口诀全部独立生效）
        # 七、无量顶下跌，后市会大涨（+15分，强积极信号）
        if is_no_volume and is_price_fall:
            score += 15
            signals.append('无量顶跌')
            logger.debug(f"口诀七：无量顶下跌，后市会大涨，量比={volume_ratio:.2f}，跌幅={price_change:.2f}%")

        # 三、缩量上涨，继续上涨（+10分，积极信号）
        elif is_volume_shrink and is_price_rise:
            score += 10
            signals.append('缩量上涨')
            logger.debug(f"口诀三：缩量上涨，继续上涨，量比={volume_ratio:.2f}，涨幅={price_change:.2f}%")

        # 六、缩量不跌，底部已现（+10分，积极信号）
        elif is_volume_shrink and is_price_stable:
            score += 10
            signals.append('缩量筑底')
            logger.debug(f"口诀六：缩量不跌，底部已现，量比={volume_ratio:.2f}，涨跌幅={price_change:.2f}%")

        # 四、缩量下跌，继续下跌（-8分，弱势信号）
        elif is_volume_shrink and is_price_fall:
            score -= 8
            signals.append('缩量下跌')
            logger.debug(f"口诀四：缩量下跌，继续下跌，量比={volume_ratio:.2f}，跌幅={price_change:.2f}%")

        # 二/八、放量下跌：前期10日涨幅>10%视为放量筑顶（口诀八，-15分），否则视为反弹机会（口诀二，+8分）
        elif is_volume_increase and is_price_fall:
            base_price = df['close'].iloc[-11] if len(df) >= 11 else 0
            top_price = df['close'].iloc[-4] if len(df) >= 11 else 0
            prior_gain = (top_price / base_price - 1) * 100 if base_price > 0 else 0
            if prior_gain > 10:
                score -= 15
                signals.append('放量顶下跌')
                logger.debug(f"口诀八：放量顶下跌，后市调整长，前10日涨幅={prior_gain:.2f}%")
            else:
                score += 8
                signals.append('放量下跌')
                logger.debug(f"口诀二：放量下跌，必然反弹，量比={volume_ratio:.2f}，跌幅={price_change:.2f}%")

        # 一、放量上涨，必然回调（+5分，谨慎信号，不是负面）
        elif is_volume_increase and is_price_rise:
            score += 5
            signals.append('放量上涨')
            logger.debug(f"口诀一：放量上涨，必然回调，量比={volume_ratio:.2f}，涨幅={price_change:.2f}%")

        # 五、放量不涨，顶点已现（-10分，负面信号）
        elif is_volume_increase and is_price_stable:
            score -= 10
            signals.append('放量滞涨')
            logger.debug(f"口诀五：放量不涨，顶点已现，量比={volume_ratio:.2f}，涨跌幅={price_change:.2f}%")

        # 口诀分析权重20分：得分限制在[-20, +20]
        score = max(-20, min(20, score))

        return score, signals
    
    def _analyze_macd_divergence(self, df):
        """【v2新增】MACD底背离检测（前瞻信号，15分）

        底背离：价格创近20日新低，但MACD柱（或DIF）未创新低
        这意味着下跌动能减弱，反转概率较高
        """
        score = 0
        signal = None

        if len(df) < 10:
            return score, signal

        # 计算MACD
        df = df.copy()
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['dif'] = df['ema12'] - df['ema26']

        # 找近10天最低收盘价和对应的DIF
        recent_10 = df.tail(10)
        price_low_idx = recent_10['close'].idxmin()
        price_low = recent_10['close'].min()
        dif_at_low = df.loc[price_low_idx, 'dif']

        # 找之前的更低点（10-20天前）
        if len(df) >= 20:
            prev_10 = df.iloc[-20:-10]
            if len(prev_10) > 0:
                prev_price_low = prev_10['close'].min()
                prev_low_idx = prev_10['close'].idxmin()
                dif_at_prev_low = df.loc[prev_low_idx, 'dif']

                # 底背离条件：价格创新低，但DIF未创新低
                if price_low < prev_price_low and dif_at_low > dif_at_prev_low:
                    score = 15
                    signal = 'MACD底背离'
                    logger.debug(f"MACD底背离: 当前低{price_low:.2f} DIF={dif_at_low:.4f} "
                               f"vs 前低{prev_price_low:.2f} DIF={dif_at_prev_low:.4f}")

        return score, signal

    def _analyze_volume_breakout(self, df):
        """【v2新增】放量突破检测（前瞻信号，15分）

        放量突破：当日收盘价突破近20日最高价，且成交量>2倍5日均量
        这意味着有资金推动，突破有效性较高
        """
        score = 0
        signal = None

        if len(df) < 20:
            return score, signal

        latest_close = df['close'].iloc[-1]
        prev_high_20 = df['high'].iloc[-20:-1].max()  # 前19日最高（不含今天）
        latest_volume = df['volume'].iloc[-1]
        vol_ma5 = df['volume'].tail(5).mean()

        if prev_high_20 > 0 and vol_ma5 > 0:
            # 突破条件：收盘价突破前19日最高价
            if latest_close > prev_high_20:
                # 放量条件：成交量>2倍5日均量
                vol_ratio = latest_volume / vol_ma5
                if vol_ratio > 2:
                    score = 15
                    signal = '放量突破20日高点'
                    logger.debug(f"放量突破: 收盘{latest_close:.2f} > 前19日高{prev_high_20:.2f} "
                               f"量比={vol_ratio:.2f}")
                elif vol_ratio > 1.3:
                    score = 8
                    signal = '温和放量突破'
                    logger.debug(f"温和放量突破: 收盘{latest_close:.2f} > 前19日高{prev_high_20:.2f} "
                               f"量比={vol_ratio:.2f}")

        return score, signal

    def _analyze_adage_trend(self, df):
        """分析近期的口诀形态趋势"""
        score = 0
        signals = []
        
        if len(df) < 10:
            return score, signals
        
        df = df.copy()
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        
        positive_days = 0  # 符合积极口诀的天数
        negative_days = 0  # 符合消极口诀的天数
        
        for i in range(-5, 0):
            if i < -len(df) + 5:
                continue
            
            curr_volume = df['volume'].iloc[i]
            curr_close = df['close'].iloc[i]
            prev_volume = df['volume'].iloc[i-1] if i-1 >= -len(df) else curr_volume
            prev_close = df['close'].iloc[i-1] if i-1 >= -len(df) else curr_close
            
            volume_ratio = curr_volume / prev_volume if prev_volume > 0 else 1
            price_change = (curr_close - prev_close) / prev_close * 100 if prev_close > 0 else 0
            
            is_volume_increase = volume_ratio > 1.3
            is_volume_decrease = volume_ratio < 0.7
            is_price_rise = price_change > 1
            is_price_fall = price_change < -1
            
            # 积极形态
            if is_volume_decrease and is_price_rise:
                positive_days += 1
            elif is_volume_decrease and price_change > -1 and price_change < 1:
                positive_days += 1
            elif is_volume_increase and is_price_fall:
                positive_days += 1
            
            # 消极形态
            if is_volume_increase and price_change > -1 and price_change < 1:
                negative_days += 1
            elif is_volume_decrease and is_price_fall:
                negative_days += 1
        
        # 统计趋势
        if positive_days >= 3:
            score += 10
            signals.append('量价齐升')
            logger.debug(f"近期趋势：{positive_days}天呈现积极量价形态")
        elif negative_days >= 3:
            score -= 10
            signals.append('量价齐跌')
            logger.debug(f"近期趋势：{negative_days}天呈现消极量价形态")
        elif positive_days > negative_days:
            score += 5
            signals.append('量价偏强')
            logger.debug(f"近期趋势：积极形态略多({positive_days} vs {negative_days})")
        elif negative_days > positive_days:
            score -= 5
            signals.append('量价偏弱')
            logger.debug(f"近期趋势：消极形态略多({negative_days} vs {positive_days})")
        
        return score, signals

    def _calculate_multi_factor_score(self, stock, fundamental_score, technical_score, positive_indicators):
        """多因子量化评分系统（乘数式合成）

        计算公式：综合评分 = (基本面×30% + 技术面×70%) × 市场因子 × 行业因子
                             × 流动性因子 × 估值因子 × 资金流因子 + 技术信号强度加分 + 筹码加减分
        评分范围：0-100分

        资金流因子（行业通行做法，大单正向）：
          fund_factor = 1 + clamp(mf_main_ratio, -0.05, 0.05)，即主力净占比 ±5% → 评分 ±5%
          无数据时因子=1（中性）
        筹码加减分（倒U+集中度）：
          获利盘>80% 或 <20% 扣3分（拥挤/套牢），30-70% 不扣分
          90%集中度<10% 加2分（筹码集中易拉升），>20% 减2分
          无数据时加0分
        """
        # 基础评分：基本面30% + 技术面70%
        base_score = (fundamental_score * 0.3) + (technical_score * 0.7)

        # 技术信号强度加分：每个积极信号加2分（排除负面与中性信号）
        truly_positive = [i for i in positive_indicators
                          if i not in NEGATIVE_INDICATORS and i not in NEUTRAL_INDICATORS]
        signal_strength = len(truly_positive) * 2

        # 四大因子系数（乘数调整）
        market_factor = self._get_market_environment_factor()  # 0.85-1.15
        industry_momentum = self._get_industry_momentum_factor(stock.get('industry', ''))  # 1.0/1.1/1.2
        liquidity_factor = self._get_liquidity_factor(stock.get('liquid_shares', 0))  # 0.95-1.15
        valuation_factor = self._get_valuation_factor(stock.get('pe', 0), stock.get('pb', 0))  # 0.85-1.21

        # 资金流因子（±5% 乘数）
        fund_factor = 1.0
        fund = stock.get('fund')
        if fund and fund.get('mf_main_ratio') is not None:
            fund_factor = 1.0 + max(-0.05, min(0.05, fund['mf_main_ratio']))

        # 筹码加减分（±3分）
        chip_bonus = 0
        chip = stock.get('chip')
        if chip:
            pr = chip.get('profit_ratio')
            if pr is not None:
                if pr > 0.80 or pr < 0.20:
                    chip_bonus -= 3
            conc = chip.get('conc90')
            if conc is not None:
                if conc < 0.10:
                    chip_bonus += 2
                elif conc > 0.20:
                    chip_bonus -= 2

        # 乘数式综合评分：基础分 × 五大因子 + 信号强度加分 + 筹码加减分
        final_score = base_score * market_factor * industry_momentum * liquidity_factor * valuation_factor * fund_factor
        final_score += signal_strength + chip_bonus

        # 评分范围控制（0-100分）
        final_score = min(100, max(0, final_score))

        logger.debug(f"多因子评分构成: 基础{base_score:.1f} × 市场{market_factor:.2f} × 行业{industry_momentum:.2f} "
                     f"× 流动{liquidity_factor:.2f} × 估值{valuation_factor:.2f} × 资金{fund_factor:.3f} "
                     f"+ 信号{signal_strength:.1f} + 筹码{chip_bonus} = {final_score:.1f}")

        return final_score

    def _analyze_kline_combos(self, stock):
        """【v2.5新增】K线组合加分（确底信号强化）

        看涨组合：看涨吞没/早晨之星/红三兵 → 各+5分，最多+10分
        强确底：v_rebound 叠加吞并反包 → 额外+8分
        双底质量：double_bottom 且二次探底不创新低+右侧放量 → 额外+6分
        """
        score = 0
        signals = []

        detail = stock.get('pattern_detail', {}) or {}
        pattern = stock.get('pattern', '') or ''
        bullish_combo = detail.get('bullish_combo', []) or []
        engulfing_confirmed = detail.get('engulfing_confirmed', False)
        double_bottom_quality = detail.get('double_bottom_quality', False)

        # 看涨K线组合加分
        for combo in bullish_combo:
            if combo in ('看涨吞没', '早晨之星', '红三兵'):
                score += 5
                signals.append(combo)

        # 强确底加分
        if pattern == 'v_rebound' and engulfing_confirmed:
            score += 8
            signals.append('吞并反包强确底')

        # 双底质量加分
        if pattern == 'double_bottom' and double_bottom_quality:
            score += 6
            signals.append('双底右侧放量确认')

        # 上限10分
        score = min(10, score)
        return score, signals

    def _analyze_bearish_combos(self, stock):
        """【v2.5新增】见顶K线组合识别（风险信号）

        返回：list[str]，如 ['看跌吞没', '黄昏之星', '巨量长上影']
        用于选股期扣分 & 持仓期收紧离场
        """
        combos = []
        kline_data = stock.get('kline_data', [])
        if len(kline_data) < 5:
            return combos

        try:
            df = pd.DataFrame(kline_data)
            close = pd.to_numeric(df['close'], errors='coerce').values
            open_ = pd.to_numeric(df['open'], errors='coerce').values
            high = pd.to_numeric(df['high'], errors='coerce').values
            volume = pd.to_numeric(df.get('volume', 0), errors='coerce').values

            # 1. 看跌吞没：前阳后阴，阴线实体吞没阳线实体
            if len(close) >= 2:
                prev_open, prev_close = open_[-2], close[-2]
                curr_open, curr_close = open_[-1], close[-1]
                if prev_close > prev_open and curr_close < curr_open:
                    if curr_open >= prev_close and curr_close <= prev_open:
                        combos.append('看跌吞没')

            # 2. 黄昏之星：左阳 + 中小实体 + 右阴，右阴收盘深入左阳实体
            if len(close) >= 3:
                o1, c1 = open_[-3], close[-3]
                o2, c2 = open_[-2], close[-2]
                o3, c3 = open_[-1], close[-1]
                if c1 > o1 and abs(c2 - o2) / (c1 - o1 + 1e-9) < 0.5:
                    if c3 < o3 and c3 < (o1 + c1) / 2:
                        combos.append('黄昏之星')

            # 3. 巨量长上影：上影线>实体2倍 + 成交量>5日均量2倍
            if len(close) >= 5:
                curr_open, curr_close = open_[-1], close[-1]
                curr_high = high[-1]
                upper_shadow = curr_high - max(curr_open, curr_close)
                body = abs(curr_close - curr_open)
                vol_ma5 = volume[-5:].mean()
                if vol_ma5 > 0 and volume[-1] > vol_ma5 * 2 and upper_shadow > body * 2:
                    combos.append('巨量长上影')

        except Exception:
            pass
        return combos

    def _calculate_risk_score(self, stock, positive_indicators):
        """计算风险评分（分数越高风险越大，需要从总分中扣除）"""
        risk_score = 0
        
        # 价格波动风险（单股数据源可能返回 None，缺失按 0 处理：无数据不加分）
        latest_price = stock.get('latest_price') or 0
        change_pct = abs(stock.get('change_pct') or 0)
        
        if change_pct > 8:  # 涨幅过大风险
            risk_score += 15
        elif change_pct > 5:
            risk_score += 10
        elif change_pct > 3:
            risk_score += 5
        
        # 换手率风险
        turnover_rate = stock.get('turnover_rate') or 0
        if turnover_rate > 15:  # 过高换手率
            risk_score += 12
        elif turnover_rate > 10:
            risk_score += 8
        
        # 市值风险（流通股本过大）
        liquid_shares = stock.get('liquid_shares') or 0
        if liquid_shares > 5000000000:  # 超过50亿股
            risk_score += 10
        elif liquid_shares > 2000000000:  # 超过20亿股
            risk_score += 5
        
        # 负面技术信号
        negative_indicators = ['放量下跌', '过高换手率(需谨慎)', '超买']
        negative_count = sum(1 for indicator in positive_indicators if indicator in negative_indicators)
        risk_score += negative_count * 8

        # 【v2.5新增】见顶K线组合风险扣分（每个+10分）
        bearish_combos = self._analyze_bearish_combos(stock)
        if bearish_combos:
            risk_score += len(bearish_combos) * 10
            logger.debug(f"股票 {stock.get('code')} 见顶K线组合: {bearish_combos}，风险+{len(bearish_combos)*10}")

        logger.debug(f"风险评分构成: 价格波动{change_pct:.1f}%={min(15, change_pct*2):.0f} + 换手率{turnover_rate:.1f}%={min(12, max(0, turnover_rate-10)*2):.0f} + 负面信号{negative_count}={negative_count*8} + 见顶组合{len(bearish_combos)}={len(bearish_combos)*10}")

        return risk_score

    def _get_dynamic_threshold(self):
        """动态评分门槛

        盘中实时（工作日 9:00-15:00）：25（数据最新、可立即执行）
        盘后/盘前/周末：40（数据为收盘价，次日或更晚才能交易，时效性等同于周末）
        """
        import datetime
        now = datetime.datetime.now()

        if now.weekday() < 5 and 9 <= now.hour < 15:
            return 25  # 盘中实时分析
        return 40      # 盘后、盘前、周末统一 40

    def _get_market_environment_factor(self):
        """获取市场环境因子（基于真实上证指数行情，取值范围0.85-1.15）

        数据源：akshare 上证指数日K线（优先新浪 stock_zh_index_daily，备选东财 index_zh_a_hist）
        计算公式：factor = 1.0 + 0.15 × 综合动量分
          综合动量分 = 0.5×s5 + 0.3×s20 + 0.2×sp（各分量截断到[-1,1]）
          s5  = 近5日涨幅 / 5%
          s20 = 近20日涨幅 / 10%
          sp  = 最新收盘价相对20日均线的偏离 / 5%
        缓存：同一交易日进程内只拉取一次；失败后10分钟内不重复请求
        兜底：数据不可用时返回中性值1.0（不使用随机数、不使用模拟数据）
        """
        import time as _time
        import datetime as _datetime

        today = _datetime.date.today().isoformat()
        cache = StockAnalyzer._market_env_cache

        # 当日已成功计算过，直接使用缓存
        if cache.get('date') == today and cache.get('factor') is not None:
            return cache['factor']

        # 距上次拉取失败不足10分钟，直接使用中性值，避免每只股票都重复请求
        if _time.time() < cache.get('retry_after', 0):
            return 1.0

        factor = self._fetch_market_environment_factor()
        if factor is None:
            StockAnalyzer._market_env_cache['retry_after'] = _time.time() + 600
            logger.warning("市场指数数据不可用，本次使用中性因子1.0（不调整评分），10分钟后自动重试")
            return 1.0

        StockAnalyzer._market_env_cache.update({'date': today, 'factor': factor, 'retry_after': 0})
        return factor

    def _fetch_market_environment_factor(self):
        """拉取真实指数数据并计算市场环境因子；数据不可用时返回None（不编造数据）"""
        if ak is None:
            logger.warning("akshare未安装，无法获取真实市场指数数据")
            return None

        import datetime as _datetime

        closes = None
        last_date = None

        # 数据源1：新浪财经 上证指数日K线
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty and 'close' in df.columns:
                closes = pd.to_numeric(df['close'], errors='coerce').dropna().reset_index(drop=True)
                if 'date' in df.columns:
                    last_date = str(df['date'].iloc[-1])
        except Exception as e:
            logger.debug(f"新浪指数接口获取失败: {str(e)}")

        # 数据源2：东方财富 上证指数日K线（备选）
        if closes is None or len(closes) < 21:
            try:
                end = _datetime.datetime.now().strftime('%Y%m%d')
                start = (_datetime.datetime.now() - _datetime.timedelta(days=90)).strftime('%Y%m%d')
                df = ak.index_zh_a_hist(symbol="000001", period="daily",
                                        start_date=start, end_date=end)
                if df is not None and not df.empty and '收盘' in df.columns:
                    closes = pd.to_numeric(df['收盘'], errors='coerce').dropna().reset_index(drop=True)
                    if '日期' in df.columns:
                        last_date = str(df['日期'].iloc[-1])
            except Exception as e:
                logger.debug(f"东财指数接口获取失败: {str(e)}")

        # ---- 数据有效性校验（不通过则不使用，返回None交由上层兜底）----
        if closes is None or len(closes) < 21:
            logger.warning("市场指数数据不足（需至少21个交易日），无法计算市场环境因子")
            return None

        if last_date:
            try:
                ld = _datetime.datetime.strptime(last_date[:10], '%Y-%m-%d').date()
                stale_days = (_datetime.date.today() - ld).days
                if stale_days > 10:
                    logger.warning(f"市场指数数据过期（最后交易日{last_date}，距今{stale_days}天），不使用过期数据")
                    return None
            except ValueError:
                logger.debug(f"无法解析指数最后交易日: {last_date}")

        # ---- 因子计算 ----
        latest = float(closes.iloc[-1])
        ret5 = latest / float(closes.iloc[-6]) - 1.0
        ret20 = latest / float(closes.iloc[-21]) - 1.0
        ma20 = float(closes.tail(20).mean())
        pos = latest / ma20 - 1.0

        s5 = max(-1.0, min(1.0, ret5 / 0.05))
        s20 = max(-1.0, min(1.0, ret20 / 0.10))
        sp = max(-1.0, min(1.0, pos / 0.05))
        composite = 0.5 * s5 + 0.3 * s20 + 0.2 * sp
        factor = 1.0 + 0.05 * composite  # v2: 压缩至0.95-1.05，避免评分饱和
        factor = max(0.95, min(1.05, factor))

        logger.info(
            f"市场环境因子={factor:.3f} | 5日涨幅{ret5*100:.2f}% 20日涨幅{ret20*100:.2f}% "
            f"20日线偏离{pos*100:.2f}% | 数据截至{last_date}"
        )
        return factor

    def _get_industry_momentum_factor(self, industry):
        """获取行业动量因子（v2: 压缩区间避免评分饱和）
        热门行业1.1倍 / 相关行业1.05倍 / 普通行业1.0倍
        """
        if not industry:
            return 1.0

        # 热门行业
        hot_industries = ['人工智能', '新能源', '半导体', '医药生物', '数字经济',
                         '云计算', '5G', '新能源汽车', '光伏', '风电']

        if any(hot in industry for hot in hot_industries):
            return 1.1
        elif any(keyword in industry for keyword in ['科技', '创新', '智能']):
            return 1.05
        else:
            return 1.0

    def _get_liquidity_factor(self, liquid_shares):
        """获取流动性因子（v2: 压缩区间避免评分饱和）"""
        if not liquid_shares:
            return 1.0

        # 中等市值股票流动性最佳
        if 500000000 <= liquid_shares <= 2000000000:  # 5亿-20亿股
            return 1.02
        elif liquid_shares < 500000000:  # 小盘股
            return 1.01
        else:  # 大盘股
            return 0.98

    def _get_valuation_factor(self, pe, pb):
        """获取估值因子（v2: 压缩区间避免评分饱和）
        PE合理估值(10-25)1.05倍 / 偏高估值(25-40)0.97倍 / 高估值(>40)或负估值0.90倍
        PB分析逻辑与PE类似：合理(1-3)1.05倍 / 偏高(3-5)0.97倍 / 高估值(>5)0.90倍
        低估值区间（PE、PB低于合理区间下限）视为安全边际高，同享1.05倍
        数据缺失时不调整（1.0）
        """
        factor = 1.0

        # PE估值分析
        if pe is not None and pe > 0:
            if pe > 40:  # 高估值
                factor *= 0.90
            elif pe > 25:  # 偏高估值
                factor *= 0.97
            else:  # 10-25合理估值，0-10低估值（安全边际高）
                factor *= 1.05
        elif pe is not None and pe <= 0:  # 负估值（亏损）
            factor *= 0.90

        # PB估值分析（与PE分析逻辑类似）
        if pb is not None and pb > 0:
            if pb > 5:  # 高估值
                factor *= 0.90
            elif pb > 3:  # 偏高估值
                factor *= 0.97
            else:  # 1-3合理估值，0-1破净低估（安全边际高）
                factor *= 1.05

        return factor


if __name__ == "__main__":
    # 测试股票分析器
    from data_collector import StockDataCollector
    from stock_selector import StockSelector
    
    try:
        collector = StockDataCollector()
        stocks = collector.get_all_stocks(limit=5)  # 只获取5只有效股票进行测试
        
        selector = StockSelector(stocks)
        selected = selector.select_by_kline_pattern()
        
        analyzer = StockAnalyzer(selected)
        analyzed = analyzer.analyze_stocks()
        
        logger.info(f"测试完成，共分析 {len(analyzed)} 只股票")
        for stock in analyzed:
            logger.info(f"{stock['code']} - {stock['name']} - 综合评分: {stock['score']:.2f}")
            logger.info(f"  基本面得分: {stock['fundamental_score']:.2f}")
            logger.info(f"  技术面得分: {stock['technical_score']:.2f}")
            logger.info(f"  行业: {stock['industry']}")
            logger.info(f"  积极指标: {stock['positive_indicators']}")
            
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")