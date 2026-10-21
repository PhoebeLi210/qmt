#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自优化实验室测试：路径判定、参数外置、快照落库、矩阵聚合。"""

import os
import sys
import json
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import db
from webapp.lab import tracker, stats
import strategy_params


def bar(date, o, h, l, c):
    return {'date': date, 'open': o, 'high': h, 'low': l, 'close': c}


# 信号日 2026-01-05（周一），T+1 起连续 20 个工作日
DATES = [f'2026-01-{d:02d}' for d in range(6, 26)] + \
        [f'2026-02-{d:02d}' for d in range(2, 5)]


class EvaluateTest(unittest.TestCase):
    """entry=10, sl=5%, tp1=6%, tp2=15%。"""

    def test_win_tp2_first(self):
        bars = [bar(DATES[0], 10, 10.2, 9.9, 10.1),
                bar(DATES[1], 10.1, 10.8, 10.0, 10.7),
                bar(DATES[2], 10.7, 11.6, 10.6, 11.5)]
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['status'], 'closed')
        self.assertEqual(out['path_result'], 'win')
        self.assertEqual(out['exit_reason'], 'tp2')
        self.assertEqual(out['hold_days'], 3)
        # 0.5*6% + 0.5*15% - 0.2%
        self.assertAlmostEqual(out['realized_ret'], 0.103, places=4)

    def test_loss_sl_first(self):
        bars = [bar(DATES[0], 10, 10.2, 9.4, 9.5)]
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['path_result'], 'loss')
        self.assertEqual(out['exit_reason'], 'sl')
        self.assertAlmostEqual(out['realized_ret'], -0.052, places=4)

    def test_same_day_sl_and_tp_counts_sl(self):
        # 同一天最低触止损、最高触止盈 → 保守计止损
        bars = [bar(DATES[0], 10, 11.6, 9.4, 10.0)]
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['path_result'], 'loss')

    def test_tp1_then_sl_composite(self):
        bars = [bar(DATES[0], 10, 10.7, 9.9, 10.5),   # 触 tp1 未触 sl
                bar(DATES[1], 10.4, 10.5, 9.4, 9.6)]  # 次日触 sl
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['path_result'], 'loss')
        self.assertEqual(out['exit_reason'], 'sl_after_tp1')
        self.assertEqual(out['tp1_touched'], 1)
        # 0.5*6% + 0.5*(-5%) - 0.2%
        self.assertAlmostEqual(out['realized_ret'], 0.003, places=4)

    def test_no_entry_main_board_limit_up(self):
        bars = [bar(DATES[0], 11.0, 11.0, 10.6, 10.9)]  # 高开 10%
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['status'], 'no_entry')

    def test_chinext_allows_20pct_gap(self):
        bars = [bar(DATES[0], 11.0, 11.2, 10.7, 11.0)]  # 高开 10%
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sz.300001')
        self.assertNotEqual(out['status'], 'no_entry')

    def test_neutral_after_20_bars(self):
        # 20 根 K 线全部在 (9.6, 11.0) 区间震荡，不触任何边界
        bars = [bar(d, 10.0 + (i % 3) * 0.1, 10.9, 9.7, 10.3)
                for i, d in enumerate(DATES)]
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['status'], 'closed')
        self.assertEqual(out['path_result'], 'neutral')
        self.assertEqual(out['hold_days'], 20)
        self.assertIsNotNone(out['ret_20d'])
        self.assertIsNotNone(out['max_gain'])

    def test_pending_when_bars_short(self):
        bars = [bar(d, 10, 10.2, 9.9, 10.1) for d in DATES[:5]]
        out = tracker.evaluate(10, 5, 6, 15, bars, code='sh.600000')
        self.assertEqual(out['status'], 'pending')
        self.assertIsNotNone(out['ret_3d'])
        self.assertIsNone(out['ret_20d'])

    def test_benchmark_excess(self):
        bars = [bar(d, 10, 10.2, 9.9, 10.5) for d in DATES]
        # 第 20 根收盘 10.5 → ret20 = 5%
        bench = {DATES[0]: 3000.0, DATES[19]: 3030.0}  # 指数 +1%
        out = tracker.evaluate(10, 5, 6, 15, bars,
                               bench=bench, code='sh.600000')
        self.assertAlmostEqual(out['bench_ret_20d'], 0.01, places=4)
        self.assertAlmostEqual(out['excess_20d'], 0.04, places=4)

    def test_empty_inputs(self):
        self.assertEqual(tracker.evaluate(0, 5, 6, 15, [], code='x')['status'],
                         'pending')
        self.assertEqual(tracker.evaluate(10, None, 6, 15,
                         [bar(DATES[0], 10, 10, 10, 10)], code='x')['status'],
                         'pending')

    def test_default_exit_by_pattern(self):
        sl, tp1, tp2, tstop = tracker.default_exit_by_pattern('breakout')
        self.assertEqual((tp1, tp2, tstop), (8.0, 15.0, 8))
        sl2, tp1b, tp2b, _ = tracker.default_exit_by_pattern('v_rebound')
        self.assertEqual((tp1b, tp2b), (5.0, 10.0))
        self.assertEqual(sl, 5.0)       # 无 ATR 时趋势默认
        self.assertEqual(sl2, 3.5)     # 无 ATR 时反弹默认


class ParamsExternalizationTest(unittest.TestCase):

    def setUp(self):
        strategy_params.reset_cache()

    def tearDown(self):
        strategy_params.reset_cache()
        os.environ.pop('CHAOGU_PARAMS_FILE', None)

    def test_baseline_values(self):
        p = strategy_params.get_exit_params()
        self.assertEqual(p['tp_breakout'], [8.0, 15.0, 8])
        self.assertEqual(p['risk_off_sl'], 3.0)
        self.assertEqual(strategy_params.active_version(), 'baseline-v1')

    def test_override_file(self):
        with tempfile.NamedTemporaryFile(
                'w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({'version': 'exp-1',
                       'exit': {'risk_off_sl': 4.0}}, f)
            path = f.name
        try:
            os.environ['CHAOGU_PARAMS_FILE'] = path
            p = strategy_params.get_exit_params()
            self.assertEqual(p['risk_off_sl'], 4.0)
            self.assertEqual(p['tp_breakout'], [8.0, 15.0, 8])  # 未覆盖项不变
            self.assertEqual(strategy_params.active_version(), 'exp-1')
        finally:
            os.unlink(path)


class DbAndStatsTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()
        self.today = datetime.now().strftime('%Y-%m-%d')

    def tearDown(self):
        import gc
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _snap(self, code='sh.600000', pattern='breakout', score=92.0,
              sl=5.0, tp1=8.0, tp2=15.0, signal_date=None):
        db.save_signal_snapshot(
            signal_date or self.today, code, 'full_scan', name='测试', pattern=pattern,
            score=score, final_score=score, risk_score=5,
            market_regime='bull', ref_price=10.0,
            sl_pct=sl, tp1_pct=tp1, tp2_pct=tp2, time_stop_days=8,
            recommended=True, rank_no=1, param_version='baseline-v1')

    def test_snapshot_outcome_roundtrip_and_matrix(self):
        self._snap()
        snaps = db.list_signals_without_outcome(10, max_signal_date=self.today)
        self.assertEqual(len(snaps), 1)
        db.upsert_outcome(snaps[0]['id'], status='closed',
                          path_result='win', realized_ret=0.10,
                          ret_20d=0.12, excess_20d=0.08, hold_days=4)
        # 幂等 upsert
        db.upsert_outcome(snaps[0]['id'], status='closed',
                          path_result='win', realized_ret=0.10,
                          ret_20d=0.12, excess_20d=0.08, hold_days=4)
        mat = stats.matrix(['full_scan'])
        cell = mat[('breakout', 0)]  # 92 分落 ≥90 档
        self.assertEqual(cell['closed'], 1)
        self.assertEqual(cell['wins'], 1)
        self.assertAlmostEqual(cell['win_rate'], 1.0)
        ov = stats.overview(['full_scan'])
        self.assertEqual(ov['n'], 1)
        self.assertEqual(ov['closed'], 1)

    def test_pending_selection_and_sources_filter(self):
        self._snap()
        # 新快照无 outcome：pending 列表查不到（还没建 outcome 行）
        self.assertEqual(len(db.list_pending_outcomes(10)), 0)
        row = db.list_signals_without_outcome(10, max_signal_date=self.today)[0]
        db.upsert_outcome(row['id'], status='pending')
        # 20 小时新鲜度：刚插入的暂不重复处理
        self.assertEqual(len(db.list_pending_outcomes(10, stale_hours=20)), 0)
        # 放宽到 0 小时应能取到
        self.assertEqual(len(db.list_pending_outcomes(10, stale_hours=0)), 1)

    def test_cell_samples(self):
        self._snap()
        rows = stats.cell_samples('breakout', 0, ['full_scan'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['code'], 'sh.600000')
        self.assertEqual(stats.cell_samples('pullback', 0, ['full_scan']), [])

    def test_cutoff_filters_old_signals(self):
        """2026-09-28 之前的信号不应出现在 lab 统计中（无资金流/筹码因子）"""
        old_date = '2026-09-27'
        self._snap(code='sh.600000', signal_date=old_date)
        self._snap(code='sz.000001', signal_date=self.today)  # 新信号
        ov = stats.overview(['full_scan'])
        self.assertEqual(ov['n'], 1, f'应只统计新信号，实际{ov["n"]}')
        mat = stats.matrix(['full_scan'])
        cell = mat[('breakout', 0)]
        self.assertEqual(cell['n'], 1, f'矩阵应只有1条，实际{cell["n"]}')

    def test_cutoff_boundary(self):
        """2026-09-28 当天应被包含"""
        self._snap(code='sh.600000', signal_date='2026-09-28')
        ov = stats.overview(['full_scan'])
        self.assertEqual(ov['n'], 1, f'2026-09-28 应被包含，实际{ov["n"]}')

    def test_p1_version_splitting(self):
        """P1 规则版本拆分：2026-10-19 前=pre，当日起=post"""
        self._snap(code='sh.600001', signal_date='2026-10-18')  # P1 前遗留
        self._snap(code='sh.600002', signal_date='2026-10-19')  # P1 后新信号
        self._snap(code='sh.600003', signal_date='2026-10-20')  # P1 后新信号
        ov = stats.overview(['full_scan'])
        self.assertEqual(ov['n'], 3)
        self.assertIn('pre', ov['by_version'])
        self.assertIn('post', ov['by_version'])
        self.assertIn('total', ov['by_version'])
        self.assertEqual(ov['by_version']['pre']['n'], 1)
        self.assertEqual(ov['by_version']['post']['n'], 2)
        self.assertEqual(ov['by_version']['total']['n'], 3)

    def test_cell_samples_has_version(self):
        """cell_samples 每条样本应携带 version 字段"""
        self._snap(code='sh.600001', signal_date='2026-10-18')
        self._snap(code='sh.600002', signal_date='2026-10-19')
        rows = stats.cell_samples('breakout', 0, ['full_scan'])
        versions = {r['code']: r['version'] for r in rows}
        self.assertEqual(versions['sh.600001'], 'P1前遗留')
        self.assertEqual(versions['sh.600002'], 'P1后')


class P1MonitorTest(unittest.TestCase):
    """P1 防守市规则监控：基线汇总 + 逐日合规校验。"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()

    def tearDown(self):
        import gc
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _snap(self, date, code, regime, score, recommended, pattern='breakout',
              source='full_scan'):
        db.save_signal_snapshot(
            date, code, source, name='测试', pattern=pattern,
            score=score, final_score=score, risk_score=5,
            market_regime=regime, ref_price=10.0,
            sl_pct=5.0, tp1_pct=8.0, tp2_pct=15.0, time_stop_days=8,
            recommended=recommended, rank_no=1 if recommended else None,
            param_version='baseline-v1')

    def test_baseline_and_ok_day(self):
        # P1 前基线：2 天 4 条信号 2 条推荐
        self._snap('2026-10-15', 'sh.600001', 'risk_off', 60, True)
        self._snap('2026-10-15', 'sh.600002', 'risk_off', 58, False)
        self._snap('2026-10-16', 'sh.600003', 'bear', 62, True)
        self._snap('2026-10-16', 'sh.600004', 'bear', 59, False)
        # P1 后 bear 日：全部 ≥55、零推荐 → 生效
        self._snap('2026-10-19', 'sh.600005', 'bear', 70, False)
        self._snap('2026-10-19', 'sh.600006', 'bear', 80, False)
        m = stats.p1_monitor()
        self.assertEqual(m['baseline']['days'], 2)
        self.assertEqual(m['baseline']['per_day'], 2.0)
        self.assertEqual(m['baseline']['rec_per_day'], 1.0)
        self.assertEqual(len(m['days']), 1)
        self.assertEqual(m['days'][0]['status'], 'ok')
        self.assertEqual(m['days'][0]['n'], 2)
        self.assertEqual(m['days'][0]['rec'], 0)
        self.assertEqual(m['violations'], 0)

    def test_violations(self):
        # bear 日有推荐 → 异常
        self._snap('2026-10-20', 'sh.600001', 'bear', 70, True)
        # risk_off 有 <55 分信号 → 异常
        self._snap('2026-10-21', 'sh.600002', 'risk_off', 50, False)
        # risk_off 反转型推荐 → 异常
        self._snap('2026-10-22', 'sh.600003', 'risk_off', 70, True,
                   pattern='v_rebound')
        m = stats.p1_monitor()
        self.assertEqual(m['violations'], 3)
        notes = {d['date']: d['note'] for d in m['days']}
        self.assertIn('推荐', notes['2026-10-20'])
        self.assertIn('<55', notes['2026-10-21'])
        self.assertIn('反转型', notes['2026-10-22'])

    def test_neutral_day_no_constraint(self):
        # bull/neutral 不受 P1 约束：<55 分推荐也不报异常
        self._snap('2026-10-23', 'sh.600001', 'bull', 45, True)
        m = stats.p1_monitor()
        self.assertEqual(m['days'][0]['status'], 'none')
        self.assertEqual(m['violations'], 0)

    def test_watch_source_excluded(self):
        # 自选分析（watch）不受 P1 约束，不纳入监控
        self._snap('2026-10-19', 'sh.600001', 'bear', 40, True,
                   source='watch')
        m = stats.p1_monitor()
        self.assertEqual(m['days'], [])
        self.assertEqual(m['violations'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
