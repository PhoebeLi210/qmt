# -*- coding: utf-8 -*-
"""定时任务节假日拦截测试：非交易日跳过，交易日正常执行"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import scheduler


class SchedulerHolidayTest(unittest.TestCase):
    def test_daily_job_skipped_on_holiday(self):
        with mock.patch('webapp.monitor.is_trading_day', return_value=False), \
             mock.patch('webapp.analysis_service.run_daily_analysis') as fn:
            scheduler._daily_job()
            fn.assert_not_called()

    def test_daily_job_runs_on_trading_day(self):
        with mock.patch('webapp.monitor.is_trading_day', return_value=True), \
             mock.patch('webapp.analysis_service.run_daily_analysis') as fn:
            scheduler._daily_job()
            fn.assert_called_once_with(notify=True)

    def test_scan_job_skipped_on_holiday(self):
        with mock.patch('webapp.monitor.is_trading_day', return_value=False), \
             mock.patch('webapp.market_scan.run_full_scan') as fn:
            scheduler._market_scan_job()
            fn.assert_not_called()

    def test_scan_job_runs_on_trading_day(self):
        with mock.patch('webapp.monitor.is_trading_day', return_value=True), \
             mock.patch('webapp.market_scan.run_full_scan') as fn:
            scheduler._market_scan_job()
            fn.assert_called_once()

    def test_lab_job_skipped_on_holiday(self):
        with mock.patch('webapp.monitor.is_trading_day', return_value=False), \
             mock.patch('webapp.lab.tracker.run_daily') as fn:
            scheduler._lab_backfill_job()
            fn.assert_not_called()

    def test_monitor_job_not_guarded_here(self):
        # 监控任务由 monitor.in_session 自行判断，调度层不拦截
        with mock.patch('webapp.monitor.run_cycle') as fn:
            scheduler._monitor_job()
            fn.assert_called_once()

    def test_calendar_failure_falls_back_to_weekday(self):
        with mock.patch('webapp.monitor.is_trading_day',
                        side_effect=RuntimeError('boom')):
            # 不抛异常，返回布尔（周末 False/工作日 True）
            self.assertIn(scheduler._is_trading_day_safe(), (True, False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
