#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略参数（版本化、可外置覆盖）

阶段 0：只把止损/止盈相关参数从 recommendation_engine 抽离到这里，
默认值与原硬编码完全一致（行为零变化）。

未来自优化流程：
  baseline（本文件）→ lab 提案批准后写 shadow/approved JSON →
  CHAOGU_PARAMS_FILE 指向生效文件，引擎自动读取，无需改代码。
"""

import os
import json
import copy
import logging

logger = logging.getLogger('strategy_params')

BASELINE_VERSION = 'baseline-v1'

# 默认参数 —— 与 recommendation_engine._suggest_exit_strategy 原值逐一对齐
_DEFAULTS = {
    'version': BASELINE_VERSION,
    'exit': {
        # ATR 自适应止损：反弹形态
        'rebound_sl_floor': 3.0,
        'rebound_sl_cap': 5.0,
        'rebound_mult_low_risk': 1.0,   # risk_score <= 20
        'rebound_mult_high_risk': 0.8,
        # ATR 自适应止损：趋势形态/未识别
        'trend_sl_floor': 5.0,
        'trend_sl_cap': 8.0,
        'trend_mult_low_risk': 2.0,     # risk_score <= 20
        'trend_mult_high_risk': 1.5,
        # ATR 缺失时的兜底止损
        'fallback_sl_rebound': 3.5,
        'fallback_sl_trend': 5.0,
        # 止盈阶梯 (tp1%, tp2%, 时间止损交易日)
        'tp_breakout': [8.0, 15.0, 8],
        'tp_trend': [6.0, 12.0, 5],
        'tp_rebound': [5.0, 10.0, 3],
        'tp_default': [6.0, 12.0, 6],
        # 盈亏比硬约束
        'rr_min': 2.0,
        'rr_tp2_mult': 2.2,
        # 见顶信号收紧
        'top_signal_factor': 0.6,
        'top_sl_floor_mult': 1.3,
        'top_sl_cap_mult': 2.0,
        # 保本移动止损阶梯（浮盈 x% → 止损上移至 y%）
        'breakeven_step1': 3.0,
        'breakeven_stop1': 0.0,
        'breakeven_step2': 5.0,
        'breakeven_stop2': 2.0,
        # risk_off 反弹观察模式
        'risk_off_sl': 3.0,
        'risk_off_tp1': 5.0,
        'risk_off_tp2': 8.0,
        'risk_off_time': 3,
    }
}

_cache = None


def get_params():
    """返回当前生效参数（深拷贝，防止调用方污染缓存）。

    覆盖文件格式：与 _DEFAULTS 同构的 JSON，只需写出要覆盖的键；
    通过环境变量 CHAOGU_PARAMS_FILE 指定。
    """
    global _cache
    if _cache is not None:
        return copy.deepcopy(_cache)

    params = copy.deepcopy(_DEFAULTS)
    path = os.environ.get('CHAOGU_PARAMS_FILE')
    if path and os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                override = json.load(f)
            if isinstance(override, dict):
                if 'version' in override:
                    params['version'] = override['version']
                if isinstance(override.get('exit'), dict):
                    params['exit'].update(override['exit'])
                logger.info('策略参数已加载覆盖文件: %s (version=%s)',
                            path, params['version'])
        except (OSError, ValueError) as e:
            logger.warning('策略参数覆盖文件读取失败，使用基线: %s', e)

    _cache = params
    return copy.deepcopy(params)


def active_version():
    return get_params()['version']


def get_exit_params():
    return get_params()['exit']


def reset_cache():
    """测试用：清掉进程内缓存。"""
    global _cache
    _cache = None
