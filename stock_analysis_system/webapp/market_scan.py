#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日全市场扫描调度（独立子进程）

为什么用子进程而不是线程内直接跑：
- main.py 全量扫描约 100 分钟、内存占用大，独立进程与 gunicorn 隔离，
  崩溃/内存峰值不影响 Web 服务；
- 与手动 `python main.py` 完全同一入口，行为一致（main 完成后自己入库）。

防重入：logs/scan.lock 记录 PID；POSIX 用 kill(pid,0) 判活，
残留锁（进程已死）自动接管。扫描结束后给所有用户推送当日推荐摘要。
"""

import os
import sys
import subprocess
import logging
from datetime import datetime

from webapp import db, push as push_mod

logger = logging.getLogger('webapp.market_scan')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_ROOT, 'logs')
_LOCK_PATH = os.path.join(_LOG_DIR, 'scan.lock')


def _pid_alive(pid):
    """POSIX 判活；非 POSIX 平台无法判断时按"存活"保守处理。"""
    if not pid:
        return False
    if sys.platform == 'win32':
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def scan_running():
    """是否已有扫描在跑：锁文件记录的进程，或手动启动的 main.py。"""
    try:
        with open(_LOCK_PATH) as f:
            pid = int(f.read().strip() or 0)
    except (OSError, ValueError):
        pid = 0
    if _pid_alive(pid):
        return True
    # 调度器之外手动启动的扫描（nohup python main.py）也避让
    if sys.platform != 'win32':
        try:
            r = subprocess.run(['pgrep', '-f', r'python.*main\.py'],
                               capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def build_summary(trade_date):
    rows = db.get_recommendations(trade_date)
    if not rows:
        return None
    regime_txt = ''
    sizing = rows[0]['position_sizing'] or ''
    if 'bear' in sizing:
        regime_txt = '大盘择时 bear（仓位×0.5）'
    elif 'risk_off' in sizing:
        regime_txt = '大盘 risk_off（反弹观察仓，轻仓严止损）'
    elif 'neutral' in sizing:
        regime_txt = '大盘择时 neutral（仓位×0.7）'
    else:
        regime_txt = '大盘择时 bull（正常仓位）'

    lines = [f'今日（{trade_date}）全市场扫描完成，共 {len(rows)} 只：{regime_txt}', '']
    for s in rows[:15]:
        price = f"{s['latest_price']:.2f}" if s['latest_price'] else '—'
        lines.append(f"{s['rank_no']}. {s['name'] or s['code']}（{s['code']}）"
                     f" {s['pattern'] or '—'} 评分{s['score']:.1f} 现价{price}")
    lines += ['', '完整止损止盈与推荐理由见网站「推荐清单」。',
              '模型机械信号，非投资建议。']
    return '\n'.join(lines)


def push_summary(trade_date=None):
    trade_date = trade_date or datetime.now().strftime('%Y-%m-%d')
    body = build_summary(trade_date)
    if not body:
        logger.warning('%s 无推荐数据，跳过摘要推送', trade_date)
        return 0
    ok_n = 0
    for user in db.list_users():
        ok, _msg = push_mod.push_to_user(user, f'chaogu 每日推荐 {trade_date}', body)
        if ok:
            ok_n += 1
    logger.info('推荐摘要推送完成: 成功 %d/%d 人', ok_n, len(db.list_users()))
    return ok_n


def run_full_scan(command=None, push=True):
    """启动全市场扫描子进程并等待结束。返回 (ok, n_recommendations)。

    command 仅测试时注入；默认 [当前解释器, main.py]，工作目录为项目根。
    """
    os.makedirs(_LOG_DIR, exist_ok=True)
    if scan_running():
        logger.warning('已有扫描在运行（锁 %s），本次跳过', _LOCK_PATH)
        return False, 0

    trade_date = datetime.now().strftime('%Y-%m-%d')
    log_path = os.path.join(_LOG_DIR, f'full_scan_{trade_date}.log')
    cmd = command or [sys.executable, os.path.join(_ROOT, 'main.py')]

    with open(_LOCK_PATH, 'w') as f:
        f.write(str(os.getpid()))  # 先记父进程；子进程启动后改写为子 PID

    try:
        with open(log_path, 'a', encoding='utf-8') as lf:
            lf.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} 定时全市场扫描启动 =====\n")
            lf.flush()
            proc = subprocess.Popen(
                cmd, cwd=_ROOT, stdout=lf, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=(sys.platform != 'win32'))
            with open(_LOCK_PATH, 'w') as f2:
                f2.write(str(proc.pid))
            rc = proc.wait()
    finally:
        try:
            os.remove(_LOCK_PATH)
        except OSError:
            pass

    if rc != 0:
        logger.error('全市场扫描子进程退出码 %s，详见 %s', rc, log_path)
        return False, 0

    rows = db.get_recommendations(trade_date)
    logger.info('全市场扫描完成: %s 入库 %d 只，日志 %s',
                trade_date, len(rows), log_path)
    if push and rows:
        push_summary(trade_date)
    return True, len(rows)
