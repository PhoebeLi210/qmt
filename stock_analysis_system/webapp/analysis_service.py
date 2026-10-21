#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单股分析服务（复用 chaogu v2.5 核心库）

与主流水线 main.py 的区别：
- main.py 面向全市场，未通过模型门槛的股票被直接丢弃；
- 本服务面向朋友自选股，无论是否通过买点条件都保留完整分析明细
  （各项评分、积极/见顶信号、未通过原因、参考止损止盈），并明确标注 passed。

执行方式：后台线程 + 当日结果唯一行（user_id, code, trade_date）。
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime

# 保证能 import 到 stock_analysis_system 下的核心模块
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from webapp import db  # noqa: E402
from webapp import push as push_mod  # noqa: E402
from stock_analyzer import StockAnalyzer, NEGATIVE_INDICATORS, NEUTRAL_INDICATORS  # noqa: E402

logger = logging.getLogger('webapp.analysis')

# 核心库组件全部惰性单例（构造时会发网络请求，不能在 import 阶段触发）
_collector = None
_analyzer = None
_engine = None
_name_map = None
_run_lock = threading.Lock()  # 串行分析：核心库带懒加载缓存，并发收益低、竞争风险高


class AnalysisError(Exception):
    pass


def _get_collector():
    global _collector
    if _collector is None:
        from data_collector_optimized import OptimizedStockDataCollector
        _collector = OptimizedStockDataCollector()
    return _collector


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = StockAnalyzer([])
    return _analyzer


def _get_engine():
    global _engine
    if _engine is None:
        from recommendation_engine import RecommendationEngine
        _engine = RecommendationEngine([])
    return _engine


def normalize_code(raw):
    """6位代码 → sh.xxxxxx / sz.xxxxxx；已规范化的直接校验返回"""
    digits = ''.join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) != 6:
        raise AnalysisError('股票代码应为6位数字')
    if digits.startswith(('688', '689')) or digits.startswith('6'):
        return f'sh.{digits}'
    if digits.startswith(('000', '001', '002', '003', '300', '301')):
        return f'sz.{digits}'
    raise AnalysisError('仅支持沪深A股（不含北交所）')


def segment_of(code):
    digits = code.split('.')[-1]
    if digits.startswith(('688', '689')):
        return '科创板'
    if digits.startswith('6'):
        return '沪市主板'
    if digits.startswith(('000', '001', '002', '003')):
        return '深市主板'
    if digits.startswith(('300', '301')):
        return '创业板'
    return ''


def _get_name_map():
    """代码→名称（akshare 全市场代码名称表，轻量，进程内缓存）"""
    global _name_map
    if _name_map is not None:
        return _name_map
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        if df is not None and not df.empty:
            code_col = 'code' if 'code' in df.columns else '代码'
            name_col = 'name' if 'name' in df.columns else '名称'
            _name_map = {str(r[code_col]): str(r[name_col]) for _, r in df.iterrows()}
            logger.info(f'自选股名称映射就绪: {len(_name_map)} 只')
    except Exception as e:
        logger.warning(f'股票名称映射获取失败，名称将显示为代码: {e}')
        _name_map = {}
    return _name_map


def lookup_name(code):
    digits = code.split('.')[-1]
    return _get_name_map().get(digits)


def analyze_one(code_raw, name_hint=None):
    """对单只股票执行完整 v2.5 分析，返回结构化结果 dict（不写库）。

    无论是否通过模型买点条件都会返回结果，passed=False 时附 fail_reasons。
    """
    code = normalize_code(code_raw)

    with _run_lock:
        collector = _get_collector()
        stock = collector._get_stock_detail_optimized(code)
        if stock is None:
            raise AnalysisError('K线数据不足20个交易日、代码无效或行情源暂时不可用')

        name = name_hint or lookup_name(code)
        stock['name'] = name or code
        stock['market_segment'] = stock.get('market_segment') or segment_of(code)

        # 1. 形态判定（顺序必须与 StockSelector.select_by_kline_pattern 一致：
        #    先底反弹（挂 pattern_detail 供 K 线组合加分消费），再上涨趋势）
        from stock_selector import StockSelector
        selector = StockSelector([stock])
        pattern_rebound, detail = selector._is_bottom_rebound(stock, return_detail=True)
        if pattern_rebound:
            stock['pattern'] = pattern_rebound
            stock['pattern_detail'] = detail
        else:
            pattern_trend = selector._is_upward_trend(stock)
            if pattern_trend:
                stock['pattern'] = pattern_trend
                stock['pattern_detail'] = {'pattern_label': pattern_trend}
            else:
                stock['pattern'] = '未识别'
                stock['pattern_detail'] = {}

        # 1.5 填充资金流+筹码因子（参与评分，失败不影响主流程）
        try:
            from webapp.lab.holdings import enrich_stocks_with_fund_chip
            enrich_stocks_with_fund_chip([stock])
        except Exception:
            logger.debug('自选分析资金流/筹码填充失败 %s', code, exc_info=True)

        # 2. 评分（直接调用内部方法，保留全部明细，不做通过性丢弃）
        analyzer = _get_analyzer()
        fundamental_score = analyzer._analyze_fundamental(stock)
        technical_score, indicators = analyzer._analyze_technical(stock)
        total_score = analyzer._calculate_multi_factor_score(
            stock, fundamental_score, technical_score, indicators)
        risk_score = analyzer._calculate_risk_score(stock, indicators)
        final_score = max(0, total_score - risk_score)
        threshold = analyzer._get_dynamic_threshold()

        # 3. 通过条件（与 StockAnalyzer.analyze_stocks 完全同口径）
        has_negative = any(i in indicators for i in NEGATIVE_INDICATORS)
        has_basic_data = any(stock.get(k) for k in ('pe', 'pb', 'liquid_shares', 'industry'))
        truly_positive = [i for i in indicators
                          if i not in NEGATIVE_INDICATORS and i not in NEUTRAL_INDICATORS]
        fail_reasons = []
        if final_score < threshold:
            fail_reasons.append(f'综合评分 {final_score:.1f} 低于动态门槛 {threshold:.0f}')
        if has_negative:
            neg = [i for i in indicators if i in NEGATIVE_INDICATORS]
            fail_reasons.append('存在一票否决信号: ' + '、'.join(neg))
        if not has_basic_data:
            fail_reasons.append('基本面数据缺失（PE/PB/流通股/行业均无）')
        if len(truly_positive) < 2:
            fail_reasons.append(f'积极技术指标仅 {len(truly_positive)} 个（需≥2个）')
        passed = not fail_reasons

        stock['fundamental_score'] = fundamental_score
        stock['technical_score'] = technical_score
        stock['score'] = total_score
        stock['risk_score'] = risk_score
        stock['final_score'] = final_score
        stock['positive_indicators'] = indicators

        # 4. 引擎层：大盘择时 / 风险等级 / 理由 / 止损止盈（单股方法，绕过数量与行业分散）
        engine = _get_engine()
        regime = engine._get_market_regime()
        stock['market_regime'] = regime
        risk_level = engine._assess_risk_level(stock)
        reason = engine._generate_enhanced_reason(stock)
        exit_strategy = engine._suggest_exit_strategy(stock)

        # 5. 从 stock dict 读已填充的 fund/chip（阶段 1.5 已算好）
        fund = stock.get('fund')
        chip_data = stock.get('chip')

    return {
        'code': code,
        'name': stock['name'],
        'latest_price': stock.get('latest_price'),
        'change_pct': stock.get('change_pct'),
        'pattern': stock['pattern'],
        'pattern_detail': stock.get('pattern_detail') or {},
        'fundamental_score': fundamental_score,
        'technical_score': technical_score,
        'score': total_score,
        'risk_score': risk_score,
        'final_score': final_score,
        'threshold': threshold,
        'positive_indicators': indicators,
        'passed': passed,
        'fail_reasons': fail_reasons,
        'risk_level': risk_level,
        'recommendation_reason': reason,
        'stop_loss': exit_strategy['stop_loss'],
        'take_profit': exit_strategy['take_profit'],
        'time_stop': exit_strategy['time_stop'],
        'market_regime': regime,
        'fund': fund,
        'chip': chip_data,
    }


def _write_result(user_id, trade_date, result):
    indicators = result['positive_indicators']
    return db.upsert_analysis_row(
        user_id, result['code'], trade_date, result['name'], status='done',
        passed=1 if result['passed'] else 0,
        fail_reasons=json.dumps(result['fail_reasons'], ensure_ascii=False),
        latest_price=result['latest_price'],
        change_pct=result['change_pct'],
        pattern=result['pattern'],
        pattern_detail=json.dumps(result['pattern_detail'], ensure_ascii=False),
        fundamental_score=result['fundamental_score'],
        technical_score=result['technical_score'],
        score=result['score'],
        risk_score=result['risk_score'],
        final_score=result['final_score'],
        threshold=result['threshold'],
        positive_indicators=json.dumps(indicators, ensure_ascii=False),
        risk_level=result['risk_level'],
        recommendation_reason=result['recommendation_reason'],
        stop_loss=result['stop_loss'],
        take_profit=result['take_profit'],
        time_stop=result['time_stop'],
        market_regime=result['market_regime'],
        fund_json=json.dumps(result.get('fund'), ensure_ascii=False)
        if result.get('fund') else None,
        chip_json=json.dumps(result.get('chip'), ensure_ascii=False)
        if result.get('chip') else None,
        error_msg=None,
    )


def _write_failure(user_id, code, trade_date, name, message):
    db.upsert_analysis_row(user_id, code, trade_date, name, status='failed', error_msg=message)


def start_analysis(user_id, code_raw, name_hint=None, notify=False):
    """后台线程执行单股分析（自选页"立即分析"按钮）。返回 (code, 当日行id)。"""
    code = normalize_code(code_raw)
    trade_date = datetime.now().strftime('%Y-%m-%d')

    row = db.get_watch(user_id, code)
    name = name_hint or (row['name'] if row else None)
    row_id = db.upsert_analysis_row(user_id, code, trade_date, name, status='pending')

    def _worker():
        try:
            result = analyze_one(code, name_hint=name)
            _write_result(user_id, trade_date, result)
            try:
                from webapp.lab.capture import capture_watch_analysis
                capture_watch_analysis(trade_date, result)
            except Exception:
                logger.debug('lab 自选信号落库跳过', exc_info=True)
            if notify:
                user = db.get_user_by_id(user_id)
                push_mod.push_to_user(
                    user, f'自选股分析完成: {result["name"]}({code})',
                    _format_push_body(result))
        except AnalysisError as e:
            _write_failure(user_id, code, trade_date, name, str(e))
        except Exception as e:
            logger.exception(f'后台分析异常 {code}')
            _write_failure(user_id, code, trade_date, name, f'分析异常: {e}')

    threading.Thread(target=_worker, daemon=True).start()
    return code, row_id


def _format_push_body(r):
    verdict = '符合模型买点条件' if r['passed'] else '不符合模型买点条件'
    lines = [
        f'结论: {verdict}',
        f'最新价: {r["latest_price"]:.2f}  形态: {r["pattern"]}',
        f'评分: 综合{r["score"]:.1f} / 最终{r["final_score"]:.1f} '
        f'(门槛{r["threshold"]:.0f})  风险分: {r["risk_score"]:.1f}',
    ]
    if not r['passed'] and r['fail_reasons']:
        lines.append('未通过: ' + '；'.join(r['fail_reasons']))
    lines.append(f'止损: {r["stop_loss"]}')
    lines.append(f'止盈: {r["take_profit"]}')
    lines.append(f'时间止损: {r["time_stop"]}')
    return '\n'.join(lines)


def run_daily_analysis(notify=True):
    """盘后批量任务：全用户自选股去重后逐只分析，结果按用户落库并汇总推送。

    同一股票只分析一次、结果复制到每个关注它的用户；推送按用户聚合为一条汇总。
    """
    trade_date = datetime.now().strftime('%Y-%m-%d')
    codes = db.list_all_watch_codes()
    logger.info(f'盘后自选股分析开始: {len(codes)} 只去重股票')

    per_user_lines = {}  # user_id -> [推送行]
    for code, name in codes:
        try:
            result = analyze_one(code, name_hint=name)
        except Exception as e:
            logger.warning(f'盘后分析失败 {code}: {e}')
            for uid in db.list_users_watching(code):
                _write_failure(uid, code, trade_date, name, str(e))
                per_user_lines.setdefault(uid, []).append(
                    f'❌ {name or code}({code}): 分析失败 - {e}')
            continue

        for uid in db.list_users_watching(code):
            _write_result(uid, trade_date, result)
            mark = '✅' if result['passed'] else '⭕'
            per_user_lines.setdefault(uid, []).append(
                f'{mark} {result["name"]}({code}) {result["pattern"]} '
                f'最终{result["final_score"]:.0f}分 '
                + ('符合买点' if result['passed'] else
                   '未通过(' + '；'.join(result['fail_reasons']) + ')'))

        try:
            from webapp.lab.capture import capture_watch_analysis
            capture_watch_analysis(trade_date, result)
        except Exception:
            logger.debug('lab 自选信号落库跳过', exc_info=True)

    if notify:
        for uid, lines in per_user_lines.items():
            user = db.get_user_by_id(uid)
            body = '\n'.join(lines) + '\n\n详情请登录系统查看个股分析页。'
            push_mod.push_to_user(user, f'{trade_date} 自选股盘后分析汇总（{len(lines)}只）', body)

    logger.info(f'盘后自选股分析完成: {len(codes)} 只')
    return len(codes)
