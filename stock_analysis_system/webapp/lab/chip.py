#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""筹码分布（CYQ）本地计算 —— 移植东方财富 stock_cyq_em 的 JS 算法。

零网络请求：仅依赖扫描时已在内存中的日K（open/high/low/close）与每股换手率。
官方接口走 push2his.eastmoney.com（云服务器 IP 被限流）且依赖 JS 引擎，
本移植与其口径一致（150 价格档、三角分布叠加、换手率衰减），
差别仅在窗口：官方取 120 个交易日，本系统扫描K线约 20-28 个交易日，
对本策略 20 个交易日的持有期而言窗口匹配，字段名带 win 记录实际窗口。

输入 bar: {'open','high','low','close','turnover'(换手率%)}，按日期升序。
输出（最新一日）：
- profit_ratio   获利盘比例（当前价下方筹码占比）
- avg_cost       筹码平均成本（50 分位价）
- conc90/conc70  90%/70% 筹码集中度 = (高-低)/(高+低)，越小越集中
- cost90_low/high, cost70_low/high
- win            实际使用的交易日数
"""

import logging
import math

logger = logging.getLogger('webapp.lab.chip')

_FACTOR = 150          # 价格档数（与东财一致）
_MAX_BARS = 120        # 与官方 range=120 对齐（数据不足时用全部）
_MIN_BARS = 10


def compute_chip(bars, max_bars=_MAX_BARS):
    """计算最新一日的筹码分布指标。数据不足或无法计算时返回 None。"""
    if not bars:
        return None
    bars = [b for b in bars if b and b.get('high') and b.get('low')
            and b.get('close') is not None and b.get('open') is not None][-max_bars:]
    if len(bars) < _MIN_BARS:
        return None

    # 换手率必须存在（% 转小数）；全部缺失则无法建模，返回 None
    turnovers = []
    for b in bars:
        t = b.get('turnover')
        try:
            t = float(t) if t is not None else None
        except (TypeError, ValueError):
            t = None
        turnovers.append(min(1.0, t / 100.0) if t is not None and 0 <= t <= 100 else None)
    if not any(t is not None for t in turnovers):
        return None
    # 单日缺失用上一根填充；开头缺失用第一根有效值
    last_valid = next((t for t in turnovers if t is not None), None)
    filled = []
    for t in turnovers:
        if t is None:
            filled.append(last_valid if last_valid is not None else 0.0)
        else:
            filled.append(t)
            last_valid = t

    max_price = max(b['high'] for b in bars)
    min_price = min(b['low'] for b in bars)
    # 全部一字板时退化为 0.01 精度（与东财 accuracy 兜底一致）
    accuracy = max(0.01, (max_price - min_price) / (_FACTOR - 1))
    xdata = [0.0] * _FACTOR

    for b, tr in zip(bars, filled):
        high, low = float(b['high']), float(b['low'])
        avg = (float(b['open']) + float(b['close']) + high + low) / 4.0
        h_idx = int(math.floor((high - min_price) / accuracy))
        l_idx = int(math.ceil((low - min_price) / accuracy))
        h_idx = min(_FACTOR - 1, max(0, h_idx))
        l_idx = min(_FACTOR - 1, max(0, l_idx))
        if l_idx > h_idx:
            l_idx, h_idx = h_idx, l_idx
        # 一字板时 G 点横坐标取 factor-1
        g_slope = (_FACTOR - 1) if high == low else 2.0 / (high - low)
        g_pos = int(math.floor((avg - min_price) / accuracy))
        g_pos = min(_FACTOR - 1, max(0, g_pos))

        # 历史筹码按换手率衰减
        for n in range(_FACTOR):
            xdata[n] *= (1.0 - tr)

        if high == low:
            # 一字板：矩形面积折算为三角形两倍
            xdata[g_pos] += g_slope * tr / 2.0
        else:
            for j in range(l_idx, h_idx + 1):
                cur = min_price + accuracy * j
                if cur <= avg:
                    if abs(avg - low) < 1e-8:
                        xdata[j] += g_slope * tr
                    else:
                        xdata[j] += (cur - low) / (avg - low) * g_slope * tr
                else:
                    if abs(high - avg) < 1e-8:
                        xdata[j] += g_slope * tr
                    else:
                        xdata[j] += (high - cur) / (high - avg) * g_slope * tr

    total = sum(xdata)
    if total <= 0:
        return None
    current = float(bars[-1]['close'])

    # 获利比例：当前价下方筹码 / 总筹码
    below = sum(x for i, x in enumerate(xdata)
                if current >= min_price + i * accuracy)
    profit_ratio = max(0.0, min(1.0, below / total))

    def cost_at(chip_qty):
        cum = 0.0
        for i, x in enumerate(xdata):
            if cum + x > chip_qty:
                return min_price + i * accuracy
            cum += x
        return max_price

    avg_cost = cost_at(total * 0.5)
    p90_low, p90_high = cost_at(total * 0.05), cost_at(total * 0.95)
    p70_low, p70_high = cost_at(total * 0.15), cost_at(total * 0.85)

    def conc(lo, hi):
        return (hi - lo) / (hi + lo) if (hi + lo) > 0 else 0.0

    return {
        'profit_ratio': round(profit_ratio, 4),
        'avg_cost': round(avg_cost, 3),
        'cost90_low': round(p90_low, 3),
        'cost90_high': round(p90_high, 3),
        'conc90': round(conc(p90_low, p90_high), 4),
        'cost70_low': round(p70_low, 3),
        'cost70_high': round(p70_high, 3),
        'conc70': round(conc(p70_low, p70_high), 4),
        'price_vs_cost': round(current / avg_cost - 1.0, 4) if avg_cost > 0 else None,
        'win': len(bars),
    }
