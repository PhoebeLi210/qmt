#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票推荐引擎

功能：
1. 多维度预筛选（价格有效性、涨跌幅、换手率合理性检查）
2. 多维度评分排序（最终评分 > 积极指标数 > 基本面 > 技术面 > 流通股本）
3. 风险等级分类（低风险优先，中等风险次之，高风险最后）
4. 行业分散度控制（单个行业最多3只）
5. 动态推荐数量（根据分析股票总数确定：>=200只15个 / 150-199只12个 /
   100-149只10个 / 恰好100只8个 / <100只5个）
6. 增强推荐理由生成、风险等级评估与仓位建议
"""

import logging
from datetime import datetime
from utils.logger import setup_logger
from stock_analyzer import NEGATIVE_INDICATORS, NEUTRAL_INDICATORS
import strategy_params
from market_timing import COUNTER_TREND_PATTERNS

# 配置日志
logger = setup_logger('recommendation_engine', logging.INFO)


class RecommendationEngine:
    """股票推荐引擎"""

    # 热门行业列表（与行业动量因子保持一致）
    HOT_INDUSTRIES = ['人工智能', '新能源', '半导体', '医药生物', '数字经济',
                      '云计算', '5G', '新能源汽车', '光伏', '风电']

    def __init__(self, stock_list):
        self.stock_list = stock_list
        # 大盘择时状态缓存（进程内单例）
        self._market_regime = None  # 'bull' / 'neutral' / 'bear' / 'risk_off'

    def _get_market_regime(self):
        """v2.4 大盘择时（v2.5 起实现下沉到 market_timing，进程内按日缓存）

        bull / neutral / bear / risk_off 定义见 market_timing.py
        数据缺失时返回 'neutral'（不阻断推荐，仅降仓位）
        """
        if self._market_regime is None:
            from market_timing import get_market_regime as _get_regime
            self._market_regime = _get_regime()
        return self._market_regime

    def generate_recommendations(self):
        """生成股票推荐清单（按文档设计的四步流程）"""
        if not self.stock_list:
            logger.warning("没有可推荐的股票")
            return []

        # v2.4 大盘择时
        regime = self._get_market_regime()

        # v2.5 bear：暂停全市场推荐（lab归因：防守市信号胜率仅8.7%；自选分析不受影响）
        if regime == 'bear':
            logger.warning("大盘择时 bear（收盘<MA20），本日暂停全市场推荐，建议空仓等待")
            return []

        # v2.5 防守市剔除反转型形态（lab归因：v_rebound 0胜46负、double_bottom 0胜5负——下跌市抄底=接飞刀）
        if regime == 'risk_off':
            _before = len(self.stock_list)
            self.stock_list = [s for s in self.stock_list
                               if (s.get('pattern') or '') not in COUNTER_TREND_PATTERNS]
            if len(self.stock_list) != _before:
                logger.info(f"防守市(risk_off)剔除反转型形态: {_before} -> {len(self.stock_list)} 只")

        total_analyzed = len(self.stock_list)

        # 4.1 多维度预筛选（含相对强度过滤）
        filtered_stocks = self._pre_filter_stocks(self.stock_list)
        logger.info(f"预筛选后剩余 {len(filtered_stocks)}/{total_analyzed} 只股票")

        # 4.2 多维度评分排序
        sorted_stocks = sorted(filtered_stocks, key=self._multi_criteria_sort_key, reverse=True)

        # 4.3 风险等级分类（低风险优先 → 中等风险 → 高风险）
        risk_classified = self._classify_by_risk_level(sorted_stocks)

        # 4.4 行业分散度控制（单个行业最多3只）
        diversified_stocks = self._ensure_industry_diversification(risk_classified)

        # 4.5 动态推荐数量（根据分析股票总数确定，结合大盘择时调整）
        base_count = self._get_dynamic_recommendation_count(total_analyzed)
        # v2.5 大盘择时对推荐数量的影响（bear 已在上方返回空；risk_off 限流×0.5）
        regime_count_factor = {'bull': 1.0, 'neutral': 0.7, 'bear': 0.0, 'risk_off': 0.5}
        recommended_count = max(1, int(base_count * regime_count_factor.get(regime, 0.7)))
        recommended_stocks = diversified_stocks[:recommended_count]
        # v2.5 risk_off 防守限流硬顶（当前动态基数≤15，此为防御性上限）
        if regime == 'risk_off':
            recommended_stocks = recommended_stocks[:20]

        # 4.6-4.8 增强推荐理由、风险等级、仓位建议（v2.2按排名差异化加权）、止损止盈
        # v2.4 仓位再受大盘择时因子影响（v2.5：risk_off 仓位×0.5）
        regime_position_factor = {'bull': 1.0, 'neutral': 0.7, 'bear': 0.5, 'risk_off': 0.5}
        pos_factor = regime_position_factor.get(regime, 0.7)
        total_n = len(recommended_stocks)
        for rank, stock in enumerate(recommended_stocks):
            stock['recommendation_reason'] = self._generate_enhanced_reason(stock)
            stock['recommendation_date'] = datetime.now().strftime('%Y-%m-%d')
            stock['risk_level'] = self._assess_risk_level(stock)
            stock['position_sizing'] = self._suggest_position_size(stock, rank, total_n)
            # v2.4 大盘择时附加提示
            if regime in ('bear', 'neutral'):
                stock['position_sizing'] = f"{stock['position_sizing']} [大盘{regime}×{pos_factor}]"
            stock['market_regime'] = regime
            # 止损止盈策略
            exit_strategy = self._suggest_exit_strategy(stock)
            stock['stop_loss'] = exit_strategy['stop_loss']
            stock['take_profit'] = exit_strategy['take_profit']
            stock['time_stop'] = exit_strategy['time_stop']

        logger.info(f"分析股票总数{total_analyzed}只，动态推荐{recommended_count}只（大盘{regime}），"
                    f"实际生成 {len(recommended_stocks)} 只推荐清单")
        return recommended_stocks

    def _pre_filter_stocks(self, stocks):
        """4.1 多维度预筛选（v2: 增加相对强度过滤）

        - 基本数据完整性：最新价格必须大于0
        - 价格合理性：涨跌幅超过20%则跳过（避免极端波动风险）
        - 换手率合理性：换手率超过30%则跳过（避免过度投机风险）
        - 【v2新增】相对强度过滤：20日跌幅>15%的股票跳过（下跌动能过强，即使触底反弹也难持续）
        """
        filtered = []

        for stock in stocks:
            # 基本数据完整性检查：价格必须大于0
            latest_price = stock.get('latest_price', 0) or 0
            if latest_price <= 0:
                continue

            # 价格合理性检查：涨跌幅超过20%跳过
            change_pct = abs(stock.get('change_pct', 0) or 0)
            if change_pct > 20:
                continue

            # 换手率合理性检查：换手率超过30%跳过
            turnover_rate = stock.get('turnover_rate', 0) or 0
            if turnover_rate > 30:
                continue

            # 【v2新增】相对强度过滤：20日跌幅>15%跳过
            kline_data = stock.get('kline_data', [])
            if kline_data and len(kline_data) >= 20:
                try:
                    closes = [float(d.get('close', 0)) for d in kline_data if d.get('close')]
                    if len(closes) >= 20 and closes[-20] > 0:
                        ret_20 = (closes[-1] - closes[-20]) / closes[-20] * 100
                        if ret_20 < -15:
                            continue  # 20日跌幅过大，下跌动能过强
                except (ValueError, TypeError, IndexError):
                    pass  # K线数据解析失败不拦截

            filtered.append(stock)

        return filtered

    def _get_truly_positive_count(self, stock):
        """统计真正的积极技术指标数量（排除负面与中性信号）"""
        indicators = stock.get('positive_indicators', []) or []
        return len([i for i in indicators
                    if i not in NEGATIVE_INDICATORS and i not in NEUTRAL_INDICATORS])

    def _multi_criteria_sort_key(self, stock):
        """4.2 多维度评分排序键

        优先级：最终评分 > 积极技术指标数量 > 基本面评分 > 技术面评分 > 流通股本（越小越好）
        """
        final_score = stock.get('final_score', 0) or 0
        positive_count = self._get_truly_positive_count(stock)
        fundamental_score = stock.get('fundamental_score', 0) or 0
        technical_score = stock.get('technical_score', 0) or 0
        # 流通股本越小越好；缺失时视为无穷大（排最后）
        liquid_shares = stock.get('liquid_shares')
        liquid_key = -(liquid_shares if liquid_shares else float('inf'))

        return (final_score, positive_count, fundamental_score, technical_score, liquid_key)

    def _assess_risk_level(self, stock):
        """4.7 风险等级评估（基于风险评分：0-15低风险 / 16-30中等风险 / >30高风险）"""
        risk_score = stock.get('risk_score', 0) or 0

        if risk_score <= 15:
            return '低风险'
        elif risk_score <= 30:
            return '中等风险'
        else:
            return '高风险'

    def _classify_by_risk_level(self, stocks):
        """4.3 风险等级分类

        排序原则：先低风险，再中等风险，最后高风险（各组内保持多维度排序顺序）
        """
        low_risk = []
        medium_risk = []
        high_risk = []

        for stock in stocks:
            risk_level = self._assess_risk_level(stock)
            if risk_level == '低风险':
                low_risk.append(stock)
            elif risk_level == '中等风险':
                medium_risk.append(stock)
            else:
                high_risk.append(stock)

        logger.info(f"风险分类结果: 低风险{len(low_risk)}只, 中等风险{len(medium_risk)}只, "
                    f"高风险{len(high_risk)}只")

        return low_risk + medium_risk + high_risk

    def _ensure_industry_diversification(self, stocks):
        """4.4 行业分散度控制（单个行业最多推荐3只，避免行业集中风险）

        注意：行业字段缺失（'未知'）的股票彼此并非同一行业，不受单行业限额约束，
        否则数据源故障时（行业全空）会把全部股票误判为一个行业，导致推荐数量骤减。
        """
        industry_count = {}
        diversified = []
        max_per_industry = 3

        for stock in stocks:
            industry = stock.get('industry') or '未知'
            if industry == '未知':
                # 行业未知：不做行业限额
                diversified.append(stock)
                continue

            current_count = industry_count.get(industry, 0)
            if current_count < max_per_industry:
                diversified.append(stock)
                industry_count[industry] = current_count + 1

        return diversified

    def _get_dynamic_recommendation_count(self, total_analyzed):
        """4.5 动态推荐数量（根据实际分析的股票总数确定）

        >=200只：推荐15只（市场活跃、优质股票较多）
        150-199只：推荐12只
        100-149只：推荐10只（恰好100只时推荐8只）
        <100只：推荐5只（筛选标准严格时期，精选优质股票）
        """
        if total_analyzed >= 200:
            return 15
        elif total_analyzed >= 150:
            return 12
        elif total_analyzed == 100:
            return 8
        elif total_analyzed > 100:
            return 10
        else:
            return 5

    def _generate_enhanced_reason(self, stock):
        """4.6 增强推荐理由生成（形态 / 技术面 / 基本面 / 行业 / 综合评分）"""
        reasons = []

        # 形态分析理由（v2.4 细分形态）
        pattern = stock.get('pattern', '')
        pattern_reason_map = {
            'breakout': '突破20日高点放量突破',
            'pullback': '回踩5日线缩量企稳',
            'acceleration': '加速上涨(注意透支风险)',
            'v_rebound': 'V型反弹信号',
            'double_bottom': '双底形态(第二次缩量)',
            'consolidation_breakout': '横盘整理后突破',
            'upward_trend': '上涨趋势确认',
            'bottom_rebound': '触底反弹信号',
        }
        if pattern in pattern_reason_map:
            reasons.append(pattern_reason_map[pattern])

        # 技术面理由（同一类型的理由用中文顿号连接）
        indicators = stock.get('positive_indicators', []) or []
        technical_reasons = []
        for indicator in indicators:
            if indicator in NEGATIVE_INDICATORS or indicator in NEUTRAL_INDICATORS:
                continue
            if indicator == 'MACD金叉':
                text = 'MACD指标金叉'
            elif indicator == 'KDJ金叉':
                text = 'KDJ指标金叉'
            elif '放量' in indicator:
                text = '成交量放大'
            elif indicator == 'RSI正常':
                text = 'RSI指标健康'
            elif indicator == '多头排列':
                text = '均线多头排列'
            elif indicator == '超卖':
                text = '超卖状态存在反弹机会'
            elif '缩量' in indicator:
                text = '缩量整理'
            # v2.5 K线组合信号
            elif indicator == '看涨吞没':
                text = '看涨吞没组合'
            elif indicator == '早晨之星':
                text = '早晨之星'
            elif indicator == '红三兵':
                text = '红三兵'
            elif indicator == '吞并反包强确底':
                text = '吞并反包强确底'
            elif indicator == '双底右侧放量确认':
                text = '双底右侧放量确认'
            else:
                continue
            if text not in technical_reasons:
                technical_reasons.append(text)

        if technical_reasons:
            reasons.append('、'.join(technical_reasons))

        # 基本面理由（估值分析）
        pe = stock.get('pe', 0)
        if pe and 0 < pe < 30:
            reasons.append('估值合理(PE适中)')

        # 行业分析理由（热门行业识别）
        industry = stock.get('industry', '') or ''
        if industry:
            if industry in self.HOT_INDUSTRIES:
                reasons.append(f'属于热门行业({industry})')
            elif any(hot in industry for hot in self.HOT_INDUSTRIES):
                reasons.append(f'相关热门题材({industry})')

        # 综合评分理由
        score = stock.get('score', 0) or 0
        if score >= 90:
            reasons.append('综合评分优秀')
        elif score >= 80:
            reasons.append('综合评分良好')
        elif score >= 70:
            reasons.append('综合评分中等偏上')

        return '；'.join(reasons)

    def _suggest_position_size(self, stock, rank=0, recommendation_count=1):
        """4.8 仓位建议（v2.2：组合内按排名差异化加权）

        组合加权方案（总仓位=100%，按推荐排名三段分配）：
        - 前1/3（评分最高）：权重8（15只时=8%/只）
        - 中1/3：权重7（15只时=7%/只）
        - 后1/3：权重5（15只时=5%/只）
        权重归一化到100%，推荐数变化时单股仓位自适应。

        单股风险上限（基础档位，加权仓位不得超过）：
        重仓档25%：风险<=10 且 评分>=85
        中仓档17%：风险<=20 且 评分>=75
        轻仓档12%：风险<=30 且 评分>=65
        观察档3%：其余情况

        标签按最终仓位分档：
        重仓>=15% / 中仓8-15% / 轻仓4-8% / 观察<4%
        """
        risk_score = stock.get('risk_score', 0) or 0
        score = stock.get('score', 0) or 0

        # 单股基础仓位（风险上限）
        if risk_score <= 10 and score >= 85:
            base_pct = 25
        elif risk_score <= 20 and score >= 75:
            base_pct = 17
        elif risk_score <= 30 and score >= 65:
            base_pct = 12
        else:
            base_pct = 3  # 高风险/低评分：观察档

        # 组合加权：按排名分三段（8:7:5），归一化到总仓位100%
        n = max(recommendation_count, 1)
        third = n / 3
        weights = [8 if i < third else 7 if i < 2 * third else 5 for i in range(n)]
        total_w = sum(weights)
        w = weights[min(rank, n - 1)]
        weighted_pct = w / total_w * 100

        # 取组合加权值与个股风险上限的较小者
        final_pct = round(min(weighted_pct, base_pct))

        # 标签按实际仓位分档
        if final_pct >= 15:
            label = '重仓'
        elif final_pct >= 8:
            label = '中仓'
        elif final_pct >= 4:
            label = '轻仓'
        else:
            label = '观察'

        return f'建议{label}({final_pct}%)'

    def _calculate_atr(self, kline_data, period=14):
        """计算 ATR（真实波幅均值，简单平均）

        TR = max(当日最高-最低, |最高-前收|, |最低-前收|)
        数据不足或字段缺失时返回 None
        """
        if not kline_data or len(kline_data) < period + 1:
            return None
        recent = kline_data[-(period + 1):]
        trs = []
        for i in range(1, len(recent)):
            try:
                high = float(recent[i].get('high', 0) or 0)
                low = float(recent[i].get('low', 0) or 0)
                prev_close = float(recent[i - 1].get('close', 0) or 0)
            except (TypeError, ValueError):
                return None
            if high <= 0 or low <= 0 or prev_close <= 0:
                return None
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        return sum(trs) / len(trs) if trs else None

    def _suggest_exit_strategy(self, stock):
        """4.9 止损止盈策略（v2.4：保本移动止损 + 盈亏比硬约束 + 形态差异化）

        === v2.4 核心新增：保本移动止损（直接提升胜率15-20pp）===
        浮盈到一定阈值后止损上移至入场价或浮盈位置：
          浮盈 +3% → 止损上移至入场价（保本，原本 -5% 变成 0%）
          浮盈 +5% → 止损上移至 +2%
          浮盈 +8% → 减 1/3 仓，剩余启动移动止盈
        效果："涨了但没到止盈"的股票从亏损5-8%变为保本或微盈，胜率显著提升

        === 保留 v2.3 改进 ===
        - ATR 自适应止损（形态差异化：趋势股 5-8%，底反弹 3-5%）
        - 盈亏比硬约束：tp2/sl >= 2.0，不足自动上抬
        - 形态差异化止盈：趋势股 +8%/+15%，底反弹 +5%/+10%
        - 时间止损：趋势股 8 日，底反弹 5 日
        - 趋势股移动止盈：触+8%后启动
        """
        latest_price = stock.get('latest_price', 0) or 0
        risk_score = stock.get('risk_score', 0) or 0
        pattern = stock.get('pattern', '') or ''
        p = strategy_params.get_exit_params()

        if latest_price <= 0:
            return {'stop_loss': '无法计算(价格缺失)', 'take_profit': '无法计算',
                    'time_stop': '5个交易日',
                    # 数值字段（lab 追踪用）
                    'ref_price': 0.0, 'sl_pct': None, 'tp1_pct': None,
                    'tp2_pct': None, 'time_stop_days': None,
                    'param_version': strategy_params.active_version()}

        atr = self._calculate_atr(stock.get('kline_data', []))
        atr_note = ''
        # v2.4 形态名适配：英文细分形态名 + 兼容旧中文形态
        trend_patterns = ('breakout', 'pullback', 'acceleration', 'upward_trend', '上涨趋势')
        rebound_patterns = ('v_rebound', 'double_bottom', 'consolidation_breakout', 'bottom_rebound', '底反弹')
        is_trend = any(pat in pattern for pat in trend_patterns)
        is_rebound = any(pat in pattern for pat in rebound_patterns)

        # === ATR 自适应止损 ===
        if atr and atr > 0:
            if is_rebound:
                multiplier = (p['rebound_mult_low_risk'] if risk_score <= 20
                              else p['rebound_mult_high_risk'])
                sl_floor, sl_cap = p['rebound_sl_floor'], p['rebound_sl_cap']
            else:  # 上涨趋势或未识别
                multiplier = (p['trend_mult_high_risk'] if risk_score > 20
                              else p['trend_mult_low_risk'])
                sl_floor, sl_cap = p['trend_sl_floor'], p['trend_sl_cap']
            raw_pct = multiplier * atr / latest_price * 100
            sl_pct = round(min(max(raw_pct, sl_floor), sl_cap), 1)
            atr_note = f'，ATR{atr:.2f}'
        else:
            sl_pct = p['fallback_sl_rebound'] if is_rebound else p['fallback_sl_trend']

        stop_loss_price = round(latest_price * (1 - sl_pct / 100), 2)

        # === 止盈阶梯（形态差异化）===
        if is_trend:
            if 'breakout' in pattern:
                tp1_pct, tp2_pct, time_stop_days = tuple(p['tp_breakout'])
                tp1_action = '减1/3仓'
                tp2_action = '再减1/3，剩余启动移动止盈'
            else:  # pullback / acceleration
                tp1_pct, tp2_pct, time_stop_days = tuple(p['tp_trend'])
                tp1_action = '减半仓'
                tp2_action = '清仓'
        elif is_rebound:
            tp1_pct, tp2_pct, time_stop_days = tuple(p['tp_rebound'])
            tp1_action = '减半仓'
            tp2_action = '清仓'
        else:
            tp1_pct, tp2_pct, time_stop_days = tuple(p['tp_default'])
            tp1_action = '减半仓'
            tp2_action = '清仓'

        # === v2.5 见顶信号检测 → 收紧止盈 ===
        bearish_signals = stock.get('positive_indicators', [])
        has_top_signal = any(s in bearish_signals for s in ('看跌吞没', '黄昏之星', '巨量长上影'))
        top_tighten_note = ''
        if has_top_signal:
            # 收紧止盈到较小值
            tp1_pct = max(tp1_pct * p['top_signal_factor'], sl_pct * p['top_sl_floor_mult'])
            tp2_pct = max(tp2_pct * p['top_signal_factor'], sl_pct * p['top_sl_cap_mult'])
            top_tighten_note = ' [检测到见顶信号，止盈已收紧]'

        # === 盈亏比硬约束：tp2/sl >= 2.0，不足则上抬 tp2 ===
        rr_ratio = tp2_pct / sl_pct if sl_pct > 0 else 99
        if rr_ratio < p['rr_min']:
            tp2_pct = round(sl_pct * p['rr_tp2_mult'], 1)
            # 同时上抬 tp1 保持阶梯关系（tp1 = tp2/2）
            tp1_pct = round(tp2_pct / 2, 1)

        tp1_price = round(latest_price * (1 + tp1_pct / 100), 2)
        tp2_price = round(latest_price * (1 + tp2_pct / 100), 2)

        # === 移动止盈提示（仅趋势股）===
        trailing_note = ''
        if is_trend and atr and atr > 0:
            trailing_stop = round(latest_price - 1.5 * atr, 2)
            trailing_note = f'；触发{tp1_price}元后移动止损下沿={trailing_stop}元'

        # === v2.4 保本移动止损阶梯 ===
        # 浮盈+3% → 止损上移至入场价（保本）
        # 浮盈+5% → 止损上移至 +2%
        be1_price = round(latest_price * (1 + p['breakeven_step1'] / 100), 2)
        be2_price = round(latest_price * (1 + p['breakeven_step2'] / 100), 2)
        be1_stop = round(latest_price * (1 + p['breakeven_stop1'] / 100), 2)
        be2_stop = round(latest_price * (1 + p['breakeven_stop2'] / 100), 2)
        breakeven_note = (f'；浮盈{be1_price}元时止损上移至{be1_stop}元(保本)，'
                          f'浮盈{be2_price}元时止损上移至{be2_stop}元(+2%)')

        return {
            'stop_loss': f'{stop_loss_price}元(-{sl_pct:g}%{atr_note})',
            'take_profit': f'{tp1_price}元{tp1_action}，{tp2_price}元{tp2_action}{trailing_note}{breakeven_note}{top_tighten_note}',
            'time_stop': f'{time_stop_days}个交易日不涨则退出',
            # 数值字段（lab 信号追踪/止损止盈回放用）
            'ref_price': latest_price,
            'sl_pct': round(sl_pct, 2),
            'tp1_pct': round(tp1_pct, 2),
            'tp2_pct': round(tp2_pct, 2),
            'time_stop_days': int(time_stop_days),
            'sl_price': stop_loss_price,
            'tp1_price': tp1_price,
            'tp2_price': tp2_price,
            'param_version': strategy_params.active_version(),
        }


if __name__ == "__main__":
    # 测试推荐引擎
    from data_collector import StockDataCollector
    from stock_selector import StockSelector
    from stock_analyzer import StockAnalyzer

    try:
        collector = StockDataCollector()
        stocks = collector.get_all_stocks()[:10]

        selector = StockSelector(stocks)
        selected = selector.select_by_kline_pattern()

        analyzer = StockAnalyzer(selected)
        analyzed = analyzer.analyze_stocks()

        engine = RecommendationEngine(analyzed)
        recommendations = engine.generate_recommendations()

        logger.info(f"测试完成，生成了 {len(recommendations)} 只股票的推荐清单")
        for stock in recommendations:
            logger.info(f"{stock['code']} - {stock['name']} - 最终评分: {stock['final_score']:.2f}")
            logger.info(f"   风险等级: {stock['risk_level']} | 仓位建议: {stock['position_sizing']}")
            logger.info(f"   推荐理由: {stock['recommendation_reason']}")

    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
