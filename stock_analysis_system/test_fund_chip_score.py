# -*- coding: utf-8 -*-
"""资金流/筹码因子参与评分的单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer import StockAnalyzer


def _base_stock(**kw):
    """最小可用 stock dict。"""
    s = {
        'code': 'sh.600000',
        'name': '测试',
        'pe': 10, 'pb': 1.0, 'liquid_shares': 100e8,
        'industry': '银行',
        'kline_data': [],
    }
    s.update(kw)
    return s


class FundChipScoreTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = StockAnalyzer([])

    def _score(self, stock):
        return self.analyzer._calculate_multi_factor_score(stock, 50, 50, [])

    def test_no_fund_chip_neutral(self):
        """无 fund/chip 数据时评分不受影响。"""
        s1 = _base_stock()
        s2 = _base_stock(fund=None, chip=None)
        self.assertAlmostEqual(self._score(s1), self._score(s2), places=5)

    def test_fund_inflow_boosts(self):
        """主力净流入 +5% → 评分乘 1.05。"""
        s_neutral = _base_stock()
        s_in = _base_stock(fund={'mf_main_ratio': 0.05})
        s_out = _base_stock(fund={'mf_main_ratio': -0.05})
        base = self._score(s_neutral)
        self.assertAlmostEqual(self._score(s_in), base * 1.05, places=3)
        self.assertAlmostEqual(self._score(s_out), base * 0.95, places=3)

    def test_fund_ratio_clamped(self):
        """主力净占比超过 ±5% 时被截断。"""
        s1 = _base_stock(fund={'mf_main_ratio': 0.10})  # 截断到 0.05
        s2 = _base_stock(fund={'mf_main_ratio': 0.05})
        self.assertAlmostEqual(self._score(s1), self._score(s2), places=5)

    def test_chip_high_profit_penalty(self):
        """获利盘 >80% 扣 3 分。"""
        s1 = _base_stock()
        s2 = _base_stock(chip={'profit_ratio': 0.85, 'conc90': 0.15})
        self.assertAlmostEqual(self._score(s2), self._score(s1) - 3, places=3)

    def test_chip_low_profit_penalty(self):
        """获利盘 <20% 扣 3 分。"""
        s1 = _base_stock()
        s2 = _base_stock(chip={'profit_ratio': 0.15, 'conc90': 0.15})
        self.assertAlmostEqual(self._score(s2), self._score(s1) - 3, places=3)

    def test_chip_mid_profit_no_penalty(self):
        """获利盘 30-70% 不扣分。"""
        s1 = _base_stock()
        s2 = _base_stock(chip={'profit_ratio': 0.50, 'conc90': 0.15})
        self.assertAlmostEqual(self._score(s2), self._score(s1), places=3)

    def test_chip_concentration_bonus(self):
        """90% 集中度 <10% 加 2 分。"""
        s1 = _base_stock()
        s2 = _base_stock(chip={'profit_ratio': 0.50, 'conc90': 0.08})
        self.assertAlmostEqual(self._score(s2), self._score(s1) + 2, places=3)

    def test_chip_concentration_penalty(self):
        """90% 集中度 >20% 减 2 分。"""
        s1 = _base_stock()
        s2 = _base_stock(chip={'profit_ratio': 0.50, 'conc90': 0.25})
        self.assertAlmostEqual(self._score(s2), self._score(s1) - 2, places=3)

    def test_combined(self):
        """组合：主力流出 -3% + 获利盘 85% → 乘 0.97 再 -3。"""
        s1 = _base_stock()
        s2 = _base_stock(fund={'mf_main_ratio': -0.03},
                         chip={'profit_ratio': 0.85, 'conc90': 0.15})
        expected = self._score(s1) * 0.97 - 3
        self.assertAlmostEqual(self._score(s2), expected, places=3)


class EnrichTest(unittest.TestCase):
    def test_enrich_stocks(self):
        from webapp.lab import holdings, fund_flow
        holdings.reset_cache()
        fund_flow.fetch_market_fund_map = lambda: {
            '600000': {'mf_main_net': 1e8, 'mf_main_ratio': 0.03}}
        bars = [{'date': f'2026-01-{i:02d}', 'open': 10, 'high': 10.5,
                 'low': 9.7, 'close': 10 + (i % 3) * 0.1, 'turnover': 15.0}
                for i in range(1, 25)]
        stocks = [{'code': 'sh.600000', 'kline_data': bars},
                  {'code': 'sz.000001', 'kline_data': bars}]
        holdings.enrich_stocks_with_fund_chip(stocks)
        self.assertIsNotNone(stocks[0]['fund'])
        self.assertAlmostEqual(stocks[0]['fund']['mf_main_ratio'], 0.03)
        self.assertIsNotNone(stocks[0]['chip'])
        self.assertIn('profit_ratio', stocks[0]['chip'])
        self.assertIsNone(stocks[1]['fund'])  # 不在 map 中
        self.assertIsNotNone(stocks[1]['chip'])

    def test_enrich_failure_safe(self):
        from webapp.lab import holdings, fund_flow
        holdings.reset_cache()
        def boom():
            raise ConnectionError('down')
        fund_flow.fetch_market_fund_map = boom
        stocks = [{'code': 'sh.600000', 'kline_data': []}]
        holdings.enrich_stocks_with_fund_chip(stocks)  # 不抛异常
        self.assertIsNone(stocks[0]['fund'])
        self.assertIsNone(stocks[0]['chip'])  # kline_data 空 → chip None


if __name__ == '__main__':
    unittest.main(verbosity=2)
