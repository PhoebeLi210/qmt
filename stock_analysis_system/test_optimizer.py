#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径回放网格寻优测试。"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import db
from webapp.lab import optimizer as opt


def bar(d, o, h, l, c):
    return {'date': d, 'open': o, 'high': h, 'low': l, 'close': c}


class ReplayOneTest(unittest.TestCase):

    def test_win_tp2(self):
        path = [bar('d1', 10, 10.2, 9.9, 10.1),
                bar('d2', 10.1, 11.6, 10.0, 11.5)]
        r = opt.replay_one(path, 10, -5, 8, 15, 20)
        self.assertEqual(r[0], 'win')
        # 0.5*8% + 0.5*15% - 0.2%
        self.assertAlmostEqual(r[1], 0.113, places=4)

    def test_loss_sl(self):
        path = [bar('d1', 10, 10.2, 9.4, 9.5)]
        r = opt.replay_one(path, 10, -5, 8, 15, 20)
        self.assertEqual(r[0], 'loss')
        self.assertAlmostEqual(r[1], -0.052, places=4)

    def test_same_day_sl_and_tp_counts_sl(self):
        path = [bar('d1', 10, 11.6, 9.4, 10.0)]
        r = opt.replay_one(path, 10, -5, 8, 15, 20)
        self.assertEqual(r[0], 'loss')

    def test_tp1_then_sl_composite(self):
        path = [bar('d1', 10, 10.9, 9.9, 10.5),  # 触 tp1(10.8)
                bar('d2', 10.4, 10.5, 9.4, 9.6)]  # 触 sl
        r = opt.replay_one(path, 10, -5, 8, 15, 20)
        self.assertEqual(r[0], 'loss')
        # 0.5*8% + 0.5*(-5%) - 0.2%
        self.assertAlmostEqual(r[1], 0.013, places=4)

    def test_neutral_after_tstop(self):
        path = [bar(f'd{i}', 10 + (i % 2) * 0.1, 10.9, 9.6, 10.3) for i in range(8)]
        r = opt.replay_one(path, 10, -5, 8, 15, 5)
        self.assertEqual(r[0], 'neutral')
        self.assertEqual(r[2], 5)

    def test_no_data(self):
        self.assertEqual(opt.replay_one([], 10, -5, 8, 15, 20)[0], 'no_data')
        self.assertEqual(opt.replay_one([bar('d', 0, 0, 0, 0)], 0, -5, 8, 15, 20)[0],
                         'no_data')


class AggregateAndGridTest(unittest.TestCase):

    def setUp(self):
        # 10 条路径：6 条稳涨触 tp2，4 条小跌触 sl
        self.samples = []
        for _ in range(6):
            self.samples.append(([
                bar('d1', 10, 11.5, 9.9, 11.4),
                bar('d2', 11.4, 12.0, 11.3, 11.8),
            ], 10.0))
        for _ in range(4):
            self.samples.append(([
                bar('d1', 10, 10.1, 9.4, 9.5),
            ], 10.0))

    def test_aggregate(self):
        replays = [opt.replay_one(p, e, -5, 8, 15, 20) for p, e in self.samples]
        s = opt.aggregate(replays)
        self.assertEqual(s['n'], 10)
        self.assertEqual(s['wins'], 6)
        self.assertAlmostEqual(s['win_rate'], 0.6)
        self.assertGreater(s['ev'], 0)

    def test_grid_search_returns_sorted(self):
        results = opt.grid_search(self.samples, sl_list=[-5, -8],
                                  tp2_list=[15, 20], tp1_ratios=[0.5],
                                  tstop_list=[20])
        self.assertEqual(len(results), 4)
        self.assertGreaterEqual(results[0][1]['ev'], results[-1][1]['ev'])

    def test_grid_search_picks_high_tp_for_this_data(self):
        # 路径 close=10.1（neutral 收益低），tp2=15 刚好触，tp2=20 触不到
        # → tp2=15 的 win 收益 > tp2=20 的 neutral 收益
        samples = []
        for _ in range(6):
            samples.append(([
                bar('d1', 10, 11.5, 9.9, 10.1),
                bar('d2', 10.1, 11.5, 10.0, 10.1),
            ], 10.0))
        for _ in range(4):
            samples.append(([
                bar('d1', 10, 10.1, 9.4, 9.5),
            ], 10.0))
        results = opt.grid_search(samples, sl_list=[-5],
                                  tp2_list=[15, 20], tp1_ratios=[0.5],
                                  tstop_list=[20])
        best_tp2 = results[0][0]['tp2_pct']
        self.assertEqual(best_tp2, 15)


class WalkForwardTest(unittest.TestCase):

    def test_split_insufficient_data(self):
        samples = [('2026-01-%02d' % (d + 1), [], 10) for d in range(5)]
        self.assertEqual(opt.split_by_weeks(samples, 8, 2), [])

    def test_split_creates_rolling_windows(self):
        samples = [('2026-01-%02d' % (d + 1), [], 10) for d in range(14)]
        splits = opt.split_by_weeks(samples, 8, 2)
        # 14 天，8+2=10，step=2：轮1 0-9，轮2 2-11，轮3 4-13
        self.assertEqual(len(splits), 3)
        self.assertEqual(len(splits[0][0]), 8)
        self.assertEqual(len(splits[0][1]), 2)

    def test_walk_forward_returns_rounds(self):
        # 构造 12 个日期、每个含 20 天路径的数据
        samples = []
        for i in range(12):
            date = f'2026-0{(i // 9) + 1}-{((i % 9) + 1):02d}'
            path = [bar(f'd{j}', 10, 11.5, 9.9, 11.4) for j in range(3)]
            samples.append((date, path, 10.0))
        result = opt.walk_forward_evaluate(samples, fit_weeks=8, val_weeks=2,
                                           min_sample=1)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['n_rounds'], 1)


class BootstrapTest(unittest.TestCase):

    def test_stability_high_for_dominant_param(self):
        # 全是上涨路径，最优参数应是最松止损(sl=-3)+最大止盈(tp2=25)+最高tp1比(0.67)
        samples = [([bar(f'd{j}', 10, 13, 9.9, 12.8) for j in range(3)], 10.0)
                   for _ in range(40)]
        best = {'sl_pct': -3, 'tp2_pct': 25, 'tp1_ratio': 0.67,
                'time_stop_days': 20}
        stab = opt.bootstrap_stability(samples, best, n_bootstrap=30)
        self.assertGreater(stab, 0.5)

    def test_stability_low_for_small_sample(self):
        samples = [([bar('d1', 10, 10.1, 9.9, 10.0)], 10.0) for _ in range(10)]
        best = {'sl_pct': -5, 'tp2_pct': 15, 'tp1_ratio': 0.5, 'time_stop_days': 20}
        self.assertEqual(opt.bootstrap_stability(samples, best), 0.0)


class DbIntegrationTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()
        self.today = '2026-01-05'

    def tearDown(self):
        import gc; gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_load_samples_for_group(self):
        path = [bar(f'd{i}', 10, 11, 9.5, 10.5) for i in range(20)]
        db.save_signal_snapshot(
            self.today, 'sh.600000', 'history', name='X', pattern='breakout',
            score=92.0, ref_price=10.0, sl_pct=5.0, tp1_pct=8.0, tp2_pct=15.0,
            time_stop_days=8)
        snap = db.list_signals_without_outcome(10, max_signal_date=self.today)[0]
        db.upsert_outcome(snap['id'], status='closed', path_result='win',
                          entry_price=10.0, path_json=json.dumps(path))
        samples = opt.load_samples_for_group('breakout', 0, sources=['history'])
        self.assertEqual(len(samples), 1)
        self.assertEqual(len(samples[0][1]), 20)

    def test_run_optimization_skips_small_sample(self):
        # 只有 1 条样本，应跳过
        path = [bar(f'd{i}', 10, 11, 9.5, 10.5) for i in range(20)]
        db.save_signal_snapshot(
            self.today, 'sh.600000', 'history', name='X', pattern='breakout',
            score=92.0, ref_price=10.0)
        snap = db.list_signals_without_outcome(10, max_signal_date=self.today)[0]
        db.upsert_outcome(snap['id'], status='closed', path_result='win',
                          entry_price=10.0, path_json=json.dumps(path))
        props = opt.run_optimization(patterns=['breakout'], bands=[0],
                                     sources=['history'], min_sample=30,
                                     verbose=False)
        self.assertEqual(len(props), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
