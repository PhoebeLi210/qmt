# -*- coding: utf-8 -*-
"""AlphaFeed 备用源测试：符号转换、数据归一化、频控/预算/熔断、monitor 兜底链路"""
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alphafeed_source as afs


class _RateLimitError(Exception):
    pass


class _AuthError(Exception):
    pass


class _FakeKlines:
    def __init__(self, df=None, fail=None):
        self.df, self.fail, self.calls, self.symbols = df, fail, 0, []

    def get(self, symbol, count=40, to_dataframe=True):
        self.calls += 1
        self.symbols.append(symbol)
        if self.fail == 'rate':
            raise _RateLimitError('Rate limit exceeded (10/min). Retry after 30000ms')
        if self.fail == 'auth':
            raise _AuthError('401 invalid api key')
        if self.fail == 'net':
            raise ConnectionError('boom')
        return self.df


class _FakeQuotes:
    def __init__(self, df=None, fail=None):
        self.df, self.fail, self.batches = df, fail, []

    def get(self, symbols=None, to_dataframe=True):
        self.batches.append(list(symbols))
        if self.fail:
            raise _RateLimitError('429')
        return self.df[df_sym := self.df['symbol'].isin(symbols)]


class _FakeClient:
    def __init__(self, kdf=None, qdf=None, kfail=None, qfail=None):
        self.klines = _FakeKlines(kdf, kfail)
        self.quotes = _FakeQuotes(qdf, qfail)


def kline_df(n=25):
    return pd.DataFrame({
        'symbol': ['600519.SH'] * n,
        'trade_date': [f'2026-09-{i:02d}' for i in range(1, n + 1)],
        'open': [10.0] * n, 'high': [10.5] * n, 'low': [9.8] * n,
        'close': [10.2] * n, 'volume': [1000.0] * n,
    })


def quote_df():
    return pd.DataFrame([
        {'symbol': '600519.SH', 'last_price': 1258.62, 'prev_close': 1235.58,
         'open': 1239.53, 'high': 1268.0, 'low': 1236.05,
         'ext.change_pct': 0.0186},
        {'symbol': '000001.SZ', 'last_price': 11.57, 'prev_close': 11.35,
         'open': 11.36, 'high': 11.65, 'low': 11.33,
         'ext.change_pct': 0.0194},
        {'symbol': 'BAD.SH', 'last_price': 0, 'prev_close': 0,
         'open': 0, 'high': 0, 'low': 0, 'ext.change_pct': None},
    ])


class AlphaFeedSourceTest(unittest.TestCase):
    def setUp(self):
        afs.reset_for_tests()
        afs._MIN_KLINE_INTERVAL = 0
        afs._MIN_QUOTE_INTERVAL = 0

    def tearDown(self):
        afs.reset_for_tests()

    def test_symbol_conversion(self):
        self.assertEqual(afs.to_af_symbol('sh.600000'), '600000.SH')
        self.assertEqual(afs.to_af_symbol('sz.300750'), '300750.SZ')
        self.assertIsNone(afs.to_af_symbol('bj.920000'))
        self.assertIsNone(afs.to_af_symbol('600000'))
        self.assertIsNone(afs.to_af_symbol(None))

    def test_kline_normalized(self):
        afs.set_client_for_tests(_FakeClient(kdf=kline_df()))
        rows = afs.get_daily_kline('sh.600519')
        self.assertEqual(len(rows), 25)
        self.assertEqual(rows[0]['date'], '2026-09-01')
        self.assertEqual(rows[0]['close'], 10.2)
        self.assertIsNone(rows[0]['turnover'])  # AlphaFeed 无历史换手率
        self.assertEqual(afs.status(), 'ready')

    def test_kline_drops_invalid_rows(self):
        df = kline_df(3)
        df.loc[1, ['open', 'high', 'low', 'close']] = 0
        afs.set_client_for_tests(_FakeClient(kdf=df))
        rows = afs.get_daily_kline('sh.600519')
        self.assertEqual(len(rows), 2)

    def test_quotes_chunked_and_normalized(self):
        afs.set_client_for_tests(_FakeClient(qdf=quote_df()))
        codes = ['sh.600519', 'sz.000001']
        out = afs.get_quotes(codes)
        self.assertEqual(set(out.keys()), {'600519', '000001'})
        self.assertAlmostEqual(out['600519']['pct'], 1.86, places=2)
        self.assertEqual(out['600519']['preclose'], 1235.58)
        self.assertIsNone(out['600519']['vol_ratio'])

    def test_quotes_batched_by_five(self):
        # 12 只 → 3 批（5+5+2）
        qdf = pd.DataFrame({'symbol': [f'{i:06d}.SH' for i in range(12)],
                            'last_price': [10.0] * 12, 'prev_close': [9.0] * 12,
                            'open': [9.5] * 12, 'high': [10.1] * 12,
                            'low': [9.4] * 12, 'ext.change_pct': [0.1] * 12})
        client = _FakeClient(qdf=qdf)
        afs.set_client_for_tests(client)
        codes = [f'sh.{i:06d}' for i in range(12)]
        out = afs.get_quotes(codes)
        self.assertEqual(len(out), 12)
        self.assertEqual([len(b) for b in client.quotes.batches], [5, 5, 2])

    def test_rate_limit_triggers_cooldown(self):
        afs.set_client_for_tests(_FakeClient(kfail='rate'))
        self.assertEqual(afs.get_daily_kline('sh.600519'), [])
        self.assertTrue(afs.status().startswith('cooling:'))
        # 冷却期内不再发请求
        self.assertEqual(afs.get_daily_kline('sh.600519'), [])
        self.assertEqual(afs._client.klines.calls, 1)

    def test_auth_error_permanently_disables(self):
        afs.set_client_for_tests(_FakeClient(kfail='auth'))
        self.assertEqual(afs.get_daily_kline('sh.600519'), [])
        self.assertEqual(afs.status(), 'disabled:auth')
        self.assertEqual(afs.get_quotes(['sh.600519']), {})  # 全端点禁用
        self.assertEqual(afs._client.quotes.batches, [])

    def test_kline_budget(self):
        afs._KLINE_BUDGET = 2
        afs.set_client_for_tests(_FakeClient(kdf=kline_df()))
        self.assertEqual(len(afs.get_daily_kline('sh.600519')), 25)
        self.assertEqual(len(afs.get_daily_kline('sh.600519')), 25)
        self.assertEqual(afs.get_daily_kline('sh.600519'), [])  # 预算耗尽
        self.assertEqual(afs._client.klines.calls, 2)

    def test_no_key_disabled(self):
        afs.reset_for_tests()
        # 无注入客户端、无环境变量时静默返回空，不抛异常
        self.assertEqual(afs.get_daily_kline('sh.600519'), [])
        self.assertEqual(afs.get_quotes(['sh.600519']), {})


class MonitorFallbackTest(unittest.TestCase):
    """东财快照+新浪均缺失时，monitor 走 AlphaFeed 兜底"""

    def setUp(self):
        afs.reset_for_tests()
        afs._MIN_QUOTE_INTERVAL = 0
        afs.set_client_for_tests(_FakeClient(qdf=quote_df()))
        # monitor 内部缓存复位
        from webapp import monitor
        self.monitor = monitor
        monitor._spot_cache.update({'ts': 0.0, 'map': None})
        monitor._quote_cache.update({'ts': 0.0, 'map': {}})

    def tearDown(self):
        afs.reset_for_tests()

    def test_alphafeed_after_em_and_sina_fail(self):
        m = self.monitor
        with mock.patch.object(m, 'get_spot_map', return_value={}), \
             mock.patch.object(m, '_sina_quotes', return_value={}):
            out = m.get_quotes(['sh.600519', 'sz.000001'], force=True)
        self.assertEqual(set(out.keys()), {'600519', '000001'})
        self.assertAlmostEqual(out['000001']['pct'], 1.94, places=2)

    def test_sina_hit_skips_alphafeed(self):
        m = self.monitor
        sina_map = {'600519': {'price': 1.0, 'pct': 0.1, 'high': 1.1,
                               'low': 0.9, 'open': 1.0, 'preclose': 1.0,
                               'vol_ratio': None}}
        with mock.patch.object(m, 'get_spot_map', return_value={}), \
             mock.patch.object(m, '_sina_quotes', return_value=sina_map):
            out = m.get_quotes(['sh.600519'], force=True)
        self.assertEqual(out['600519']['price'], 1.0)
        # 新浪已覆盖，AlphaFeed 不应被调用
        self.assertEqual(afs._client.quotes.batches, [])


class CollectorKlineFallbackTest(unittest.TestCase):
    """东财/腾讯/新浪 K 线全挂时，采集器走 AlphaFeed 兜底并产出完整 stock_data"""

    def setUp(self):
        afs.reset_for_tests()
        afs._MIN_KLINE_INTERVAL = 0
        afs.set_client_for_tests(_FakeClient(kdf=kline_df()))

    def tearDown(self):
        afs.reset_for_tests()

    def _collector(self):
        import data_collector_optimized as dco
        c = dco.OptimizedStockDataCollector()
        c._industry_map = {'600519': '白酒'}
        return c

    def test_detail_uses_alphafeed_when_all_akshare_dead(self):
        import data_collector_optimized as dco
        collector = self._collector()

        def _boom(*a, **k):
            raise ConnectionError('data source blocked')

        with mock.patch.object(dco.ak, 'stock_individual_info_em', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_a_hist', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_a_hist_tx', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_a_daily', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_valuation_baidu', side_effect=_boom):
            data = collector._get_stock_detail_optimized('sh.600519')

        self.assertIsNotNone(data, 'AlphaFeed 兜底后应能产出数据')
        self.assertEqual(len(data['kline_data']), 25)
        self.assertEqual(data['latest_price'], 10.2)
        self.assertEqual(data['industry'], '白酒')
        self.assertEqual(afs._client.klines.symbols, ['600519.SH'])

    def test_tencent_fallback_used_when_eastmoney_fails(self):
        """东财挂时优先用腾讯 hist，新浪/AlphaFeed 不应被调用"""
        import data_collector_optimized as dco
        collector = self._collector()

        tx_df = pd.DataFrame({
            'date': [f'2026-09-{i:02d}' for i in range(1, 26)],
            'open': [10.0]*25, 'close': [10.2]*25,
            'high': [10.5]*25, 'low': [9.8]*25,
            'volume': [1000.0]*25, 'turnover': [0.003]*25,
        })

        def _boom(*a, **k):
            raise ConnectionError('eastmoney blocked')

        sina_calls = []
        with mock.patch.object(dco.ak, 'stock_individual_info_em', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_a_hist', side_effect=_boom), \
             mock.patch.object(dco.ak, 'stock_zh_a_hist_tx', return_value=tx_df), \
             mock.patch.object(dco.ak, 'stock_zh_a_daily',
                               side_effect=lambda *a, **k: sina_calls.append(1) or pd.DataFrame()), \
             mock.patch.object(dco.ak, 'stock_zh_valuation_baidu', side_effect=_boom):
            data = collector._get_stock_detail_optimized('sh.600519')

        self.assertIsNotNone(data)
        self.assertEqual(len(data['kline_data']), 25)
        self.assertEqual(data['kline_data'][0]['turnover'], 0.3)  # 腾讯小数→百分数
        self.assertEqual(len(sina_calls), 0)  # 腾讯成功，新浪不应被调用
        self.assertEqual(afs._client.klines.calls, 0)  # AlphaFeed 也不应被调用


if __name__ == '__main__':
    unittest.main(verbosity=2)

