#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场扫描定时任务测试：子进程编排、锁防重入、摘要生成、调度注册。"""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp import db, market_scan
import webapp.scheduler as sch


class ScanScheduleTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        db.init_db()
        self.today = datetime.now().strftime('%Y-%m-%d')

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_run_success_and_lock_cleanup(self):
        ok, n = market_scan.run_full_scan(
            command=[sys.executable, '-c', 'print("fake scan ok")'], push=False)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(market_scan._LOCK_PATH), '锁文件应在结束后清除')

    def test_run_failure(self):
        ok, n = market_scan.run_full_scan(
            command=[sys.executable, '-c', 'import sys; sys.exit(2)'], push=False)
        self.assertFalse(ok)
        self.assertEqual(n, 0)
        self.assertFalse(os.path.exists(market_scan._LOCK_PATH))

    def test_lock_prevents_reentry(self):
        os.makedirs(market_scan._LOG_DIR, exist_ok=True)
        with open(market_scan._LOCK_PATH, 'w') as f:
            f.write(str(os.getpid()))  # 当前进程必然存活
        try:
            self.assertTrue(market_scan.scan_running())
            ok, _ = market_scan.run_full_scan(
                command=[sys.executable, '-c', 'print("should not run")'], push=False)
            self.assertFalse(ok, '锁存在时必须跳过')
        finally:
            os.remove(market_scan._LOCK_PATH)

    def test_stale_lock_is_taken_over_on_posix(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX kill 判定')
        os.makedirs(market_scan._LOG_DIR, exist_ok=True)
        with open(market_scan._LOCK_PATH, 'w') as f:
            f.write('999999')  # 正常系统不存在的 PID
        try:
            self.assertFalse(market_scan.scan_running(), '死锁应被识别为未运行')
        finally:
            os.remove(market_scan._LOCK_PATH)

    def _insert_one(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO daily_recommendations
                   (trade_date,rank_no,code,name,latest_price,change_pct,pattern,score,
                    position_sizing,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (self.today, 1, 'sh.600000', '浦发银行', 9.0, 0.22, 'pullback', 92.0,
                 '建议中仓(10%) [大盘bear×0.5]', now))

    def test_summary_content(self):
        self._insert_one()
        body = market_scan.build_summary(self.today)
        self.assertIsNotNone(body)
        self.assertIn('共 1 只', body)
        self.assertIn('bear', body)
        self.assertIn('浦发银行', body)
        self.assertIn('pullback', body)

    def test_summary_empty_day(self):
        self.assertIsNone(market_scan.build_summary('2020-01-01'))

    def test_scheduler_registers_three_jobs(self):
        sch.start_scheduler()
        try:
            ids = {j.id for j in sch._scheduler.get_jobs()}
            self.assertEqual(
                ids, {'daily_watch_analysis', 'intraday_monitor',
                      'daily_market_scan', 'daily_lab_backfill'})
            scan_job = next(j for j in sch._scheduler.get_jobs()
                            if j.id == 'daily_market_scan')
            nxt = scan_job.trigger.get_next_fire_time(None, datetime.now())
            self.assertEqual((nxt.hour, nxt.minute), (15, 50))
            lab_job = next(j for j in sch._scheduler.get_jobs()
                           if j.id == 'daily_lab_backfill')
            nxt2 = lab_job.trigger.get_next_fire_time(None, datetime.now())
            self.assertEqual((nxt2.hour, nxt2.minute), (17, 40))
        finally:
            sch.shutdown_scheduler()


if __name__ == '__main__':
    unittest.main(verbosity=2)
