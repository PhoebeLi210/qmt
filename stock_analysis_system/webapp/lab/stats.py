#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板统计：总览 + 形态 × 分数段胜率矩阵。"""

from webapp import db

PATTERN_ORDER = ['breakout', 'pullback', 'v_rebound', 'double_bottom',
                 'consolidation_breakout', 'acceleration', 'upward_trend',
                 'bottom_rebound']
PATTERN_LABELS = {
    'breakout': '放量突破',
    'pullback': '回踩企稳',
    'v_rebound': 'V型反弹',
    'double_bottom': '双底形态',
    'consolidation_breakout': '横盘突破',
    'acceleration': '加速上涨',
    'upward_trend': '上涨趋势',
    'bottom_rebound': '触底反弹',
    'other': '其他/未识别',
}
BAND_ORDER = [0, 1, 2, 3, 4]
BAND_LABELS = {0: '≥90', 1: '80–90', 2: '70–80', 3: '60–70', 4: '<60'}
SOURCES = ['full_scan', 'watch', 'history']
SOURCE_LABELS = {'full_scan': '全候选扫描', 'watch': '自选分析', 'history': '历史回填'}
REGIMES = ['bull', 'neutral', 'bear', 'risk_off']
MIN_SAMPLE = 30

# 资金流/筹码因子纳入评分的分界日（之前的胜率不含这两因子，不代表当前策略）
FUND_CHIP_CUTOFF = '2026-09-28'

# P1 防守市规则首个生效交易日（2026-10-17 周六部署，10-19 周一起跑）
P1_EFFECTIVE_DATE = '2026-10-19'
# 反转型/抄底型形态（与 market_timing.COUNTER_TREND_PATTERNS 保持一致；
# 此处独立定义避免 lab 依赖策略模块）
_P1_COUNTER_TREND = ('v_rebound', 'double_bottom', 'bottom_rebound')

_BAND_SQL = """CASE
  WHEN score >= 90 THEN 0 WHEN score >= 80 THEN 1
  WHEN score >= 70 THEN 2 WHEN score >= 60 THEN 3
  ELSE 4 END"""
_PAT_SQL = ("CASE WHEN pattern IN "
            "('breakout','pullback','v_rebound','double_bottom',"
            "'consolidation_breakout','acceleration','upward_trend','bottom_rebound') "
            "THEN pattern ELSE 'other' END")


def _where(sources, regime):
    where = ['s.source IN (%s)' % ','.join('?' * len(sources))]
    args = list(sources)
    # 只统计含资金流/筹码因子的新逻辑信号（2026-09-28 起）
    where.append('s.signal_date >= ?')
    args.append(FUND_CHIP_CUTOFF)
    if regime:
        where.append('s.market_regime = ?')
        args.append(regime)
    return ' AND '.join(where), args


def overview(sources, regime=None):
    where, args = _where(sources, regime)
    with db.get_db() as conn:
        row = conn.execute(f"""
            SELECT
              COUNT(*) AS n,
              SUM(CASE WHEN o.status IS NULL OR o.status='pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN o.status='no_entry' THEN 1 ELSE 0 END) AS no_entry,
              SUM(CASE WHEN o.status='closed' THEN 1 ELSE 0 END) AS closed,
              SUM(CASE WHEN o.path_result='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN o.path_result='loss' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN o.path_result='neutral' THEN 1 ELSE 0 END) AS neutrals,
              AVG(CASE WHEN o.status='closed' THEN o.realized_ret END) AS avg_realized,
              AVG(CASE WHEN o.ret_20d IS NOT NULL THEN o.ret_20d END) AS avg_ret20,
              AVG(CASE WHEN o.excess_20d IS NOT NULL THEN o.excess_20d END) AS avg_excess,
              AVG(CASE WHEN o.status='closed' THEN o.hold_days END) AS avg_hold
            FROM signal_snapshots s
            LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
            WHERE {where}""", args).fetchone()

        # 按 P1 规则版本拆分（P1前遗留 vs P1后新信号），让新旧胜率分离可见
        by_v_rows = conn.execute(f"""
            SELECT
              CASE WHEN s.signal_date >= ? THEN 'post' ELSE 'pre' END AS version,
              COUNT(*) AS n,
              SUM(CASE WHEN o.status IS NULL OR o.status='pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN o.status='closed' THEN 1 ELSE 0 END) AS closed,
              SUM(CASE WHEN o.path_result='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN o.path_result='loss' THEN 1 ELSE 0 END) AS losses,
              AVG(CASE WHEN o.status='closed' THEN o.realized_ret END) AS avg_realized,
              AVG(CASE WHEN o.status='closed' THEN o.hold_days END) AS avg_hold
            FROM signal_snapshots s
            LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
            WHERE {where}
            GROUP BY version""", [P1_EFFECTIVE_DATE] + args).fetchall()
    ov = dict(row)
    ov['by_version'] = {}
    for vr in by_v_rows:
        d = dict(vr)
        d['win_rate'] = (d['wins'] / d['closed']) if d['closed'] else None
        ov['by_version'][d['version']] = d
    # 合计行（与 ov 主行重复，但给模板统一迭代用）
    ov['by_version']['total'] = {
        'version': 'total',
        'n': ov['n'], 'pending': ov['pending'], 'closed': ov['closed'],
        'wins': ov['wins'], 'losses': ov['losses'], 'avg_realized': ov['avg_realized'],
        'avg_hold': ov['avg_hold'],
        'win_rate': (ov['wins'] / ov['closed']) if ov['closed'] else None,
    }

    # 按大盘状态分组统计（核心！判断策略在不同行情下的真实表现）
    by_regime_rows = conn.execute(f"""
        SELECT
          COALESCE(s.market_regime, 'unknown') AS regime,
          COUNT(*) AS n,
          SUM(CASE WHEN o.status IS NULL OR o.status='pending' THEN 1 ELSE 0 END) AS pending,
          SUM(CASE WHEN o.status='closed' THEN 1 ELSE 0 END) AS closed,
          SUM(CASE WHEN o.path_result='win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN o.path_result='loss' THEN 1 ELSE 0 END) AS losses,
          AVG(CASE WHEN o.status='closed' THEN o.realized_ret END) AS avg_realized,
          AVG(CASE WHEN o.status='closed' THEN o.hold_days END) AS avg_hold
        FROM signal_snapshots s
        LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
        WHERE {where}
        GROUP BY s.market_regime
        ORDER BY CASE s.market_regime
          WHEN 'bull' THEN 1 WHEN 'neutral' THEN 2
          WHEN 'risk_off' THEN 3 WHEN 'bear' THEN 4 ELSE 5 END""", args).fetchall()
    ov['by_regime'] = []
    for rr in by_regime_rows:
        d = dict(rr)
        d['win_rate'] = (d['wins'] / d['closed']) if d['closed'] else None
        ov['by_regime'].append(d)
    return ov


def matrix(sources, regime=None):
    """返回 {(pattern_key, band): 统计 dict}，只统计 closed 行的胜率。"""
    where, args = _where(sources, regime)
    with db.get_db() as conn:
        rows = conn.execute(f"""
            SELECT {_PAT_SQL} AS pat, {_BAND_SQL} AS band,
              COUNT(*) AS n,
              SUM(CASE WHEN o.status='closed' THEN 1 ELSE 0 END) AS closed,
              SUM(CASE WHEN o.path_result='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN o.path_result='loss' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN o.path_result='neutral' THEN 1 ELSE 0 END) AS neutrals,
              AVG(CASE WHEN o.status='closed' THEN o.realized_ret END) AS avg_realized,
              AVG(CASE WHEN o.ret_20d IS NOT NULL THEN o.ret_20d END) AS avg_ret20,
              AVG(CASE WHEN o.excess_20d IS NOT NULL THEN o.excess_20d END) AS avg_excess
            FROM signal_snapshots s
            LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
            WHERE {where}
            GROUP BY pat, band""", args).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        d['win_rate'] = (d['wins'] / d['closed']) if d['closed'] else None
        out[(r['pat'], r['band'])] = d
    return out


def cell_samples(pattern_key, band, sources, regime=None, limit=200):
    """格子下钻：该形态×分数段的信号明细。"""
    where, args = _where(sources, regime)
    where += f' AND {_PAT_SQL} = ? AND {_BAND_SQL} = ?'
    args += [pattern_key, band]
    with db.get_db() as conn:
        rows = conn.execute(f"""
            SELECT s.signal_date, s.code, s.name, s.pattern, s.score,
                   CASE WHEN s.signal_date >= ? THEN 'P1后' ELSE 'P1前遗留' END AS version,
                   s.market_regime, s.recommended, s.ref_price, s.source,
                   o.status, o.path_result, o.realized_ret,
                   o.ret_5d, o.ret_20d, o.excess_20d, o.hold_days, o.exit_reason,
                   o.entry_date, o.entry_price
            FROM signal_snapshots s
            LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
            WHERE {where}
            ORDER BY s.signal_date DESC, s.id DESC LIMIT ?""",
            [P1_EFFECTIVE_DATE] + args + [limit]).fetchall()
    return [dict(r) for r in rows]


def p1_monitor():
    """P1 防守市规则监控：基线（因子分界日~P1前）vs P1 后逐日信号量与合规校验。

    校验规则（仅全市场来源 full_scan/history；自选分析不受 P1 约束）：
      - 防守市（bear/risk_off）当日信号应全部 ≥55 分（main.py 门槛）
      - bear 当日推荐数应为 0（引擎停推）
      - risk_off 当日推荐中不应有反转型形态
    返回 {'effective', 'baseline': {days, per_day, rec_per_day},
          'days': [...], 'violations': int}
    """
    ct = "','".join(_P1_COUNTER_TREND)
    with db.get_db() as conn:
        base = conn.execute("""
            SELECT COUNT(DISTINCT signal_date) AS days, COUNT(*) AS n,
                   COALESCE(SUM(recommended), 0) AS rec
            FROM signal_snapshots
            WHERE source IN ('full_scan','history')
              AND signal_date >= ? AND signal_date < ?""",
            (FUND_CHIP_CUTOFF, P1_EFFECTIVE_DATE)).fetchone()
        rows = conn.execute(f"""
            SELECT signal_date, market_regime, COUNT(*) AS n,
                   COALESCE(SUM(recommended), 0) AS rec,
                   AVG(score) AS avg_score,
                   SUM(CASE WHEN score < 55 THEN 1 ELSE 0 END) AS lt55,
                   SUM(CASE WHEN recommended = 1 AND pattern IN ('{ct}')
                            THEN 1 ELSE 0 END) AS ct_rec
            FROM signal_snapshots
            WHERE source IN ('full_scan','history') AND signal_date >= ?
            GROUP BY signal_date, market_regime
            ORDER BY signal_date DESC""", (P1_EFFECTIVE_DATE,)).fetchall()

    # 同日可能因盘中/盘后择时变化出现多行 → 按日合并
    by_date = {}
    for r in rows:
        d = by_date.setdefault(r['signal_date'], {
            'date': r['signal_date'], 'regimes': set(), 'n': 0, 'rec': 0,
            '_score_sum': 0.0, 'lt55': 0, 'ct_rec': 0})
        d['regimes'].add(r['market_regime'] or 'unknown')
        d['n'] += r['n']
        d['rec'] += r['rec'] or 0
        d['_score_sum'] += (r['avg_score'] or 0) * r['n']
        d['lt55'] += r['lt55'] or 0
        d['ct_rec'] += r['ct_rec'] or 0

    days = []
    for d in by_date.values():
        d['avg_score'] = round(d['_score_sum'] / d['n'], 1) if d['n'] else None
        d.pop('_score_sum')
        d['regime'] = '/'.join(sorted(d.pop('regimes')))
        regime_set = set(d['regime'].split('/'))
        problems = []
        if regime_set & {'bear', 'risk_off'} and d['lt55']:
            problems.append(f"{d['lt55']}条信号<55分")
        if 'bear' in regime_set and d['rec']:
            problems.append(f"bear日推荐{d['rec']}条")
        if 'risk_off' in regime_set and d['ct_rec']:
            problems.append(f"反转型推荐{d['ct_rec']}条")
        if problems:
            d['status'], d['note'] = 'violation', '；'.join(problems)
        elif regime_set & {'bear', 'risk_off'}:
            d['status'], d['note'] = 'ok', '防守规则生效'
        else:
            d['status'], d['note'] = 'none', ''
        days.append(d)
    days.sort(key=lambda x: x['date'], reverse=True)

    b_days = base['days'] or 0
    baseline = {
        'days': b_days,
        'per_day': round((base['n'] or 0) / b_days, 1) if b_days else 0,
        'rec_per_day': round((base['rec'] or 0) / b_days, 1) if b_days else 0,
    }
    return {'effective': P1_EFFECTIVE_DATE, 'baseline': baseline,
            'days': days,
            'violations': sum(1 for d in days if d['status'] == 'violation')}
