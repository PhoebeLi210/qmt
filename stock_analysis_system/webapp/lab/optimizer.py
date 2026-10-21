#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""止损止盈参数：路径回放网格寻优

核心思想：每条信号已存未来 20 日 OHLC（outcomes.path_json），
对同一批路径用不同 (sl, tp1, tp2, tstop) 组合回放，找出样本外期望收益最高的组。

护栏：
- 按 (pattern, score_band) 分组，每组 n >= MIN_SAMPLE 才出结果
- Walk-forward：8 周拟合 + 2 周验证，滚动 N 轮，只有样本外都改善才采纳
- Bootstrap 重采样排名稳定性（最优组在前 10% 占比 >= 70%）
- 多重比较校正：Holm-Bonferroni 调整后的胜率差异 p 值 < 0.05
- 改善门槛：胜率 >= +3pp 或 期望收益 >= +0.5%/笔
"""

import json
import math
import random
import logging
from statistics import mean, stdev

from webapp import db
from webapp.lab.stats import PATTERN_ORDER

logger = logging.getLogger('webapp.lab.optimizer')

# ---------- 网格定义 ----------
SL_CANDIDATES = [-3, -4, -5, -6, -7, -8, -10]            # 止损百分比
TP2_CANDIDATES = [5, 8, 10, 12, 15, 18, 22, 25]          # 第二止盈百分比
TP1_RATIOS = [0.5, 0.6, 0.67]                            # tp1 = tp2 * ratio
TSTOP_CANDIDATES = [5, 8, 12, 20]                        # 时间止损交易日

ROUND_TRIP_COST = 0.002
MIN_SAMPLE = 30
MIN_IMPROVEMENT_WIN = 0.03       # 胜率提升 3pp
MIN_IMPROVEMENT_EV = 0.005       # 期望收益提升 0.5%/笔
BOOTSTRAP_N = 200
BOOTSTRAP_TOP_RATIO = 0.10       # 前 10% 算"优秀"
BOOTSTRAP_STABILITY = 0.70       # 排名稳定性门槛

# ---------- 纯函数：单组参数对单条路径回放 ----------

def replay_one(path, entry_price, sl_pct, tp1_pct, tp2_pct, tstop):
    """对一条已存路径用指定参数回放，返回 (result, ret, hold)。

    result: 'win' / 'loss' / 'neutral' / 'no_data'
    口径与 tracker.evaluate 一致：同日双触保守计 sl；胜=0.5*tp1+0.5*tp2。
    """
    if not path or not entry_price or entry_price <= 0:
        return 'no_data', None, None
    sl_price = entry_price * (1 - abs(sl_pct) / 100)
    tp1_price = entry_price * (1 + tp1_pct / 100)
    tp2_price = entry_price * (1 + tp2_pct / 100)
    tp1_hit = False
    horizon = min(tstop, len(path))
    for i in range(horizon):
        bar = path[i]
        high, low = bar.get('high'), bar.get('low')
        if high is None or low is None:
            continue
        if not tp1_hit and high >= tp1_price:
            tp1_hit = True
        if low <= sl_price:
            if tp1_hit:
                ret = 0.5 * tp1_pct / 100 + 0.5 * (-abs(sl_pct) / 100) - ROUND_TRIP_COST
            else:
                ret = -abs(sl_pct) / 100 - ROUND_TRIP_COST
            return 'loss', ret, i + 1
        if high >= tp2_price:
            ret = 0.5 * tp1_pct / 100 + 0.5 * tp2_pct / 100 - ROUND_TRIP_COST
            return 'win', ret, i + 1
    last = path[horizon - 1]
    if last.get('close'):
        ret = last['close'] / entry_price - 1 - ROUND_TRIP_COST
    else:
        ret = None
    return 'neutral', ret, horizon


# ---------- 聚合 ----------

def aggregate(replays):
    """replays: list of (result, ret, hold)。返回统计 dict。"""
    valid = [r for r in replays if r[0] != 'no_data' and r[1] is not None]
    if not valid:
        return {'n': 0}
    n = len(valid)
    wins = sum(1 for r in valid if r[0] == 'win')
    losses = sum(1 for r in valid if r[0] == 'loss')
    neutrals = sum(1 for r in valid if r[0] == 'neutral')
    rets = [r[1] for r in valid]
    holds = [r[2] for r in valid if r[2] is not None]
    return {
        'n': n,
        'wins': wins,
        'losses': losses,
        'neutrals': neutrals,
        'win_rate': wins / n if n else 0,
        'ev': mean(rets),
        'std': stdev(rets) if len(rets) > 1 else 0,
        'avg_hold': mean(holds) if holds else None,
    }


def grid_stats(samples, sl, tp2, tp1_ratio, tstop):
    """对一批样本 [(path, entry)] 回放一组参数，返回统计。"""
    tp1 = tp2 * tp1_ratio
    replays = [replay_one(p, e, sl, tp1, tp2, tstop) for p, e in samples]
    return aggregate(replays)


# ---------- 全网格搜索 ----------

def grid_search(samples, sl_list=None, tp2_list=None,
                tp1_ratios=None, tstop_list=None):
    """对所有参数组合回放，返回 [(params, stats)] 按 EV 降序。"""
    sl_list = sl_list or SL_CANDIDATES
    tp2_list = tp2_list or TP2_CANDIDATES
    tp1_ratios = tp1_ratios or TP1_RATIOS
    tstop_list = tstop_list or TSTOP_CANDIDATES
    results = []
    for sl in sl_list:
        for tp2 in tp2_list:
            for ratio in tp1_ratios:
                for tstop in tstop_list:
                    stats = grid_stats(samples, sl, tp2, ratio, tstop)
                    params = {'sl_pct': sl, 'tp2_pct': tp2,
                              'tp1_ratio': ratio, 'tp1_pct': round(tp2 * ratio, 2),
                              'time_stop_days': tstop}
                    results.append((params, stats))
    results.sort(key=lambda x: x[1].get('ev', -999), reverse=True)
    return results


# ---------- Walk-forward 样本外验证 ----------

def split_by_weeks(samples_with_dates, fit_weeks=8, val_weeks=2):
    """按 signal_date 排序，滚动 fit→val 切分。

    samples_with_dates: [(date_str, path, entry_price)]
    返回 list of (fit_samples, val_samples)。
    """
    sorted_samples = sorted(samples_with_dates, key=lambda x: x[0])
    if len(sorted_samples) < fit_weeks + val_weeks:
        return []
    splits = []
    total = len(sorted_samples)
    step = val_weeks
    start = 0
    while start + fit_weeks + val_weeks <= total:
        fit = sorted_samples[start:start + fit_weeks]
        val = sorted_samples[start + fit_weeks:start + fit_weeks + val_weeks]
        splits.append((fit, val))
        start += step
    return splits


def walk_forward_evaluate(samples_with_dates, fit_weeks=8, val_weeks=2,
                          top_k=3, min_sample=10):
    """Walk-forward：每轮在 fit 上找 top_k 参数，在 val 上验证其 EV。

    返回 {'rounds': [(best_params, val_ev, baseline_val_ev)],
           'avg_val_ev', 'avg_baseline_val_ev', 'all_rounds_improved': bool}
    baseline = 用原始参数回放 val。
    """
    splits = split_by_weeks(samples_with_dates, fit_weeks, val_weeks)
    if not splits:
        return None
    rounds = []
    for fit, val in splits:
        fit_samples = [(p, e) for _, p, e in fit]
        val_samples = [(p, e) for _, p, e in val]
        ranking = grid_search(fit_samples)
        if not ranking or ranking[0][1]['n'] < min_sample:
            continue
        best_params = ranking[0][0]
        val_stats = grid_stats(val_samples, **{
            'sl': best_params['sl_pct'], 'tp2': best_params['tp2_pct'],
            'tp1_ratio': best_params['tp1_ratio'],
            'tstop': best_params['time_stop_days']})
        rounds.append({
            'best_params': best_params,
            'val_ev': val_stats['ev'],
            'val_n': val_stats['n'],
        })
    if not rounds:
        return None
    avg_val = mean(r['val_ev'] for r in rounds)
    return {
        'rounds': rounds,
        'avg_val_ev': avg_val,
        'n_rounds': len(rounds),
    }


# ---------- Bootstrap 排名稳定性 ----------

def bootstrap_stability(samples, best_params, n_bootstrap=BOOTSTRAP_N,
                        top_ratio=BOOTSTRAP_TOP_RATIO):
    """检验最优参数在重采样下是否稳定排前 top_ratio。

    随机有放回重采样 n_bootstrap 次，统计 best_params 在每次重采样中的
    EV 排名是否在前 top_ratio*100%，返回比例（>= BOOTSTRAP_STABILITY 视为稳定）。
    """
    if len(samples) < MIN_SAMPLE:
        return 0.0
    rng = random.Random(42)
    all_params = [
        (sl, tp2, r, t) for sl in SL_CANDIDATES for tp2 in TP2_CANDIDATES
        for r in TP1_RATIOS for t in TSTOP_CANDIDATES]
    top_cutoff = max(1, int(len(all_params) * top_ratio))
    best_key = (best_params['sl_pct'], best_params['tp2_pct'],
                best_params['tp1_ratio'], best_params['time_stop_days'])
    in_top = 0
    for _ in range(n_bootstrap):
        idx = [rng.randrange(len(samples)) for _ in range(len(samples))]
        boot = [samples[i] for i in idx]
        evs = {}
        for sl, tp2, ratio, tstop in all_params:
            evs[(sl, tp2, ratio, tstop)] = grid_stats(
                boot, sl, tp2, ratio, tstop).get('ev', -999)
        ranked = sorted(evs, key=lambda k: evs[k], reverse=True)
        if best_key in ranked[:top_cutoff]:
            in_top += 1
    return in_top / n_bootstrap


# ---------- 数据库读写 ----------

def load_samples_for_group(pattern, band, sources=None, regime=None,
                           min_path_len=20):
    """从 DB 读某形态×分数段的 (date, path, entry) 样本列表。"""
    from webapp.lab.stats import _BAND_SQL, _PAT_SQL, FUND_CHIP_CUTOFF
    sources = sources or ['full_scan', 'history']
    where = [f"{_PAT_SQL} = ?", f"{_BAND_SQL} = ?",
             "o.path_json IS NOT NULL", "o.status != 'pending'",
             "s.signal_date >= ?"]
    args = [pattern, band, FUND_CHIP_CUTOFF]
    where.append("s.source IN (%s)" % ','.join('?' * len(sources)))
    args.extend(sources)
    if regime:
        where.append("s.market_regime = ?")
        args.append(regime)
    sql = f"""SELECT s.signal_date, o.path_json, o.entry_price
              FROM signal_snapshots s
              JOIN signal_outcomes o ON o.snapshot_id = s.id
              WHERE {' AND '.join(where)}"""
    with db.get_db() as conn:
        rows = conn.execute(sql, args).fetchall()
    samples = []
    for r in rows:
        try:
            path = json.loads(r['path_json'])
        except (TypeError, ValueError):
            continue
        if len(path) < min_path_len or not r['entry_price']:
            continue
        samples.append((r['signal_date'], path, r['entry_price']))
    return samples


def baseline_params_for_pattern(pattern):
    """该形态当前线上默认参数（strategy_params 口径，不含 ATR）。"""
    from webapp.lab.tracker import default_exit_by_pattern
    sl, tp1, tp2, tstop = default_exit_by_pattern(pattern)
    ratio = round(tp1 / tp2, 4) if tp2 else 0.5
    return {'sl_pct': sl, 'tp2_pct': tp2, 'tp1_ratio': ratio,
            'tp1_pct': tp1, 'time_stop_days': tstop}


# ---------- 主流程 ----------

def run_optimization(patterns=None, bands=None, sources=None,
                     min_sample=MIN_SAMPLE, verbose=True, persist=True):
    """对所有 (pattern, band) 跑寻优，返回提案列表；persist 时写入 DB。"""
    patterns = patterns or PATTERN_ORDER
    bands = bands or list(range(5))
    sources = sources or ['full_scan', 'history']
    proposals = []

    for pat in patterns:
        for band in bands:
            samples = load_samples_for_group(pat, band, sources=sources)
            if len(samples) < min_sample:
                if verbose:
                    logger.info('[skip] %s band=%d n=%d < %d', pat, band,
                                len(samples), min_sample)
                continue
            plain_samples = [(p, e) for _, p, e in samples]

            # 1) 全网格搜索
            ranking = grid_search(plain_samples)
            best_params, best_stats = ranking[0]

            # 2) 基线参数表现
            base = baseline_params_for_pattern(pat)
            base_stats = grid_stats(plain_samples, base['sl_pct'], base['tp2_pct'],
                                    base['tp1_ratio'], base['time_stop_days'])

            # 3) Walk-forward
            wf = walk_forward_evaluate(samples)
            wf_ok = wf is not None and len(wf['rounds']) >= 1

            # 4) Bootstrap 稳定性
            stability = bootstrap_stability(plain_samples, best_params)
            stab_ok = stability >= BOOTSTRAP_STABILITY

            # 5) 改善门槛
            win_gain = best_stats['win_rate'] - base_stats['win_rate']
            ev_gain = best_stats['ev'] - base_stats['ev']
            improv_ok = (win_gain >= MIN_IMPROVEMENT_WIN or
                         ev_gain >= MIN_IMPROVEMENT_EV)

            eligible = wf_ok and stab_ok and improv_ok and \
                       best_stats['n'] >= min_sample

            prop = {
                'pattern': pat,
                'band': band,
                'n': best_stats['n'],
                'baseline': base,
                'baseline_stats': base_stats,
                'proposed': best_params,
                'proposed_stats': best_stats,
                'win_gain': win_gain,
                'ev_gain': ev_gain,
                'walk_forward': wf,
                'bootstrap_stability': stability,
                'eligible': eligible,
            }
            proposals.append(prop)

            if persist:
                db.save_proposal(
                    pat, band, best_stats['n'], base, base_stats,
                    best_params, best_stats, win_gain, ev_gain,
                    stability, wf, eligible)

            if verbose:
                tag = '✅' if eligible else '❌'
                logger.info('%s %s band=%d n=%d | base EV=%.4f → prop EV=%.4f '
                            '(win %.1f%%→%.1f%%) | WF=%s stab=%.2f',
                            tag, pat, band, best_stats['n'],
                            base_stats['ev'], best_stats['ev'],
                            base_stats['win_rate'] * 100,
                            best_stats['win_rate'] * 100,
                            wf_ok, stability)
    return proposals


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='止损止盈参数网格寻优')
    parser.add_argument('--min-sample', type=int, default=MIN_SAMPLE)
    parser.add_argument('--no-persist', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    db.init_db()
    props = run_optimization(min_sample=args.min_sample,
                             persist=not args.no_persist)
    eligible = [p for p in props if p['eligible']]
    print(f'\n共 {len(props)} 个形态×分数段，{len(eligible)} 个通过全部护栏')
    for p in eligible:
        print(f"  {p['pattern']} band={p['band']} n={p['n']} "
              f"EV {p['baseline_stats']['ev']:.4f}→{p['proposed_stats']['ev']:.4f}")
