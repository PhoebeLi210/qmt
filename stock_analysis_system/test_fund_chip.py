#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段一扩展因子测试：筹码分布(CYQ 移植)、资金流(新浪)解析与降级、快照落库。"""

import gc
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import db
from webapp.lab import chip, fund_flow, holdings, capture


def cb(date, o, h, l, c, t):
    return {'date': date, 'open': o, 'high': h, 'low': l,
            'close': c, 'turnover': t}


class ChipTest(unittest.TestCase):

    def test_empty_and_short(self):
        self.assertIsNone(chip.compute_chip([]))
        self.assertIsNone(chip.compute_chip([
            cb('2026-01-01', 10, 10.2, 9.9, 10, 5.0)] * 5))

    def test_no_turnover_returns_none(self):
        bars = [{'date': f'2026-01-{i:02d}', 'open': 10, 'high': 10.2,
                 'low': 9.8, 'close': 10.0} for i in range(1, 20)]
        self.assertIsNone(chip.compute_chip(bars))

    def test_constant_price_full_turnover(self):
        # 价格一字不动、每日 100% 换手：筹码全部在当前价
        bars = [cb(f'2026-01-{i:02d}', 10, 10, 10, 10, 100.0)
                for i in range(1, 20)]
        r = chip.compute_chip(bars)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r['profit_ratio'], 1.0, places=3)
        self.assertAlmostEqual(r['avg_cost'], 10.0, places=2)
        self.assertLess(r['conc90'], 0.005)
        self.assertEqual(r['win'], 19)
        self.assertAlmostEqual(r['price_vs_cost'], 0.0, places=3)

    def test_price_rises_with_full_rotation(self):
        # 前 15 日在 10 元换手，近 5 日 11 元区间高换手且收在高位：绝大多数筹码获利
        bars = [cb(f'2026-01-{i:02d}', 10, 10.1, 9.9, 10, 30.0)
                for i in range(1, 16)]
        bars += [cb(f'2026-02-{i:02d}', 10.95, 11.1, 10.9, 11.1, 100.0)
                 for i in range(1, 6)]
        r = chip.compute_chip(bars)
        self.assertGreater(r['profit_ratio'], 0.9)
        self.assertGreater(r['avg_cost'], 10.5)
        self.assertGreater(r['price_vs_cost'], 0.0)

    def test_price_falls_trapped_chips(self):
        # 前 15 日 10 元高换手，近 5 日跌到 9 元：多数筹码套牢
        bars = [cb(f'2026-01-{i:02d}', 10, 10.1, 9.9, 10, 30.0)
                for i in range(1, 16)]
        bars += [cb(f'2026-02-{i:02d}', 9, 9.1, 8.9, 9, 5.0)
                 for i in range(1, 6)]
        r = chip.compute_chip(bars)
        self.assertLess(r['profit_ratio'], 0.25)
        self.assertLess(r['price_vs_cost'], 0.0)

    def test_concentration_monotonic(self):
        # 宽幅震荡 vs 窄幅横盘：窄幅集中度数值更小
        wide = [cb(f'2026-01-{i:02d}',
                   10 + (i % 5) - 2, 13, 7, 10 + (i % 5) - 2, 20.0)
                for i in range(1, 25)]
        narrow = [cb(f'2026-01-{i:02d}',
                     10 + (i % 3) * 0.05, 10.15, 9.85,
                     10 + (i % 3) * 0.05, 20.0)
                  for i in range(1, 25)]
        self.assertGreater(chip.compute_chip(wide)['conc90'],
                           chip.compute_chip(narrow)['conc90'])


class FundFlowTest(unittest.TestCase):

    def setUp(self):
        fund_flow.reset_cache()

    def tearDown(self):
        fund_flow.reset_cache()

    def test_row_parse(self):
        row = {
            'symbol': 'sh600000', 'name': '浦发银行',
            'netamount': '19537646.33', 'ratioamount': '0.0410485',
            'r0_in': '114883489.9', 'r0_out': '65103029.49',
            'r0_net': '49780460.41', 'r3_in': '16272302',
            'r3_out': '21593125.51', 'r3_net': '-5320823.51',
            'r0_ratio': '0.104589', 'r3_ratio': '-0.011179',
            'amount': '475964884',
        }
        f = fund_flow._row_to_factor(row)
        self.assertAlmostEqual(f['mf_net'], 19537646.33)
        self.assertAlmostEqual(f['mf_super_net'], 49780460.41)
        self.assertAlmostEqual(f['mf_big_net'], -5320823.51)
        self.assertAlmostEqual(f['mf_main_net'], 44459636.90)
        self.assertAlmostEqual(f['mf_main_ratio'], 0.093410, places=6)
        self.assertAlmostEqual(f['mf_amount'], 475964884)

    def test_bad_values_become_none(self):
        f = fund_flow._row_to_factor(
            {'symbol': 'sz000001', 'r0_net': '--', 'r3_net': '',
             'r0_ratio': None, 'r3_ratio': 'x', 'netamount': '-9e20'})
        self.assertIsNone(f['mf_super_net'])
        self.assertIsNone(f['mf_main_net'])
        self.assertIsNone(f['mf_net'])

    def _patch_http(self, payload):
        class _Resp:
            def __init__(self, data):
                self._d = data

            def raise_for_status(self):
                pass

            def json(self):
                return self._d

        class _Session:
            def __init__(self):
                self.calls = 0

            def get(self, url, params=None, headers=None, timeout=None):
                self.calls += 1
                if isinstance(payload, Exception):
                    raise payload
                # 第 1 页返回数据，后续页为空（正常翻页终止）
                return _Resp(payload if params['page'] == 1 else [])

        s = _Session()
        old = fund_flow.requests.Session
        fund_flow.requests.Session = lambda: s
        self.addCleanup(setattr, fund_flow.requests, 'Session', old)
        return s

    def test_fetch_success_and_cache(self):
        payload = [
            {'symbol': 'sh600000', 'r0_net': '100', 'r3_net': '20',
             'r0_ratio': '0.01', 'r3_ratio': '0.002',
             'netamount': '120', 'ratioamount': '0.012', 'amount': '10000'},
            {'symbol': 'sz000001', 'r0_net': '-50', 'r3_net': '-10',
             'r0_ratio': '-0.005', 'r3_ratio': '-0.001',
             'netamount': '-60', 'ratioamount': '-0.006', 'amount': '10000'},
        ]
        s = self._patch_http(payload)
        m1 = fund_flow.fetch_market_fund_map()
        m2 = fund_flow.fetch_market_fund_map()  # 同日命中缓存
        self.assertEqual(s.calls, 2)  # 首页数据 + 次页空终止
        self.assertIs(m1, m2)
        self.assertAlmostEqual(m1['600000']['mf_main_net'], 120.0)
        self.assertAlmostEqual(m1['000001']['mf_main_net'], -60.0)
        self.assertEqual(fund_flow.get_fund_factor('sh.600000', m1)
                         ['mf_main_net'], 120.0)
        self.assertIsNone(fund_flow.get_fund_factor('sh.999999', m1))

    def test_fetch_failure_returns_empty(self):
        self._patch_http(ConnectionError('blocked'))
        # 两次尝试都失败（_fetch_once 内部重试一次）后返回 {}
        m = fund_flow.fetch_market_fund_map()
        self.assertEqual(m, {})
        # 失败也写缓存，避免扫描链路反复重试
        self.assertEqual(fund_flow.fetch_market_fund_map(), {})

    def test_truncated_page2_empty_retries(self):
        # 首次：首页满 6000 行、第 2 页被限流返回空 -> 截断，必须重试
        # 重试：第 2 页返回 438 行、第 3 页空 -> 完整 6438 行
        p1 = [{'symbol': f'sh{i:06d}'} for i in range(1, 6001)]
        p2 = ([{'symbol': 'sz300750', 'r0_net': '-1', 'r3_net': '-1',
                'r0_ratio': '-0.06', 'r3_ratio': '-0.06'}]
              + [{'symbol': f'sz30{i:04d}'} for i in range(1, 438)])
        state = {'attempt': 0, 'calls': 0}

        class _Resp:
            def __init__(self, d):
                self._d = d

            def raise_for_status(self):
                pass

            def json(self):
                return self._d

        class _Session:
            def get(self, url, params=None, headers=None, timeout=None):
                page = params['page']
                state['calls'] += 1
                if page == 1:
                    state['attempt'] += 1
                    return _Resp(p1)
                if state['attempt'] == 1:
                    return _Resp([])  # 被限流：空页
                return _Resp(p2 if page == 2 else [])

        old = fund_flow.requests.Session
        fund_flow.requests.Session = lambda: _Session()
        self.addCleanup(setattr, fund_flow.requests, 'Session', old)
        m = fund_flow.fetch_market_fund_map()
        self.assertEqual(len(m), 6438)
        self.assertIn('300750', m)  # 排在第 2 页的股票不丢
        self.assertAlmostEqual(m['300750']['mf_main_ratio'], -0.12)


class CaptureIntegrationTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()
        self.today = datetime.now().strftime('%Y-%m-%d')
        fund_flow.reset_cache()

    def tearDown(self):
        fund_flow.reset_cache()
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _engine(self):
        class _Engine:
            _market_regime = 'neutral'

            def _suggest_exit_strategy(self, stock):
                return {'ref_price': 10.0, 'sl_pct': 5.0, 'tp1_pct': 8.0,
                        'tp2_pct': 15.0, 'time_stop_days': 8,
                        'param_version': 'baseline-v1'}

            def _get_truly_positive_count(self, stock):
                return 2

        return _Engine()

    def _stock(self):
        return {
            'code': 'sh.600000', 'name': '测试行', 'pattern': 'breakout',
            'score': 91, 'final_score': 86, 'risk_score': 5,
            'positive_indicators': ['放量突破', 'MACD金叉'],
            'pe': 12.3, 'turnover_rate': 3.2,
            'kline_data': [cb(f'2026-01-{i:02d}',
                              10 + (i % 4) * 0.1, 10.5, 9.7,
                              10 + (i % 4) * 0.1, 15.0)
                           for i in range(1, 25)],
        }

    def test_fund_and_chip_persisted(self):
        fake_map = {'600000': {'mf_main_net': 1200000.0,
                               'mf_main_ratio': 0.03}}
        old_fetch = fund_flow.fetch_market_fund_map
        fund_flow.fetch_market_fund_map = lambda: fake_map
        try:
            n = capture.capture_full_scan(
                self.today, [self._stock()], [{'code': 'sh.600000'}],
                self._engine())
        finally:
            fund_flow.fetch_market_fund_map = old_fetch
        self.assertEqual(n, 1)
        row = db.list_signals_without_outcome(10, max_signal_date=self.today)[0]
        factors = json.loads(row['factors_json'])
        self.assertEqual(factors['fund']['mf_main_net'], 1200000.0)
        self.assertIn('profit_ratio', factors['chip'])
        self.assertEqual(factors['chip']['win'], 24)
        self.assertEqual(factors['pe'], 12.3)
        self.assertIn('放量突破', factors['indicators'])

    def test_fund_failure_still_captures(self):
        old_fetch = fund_flow.fetch_market_fund_map
        fund_flow.fetch_market_fund_map = lambda: {}
        try:
            n = capture.capture_full_scan(
                self.today, [self._stock()], [], self._engine())
        finally:
            fund_flow.fetch_market_fund_map = old_fetch
        self.assertEqual(n, 1)
        row = db.list_signals_without_outcome(10, max_signal_date=self.today)[0]
        factors = json.loads(row['factors_json'])
        self.assertNotIn('fund', factors)
        self.assertIn('chip', factors)  # 筹码本地计算不受网络影响


class HoldingsExtTest(unittest.TestCase):
    """持仓页/盯盘扩展数据助手（资金流 + 筹码），全程打桩不触网。"""

    def setUp(self):
        holdings.reset_cache()
        self.bars = [cb(f'2026-01-{i:02d}',
                        10 + (i % 4) * 0.1, 10.5, 9.7,
                        10 + (i % 4) * 0.1, 15.0)
                     for i in range(1, 25)]
        self._orig_fetch_bars = holdings._fetch_bars
        self._orig_fund = fund_flow.fetch_market_fund_map

    def tearDown(self):
        holdings._fetch_bars = self._orig_fetch_bars
        fund_flow.fetch_market_fund_map = self._orig_fund
        holdings.reset_cache()

    def test_ext_map_merge_and_dedup(self):
        fund_flow.fetch_market_fund_map = lambda: {
            '600000': {'mf_main_net': 1.2e8, 'mf_main_ratio': 0.05,
                       'mf_amount': 2.0e9}}
        calls = []

        def fake_bars(digits, market):
            calls.append((digits, market))
            return self.bars

        holdings._fetch_bars = fake_bars
        ext = holdings.get_ext_map(['sh.600000', 'sh.600000'])
        self.assertEqual(set(ext), {'sh.600000'})
        self.assertAlmostEqual(ext['sh.600000']['fund']['mf_main_ratio'], 0.05)
        self.assertEqual(ext['sh.600000']['close'], self.bars[-1]['close'])
        self.assertIn('profit_ratio', ext['sh.600000']['chip'])
        self.assertEqual(calls, [('600000', 'sh')])  # 去重只拉一次K线

    def test_fund_failure_chip_still_works(self):
        fund_flow.fetch_market_fund_map = lambda: {}
        holdings._fetch_bars = lambda d, m: self.bars
        ext = holdings.get_ext_map(['sh.600000'])
        self.assertIsNone(ext['sh.600000']['fund'])
        self.assertIsNotNone(ext['sh.600000']['chip'])

    def test_bars_failure_fund_still_works(self):
        fund_flow.fetch_market_fund_map = lambda: {
            '600000': {'mf_main_net': -1e8, 'mf_main_ratio': -0.04}}

        def boom(digits, market):
            raise ConnectionError('blocked')

        holdings._fetch_bars = boom
        ext = holdings.get_ext_map(['sh.600000'])
        self.assertIsNotNone(ext['sh.600000']['fund'])
        self.assertIsNone(ext['sh.600000']['chip'])
        self.assertIsNone(ext['sh.600000']['close'])

    def test_outflow_map_only_ratio_available(self):
        fund_flow.fetch_market_fund_map = lambda: {
            '600000': {'mf_main_net': -1e8, 'mf_main_ratio': -0.1},
            '000001': {'mf_main_net': None, 'mf_main_ratio': None}}
        out = holdings.get_main_outflow_map(['sh.600000', 'sz.000001'])
        self.assertEqual(set(out), {'sh.600000'})
        self.assertAlmostEqual(out['sh.600000']['mf_main_ratio'], -0.1)

    def test_empty_codes(self):
        self.assertEqual(holdings.get_ext_map([]), {})
        self.assertEqual(holdings.get_main_outflow_map([]), {})

    def test_bars_failure_short_cooldown(self):
        # 首次失败：冷却期内不重试；超过 _FAIL_TTL 后重试成功
        fund_flow.fetch_market_fund_map = lambda: {}
        orig_now = holdings._now
        clock = {'t': 1000.0}
        holdings._now = lambda: clock['t']
        state = {'n': 0}

        def flaky(digits, market):
            state['n'] += 1
            if state['n'] == 1:
                raise ConnectionError('boom')
            return self.bars

        holdings._fetch_bars = flaky
        self.addCleanup(setattr, holdings, '_now', orig_now)
        ext = holdings.get_ext_map(['sh.600000'])
        self.assertIsNone(ext['sh.600000']['chip'])
        self.assertIsNone(holdings._bars_for('sh.600000'))  # 冷却期
        self.assertEqual(state['n'], 1)
        clock['t'] += holdings._FAIL_TTL + 1
        self.assertIsNotNone(holdings._bars_for('sh.600000'))  # 重试成功
        self.assertEqual(state['n'], 2)


class AnalysisResultExtColsTest(unittest.TestCase):
    """analysis_results 的 fund_json/chip_json 落库往返与旧库迁移。"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        self.today = datetime.now().strftime('%Y-%m-%d')

    def tearDown(self):
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_upsert_round_trip(self):
        db.init_db()
        uid = db.create_user('u1', 'x')
        fund = {'mf_main_net': 1200000.0, 'mf_main_ratio': 0.03}
        chip_d = {'profit_ratio': 0.7, 'avg_cost': 9.2, 'win': 120}
        rid = db.upsert_analysis_row(uid, 'sh.600000', self.today, '测试',
                                     status='done', fund_json=json.dumps(fund),
                                     chip_json=json.dumps(chip_d))
        row = db.get_analysis(rid)
        self.assertEqual(db.parse_json_field(row['fund_json'], None), fund)
        self.assertEqual(db.parse_json_field(row['chip_json'], None)['win'], 120)
        # None 也应正常落库/读取
        rid2 = db.upsert_analysis_row(uid, 'sz.000001', self.today, '无数据',
                                      status='done', fund_json=None,
                                      chip_json=None)
        row2 = db.get_analysis(rid2)
        self.assertIsNone(db.parse_json_field(row2['fund_json'], None))
        self.assertIsNone(db.parse_json_field(row2['chip_json'], None))

    def test_legacy_table_migration(self):
        # 模拟旧版库：analysis_results 无 fund_json/chip_json 列
        import sqlite3
        conn = sqlite3.connect(self.tmp.name)
        conn.execute(
            'CREATE TABLE analysis_results ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, '
            'code TEXT, trade_date TEXT, name TEXT, status TEXT, '
            'created_at TEXT, updated_at TEXT)')
        conn.commit()
        conn.close()

        db.init_db()  # 应幂等补列
        import sqlite3 as s2
        c2 = s2.connect(self.tmp.name)
        cols = {r[1] for r in c2.execute('PRAGMA table_info(analysis_results)')}
        c2.close()
        self.assertIn('fund_json', cols)
        self.assertIn('chip_json', cols)


if __name__ == '__main__':
    unittest.main(verbosity=2)
