#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中监控（二期止损止盈/买点 + 三期移动止损/见顶近似）规则测试。

不依赖网络：用临时 SQLite + 假实时快照，直接驱动 monitor.run_cycle。
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import db, monitor
from webapp.lab import holdings


def spot(price, high=None, preclose=10.0, pct=0.0, vr=None,
         low=None, open_=None):
    return {
        'price': price,
        'pct': pct,
        'high': high if high is not None else price,
        'low': low if low is not None else price,
        'open': open_ if open_ is not None else price,
        'preclose': preclose,
        'vol_ratio': vr,
    }


class MonitorRulesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()
        self.uid = db.create_user('u1', 'x')
        self.today = datetime.now().strftime('%Y-%m-%d')
        # 屏蔽真实行情
        self._orig_spot = monitor.get_spot_map
        monitor.get_spot_map = lambda force=False: self._snap
        self._snap = {}
        # 屏蔽真实资金流接口（run_cycle 内局部 import，须在 holdings 模块上打桩）
        self._orig_fund = holdings.get_main_outflow_map
        holdings.get_main_outflow_map = lambda codes: self._fund
        self._fund = {}

    def tearDown(self):
        monitor.get_spot_map = self._orig_spot
        holdings.get_main_outflow_map = self._orig_fund
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _alert_types(self, uid=None):
        uid = uid or self.uid
        return {a['alert_type'] for a in db.list_alerts(uid, limit=200)}

    def _cycle(self):
        return monitor.run_cycle(force=True)

    def test_stop_loss_and_take_profit(self):
        # 成本 10，止损 7% -> 9.30，止盈 15% -> 11.50
        pid_stop = db.create_position(self.uid, 'sh.600001', 10.0, shares=1000,
                                      name='止损票', stop_pct=0.07, take_pct=0.15)
        pid_take = db.create_position(self.uid, 'sh.600002', 10.0, shares=1000,
                                      name='止盈票', stop_pct=0.07, take_pct=0.15,
                                      trail_pct=0)
        self._snap = {'600001': spot(9.20, high=9.30),
                      '600002': spot(11.60, high=11.70)}
        n = self._cycle()
        self.assertIn('stop_loss', self._alert_types())
        self.assertIn('take_profit', self._alert_types())
        self.assertEqual(n, 2)

    def test_no_alert_inside_band_and_dedup(self):
        pid = db.create_position(self.uid, 'sh.600003', 10.0,
                                 stop_pct=0.07, take_pct=0.15, trail_pct=0)
        self._snap = {'600003': spot(10.5, high=10.6)}
        self.assertEqual(self._cycle(), 0)
        self.assertEqual(self._alert_types(), set())

        # 触发止损后再来一轮，当日同类型不得重复
        self._snap = {'600003': spot(9.10, high=9.20)}
        self.assertEqual(self._cycle(), 1)
        self._snap = {'600003': spot(9.00, high=9.10)}
        self.assertEqual(self._cycle(), 0)
        self.assertEqual(
            [a for a in db.list_alerts(self.uid) if a['alert_type'] == 'stop_loss']
            .__len__(), 1)
        db.close_position(pid, self.uid)

    def test_trailing_stop_state_machine(self):
        # 移动回撤 5%：先冲高到 12（peak 持久化），再回落至 11.35（12*0.95=11.40）
        db.create_position(self.uid, 'sh.600004', 10.0,
                           stop_pct=0.07, take_pct=0.5, trail_pct=0.05)
        self._snap = {'600004': spot(12.0, high=12.0)}
        self._cycle()
        open_rows, _ = db.list_positions(self.uid)
        self.assertAlmostEqual(open_rows[0]['peak_price'], 12.0, places=4)
        self.assertNotIn('trailing_stop', self._alert_types())  # 高位不触发

        self._snap = {'600004': spot(11.35, high=12.0, preclose=10.0)}
        self._cycle()
        self.assertIn('trailing_stop', self._alert_types())
        # 移动止损线 11.40 > 硬止损 9.30，说明用的是 trailing 线
        alerts = {a['alert_type']: a for a in db.list_alerts(self.uid)}
        self.assertAlmostEqual(alerts['trailing_stop']['ref_price'], 11.40, places=2)

    def test_top_warning_surge_then_pullback(self):
        # 昨收 10，最高 10.50(+5%)，现价 10.25（自高点回落 2.38%）
        db.create_position(self.uid, 'sh.600005', 10.0,
                           stop_pct=0.5, take_pct=0.5, trail_pct=0.0)
        self._snap = {'600005': spot(10.25, high=10.50, preclose=10.0, vr=2.1)}
        self._cycle()
        self.assertIn('top_warning', self._alert_types())

    def test_top_warning_not_triggered_on_quiet_day(self):
        db.create_position(self.uid, 'sh.600006', 10.0,
                           stop_pct=0.5, take_pct=0.5, trail_pct=0.0)
        # 最高仅 +1.5%，即使回落也不算见顶
        self._snap = {'600006': spot(10.05, high=10.15, preclose=10.0)}
        self._cycle()
        self.assertNotIn('top_warning', self._alert_types())

    def test_buy_point_armed_and_held_excluded(self):
        uid2 = db.create_user('u2', 'x')
        # u1：关注 600007 且最近分析通过，参考价 10；u2 同股但已持仓
        db.add_watch(self.uid, 'sh.600007', '买点票')
        db.upsert_analysis_row(self.uid, 'sh.600007', self.today, '买点票',
                               status='done', passed=1, latest_price=10.0,
                               pattern='底部反弹')
        db.add_watch(uid2, 'sh.600007', '买点票')
        db.create_position(uid2, 'sh.600007', 9.5)  # 已持仓 -> 不再发买点提醒
        self._snap = {'600007': spot(10.02, high=10.10, preclose=10.0)}
        self._cycle()
        self.assertIn('buy_point', self._alert_types(self.uid))
        self.assertNotIn('buy_point', self._alert_types(uid2))

    def test_buy_point_needs_pullback_to_reference(self):
        # 现价高于参考价超过 0.5% 带宽 -> 不提醒
        db.add_watch(self.uid, 'sh.600008', '远离票')
        db.upsert_analysis_row(self.uid, 'sh.600008', self.today, '远离票',
                               status='done', passed=1, latest_price=10.0)
        self._snap = {'600008': spot(10.20, high=10.30, preclose=10.0)}
        self._cycle()
        self.assertNotIn('buy_point', self._alert_types())

    def test_fund_outflow_alert(self):
        # 价格平静（不触发其他预警），主力净占比 -10% -> 资金流出预警
        db.create_position(self.uid, 'sh.600009', 10.0,
                           stop_pct=0.5, take_pct=0.5, trail_pct=0)
        self._snap = {'600009': spot(10.0, high=10.05, preclose=10.0)}
        self._fund = {'sh.600009': {
            'mf_main_ratio': -0.10, 'mf_main_net': -1.5e8,
            'mf_amount': 1.0e9}}
        self._cycle()
        self.assertIn('fund_outflow', self._alert_types())

    def test_fund_outflow_threshold_and_liquidity(self):
        # -5% 未达 -8% 门槛
        db.create_position(self.uid, 'sh.600010', 10.0,
                           stop_pct=0.5, take_pct=0.5, trail_pct=0)
        # 成交额低于 2000 万，即使比率达标也不预警（噪音）
        db.create_position(self.uid, 'sh.600011', 10.0,
                           stop_pct=0.5, take_pct=0.5, trail_pct=0)
        self._snap = {'600010': spot(10.0, high=10.05, preclose=10.0),
                      '600011': spot(10.0, high=10.05, preclose=10.0)}
        self._fund = {
            'sh.600010': {'mf_main_ratio': -0.05, 'mf_main_net': -5e7,
                          'mf_amount': 1e9},
            'sh.600011': {'mf_main_ratio': -0.20, 'mf_main_net': -3e6,
                          'mf_amount': 1.5e7},
        }
        self._cycle()
        self.assertNotIn('fund_outflow', self._alert_types())

    def test_fund_map_failure_breaks_nothing(self):
        # 资金流接口整体不可用时，价格类预警照常工作
        holdings.get_main_outflow_map = lambda codes: (_ for _ in ()).throw(
            RuntimeError('network down'))
        db.create_position(self.uid, 'sh.600012', 10.0,
                           stop_pct=0.07, take_pct=0.5, trail_pct=0)
        self._snap = {'600012': spot(9.20, high=9.30)}
        self.assertEqual(self._cycle(), 1)
        self.assertIn('stop_loss', self._alert_types())


if __name__ == '__main__':
    unittest.main(verbosity=2)
