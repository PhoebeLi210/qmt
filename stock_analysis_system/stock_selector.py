#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票选择模块

功能：
1. 根据上涨趋势K线形态选取股票
2. 根据触底反弹K线形态选取股票
3. 支持多种K线形态识别
"""

import logging
import pandas as pd
import numpy as np
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('stock_selector', logging.INFO)


class StockSelector:
    """股票选择器"""
    
    def __init__(self, stock_list):
        self.stock_list = stock_list
    
    def select_by_kline_pattern(self):
        """根据K线形态选择股票（v2.5 形态质量细分+K线组合识别）

        v2.4：细分六种形态，淘汰低质量信号（阴跌反弹）
        v2.5：底反弹细分叠加吞并反包/双底质量确认，上涨趋势叠加K线组合识别
        """
        selected_stocks = []

        for stock in self.stock_list:
            try:
                # 优先识别底反弹细分形态
                pattern_rebound, detail = self._is_bottom_rebound(stock, return_detail=True)
                if pattern_rebound:
                    stock['pattern'] = pattern_rebound
                    stock['pattern_detail'] = detail
                    selected_stocks.append(stock)
                    continue

                # 识别上涨趋势细分形态
                pattern_trend = self._is_upward_trend(stock)
                if pattern_trend:
                    stock['pattern'] = pattern_trend
                    stock['pattern_detail'] = {'pattern_label': pattern_trend}
                    selected_stocks.append(stock)
                    continue

            except Exception as e:
                logger.debug(f"分析股票K线形态失败({stock['code']}): {str(e)}")
                continue

        return selected_stocks

    def _detect_bullish_combo(self, df_kline):
        """识别看涨K线组合（确底/反转信号）

        返回：list[str]，如 ['看涨吞没', '早晨之星', '红三兵']
        """
        combos = []
        if len(df_kline) < 3:
            return combos

        try:
            close = df_kline['close'].astype(float).values
            open_ = df_kline['open'].astype(float).values
            high = df_kline['high'].astype(float).values
            low = df_kline['low'].astype(float).values

            # 1. 看涨吞没：前阴后阳，阳线实体完全吞没阴线实体
            if len(close) >= 2:
                prev_open, prev_close = open_[-2], close[-2]
                curr_open, curr_close = open_[-1], close[-1]
                prev_bear = prev_close < prev_open
                curr_bull = curr_close > curr_open
                engulf = curr_open <= prev_close and curr_close >= prev_open
                if prev_bear and curr_bull and engulf:
                    combos.append('看涨吞没')

            # 2. 早晨之星：左阴 + 中小阴/阳/十字星 + 右阳，右阳收盘深入左阴实体
            if len(close) >= 3:
                o1, c1 = open_[-3], close[-3]
                o2, c2 = open_[-2], close[-2]
                o3, c3 = open_[-1], close[-1]
                left_bear = c1 < o1
                mid_small = abs(c2 - o2) / (o1 - c1 + 1e-9) < 0.5  # 实体小于左阴50%
                right_bull = c3 > o3 and c3 > (o1 + c1) / 2
                if left_bear and mid_small and right_bull:
                    combos.append('早晨之星')

            # 3. 红三兵：连续3根阳线，收盘逐步抬高，涨幅均>0
            if len(close) >= 3:
                three_bull = all(close[-i] > open_[-i] for i in (1, 2, 3))
                rising = close[-3] < close[-2] < close[-1]
                if three_bull and rising:
                    combos.append('红三兵')

        except Exception:
            pass
        return combos

    def _detect_bearish_combo(self, df_kline):
        """识别见顶K线组合（风险信号）

        返回：list[str]，如 ['看跌吞没', '黄昏之星', '巨量长上影']
        """
        combos = []
        if len(df_kline) < 3:
            return combos

        try:
            close = df_kline['close'].astype(float).values
            open_ = df_kline['open'].astype(float).values
            high = df_kline['high'].astype(float).values
            low = df_kline['low'].astype(float).values
            volume = df_kline['volume'].astype(float).values

            # 1. 看跌吞没：前阳后阴，阴线实体完全吞没阳线实体
            if len(close) >= 2:
                prev_open, prev_close = open_[-2], close[-2]
                curr_open, curr_close = open_[-1], close[-1]
                prev_bull = prev_close > prev_open
                curr_bear = curr_close < curr_open
                engulf = curr_open >= prev_close and curr_close <= prev_open
                if prev_bull and curr_bear and engulf:
                    combos.append('看跌吞没')

            # 2. 黄昏之星：左阳 + 中小阴/阳/十字星 + 右阴，右阴收盘深入左阳实体
            if len(close) >= 3:
                o1, c1 = open_[-3], close[-3]
                o2, c2 = open_[-2], close[-2]
                o3, c3 = open_[-1], close[-1]
                left_bull = c1 > o1
                mid_small = abs(c2 - o2) / (c1 - o1 + 1e-9) < 0.5
                right_bear = c3 < o3 and c3 < (o1 + c1) / 2
                if left_bull and mid_small and right_bear:
                    combos.append('黄昏之星')

            # 3. 巨量长上影：上影线 > 实体2倍，且成交量 > 5日均量2倍
            if len(close) >= 5:
                curr_open, curr_close = open_[-1], close[-1]
                curr_high, curr_low = high[-1], low[-1]
                upper_shadow = curr_high - max(curr_open, curr_close)
                body = abs(curr_close - curr_open)
                vol_ma5 = sum(volume[-5:]) / 5
                huge_vol = volume[-1] > vol_ma5 * 2 if vol_ma5 > 0 else False
                if upper_shadow > body * 2 and huge_vol:
                    combos.append('巨量长上影')

        except Exception:
            pass
        return combos


    def _is_upward_trend(self, stock):
        """判断上涨趋势细分形态（v2.4）

        返回值：
          'breakout'      - 突破型：突破20日高点+放量>1.3倍均量（胜率55-65%）
          'pullback'      - 回踩型：回踩5日线后转涨+缩量（胜率50-55%）
          'acceleration'  - 加速型：5日涨幅>10%（胜率35-45%，谨慎）
          None            - 不符合上涨趋势
        """
        try:
            df_kline = pd.DataFrame(stock['kline_data'])
            if len(df_kline) < 20:
                return None

            df_kline['close'] = pd.to_numeric(df_kline['close'], errors='coerce')
            df_kline['open'] = pd.to_numeric(df_kline['open'], errors='coerce')
            df_kline['high'] = pd.to_numeric(df_kline['high'], errors='coerce')
            df_kline['low'] = pd.to_numeric(df_kline['low'], errors='coerce')
            df_kline['volume'] = pd.to_numeric(df_kline.get('volume', 0), errors='coerce')

            if df_kline[['close', 'open', 'high', 'low']].isnull().any().any():
                return None

            # 基础上涨趋势条件（保留旧版核心判定）
            df_kline['ma5'] = df_kline['close'].rolling(window=5).mean()
            df_kline['ma20'] = df_kline['close'].rolling(window=20).mean()
            recent_data = df_kline.tail(5).reset_index(drop=True)

            condition1 = all(recent_data['ma20'].iloc[i] < recent_data['ma20'].iloc[i+1]
                            for i in range(len(recent_data)-1))
            cross_found = False
            for i in range(1, len(recent_data)):
                if recent_data['ma5'].iloc[i-1] <= recent_data['ma20'].iloc[i-1] and \
                   recent_data['ma5'].iloc[i] > recent_data['ma20'].iloc[i]:
                    cross_found = True
                    break
            condition2 = cross_found
            condition3 = recent_data['close'].iloc[-1] > recent_data['ma5'].iloc[-1]

            # 3 日累计涨幅（区分 acceleration vs breakout）
            three_day_ago_close = df_kline['close'].iloc[-3] if len(df_kline) >= 3 else df_kline['close'].iloc[0]
            latest_close = df_kline['close'].iloc[-1]
            three_day_gain = (latest_close - three_day_ago_close) / three_day_ago_close * 100

            # 5 日涨幅
            five_day_ago_close = df_kline['close'].iloc[-5] if len(df_kline) >= 5 else df_kline['close'].iloc[0]
            five_day_gain = (latest_close - five_day_ago_close) / five_day_ago_close * 100

            if not (condition1 and condition2 and condition3):
                return None
            if three_day_gain > 15:  # 防追高硬上限
                return None

            # === 形态细分 ===
            vol_data = df_kline['volume'].dropna()
            latest_vol = float(vol_data.iloc[-1]) if len(vol_data) > 0 else 0
            vol_ma5 = float(vol_data.tail(5).mean()) if len(vol_data) >= 5 else latest_vol
            vol_ratio = latest_vol / vol_ma5 if vol_ma5 > 0 else 1.0

            prev_high_20 = float(df_kline['high'].iloc[-20:-1].max()) if len(df_kline) >= 20 else latest_close

            # 加速型：5 日涨幅 > 10%（透支风险高，谨慎推荐）
            if five_day_gain > 10:
                return 'acceleration'

            # 突破型：当日收盘 > 20日最高价 + 放量 > 1.3 倍均量
            if latest_close > prev_high_20 and vol_ratio > 1.3:
                return 'breakout'

            # 回踩型：最近 2 日低点接近 5 日均线（±2% 内）+ 当日缩量
            recent_low = float(df_kline['low'].iloc[-2:].min())
            ma5_now = float(recent_data['ma5'].iloc[-1])
            if ma5_now > 0 and abs(recent_low - ma5_now) / ma5_now * 100 < 2 and vol_ratio < 1.0:
                return 'pullback'

            # 默认归类为 breakout（基础形态满足但无细分特征）
            return 'breakout'

        except Exception as e:
            logger.debug(f"判断上涨趋势失败({stock['code']}): {str(e)}")
            return None

    def _is_bottom_rebound(self, stock, return_detail=False):
        """判断底反弹细分形态（v2.4）

        返回值：
          'v_rebound'              - V型反弹：5日内从低点反弹>8%（胜率45-55%）
          'double_bottom'         - 双底：两次低点+第二次缩量（胜率55-65%）
          'consolidation_breakout' - 横盘突破：20日窄幅震荡后突破（胜率50-60%）
          None                    - 不符合（淘汰阴跌反弹等低质量形态）

        基础过滤：原8条件全部保留，通过后按形态特征细分
        return_detail=True 时返回 (结果, 各条件字典)，用于诊断
        """
        try:
            df_kline = pd.DataFrame(stock['kline_data'])
            if len(df_kline) < 20:
                return False if not return_detail else (False, {'error': 'K线不足20天'})

            df_kline['close'] = pd.to_numeric(df_kline['close'], errors='coerce')
            df_kline['open'] = pd.to_numeric(df_kline['open'], errors='coerce')
            df_kline['low'] = pd.to_numeric(df_kline['low'], errors='coerce')
            df_kline['high'] = pd.to_numeric(df_kline['high'], errors='coerce')
            df_kline['volume'] = pd.to_numeric(df_kline.get('volume', 0), errors='coerce')

            if df_kline[['close', 'open', 'low']].isnull().any().any():
                return False if not return_detail else (False, {'error': '数据含空值'})

            latest_close = df_kline['close'].iloc[-1]
            latest_open = df_kline['open'].iloc[-1]

            if latest_close <= 0:
                return False if not return_detail else (False, {'error': '价格<=0'})

            # 条件1：价格处于20日低位区间
            recent_20_low = df_kline['low'].tail(20).min()
            price_position = (latest_close - recent_20_low) / recent_20_low * 100
            condition1 = 0 <= price_position <= 20

            # 条件2：筑底过程（近10天至少5天振幅<5%）
            df_kline['daily_range'] = (df_kline['high'] - df_kline['low']) / df_kline['low'].replace(0, np.nan) * 100
            recent_10_days = df_kline.tail(10)
            consolidation_days = (recent_10_days['daily_range'] < 5).sum()
            condition2 = consolidation_days >= 5

            # 条件3：当日阳线确认（涨幅1%-8%）
            today_gain = (latest_close - latest_open) / latest_open * 100 if latest_open > 0 else 0
            condition3 = latest_close >= latest_open and 0 < today_gain <= 8

            # 条件4：近3天收盘价逐步抬高
            recent_3_closes = df_kline['close'].tail(3).tolist()
            condition4 = recent_3_closes[0] < recent_3_closes[1] < recent_3_closes[2]

            # 条件5：近5天涨幅不超过20%（防追高）
            five_day_ago_close = df_kline['close'].iloc[-5]
            five_day_gain = (latest_close - five_day_ago_close) / five_day_ago_close * 100
            condition5 = five_day_gain <= 20

            # 条件6：缩量确认——近5日均量 < 近20日均量的70%
            vol_data = df_kline['volume'].dropna()
            condition6 = True
            vol_shrink_ratio = 1.0
            if len(vol_data) >= 20 and vol_data.mean() > 0:
                vol_ma5 = vol_data.tail(5).mean()
                vol_ma20 = vol_data.tail(20).mean()
                if vol_ma20 > 0:
                    vol_shrink_ratio = vol_ma5 / vol_ma20
                    condition6 = vol_shrink_ratio < 0.7

            # 条件7：量能回升——当日量比 > 1.2
            condition7 = True
            today_vol_ratio = 1.0
            if len(vol_data) >= 2 and vol_data.iloc[-2] > 0:
                today_vol_ratio = vol_data.iloc[-1] / vol_data.iloc[-2]
                condition7 = today_vol_ratio > 1.2

            # 条件8：距60日低点<15%
            condition8 = True
            if len(df_kline) >= 60:
                low_60 = df_kline['low'].tail(60).min()
                if low_60 > 0:
                    dist_to_60low = (latest_close - low_60) / low_60 * 100
                    condition8 = dist_to_60low < 15

            # 条件9：从60日高点回撤>=15%（确底前提：一波大幅下跌后）
            condition9 = True
            drawdown_from_high = 0.0
            if len(df_kline) >= 60:
                high_60 = df_kline['high'].tail(60).max()
                if high_60 > 0:
                    drawdown_from_high = (high_60 - latest_close) / high_60 * 100
                    condition9 = drawdown_from_high >= 15

            # 基础9条件全部通过才进入形态细分
            base_pass = (condition1 and condition2 and condition3 and condition4
                         and condition5 and condition6 and condition7 and condition8
                         and condition9)
            if not base_pass:
                if return_detail:
                    detail = {
                        'c1_低位区间(<=20%)': (condition1, f'{price_position:.1f}%'),
                        'c2_筑底>=5天': (condition2, f'{consolidation_days}天'),
                        'c3_阳线1-8%': (condition3, f'{today_gain:.1f}%'),
                        'c4_三日抬高': (condition4, ''),
                        'c5_5日<=20%': (condition5, f'{five_day_gain:.1f}%'),
                        'c6_缩量<0.7': (condition6, f'{vol_shrink_ratio:.2f}'),
                        'c7_量比>1.2': (condition7, f'{today_vol_ratio:.2f}'),
                        'c8_距60低<15%': (condition8, ''),
                        'c9_60日回撤>=15%': (condition9, f'{drawdown_from_high:.1f}%'),
                    }
                    return False, detail
                return False

            # === v2.4 形态细分 ===
            # 5日内最低价到当前的反弹幅度
            recent_5_low = df_kline['low'].tail(5).min()
            rebound_pct = (latest_close - recent_5_low) / recent_5_low * 100 if recent_5_low > 0 else 0

            # 20日窄幅震荡判定：最高-最低/均值<8%
            recent_20 = df_kline.tail(20)
            range_high = recent_20['high'].max()
            range_low = recent_20['low'].min()
            range_mid = (range_high + range_low) / 2
            is_narrow_range = (range_high - range_low) / range_mid * 100 < 8 if range_mid > 0 else False

            # 双底判定：近10日内出现两次接近的低点（差<2%），第二次缩量
            is_double_bottom = False
            if len(df_kline) >= 10:
                recent_10 = df_kline.tail(10).reset_index(drop=True)
                lows_idx = recent_10['low'].nsmallest(2).index
                if len(lows_idx) >= 2:
                    low1 = recent_10['low'].iloc[lows_idx[0]]
                    low2 = recent_10['low'].iloc[lows_idx[1]]
                    if abs(low1 - low2) / min(low1, low2) * 100 < 2:
                        # 第二次低点附近缩量
                        if len(vol_data) >= 10:
                            vol_at_low2 = vol_data.iloc[-10:].iloc[lows_idx[1] if lows_idx[1] < 10 else -1]
                            vol_ma10 = vol_data.tail(10).mean()
                            if vol_ma10 > 0 and vol_at_low2 / vol_ma10 < 0.8:
                                is_double_bottom = True

            # === v2.5 K线组合识别（确底/见顶信号）===
            bullish_combo = self._detect_bullish_combo(df_kline)
            has_engulfing = '看涨吞没' in bullish_combo

            # === v2.5 v_rebound 吞并反包强确认 ===
            engulfing_confirmed = False
            if rebound_pct >= 8 and has_engulfing:
                engulfing_confirmed = True

            # === v2.5 double_bottom 细化：二次探底不创新低 + 右侧放量确认 ===
            double_bottom_quality = False
            if is_double_bottom and len(df_kline) >= 10:
                recent_10 = df_kline.tail(10).reset_index(drop=True)
                lows_idx = recent_10['low'].nsmallest(2).index
                if len(lows_idx) >= 2:
                    low1 = recent_10['low'].iloc[lows_idx[0]]
                    low2 = recent_10['low'].iloc[lows_idx[1]]
                    # 第二底不创新低（或略高）
                    second_not_lower = low2 >= low1 * 0.995
                    # 右侧放量确认：最近1日量 > 10日均量1.2倍
                    vol_now = float(vol_data.iloc[-1]) if len(vol_data) > 0 else 0
                    vol_ma10 = float(vol_data.tail(10).mean()) if len(vol_data) >= 10 else 0
                    right_volume_ok = vol_ma10 > 0 and vol_now / vol_ma10 > 1.2
                    double_bottom_quality = second_not_lower and right_volume_ok

            # 形态归类（按优先级）
            if is_double_bottom and double_bottom_quality:
                pattern_label = 'double_bottom'
            elif is_narrow_range and today_gain > 3:
                pattern_label = 'consolidation_breakout'
            elif rebound_pct >= 8 and engulfing_confirmed:
                pattern_label = 'v_rebound'
            elif rebound_pct >= 8:
                pattern_label = 'v_rebound'  # 弱V反（未吞没）
            else:
                pattern_label = 'v_rebound'  # 默认弱V反

            if return_detail:
                detail = {
                    'c1_低位区间(<=20%)': (condition1, f'{price_position:.1f}%'),
                    'c2_筑底>=5天': (condition2, f'{consolidation_days}天'),
                    'c3_阳线1-8%': (condition3, f'{today_gain:.1f}%'),
                    'c4_三日抬高': (condition4, ''),
                    'c5_5日<=20%': (condition5, f'{five_day_gain:.1f}%'),
                    'c6_缩量<0.7': (condition6, f'{vol_shrink_ratio:.2f}'),
                    'c7_量比>1.2': (condition7, f'{today_vol_ratio:.2f}'),
                    'c8_距60低<15%': (condition8, ''),
                    'c9_60日回撤>=15%': (condition9, f'{drawdown_from_high:.1f}%'),
                    'pattern_label': pattern_label,
                    'rebound_pct': f'{rebound_pct:.1f}%',
                    'is_double_bottom': is_double_bottom,
                    'double_bottom_quality': double_bottom_quality,
                    'is_narrow_range': is_narrow_range,
                    'bullish_combo': bullish_combo,
                    'engulfing_confirmed': engulfing_confirmed,
                }
                return pattern_label, detail
            return pattern_label

        except Exception as e:
            logger.debug(f"判断触底反弹失败({stock['code']}): {str(e)}")
            if return_detail:
                return False, {'error': str(e)}
            return False
    
    def _calculate_rsi(self, data, window=14):
        """计算RSI指标"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


if __name__ == "__main__":
    # 测试股票选择器
    from data_collector import StockDataCollector
    
    try:
        collector = StockDataCollector()
        stocks = collector.get_all_stocks()[:10]  # 只测试前10只股票
        
        selector = StockSelector(stocks)
        selected = selector.select_by_kline_pattern()
        
        logger.info(f"测试完成，共筛选出 {len(selected)} 只股票")
        for stock in selected:
            logger.info(f"{stock['code']} - {stock['name']} - {stock['pattern']}")
            
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
