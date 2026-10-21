#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号快照采集：把每日全候选分析结果（含未推荐）结构化落库。

source 取值：
- full_scan 全市场扫描的全部分析完成股（~290/日，校准评分门槛的主样本）
- watch     自选股分析（含未通过，样本有自选偏差，看板可单独筛选）
- history   历史 daily_recommendations 回填（只有最终推荐、无因子拆解）
"""

import json
import logging

from webapp import db

logger = logging.getLogger('webapp.lab.capture')

_baseline_seeded = False


def _ensure_baseline():
    global _baseline_seeded
    if _baseline_seeded:
        return
    try:
        import strategy_params
        params = strategy_params.get_params()
        db.ensure_param_version(
            params['version'], 'baseline',
            json.dumps(params, ensure_ascii=False),
            'v2.5 线上基线参数（自优化实验室上线时固化）')
        _baseline_seeded = True
    except Exception:
        logger.exception('基线参数版本登记失败（不影响采集）')


def _factors_json(stock, fund=None, chip=None):
    keys = ('pe', 'pb', 'turnover_rate', 'change_pct', 'liquid_shares',
            'market_segment', 'industry', 'concept')
    factors = {k: stock.get(k) for k in keys if stock.get(k) is not None}
    indicators = stock.get('positive_indicators') or []
    if indicators:
        factors['indicators'] = list(indicators)
    # 阶段一扩展因子：只落库观察，不参与评分
    if fund:
        factors['fund'] = fund
    if chip:
        factors['chip'] = chip
    return json.dumps(factors, ensure_ascii=False, default=str)


def capture_full_scan(signal_date, analyzed_stocks, recommendations, engine):
    """全市场扫描后调用：全部分析完成股入库，推荐股标 recommended/rank。"""
    _ensure_baseline()
    import strategy_params
    from webapp.lab import fund_flow, chip as chip_mod
    version = strategy_params.active_version()
    regime = getattr(engine, '_market_regime', None)

    # 全市场资金流仅拉取一次（失败返回 {}，不阻断采集）
    try:
        fund_map = fund_flow.fetch_market_fund_map()
    except Exception:
        logger.exception('资金流快照获取失败，本日资金因子留空')
        fund_map = {}

    rank_map = {}
    for i, s in enumerate(recommendations or [], 1):
        rank_map[s.get('code')] = i

    n = 0
    for stock in analyzed_stocks or []:
        code = stock.get('code')
        if not code:
            continue
        try:
            ex = engine._suggest_exit_strategy(stock)
            indicators = stock.get('positive_indicators') or []
            pos_count = engine._get_truly_positive_count(stock)
            # 资金流（按代码查表，本地操作）
            fund = None
            try:
                fund = fund_flow.get_fund_factor(code, fund_map)
            except Exception:
                logger.debug('资金因子取值失败 %s', code)
            # 筹码分布（纯本地计算，不发网络请求）
            chip = None
            try:
                chip = chip_mod.compute_chip(stock.get('kline_data'))
            except Exception:
                logger.debug('筹码分布计算失败 %s', code)
            db.save_signal_snapshot(
                signal_date, code, 'full_scan',
                name=stock.get('name'),
                pattern=stock.get('pattern'),
                score=stock.get('score'),
                final_score=stock.get('final_score'),
                risk_score=stock.get('risk_score'),
                fundamental_score=stock.get('fundamental_score'),
                technical_score=stock.get('technical_score'),
                positive_count=pos_count or len(indicators),
                market_regime=stock.get('market_regime') or regime,
                ref_price=ex.get('ref_price'),
                sl_pct=ex.get('sl_pct'),
                tp1_pct=ex.get('tp1_pct'),
                tp2_pct=ex.get('tp2_pct'),
                time_stop_days=ex.get('time_stop_days'),
                recommended=code in rank_map,
                rank_no=rank_map.get(code),
                param_version=ex.get('param_version') or version,
                factors_json=_factors_json(stock, fund=fund, chip=chip))
            n += 1
        except Exception:
            logger.exception('信号快照写入失败 %s', code)
    logger.info('全候选信号已落库: %s 共 %d 只（推荐 %d，资金覆盖 %d，筹码覆盖 %d）',
                signal_date, n, len(rank_map),
                sum(1 for s in (analyzed_stocks or [])
                    if fund_flow.get_fund_factor(s.get('code'), fund_map)),
                sum(1 for s in (analyzed_stocks or []) if s.get('kline_data')))
    return n


def capture_watch_analysis(signal_date, result):
    """自选股单股分析完成后调用（passed 与否都记录）。"""
    _ensure_baseline()
    import strategy_params
    try:
        db.save_signal_snapshot(
            signal_date, result['code'], 'watch',
            name=result.get('name'),
            pattern=result.get('pattern'),
            score=result.get('score'),
            final_score=result.get('final_score'),
            risk_score=result.get('risk_score'),
            fundamental_score=result.get('fundamental_score'),
            technical_score=result.get('technical_score'),
            positive_count=len([
                i for i in (result.get('positive_indicators') or [])]),
            market_regime=result.get('market_regime'),
            ref_price=result.get('latest_price'),
            sl_pct=None,
            tp1_pct=None,
            tp2_pct=None,
            time_stop_days=None,
            recommended=False,
            rank_no=None,
            param_version=strategy_params.active_version(),
            factors_json=json.dumps(
                {'indicators': result.get('positive_indicators') or [],
                 'passed': bool(result.get('passed'))},
                ensure_ascii=False, default=str))
    except Exception:
        logger.exception('自选分析信号快照写入失败 %s', result.get('code'))
