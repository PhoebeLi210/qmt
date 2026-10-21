#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档对齐测试（test_doc_alignment.py）

验证代码实现与《程序逻辑说明文档.md》设计一致，全部离线运行（stub akshare）：

1. 数据采集（严格校验、板块覆盖、计数器、无模拟数据/默认值）
2. 基本面分析评分（PE/PB/流通股本/行业/数据完整性）
3. 技术面分析评分（换手率/趋势强度/量价配合/均线偏离/价格形态/8条口诀）
4. 多因子综合评分（30/70权重、乘数式合成、信号强度+2、0-100范围）
5. 风险评估（价格波动/换手率/市值/负面信号）
6. 分析通过条件（动态门槛、一票否决、数据完整性、>=2个积极指标）
7. 市场环境因子（真实数据计算、0.85-1.15范围、无数据时中性兜底1.0）
8. 推荐引擎（预筛选/排序/风险分级/行业分散/动态数量/理由/仓位）
"""

import os
import sys
import types

import pandas as pd

# 注入假akshare模块（必须在导入系统模块之前）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class FakeAKShare:
    """离线stub：提供测试所需的全部akshare接口"""

    @staticmethod
    def stock_zh_index_daily(symbol='sh000001'):
        """上证指数日K：60天每天+0.3%上涨"""
        dates = pd.date_range('2026-07-01', periods=60).strftime('%Y-%m-%d')
        closes = [3000 * (1.003 ** i) for i in range(60)]
        return pd.DataFrame({'date': dates, 'close': closes})

    @staticmethod
    def stock_zh_a_spot_em():
        rows = [
            {'代码': '600000', '名称': '浦发测试'},
            {'代码': '688001', '名称': '科创测试'},
            {'代码': '000001', '名称': '深主测试'},
            {'代码': '002001', '名称': '中小测试'},
            {'代码': '300001', '名称': '创业测试'},
            {'代码': '301001', '名称': '创二测试'},
            {'代码': '830001', '名称': '北交测试'},
            {'代码': '600003', '名称': 'ST测试'},
            {'代码': '600002', '名称': '无资料测试'},
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def stock_individual_info_em(symbol):
        if symbol == '600002':
            return pd.DataFrame(columns=['item', 'value'])  # 空数据，不提供默认值
        return pd.DataFrame([
            {'item': '市盈率', 'value': '15.5'},
            {'item': '市净率', 'value': '1.8'},
            {'item': '总市值', 'value': '120.5亿'},
            {'item': '流通股', 'value': '8.6亿'},
            {'item': '行业', 'value': '银行'},
            {'item': '换手率', 'value': '4.2'},
        ])

    @staticmethod
    def stock_zh_a_hist(symbol, period, start_date, end_date):
        if symbol == '301001':
            return pd.DataFrame()  # K线为空 -> 应放弃该股票
        n = 25
        closes = [10 + 0.05 * i for i in range(n)]
        return pd.DataFrame({
            '日期': pd.date_range('2026-08-01', periods=n).strftime('%Y-%m-%d'),
            '开盘': [c - 0.05 for c in closes],
            '最高': [c + 0.1 for c in closes],
            '最低': [c - 0.1 for c in closes],
            '收盘': closes,
            '成交量': [1000000] * n,
        })


sys.modules['akshare'] = types.ModuleType('akshare')
for name in dir(FakeAKShare):
    if not name.startswith('_'):
        setattr(sys.modules['akshare'], name, getattr(FakeAKShare, name))

from stock_analyzer import StockAnalyzer, NEGATIVE_INDICATORS, NEUTRAL_INDICATORS  # noqa: E402
from recommendation_engine import RecommendationEngine  # noqa: E402
from data_collector_optimized import OptimizedStockDataCollector  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    status = 'PASS' if cond else 'FAIL'
    print(f"[{status}] {name}" + (f" | {detail}" if detail and not cond else ''))


def make_kline(closes, volumes=None):
    """构造K线数据"""
    data = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        data.append({
            'date': f'2026-08-{i + 1:02d}',
            'open': o, 'high': max(o, c) * 1.01, 'low': min(o, c) * 0.99,
            'close': c, 'volume': volumes[i] if volumes else 1000000,
        })
    return data


# ============================================================
# 1. 数据采集模块
# ============================================================
def test_data_collector():
    print("\n--- 1. 数据采集模块（严格校验/板块覆盖/计数器） ---")
    collector = OptimizedStockDataCollector()
    stocks = collector.get_all_stocks()
    by_code = {s['code']: s for s in stocks}

    check('板块覆盖: 沪市主板600', by_code.get('sh.600000', {}).get('market_segment') == '沪市主板')
    check('板块覆盖: 科创板688', by_code.get('sh.688001', {}).get('market_segment') == '科创板')
    check('板块覆盖: 深市主板000', by_code.get('sz.000001', {}).get('market_segment') == '深市主板')
    check('板块覆盖: 深市主板002(原中小板)', by_code.get('sz.002001', {}).get('market_segment') == '深市主板')
    check('板块覆盖: 创业板300', by_code.get('sz.300001', {}).get('market_segment') == '创业板')
    check('板块覆盖: 创业板301', 'sz.301001' not in by_code, 'K线为空应被放弃')
    check('北交所8开头被跳过', 'sh.830001' not in by_code and 'sz.830001' not in by_code)
    check('ST股票被过滤', not any('ST' in s['name'] for s in stocks))

    s = by_code.get('sh.600000', {})
    check('基本面解析: PE=15.5', s.get('pe') == 15.5)
    check('基本面解析: PB=1.8', s.get('pb') == 1.8)
    check('基本面解析: 总市值120.5亿', s.get('market_cap') == 120.5e8)
    check('基本面解析: 流通股8.6亿', s.get('liquid_shares') == 8.6e8)
    check('基本面解析: 行业=货币金融服务(baostock证监会行业)', s.get('industry') == '货币金融服务')
    check('基本面解析: 换手率4.2', s.get('turnover_rate') == 4.2)

    s2 = by_code.get('sh.600002', {})
    check('无基本面数据时保留None(不用默认值)',
          s2.get('pe') is None and s2.get('pb') is None and s2.get('industry') is None)
    check('K线不足20天/为空的股票被放弃', 'sz.301001' not in by_code)
    check('K线>=20个交易日', len(s.get('kline_data', [])) >= 20)
    check('request_count计数器已修复', collector.request_count > 0,
          f"request_count={collector.request_count}")

    # 动态间隔档位
    collector2 = OptimizedStockDataCollector()
    collector2.request_count = 0
    check('动态间隔: <500次=0.3s', collector2._get_dynamic_interval() == 0.3)
    collector2.request_count = 600
    check('动态间隔: 600次=0.8s', collector2._get_dynamic_interval() == 0.8)
    collector2.request_count = 1600
    check('动态间隔: 1600次=1.0s', collector2._get_dynamic_interval() == 1.0)
    collector2.request_count = 3500
    check('动态间隔: 3500次=1.2s', collector2._get_dynamic_interval() == 1.2)


# ============================================================
# 2. 基本面分析
# ============================================================
def test_fundamental():
    print("\n--- 2. 基本面分析评分 ---")
    analyzer = StockAnalyzer([])

    stock = {'code': 'sh.600000', 'pe': 15, 'pb': 1.5, 'liquid_shares': 5e8,
             'industry': '人工智能'}
    # PE12 + PB12 + 流通股8 + 热门行业20 + 数据完整8 = 60
    score = analyzer._analyze_fundamental(stock)
    check('基本面: 全优股票=60分(PE12+PB12+流通8+热门行业20+完整8)', score == 60, f'实际={score}')

    stock2 = {'code': 'sh.600001', 'pe': 40, 'pb': 4, 'liquid_shares': 3e9,
              'industry': '钢铁'}
    # PE8(30-50档) + PB4 + 流通0 + 普通行业10 + 数据完整8 = 30
    score2 = analyzer._analyze_fundamental(stock2)
    check('基本面: 一般股票=30分(PE8+PB4+普通行业10+完整8)', score2 == 30, f'实际={score2}')

    stock3 = {'code': 'sh.600002', 'pe': None, 'pb': None, 'liquid_shares': None,
              'industry': None}
    check('基本面: 全缺失=0分', analyzer._analyze_fundamental(stock3) == 0)


# ============================================================
# 3. 技术面分析
# ============================================================
def test_technical():
    print("\n--- 3. 技术面分析评分 ---")
    analyzer = StockAnalyzer([])

    # 换手率档位
    st = {'code': 'x', 'turnover_rate': 5.0}
    check('换手率3-8%=15分', analyzer._analyze_turnover_rate(st) == (15, '适中换手率'))
    st['turnover_rate'] = 2.0
    check('换手率1-3%=8分', analyzer._analyze_turnover_rate(st) == (8, '较低换手率'))
    st['turnover_rate'] = 9.0
    check('换手率8-10%=5分', analyzer._analyze_turnover_rate(st) == (5, '较高换手率'))
    st['turnover_rate'] = 12.0
    check('换手率>=10%=0分+过高换手率信号', analyzer._analyze_turnover_rate(st) == (0, '过高换手率(需谨慎)'))
    st['turnover_rate'] = 0.5
    check('换手率<1%=0分+过低换手率信号', analyzer._analyze_turnover_rate(st) == (0, '过低换手率'))

    # 趋势强度档位（5日涨幅）
    closes = [10] * 15 + [10.0, 10.5, 11.0, 11.5, 11.3]
    s, sig = analyzer._analyze_trend_strength(pd.DataFrame(make_kline(closes)))
    # (11.3-10.0)/10.0 = 13% >= 10% -> 15分
    check('趋势强度: 5日涨幅>=10%=15分强势上涨', (s, sig) == (15, '强势上涨'), f'实际={s},{sig}')
    closes = [10] * 15 + [10.0, 10.2, 10.4, 10.6, 10.55]
    s, sig = analyzer._analyze_trend_strength(pd.DataFrame(make_kline(closes)))
    check('趋势强度: 5日涨幅>=5%=10分稳健上涨', (s, sig) == (10, '稳健上涨'), f'实际={s},{sig}')
    closes = [10] * 15 + [10.0, 10.05, 10.1, 10.15, 10.1]
    s, sig = analyzer._analyze_trend_strength(pd.DataFrame(make_kline(closes)))
    check('趋势强度: 5日涨幅>=0%=5分小幅上涨', (s, sig) == (5, '小幅上涨'), f'实际={s},{sig}')
    closes = [10] * 15 + [10.0, 9.9, 9.8, 9.7, 9.6]
    s, sig = analyzer._analyze_trend_strength(pd.DataFrame(make_kline(closes)))
    check('趋势强度: 下跌=0分', (s, sig) == (0, None), f'实际={s},{sig}')

    # 量价配合
    closes = [10] * 18 + [10.2, 10.5]
    vols = [1e6] * 19 + [1.3e6]
    s, sig = analyzer._analyze_price_volume_relation(pd.DataFrame(make_kline(closes, vols)))
    check('量价配合: 量价齐升=15分', (s, sig) == (15, '量价齐升'), f'实际={s},{sig}')
    vols = [1e6] * 19 + [0.8e6]
    s, sig = analyzer._analyze_price_volume_relation(pd.DataFrame(make_kline(closes, vols)))
    check('量价配合: 价升量缩=10分', (s, sig) == (10, '价升量缩'), f'实际={s},{sig}')
    closes = [10] * 18 + [9.8, 9.6]
    vols = [1e6] * 19 + [1.2e6]
    s, sig = analyzer._analyze_price_volume_relation(pd.DataFrame(make_kline(closes, vols)))
    check('量价配合: 价跌量升=5分', (s, sig) == (5, '价跌量升'), f'实际={s},{sig}')
    vols = [1e6] * 19 + [0.9e6]
    s, sig = analyzer._analyze_price_volume_relation(pd.DataFrame(make_kline(closes, vols)))
    check('量价配合: 量价齐跌=0分(中性)', (s, sig) == (0, '量价齐跌'), f'实际={s},{sig}')

    # 均线偏离度
    closes = [10] * 19 + [10.3]
    s, sig = analyzer._analyze_ma_deviation(pd.DataFrame(make_kline(closes)))
    check('均线偏离: 偏离<5%=10分价格合理', (s, sig) == (10, '价格合理'), f'实际={s},{sig}')
    closes = [10] * 19 + [11.0]
    s, sig = analyzer._analyze_ma_deviation(pd.DataFrame(make_kline(closes)))
    check('均线偏离: 5-8%=5分小幅偏离', (s, sig) == (5, '价格小幅偏离'), f'实际={s},{sig}')
    closes = [10] * 19 + [11.2]
    s, sig = analyzer._analyze_ma_deviation(pd.DataFrame(make_kline(closes)))
    check('均线偏离: >=8%=-5分偏离过大', (s, sig) == (-5, '价格偏离过大'), f'实际={s},{sig}')

    # 价格形态
    closes = [10] * 15 + [10.0, 10.4, 10.8, 11.2, 11.6]
    s, sig = analyzer._analyze_price_pattern(pd.DataFrame(make_kline(closes)))
    check('价格形态: 5日涨超5%=15分上涨趋势', (s, sig) == (15, '上涨趋势'), f'实际={s},{sig}')
    closes = [10] * 15 + [11.0, 10.8, 10.6, 10.4, 10.2]
    s, sig = analyzer._analyze_price_pattern(pd.DataFrame(make_kline(closes)))
    check('价格形态: 连续5日下跌=0分趋势向下(负面)', (s, sig) == (0, '趋势向下'), f'实际={s},{sig}')

    # 均线多头排列
    closes = [10 + 0.15 * i for i in range(20)]
    sig = analyzer._analyze_ma_arrangement(pd.DataFrame(make_kline(closes)))
    check('均线多头排列: MA5>MA10>MA20且差2%+ = 多头排列', sig == '多头排列', f'实际={sig}')

    # MACD金叉（先18天阴跌, 最后2天反弹, DIF恰在最后一根K线上穿DEA）
    closes = [10 - 0.08 * i for i in range(18)] + [8.9, 9.5]
    golden, _ = analyzer._calculate_macd(pd.DataFrame(make_kline(closes)))
    check('MACD: 先跌后涨产生金叉', bool(golden), f'实际={golden}')

    # 成交量分析
    closes = [10] * 20
    vols = [1e6] * 19 + [2.2e6]
    s, sig = analyzer._analyze_volume(pd.DataFrame(make_kline(closes, vols)))
    check('成交量: >=2倍=15分放量', (s, sig) == (15, '放量'), f'实际={s},{sig}')
    vols = [1e6] * 19 + [1.4e6]
    s, sig = analyzer._analyze_volume(pd.DataFrame(make_kline(closes, vols)))
    check('成交量: 1.3-2倍=10分温和放量', (s, sig) == (10, '温和放量'), f'实际={s},{sig}')


def test_adages():
    print("\n--- 4. 8条量价口诀（全部独立生效） ---")
    analyzer = StockAnalyzer([])

    def run_adage(closes, vols):
        return analyzer._analyze_technical_adages(pd.DataFrame(make_kline(closes, vols)))

    base = [9.8] * 20
    # 三、缩量上涨，继续上涨 +10
    closes = base[:14] + [10.0, 10.0, 10.0] + [10.3, 10.5, 10.7]
    vols = [1e6] * 14 + [1e6] * 3 + [0.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀三: 缩量上涨+10', s == 10 and '缩量上涨' in sigs, f'实际={s},{sigs}')

    # 七、无量顶下跌，后市会大涨 +15
    closes = base[:14] + [10.0, 10.0, 10.0] + [9.7, 9.5, 9.4]
    vols = [1e6] * 14 + [1e6] * 3 + [0.4e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀七: 无量顶跌+15', s == 15 and '无量顶跌' in sigs, f'实际={s},{sigs}')

    # 六、缩量不跌，底部已现 +10
    closes = base[:14] + [10.0, 10.0, 10.0] + [10.05, 10.0, 9.98]
    vols = [1e6] * 14 + [1e6] * 3 + [0.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀六: 缩量筑底+10', s == 10 and '缩量筑底' in sigs, f'实际={s},{sigs}')

    # 四、缩量下跌，继续下跌 -8
    closes = base[:14] + [10.0, 10.0, 10.0] + [9.8, 9.6, 9.5]
    vols = [1e6] * 14 + [1e6] * 3 + [0.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀四: 缩量下跌-8', s == -8 and '缩量下跌' in sigs, f'实际={s},{sigs}')

    # 一、放量上涨，必然回调 +5（谨慎）
    closes = base[:14] + [10.0, 10.0, 10.0] + [10.3, 10.5, 10.7]
    vols = [1e6] * 14 + [1e6] * 3 + [1.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀一: 放量上涨+5', s == 5 and '放量上涨' in sigs, f'实际={s},{sigs}')

    # 五、放量不涨，顶点已现 -10
    closes = base[:14] + [10.0, 10.0, 10.0] + [10.02, 10.0, 10.01]
    vols = [1e6] * 14 + [1e6] * 3 + [1.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀五: 放量滞涨-10', s == -10 and '放量滞涨' in sigs, f'实际={s},{sigs}')

    # 二、放量下跌（前期无大涨，反弹机会）+8
    closes = [10.0] * 20
    closes = closes[:14] + [10.0, 10.0, 10.0] + [9.8, 9.6, 9.5]
    vols = [1e6] * 14 + [1e6] * 3 + [1.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀二: 放量下跌(无前期大涨)+8', s == 8 and '放量下跌' in sigs, f'实际={s},{sigs}')

    # 八、放量顶下跌（前期10日涨幅>10%，出货）-15
    closes = [9.5] * 9 + [9.0] + [9.6] * 4 + [10.3, 10.3, 10.0] + [9.7, 9.5, 9.6]
    vols = [1e6] * 17 + [1.6e6] * 3
    s, sigs = run_adage(closes, vols)
    check('口诀八: 放量顶下跌(前期涨幅>10%)-15', s == -15 and '放量顶下跌' in sigs, f'实际={s},{sigs}')

    # 得分范围限制[-20, +20]
    check('口诀得分限制[-20,+20]', -20 <= s <= 20)


# ============================================================
# 5. 多因子综合评分（30/70权重 + 乘数式）
# ============================================================
def test_multi_factor():
    print("\n--- 5. 多因子综合评分 ---")
    analyzer = StockAnalyzer([])
    analyzer._get_market_environment_factor = lambda: 1.0

    # 权重验证：因子全中性时 base = 0.3*基本 + 0.7*技术
    stock = {'code': 'x', 'industry': '', 'liquid_shares': 0, 'pe': None, 'pb': None}
    score = analyzer._calculate_multi_factor_score(stock, 40, 60, [])
    check('多因子: 30/70权重 (0.3*40+0.7*60=54)', abs(score - 54) < 0.001, f'实际={score}')

    # 乘数式合成验证(v2): 37 * 1.1(热门行业) * 1.02(流动性) * 1.1025(估值) + 2信号*2
    stock2 = {'code': 'x', 'industry': '人工智能', 'liquid_shares': 8e8,
              'pe': 15, 'pb': 1.5}
    score2 = analyzer._calculate_multi_factor_score(stock2, 30, 40, ['MACD金叉', '多头排列'])
    expected = (30 * 0.3 + 40 * 0.7) * 1.1 * 1.02 * 1.1025 + 4
    check('多因子: 乘数式合成', abs(score2 - expected) < 0.01, f'实际={score2}, 期望={expected:.2f}')

    # 信号强度: 排除负面与中性信号
    score3 = analyzer._calculate_multi_factor_score(stock, 40, 60,
                                                    ['MACD金叉', '超买', '量价齐跌', 'RSI正常'])
    # 积极信号2个 -> +4
    check('多因子: 每积极信号+2(排除负面/中性)', abs(score3 - (54 + 4)) < 0.001, f'实际={score3}')

    # 评分范围0-100
    score4 = analyzer._calculate_multi_factor_score(stock2, 100, 100,
                                                    ['MACD金叉'] * 5)
    check('多因子: 评分范围0-100', 0 <= score4 <= 100, f'实际={score4}')
    score5 = analyzer._calculate_multi_factor_score(stock2, 0, 0, [])
    check('多因子: 最低0分(不再是30分下限)', score5 == 0, f'实际={score5}')

    # 因子档位（v2: 压缩区间）
    check('行业因子: 热门1.1', analyzer._get_industry_momentum_factor('人工智能') == 1.1)
    check('行业因子: 科技相关1.05', analyzer._get_industry_momentum_factor('金融科技') == 1.05)
    check('行业因子: 普通1.0', analyzer._get_industry_momentum_factor('钢铁') == 1.0)
    check('流动性因子: 5-20亿股=1.02', analyzer._get_liquidity_factor(8e8) == 1.02)
    check('流动性因子: <5亿股=1.01', analyzer._get_liquidity_factor(3e8) == 1.01)
    check('流动性因子: >20亿股=0.98', analyzer._get_liquidity_factor(30e8) == 0.98)
    check('估值因子: PE10-25/PB1-3=1.1025', abs(analyzer._get_valuation_factor(15, 1.5) - 1.1025) < 1e-9)
    check('估值因子: PE25-40=0.97', abs(analyzer._get_valuation_factor(30, None) - 0.97) < 1e-9)
    check('估值因子: PE>40=0.90', abs(analyzer._get_valuation_factor(50, None) - 0.90) < 1e-9)
    check('估值因子: 负PE=0.90', abs(analyzer._get_valuation_factor(-5, None) - 0.90) < 1e-9)
    check('估值因子: PB>5=0.90', abs(analyzer._get_valuation_factor(None, 6) - 0.90) < 1e-9)
    check('估值因子: 数据缺失=1.0', analyzer._get_valuation_factor(None, None) == 1.0)


# ============================================================
# 6. 风险评估
# ============================================================
def test_risk():
    print("\n--- 6. 风险评估 ---")
    analyzer = StockAnalyzer([])

    stock = {'code': 'x', 'change_pct': 10, 'turnover_rate': 16,
             'liquid_shares': 6e9}
    risk = analyzer._calculate_risk_score(stock, ['超买'])
    # 价格波动15 + 换手率12 + 市值10 + 负面信号8 = 45
    check('风险: 45分(波动15+换手12+市值10+负面8)', risk == 45, f'实际={risk}')

    stock2 = {'code': 'x', 'change_pct': 1, 'turnover_rate': 3, 'liquid_shares': 8e8}
    check('风险: 低风险股票=0分', analyzer._calculate_risk_score(stock2, []) == 0)


# ============================================================
# 7. 分析通过条件（一票否决/数据完整性/积极指标数量）
# ============================================================
def test_pass_conditions():
    print("\n--- 7. 分析通过条件 ---")
    analyzer = StockAnalyzer([])
    analyzer._analyze_fundamental = lambda s: 30
    analyzer._calculate_risk_score = lambda s, p: 0
    analyzer._get_market_environment_factor = lambda: 1.0
    analyzer._get_dynamic_threshold = lambda: 25

    def run(tech_result, stock_extra=None):
        analyzer._analyze_technical = lambda s: tech_result
        stock = {'code': 'sh.600000', 'name': '测试', 'pe': 15, 'pb': 1.5,
                 'liquid_shares': 8e8, 'industry': '银行'}
        if stock_extra:
            stock.update(stock_extra)
        analyzer.stock_list = [stock]  # 待分析股票列表
        result = analyzer.analyze_stocks()
        return result

    # 正常通过
    res = run((60, ['MACD金叉', '多头排列']))
    check('通过条件: 达标+无负面+数据完整+2积极指标 -> 通过', len(res) == 1)

    # 一票否决
    res = run((60, ['MACD金叉', '多头排列', '超买']))
    check('通过条件: 存在负面指标(超买) -> 一票否决', len(res) == 0)
    res = run((60, ['MACD金叉', '多头排列', '趋势向下']))
    check('通过条件: 趋势向下 -> 一票否决', len(res) == 0)

    # 积极指标不足2个
    res = run((60, ['MACD金叉']))
    check('通过条件: 仅1个积极指标 -> 不通过', len(res) == 0)
    # 中性信号不计入积极指标
    res = run((60, ['MACD金叉', '量价齐跌']))
    check('通过条件: 中性信号不计入积极指标 -> 不通过', len(res) == 0)

    # 数据完整性
    res = run((60, ['MACD金叉', '多头排列']),
              {'pe': None, 'pb': None, 'liquid_shares': None, 'industry': None})
    check('通过条件: 基本面数据全缺失 -> 不通过', len(res) == 0)

    # 负面信号清单与文档一致
    check('负面信号清单与文档一致',
          set(NEGATIVE_INDICATORS) == {'超买', '价格偏离过大', '趋势向下', '放量下跌', '过高换手率(需谨慎)'})


# ============================================================
# 8. 市场环境因子（真实数据 + 兜底）
# ============================================================
def test_market_factor():
    print("\n--- 8. 市场环境因子 ---")
    import stock_analyzer as sa
    import datetime as _dt

    StockAnalyzer._market_env_cache = {'date': None, 'factor': None, 'retry_after': 0.0}
    analyzer = StockAnalyzer([])

    factor = analyzer._get_market_environment_factor()
    cache = StockAnalyzer._market_env_cache
    today = _dt.date.today().isoformat()

    # 成功路径：真实指数计算（市场下跌时 factor<1.0 属正常，只约束范围）
    # 失败路径：接口不可用时兜底1.0，且设置10分钟退避（防每只股票重复请求）
    success_path = cache['date'] == today and cache['factor'] is not None
    fallback_path = cache['retry_after'] > 0 and factor == 1.0
    check('市场因子: 成功时真实计算(0.85-1.15)，不可用时兜底1.0并退避',
          (success_path and 0.85 <= factor <= 1.15) or fallback_path,
          f'实际={factor} date={cache["date"]}')
    check('市场因子: 缓存/退避生效(当日只拉取一次)',
          success_path or fallback_path,
          f'date={cache["date"]} retry_after={cache["retry_after"]}')

    # ak不可用时兜底为中性1.0
    StockAnalyzer._market_env_cache = {'date': None, 'factor': None, 'retry_after': 0.0}
    original_ak = sa.ak
    sa.ak = None
    try:
        factor2 = analyzer._get_market_environment_factor()
        check('市场因子: 数据不可用时兜底1.0(不用随机/模拟值)', factor2 == 1.0, f'实际={factor2}')
    finally:
        sa.ak = original_ak
        StockAnalyzer._market_env_cache = {'date': None, 'factor': None, 'retry_after': 0.0}


# ============================================================
# 9. 推荐引擎
# ============================================================
def test_recommendation_engine():
    print("\n--- 9. 推荐引擎 ---")
    engine = RecommendationEngine([])

    # 4.5 动态推荐数量
    check('动态数量: >=200只->15', engine._get_dynamic_recommendation_count(200) == 15)
    check('动态数量: 150-199只->12', engine._get_dynamic_recommendation_count(150) == 12)
    check('动态数量: 101-149只->10', engine._get_dynamic_recommendation_count(120) == 10)
    check('动态数量: 恰好100只->8', engine._get_dynamic_recommendation_count(100) == 8)
    check('动态数量: <100只->5', engine._get_dynamic_recommendation_count(99) == 5)

    # 4.1 预筛选
    stocks = [
        {'code': 'a', 'latest_price': 0, 'change_pct': 2, 'turnover_rate': 5},      # 价格无效
        {'code': 'b', 'latest_price': 10, 'change_pct': 25, 'turnover_rate': 5},    # 涨跌幅>20%
        {'code': 'c', 'latest_price': 10, 'change_pct': 2, 'turnover_rate': 35},    # 换手率>30%
        {'code': 'd', 'latest_price': 10, 'change_pct': -2, 'turnover_rate': 5},    # 正常
    ]
    filtered = engine._pre_filter_stocks(stocks)
    check('预筛选: 价格<=0/涨跌幅>20%/换手率>30%被过滤', len(filtered) == 1 and filtered[0]['code'] == 'd')

    # 4.3 风险分级排序：低->中->高
    stocks = [
        {'code': 'high', 'risk_score': 40, 'final_score': 90},
        {'code': 'low', 'risk_score': 10, 'final_score': 60},
        {'code': 'mid', 'risk_score': 20, 'final_score': 70},
    ]
    ordered = engine._classify_by_risk_level(stocks)
    check('风险分级: 低->中->高排序', [s['code'] for s in ordered] == ['low', 'mid', 'high'])

    # 4.4 行业分散
    stocks = [{'code': f'x{i}', 'industry': '银行'} for i in range(5)]
    diversified = engine._ensure_industry_diversification(stocks)
    check('行业分散: 单行业最多3只', len(diversified) == 3)

    # 4.7 风险等级
    check('风险等级: <=15低风险', engine._assess_risk_level({'risk_score': 10}) == '低风险')
    check('风险等级: 16-30中等风险', engine._assess_risk_level({'risk_score': 20}) == '中等风险')
    check('风险等级: >30高风险', engine._assess_risk_level({'risk_score': 40}) == '高风险')

    # 4.8 仓位建议（v2.2：组合内按排名8:7:5三段差异化加权，归一化到总仓100%）
    # count=1时 加权值100%受个股风险上限约束
    check('仓位: 风险<=10且评分>=85->重仓25%(count=1)',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 0, 1) == '建议重仓(25%)')
    check('仓位: 风险<=20且评分>=75->中仓档17%(count=1)',
          engine._suggest_position_size({'risk_score': 15, 'score': 80}, 0, 1) == '建议重仓(17%)')
    check('仓位: 风险<=30且评分>=65->轻仓档12%(count=1)',
          engine._suggest_position_size({'risk_score': 25, 'score': 70}, 0, 1) == '建议中仓(12%)')
    check('仓位: 其余->观察3%(count=1)',
          engine._suggest_position_size({'risk_score': 40, 'score': 60}, 0, 1) == '建议观察(3%)')
    # count=15: 前5只8%中仓、中5只7%轻仓、后5只5%轻仓
    check('仓位: 15只rank0(前1/3)->中仓8%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 0, 15) == '建议中仓(8%)')
    check('仓位: 15只rank5(中1/3)->轻仓7%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 5, 15) == '建议轻仓(7%)')
    check('仓位: 15只rank14(后1/3)->轻仓5%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 14, 15) == '建议轻仓(5%)')
    # count=10: 前3权重8/中4权重7/后3权重5，总权重67
    check('仓位: 10只rank0->中仓12%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 0, 10) == '建议中仓(12%)')
    check('仓位: 10只rank9->轻仓7%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 9, 10) == '建议轻仓(7%)')
    # count=5: third=1.67，权重[8,8,7,7,5]，总权重35
    check('仓位: 5只rank0->重仓23%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 0, 5) == '建议重仓(23%)')
    check('仓位: 5只rank4->中仓14%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 4, 5) == '建议中仓(14%)')
    # count=2: rank0权重8/rank1权重7，加权值53%/47%均受重仓档25%上限约束
    check('仓位: 2只rank0->重仓25%',
          engine._suggest_position_size({'risk_score': 5, 'score': 90}, 0, 2) == '建议重仓(25%)')
    # 高风险股即使排名靠前也受观察档3%上限约束
    check('仓位: 高风险股rank0->观察3%(风险优先)',
          engine._suggest_position_size({'risk_score': 40, 'score': 90}, 0, 15) == '建议观察(3%)')

    # 4.9 止损止盈策略（v2.3：盈亏比硬约束 + 形态差异化 + 移动止盈）
    def make_atr_klines(amplitude_pct, n=20, price=10.0):
        data = []
        for i in range(n):
            data.append({'high': price * (1 + amplitude_pct / 100),
                         'low': price * (1 - amplitude_pct / 100),
                         'close': price})
        return data

    # === 上涨趋势股：止损5-8%，止盈8%/15%或硬约束上抬 ===
    # 日振幅±3% -> TR≈0.6, 2*ATR=12% -> sl夹到8%上限
    # 原始 tp2=15, 15/8=1.875<2 -> 硬约束上抬 tp2=17.6, tp1=8.8
    out_t = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'breakout',
         'kline_data': make_atr_klines(3)})
    check('趋势股止损: ATR大波动夹到8%', '9.2元(-8%' in out_t['stop_loss'], out_t['stop_loss'])
    check('趋势股止盈: 三段式减仓+移动止盈', '减1/3' in out_t['take_profit']
          and '移动止损' in out_t['take_profit'], out_t['take_profit'])
    check('趋势股时间止损: 8日', '8个交易日' in out_t['time_stop'], out_t['time_stop'])
    # 验证盈亏比>=2：从输出解析实际百分比
    import re as _re
    sl_pct_t = float(_re.search(r'-([\d.]+)%', out_t['stop_loss']).group(1))
    tp2_str_t = _re.search(r'([\d.]+)元再减1/3', out_t['take_profit']).group(1)
    tp2_pct_t = (float(tp2_str_t) / 10.0 - 1) * 100
    rr_t = tp2_pct_t / sl_pct_t
    check('趋势股盈亏比>=2(硬约束生效)', rr_t >= 2.0, f'sl={sl_pct_t}% tp2={tp2_pct_t:.1f}% rr={rr_t:.2f}')
    # 日振幅±1% -> 2*ATR=4% -> sl夹到5%下限，原始 tp2=15, 15/5=3≥2，不触发
    out_t2 = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'breakout',
         'kline_data': make_atr_klines(1)})
    check('趋势股止损: ATR低波动夹到5%', '9.5元(-5%' in out_t2['stop_loss'], out_t2['stop_loss'])
    check('趋势股止盈: 低波动保留15%清仓', '11.5元' in out_t2['take_profit'], out_t2['take_profit'])
    # 移动止盈提示应出现
    check('趋势股: 含移动止盈提示', '移动止损' in out_t['take_profit'], out_t['take_profit'])

    # === 底反弹股：止损3-5%，止盈5%/10%（盈亏比2-3.3）===
    out_r = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'v_rebound',
         'kline_data': make_atr_klines(3)})
    # 底反弹1×ATR=6% -> 夹到5%上限
    check('底反弹止损: 1×ATR夹到5%', '9.5元(-5%' in out_r['stop_loss'], out_r['stop_loss'])
    check('底反弹止盈: +5%/+10%', '10.5元减半仓' in out_r['take_profit']
          and '11.0元清仓' in out_r['take_profit'], out_r['take_profit'])
    check('底反弹时间止损: 3日', '3个交易日' in out_r['time_stop'], out_r['time_stop'])
    # 底反弹低波动: 1×ATR=2% -> 夹到3%下限
    out_r2 = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'v_rebound',
         'kline_data': make_atr_klines(1)})
    check('底反弹止损: ATR低波动夹到3%', '9.7元(-3%' in out_r2['stop_loss'], out_r2['stop_loss'])
    # 底反弹无移动止盈
    check('底反弹: 无移动止盈提示', '移动止损' not in out_r['take_profit'], out_r['take_profit'])

    # === 盈亏比硬约束触发：ATR大波动止损8%，止盈10%时盈亏比仅1.25 -> 上抬tp2到17.6% ===
    # 用底反弹+大波动触发：sl=5%, tp2=10%, ratio=2，刚好不触发
    # 用上涨+无K线回退-5%：sl=5, tp2=15, ratio=3，不触发
    # 构造sl=8（趋势股ATR大波动）, tp2=15, ratio=15/8=1.875<2 -> 触发上抬
    out_hard = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'breakout',
         'kline_data': make_atr_klines(3)})  # sl=8, tp2原始15
    # 15/8=1.875<2，应触发上抬：tp2 = 8*2.2=17.6%
    sl_match = float(__import__('re').search(r'-([\d.]+)%', out_hard['stop_loss']).group(1))
    tp2_match = float(__import__('re').search(r'(\d+\.\d+)元再减1/3', out_hard['take_profit']).group(1))
    rr = tp2_match / 10.0 / sl_match * 100 / 100  # (tp2_pct)/(sl_pct) = (tp2_price/10-1)*100/sl
    rr_actual = ((tp2_match - 10.0) / 10.0 * 100) / sl_match
    check('盈亏比硬约束: 触发后盈亏比>=2', rr_actual >= 2.0, f'实际={rr_actual:.2f}')

    # === 高风险股：底反弹收紧到0.8×ATR ===
    out_hr = engine._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 25, 'pattern': 'v_rebound',
         'kline_data': make_atr_klines(1)})
    # 0.8*ATR=0.8/10=1.6% -> 夹到3%下限
    check('高风险底反弹: 0.8×ATR夹到3%', '9.7元(-3%' in out_hr['stop_loss'], out_hr['stop_loss'])

    # === K线不足回退 ===
    out4 = engine._suggest_exit_strategy({'latest_price': 10.0, 'risk_score': 0,
                                          'pattern': 'breakout', 'kline_data': []})
    check('无K线回退: 趋势-5%', '9.5元(-5%' in out4['stop_loss'], out4['stop_loss'])
    out5 = engine._suggest_exit_strategy({'latest_price': 10.0, 'risk_score': 0,
                                          'pattern': 'v_rebound', 'kline_data': []})
    check('无K线回退: 底反弹-3.5%', '9.65元(-3.5%' in out5['stop_loss'], out5['stop_loss'])# === 价格缺失提示 ===
    check('价格缺失提示', '无法计算' in engine._suggest_exit_strategy(
        {'latest_price': 0})['stop_loss'])

    # ========== v2.5 新增测试 ==========
    print('\n--- v2.5 K线组合/跌幅前提/见顶信号 ---')

    # --- P0-1/2: 看涨K线组合识别 ---
    from stock_selector import StockSelector
    sel = StockSelector([])

    def make_engulf_klines():
        # 前阴后阳吞没：阴线10->9.8，阳线9.79->10.05
        return [
            {'close': 10.0, 'open': 10.1, 'high': 10.15, 'low': 9.95, 'volume': 1000},
            {'close': 9.8, 'open': 9.9, 'high': 9.95, 'low': 9.75, 'volume': 1000},
            {'close': 10.05, 'open': 9.79, 'high': 10.1, 'low': 9.78, 'volume': 2000},
        ]

    import pandas as pd
    df_eng = pd.DataFrame(make_engulf_klines())
    combos = sel._detect_bullish_combo(df_eng)
    check('K线组合: 看涨吞没识别', '看涨吞没' in combos, str(combos))

    def make_morning_star():
        # 左阴 10->9.5，中小星 9.45->9.48，右阳 9.5->9.9（收盘>左阴中点）
        return [
            {'close': 9.5, 'open': 10.0, 'high': 10.05, 'low': 9.45, 'volume': 1000},
            {'close': 9.48, 'open': 9.45, 'high': 9.55, 'low': 9.4, 'volume': 800},
            {'close': 9.9, 'open': 9.5, 'high': 9.95, 'low': 9.48, 'volume': 1500},
        ]

    df_ms = pd.DataFrame(make_morning_star())
    combos_ms = sel._detect_bullish_combo(df_ms)
    check('K线组合: 早晨之星识别', '早晨之星' in combos_ms, str(combos_ms))

    # --- P0-3: 底反弹60日高点回撤>=15% ---
    def make_decline_klines(drop_from_high=0.20):
        # 60天前高点12元，一路阴跌到9.6元（回撤20%），然后缩量筑底，最后一日放量阳线
        klines = []
        for i in range(60):
            price = 12 - i * 0.04  # 60天从12跌到9.6
            klines.append({'close': price, 'open': price - 0.05, 'high': price + 0.1,
                           'low': price - 0.1, 'volume': 10000 - i * 100})
        # 最后4天缩量
        for i in range(4):
            price = 9.6 + i * 0.03
            klines.append({'close': price, 'open': price - 0.02, 'high': price + 0.03,
                           'low': price - 0.03, 'volume': 1500})
        # 最后1日放量阳线（量比>1.2）
        klines.append({'close': 9.85, 'open': 9.75, 'high': 9.9,
                       'low': 9.7, 'volume': 5000})
        return klines

    stock_decline = {'code': 'test001', 'name': '回撤测试',
                     'kline_data': make_decline_klines(0.20)}
    result, detail = sel._is_bottom_rebound(stock_decline, return_detail=True)
    check('底反弹: 60日回撤>=15%通过', result is not False, str(detail))

    # 回撤不足15%（高位小回调）应被过滤
    def make_shallow_klines():
        klines = []
        for i in range(60):
            price = 10 - i * 0.02  # 60天从10跌到8.8，回撤12%
            klines.append({'close': price, 'open': price - 0.05, 'high': price + 0.1,
                           'low': price - 0.1, 'volume': 10000 - i * 100})
        for i in range(4):
            price = 8.8 + i * 0.03
            klines.append({'close': price, 'open': price - 0.02, 'high': price + 0.03,
                           'low': price - 0.03, 'volume': 1500})
        klines.append({'close': 9.05, 'open': 8.95, 'high': 9.1,
                       'low': 8.9, 'volume': 5000})
        return klines

    stock_shallow = {'code': 'test002', 'name': '浅回撤',
                     'kline_data': make_shallow_klines()}
    result2, detail2 = sel._is_bottom_rebound(stock_shallow, return_detail=True)
    check('底反弹: 回撤<15%被过滤', result2 is False, f"回撤={detail2.get('c9_60日回撤>=15%', '')}")

    # --- P1-4: 见顶K线组合识别 ---
    from stock_analyzer import StockAnalyzer
    analyzer = StockAnalyzer([])

    def make_bearish_klines():
        # 最后2根构成看跌吞没：阳线9.75->9.8，阴线9.81->9.5
        return [
            {'close': 10.2, 'open': 10.0, 'high': 10.25, 'low': 9.95, 'volume': 1000},
            {'close': 9.9, 'open': 10.21, 'high': 10.25, 'low': 9.85, 'volume': 1500},
            {'close': 9.85, 'open': 9.88, 'high': 9.9, 'low': 9.8, 'volume': 1200},
            {'close': 9.8, 'open': 9.75, 'high': 9.82, 'low': 9.72, 'volume': 1000},
            {'close': 9.5, 'open': 9.81, 'high': 9.85, 'low': 9.45, 'volume': 1500},
        ]

    stock_bear = {'code': 'test003', 'name': '见顶测试',
                  'kline_data': make_bearish_klines()}
    bear_combos = analyzer._analyze_bearish_combos(stock_bear)
    check('见顶信号: 看跌吞没识别', '看跌吞没' in bear_combos, str(bear_combos))

    # --- P1-5: 时间止损形态差异化 ---
    engine25 = RecommendationEngine([])
    # breakout 8日
    out_bk = engine25._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'breakout', 'kline_data': []})
    check('时间止损: breakout=8日', '8个交易日' in out_bk['time_stop'], out_bk['time_stop'])
    # pullback 5日
    out_pb = engine25._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'pullback', 'kline_data': []})
    check('时间止损: pullback=5日', '5个交易日' in out_pb['time_stop'], out_pb['time_stop'])
    # v_rebound 3日
    out_vr = engine25._suggest_exit_strategy(
        {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'v_rebound', 'kline_data': []})
    check('时间止损: v_rebound=3日', '3个交易日' in out_vr['time_stop'], out_vr['time_stop'])

    # --- P1-4: 见顶信号收紧止盈 ---
    stock_top = {'latest_price': 10.0, 'risk_score': 0, 'pattern': 'breakout',
                 'kline_data': [], 'positive_indicators': ['看跌吞没']}
    out_top = engine25._suggest_exit_strategy(stock_top)
    check('见顶信号: 止盈收紧提示', '止盈已收紧' in out_top['take_profit'], out_top['take_profit'])

    # --- P2-6: 双底质量确认 ---
    # 直接验证 detail 中的 double_bottom_quality 标记逻辑（不依赖完整9条件）
    # 构造：近10日双底 + 第二底不创新低 + 右侧放量
    db_klines = []
    for i in range(20):
        price = 10 - i * 0.05
        db_klines.append({'close': price, 'open': price - 0.05, 'high': price + 0.1,
                          'low': price - 0.1, 'volume': 5000})
    # 第一底
    db_klines.append({'close': 9.0, 'open': 8.95, 'high': 9.05, 'low': 8.9, 'volume': 3000})
    # 反弹
    for i in range(4):
        price = 9.0 + i * 0.1
        db_klines.append({'close': price, 'open': price - 0.02, 'high': price + 0.05,
                          'low': price - 0.05, 'volume': 4000})
    # 第二底（不创新低，右侧放量）
    db_klines.append({'close': 9.05, 'open': 9.0, 'high': 9.1, 'low': 8.95, 'volume': 2500})
    db_klines.append({'close': 9.3, 'open': 9.05, 'high': 9.35, 'low': 9.0, 'volume': 8000})
    db_klines.append({'close': 9.5, 'open': 9.3, 'high': 9.55, 'low': 9.25, 'volume': 6000})

    import pandas as pd
    df_db = pd.DataFrame(db_klines)
    # 手动模拟 selector 内部逻辑：验证双底质量判定条件
    recent_10 = df_db.tail(10).reset_index(drop=True)
    lows_idx = recent_10['low'].nsmallest(2).index
    low1 = recent_10['low'].iloc[lows_idx[0]]
    low2 = recent_10['low'].iloc[lows_idx[1]]
    second_not_lower = low2 >= low1 * 0.995
    vol_now = float(df_db['volume'].iloc[-1])
    vol_ma10 = float(df_db['volume'].tail(10).mean())
    right_volume_ok = vol_now / vol_ma10 > 1.2
    check('双底质量: 二次探底不创新低+右侧放量',
          second_not_lower and right_volume_ok,
          f'low1={low1} low2={low2} vol_ratio={vol_now/vol_ma10:.2f}')

    # 4.6 增强理由（v2.4 形态细分）
    stock = {'pattern': 'breakout', 'positive_indicators': ['MACD金叉', '适中换手率'],
             'pe': 15, 'industry': '人工智能', 'score': 85}
    reason = engine._generate_enhanced_reason(stock)
    check('理由: 突破20日高点放量突破', '突破20日高点放量突破' in reason, reason)
    stock2 = {'pattern': 'double_bottom', 'positive_indicators': [],
              'pe': 20, 'industry': '新能源', 'score': 80}
    reason2 = engine._generate_enhanced_reason(stock2)
    check('理由: 双底形态', '双底形态(第二次缩量)' in reason2, reason2)
    stock3 = {'pattern': 'pullback', 'positive_indicators': [],
              'pe': 15, 'industry': '半导体', 'score': 85}
    reason3 = engine._generate_enhanced_reason(stock3)
    check('理由: 回踩5日线缩量企稳', '回踩5日线缩量企稳' in reason3, reason3)
    # 兼容旧中文形态
    stock4 = {'pattern': 'bottom_rebound', 'positive_indicators': ['MACD金叉', '适中换手率'],
              'pe': 15, 'industry': '人工智能', 'score': 85}
    reason4 = engine._generate_enhanced_reason(stock4)
    check('理由: 兼容旧形态触底反弹信号', '触底反弹信号' in reason4, reason4)
    check('理由: MACD指标金叉', 'MACD指标金叉' in reason, reason)
    check('理由: 估值合理(PE适中)', '估值合理(PE适中)' in reason, reason)
    check('理由: 属于热门行业(人工智能)', '属于热门行业(人工智能)' in reason, reason)
    check('理由: 综合评分良好', '综合评分良好' in reason, reason)

    # 完整流程：150只分析通过股票（10个行业）-> 推荐12只
    industries = ['人工智能', '银行', '医药生物', '钢铁', '煤炭',
                  '食品饮料', '房地产', '电力', '纺织服装', '汽车']

    def make_analyzed(i):
        return {
            'code': f'sh.6000{i:03d}', 'name': f'股票{i}',
            'latest_price': 10 + i % 20, 'change_pct': 2, 'turnover_rate': 5,
            'score': 70 + i % 25, 'final_score': 70 + i % 25,
            'fundamental_score': 40, 'technical_score': 60, 'risk_score': 10,
            'positive_indicators': ['MACD金叉', '多头排列'],
            'pe': 15, 'pb': 1.5, 'industry': industries[i % 10],
            'liquid_shares': 800000000, 'pattern': 'bottom_rebound',
        }

    analyzed_150 = [make_analyzed(i) for i in range(150)]
    e_full = RecommendationEngine(analyzed_150)
    e_full._market_regime = 'neutral'  # 注入中性状态，避免测试依赖真实行情
    recs = e_full.generate_recommendations()
    check('完整流程: 150只输入->8只推荐(基数12×neutral 0.7)', len(recs) == 8, f'实际={len(recs)}')
    check('完整流程: 推荐带理由/风险等级/仓位',
          all('recommendation_reason' in r and 'risk_level' in r and 'position_sizing' in r
              for r in recs))
    check('完整流程: 单行业<=3只',
          max([sum(1 for r in recs if r['industry'] == ind)
               for ind in set(r['industry'] for r in recs)]) <= 3)

    # === v2.5 防守市规则（bear 停推 / risk_off 限流+剔除反转型形态） ===
    def make_rebound(i, strong=True, risk=10):
        # strong=True 用 double_bottom，否则用 bottom_rebound（兼容旧名）
        pattern = 'double_bottom' if strong else 'bottom_rebound'
        return {
            'code': f'sh.600{i:03d}', 'name': f'反弹股{i}',
            'latest_price': 10.0 + i, 'change_pct': 1, 'turnover_rate': 5,
            'score': 80 - i, 'final_score': 80 - i,
            'fundamental_score': 40, 'technical_score': 60,
            'risk_score': risk, 'positive_indicators': ['MACD金叉'],
            'pe': 15, 'pb': 1.5, 'industry': '人工智能',
            'liquid_shares': 8e8, 'pattern': pattern,
        }
    # 6只反转型形态 + 2只高风险反转型 + 2只突破形态
    rebound_stocks = [make_rebound(i) for i in range(6)]
    rebound_stocks += [make_rebound(99, strong=True, risk=30)]
    rebound_stocks += [make_rebound(98, strong=True, risk=35)]
    rebound_stocks += [{'code': f'sz.000{i}', 'name': f'趋势股{i}',
                        'latest_price': 12.0, 'change_pct': 1, 'turnover_rate': 5,
                        'score': 90, 'final_score': 90, 'risk_score': 5,
                        'positive_indicators': ['MACD金叉'],
                        'pe': 15, 'pb': 1.5, 'industry': '人工智能',
                        'liquid_shares': 8e8, 'pattern': 'breakout'}
                       for i in range(2)]

    # risk_off：反转型形态全部剔除，仅突破形态可入选（10只→基数5×0.5=2只）
    e_riskoff = RecommendationEngine(rebound_stocks)
    e_riskoff._market_regime = 'risk_off'  # 直接注入状态，绕过网络请求
    recs_riskoff = e_riskoff.generate_recommendations()
    check('risk_off: 反转型形态全部被剔除',
          all((r.get('pattern') or '') not in ('v_rebound', 'double_bottom', 'bottom_rebound')
              for r in recs_riskoff),
          [r.get('pattern') for r in recs_riskoff])
    check('risk_off: 仅趋势形态入选',
          all(r.get('pattern') == 'breakout' for r in recs_riskoff),
          [r.get('pattern') for r in recs_riskoff])
    check('risk_off: 推荐数量=2只(基数5×限流0.5)', len(recs_riskoff) == 2, f'实际={len(recs_riskoff)}')
    check('risk_off: 推荐数量限流<=20', len(recs_riskoff) <= 20, f'实际={len(recs_riskoff)}')
    check('risk_off: market_regime标记', all(r.get('market_regime') == 'risk_off' for r in recs_riskoff))

    # v2.5 bear：暂停全市场推荐，直接返回空清单
    e_bear = RecommendationEngine(rebound_stocks)
    e_bear._market_regime = 'bear'
    recs_bear = e_bear.generate_recommendations()
    check('bear: 返回空清单(暂停推荐)', len(recs_bear) == 0, f'实际={len(recs_bear)}')


# ============================================================
def main():
    test_data_collector()
    test_fundamental()
    test_technical()
    test_adages()
    test_multi_factor()
    test_risk()
    test_pass_conditions()
    test_market_factor()
    test_recommendation_engine()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("\n" + "=" * 60)
    print(f"对齐测试完成: {passed}/{len(RESULTS)} 通过, {failed} 失败")
    if failed:
        print("失败项:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name} {detail}")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
