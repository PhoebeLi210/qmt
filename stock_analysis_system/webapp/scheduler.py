#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定时任务

1. 交易日 15:40 盘后自选股批量分析并推送
2. 交易时段盘中监控（每 2 分钟）：止损/止盈/移动止损/见顶近似/买点提醒
   （monitor 内部自行校验交易日历与时段，非交易时段直接返回）

依赖 APScheduler；未安装时 Web 仍可正常运行，只是不自动跑批（可手动调
analysis_service.run_daily_analysis / monitor.run_cycle）。
"""

import logging
import os

logger = logging.getLogger('webapp.scheduler')

_scheduler = None

DAILY_JOB_HOUR = 15
DAILY_JOB_MINUTE = 40
SCAN_HOUR = int(os.environ.get('CHAOGU_SCAN_HOUR', '15'))
SCAN_MINUTE = int(os.environ.get('CHAOGU_SCAN_MINUTE', '50'))
LAB_HOUR = int(os.environ.get('CHAOGU_LAB_HOUR', '17'))
LAB_MINUTE = int(os.environ.get('CHAOGU_LAB_MINUTE', '40'))
MONITOR_INTERVAL_MIN = int(os.environ.get('CHAOGU_MONITOR_INTERVAL', '2'))


def _is_trading_day_safe():
    """交易日判断（带 akshare 交易日历）；接口异常时降级为工作日判断。"""
    try:
        from webapp.monitor import is_trading_day
        return is_trading_day()
    except Exception:
        logger.exception('交易日历判断异常，降级为工作日判断')
        from datetime import datetime
        return datetime.now().weekday() < 5


def _daily_job():
    # 延迟导入，避免调度器模块加载时拉起核心库
    from webapp.analysis_service import run_daily_analysis
    if not _is_trading_day_safe():
        logger.info('今日非交易日（节假日/休市），跳过盘后自选股分析')
        return
    try:
        run_daily_analysis(notify=True)
    except Exception:
        logger.exception('盘后自选股批量任务异常')


def _monitor_job():
    from webapp import monitor
    try:
        monitor.run_cycle()
    except Exception:
        logger.exception('盘中监控任务异常')


def _market_scan_job():
    from webapp import market_scan
    if not _is_trading_day_safe():
        logger.info('今日非交易日（节假日/休市），跳过全市场扫描')
        return
    try:
        market_scan.run_full_scan()
    except Exception:
        logger.exception('全市场扫描定时任务异常')


def _lab_backfill_job():
    from webapp.lab import tracker
    if not _is_trading_day_safe():
        logger.info('今日非交易日（节假日/休市），跳过 lab 结果回填')
        return
    try:
        tracker.run_daily()
    except Exception:
        logger.exception('lab 结果回填任务异常')


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning('未安装 apscheduler，定时任务未启动（pip install apscheduler）')
        return

    _scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
    _scheduler.add_job(
        _daily_job, 'cron',
        day_of_week='mon-fri', hour=DAILY_JOB_HOUR, minute=DAILY_JOB_MINUTE,
        id='daily_watch_analysis', max_instances=1, coalesce=True)

    if os.environ.get('CHAOGU_DISABLE_MONITOR') != '1':
        # 9:00-14:58 每 2 分钟触发，函数内部只在 9:30-11:30/13:00-15:00 实跑
        _scheduler.add_job(
            _monitor_job, 'cron',
            day_of_week='mon-fri', hour='9-14', minute=f'*/{MONITOR_INTERVAL_MIN}',
            second=20, id='intraday_monitor', max_instances=1, coalesce=True)
        logger.info(f'盘中监控已启动: 交易时段每 {MONITOR_INTERVAL_MIN} 分钟一轮')

    if os.environ.get('CHAOGU_DISABLE_SCAN') != '1':
        # 全市场扫描约 100 分钟，排在自选分析(15:40)之后；子进程+文件锁防重入
        _scheduler.add_job(
            _market_scan_job, 'cron',
            day_of_week='mon-fri', hour=SCAN_HOUR, minute=SCAN_MINUTE,
            id='daily_market_scan', max_instances=1, coalesce=True)
        logger.info(f'全市场扫描定时已启动: 周一至周五 {SCAN_HOUR}:{SCAN_MINUTE:02d}')

    if os.environ.get('CHAOGU_DISABLE_LAB') != '1':
        # 信号结果回填：扫描约 17:35 结束，17:40 起拉 T+1..T+20 行情
        _scheduler.add_job(
            _lab_backfill_job, 'cron',
            day_of_week='mon-fri', hour=LAB_HOUR, minute=LAB_MINUTE,
            id='daily_lab_backfill', max_instances=1, coalesce=True)
        logger.info(f'lab 结果回填定时已启动: 周一至周五 {LAB_HOUR}:{LAB_MINUTE:02d}')

    _scheduler.start()
    logger.info(f'盘后自选分析定时已启动: 周一至周五 {DAILY_JOB_HOUR}:{DAILY_JOB_MINUTE:02d}')


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
