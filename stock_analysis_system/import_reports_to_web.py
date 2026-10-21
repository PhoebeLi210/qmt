#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""将 reports/股票推荐报告_*.txt 解析并导入 Web 数据库（一次性历史数据迁移）

用法：
  $env:PYTHONPATH = "$PWD\.deps"; py -3 import_reports_to_web.py
"""

import os
import re
import sys
import glob

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp.db import init_db, save_daily_recommendations

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')

HEADER_RE = re.compile(r'^\s*(\d+)\.\s*(\S+)\s*-\s*(.+?)\s*$')
FLOAT_RE = re.compile(r'-?\d+(?:\.\d+)?')


def parse_report(path):
    """解析一份 txt 报告 → (trade_date, [stock_dict, ...])"""
    trade_date = None
    stocks = []
    cur = None

    def finish():
        if cur and cur.get('code'):
            stocks.append(cur)

    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m_date = re.match(r'^生成日期:\s*(\d{4}-\d{2}-\d{2})', line)
            if m_date:
                trade_date = m_date.group(1)
                continue
            m_head = HEADER_RE.match(line)
            if m_head:
                finish()
                cur = {'code': m_head.group(2), 'name': m_head.group(3).strip()}
                continue
            if cur is None:
                continue
            field = _parse_field(line)
            if field:
                key, value = field
                cur[key] = value
    finish()
    return trade_date, stocks


def _parse_field(line):
    m = re.match(r'^\s{2,}(.+?):\s*(.*)$', line)
    if not m:
        return None
    label, value = m.group(1), m.group(2).strip()
    if label == '价格':
        nums = FLOAT_RE.search(value)
        return ('latest_price', float(nums.group()) if nums else None)
    if label == '涨幅':
        nums = FLOAT_RE.search(value)
        return ('change_pct', float(nums.group()) if nums else None)
    if label == '形态':
        return ('pattern', value)
    if label == '评分':
        nums = FLOAT_RE.search(value)
        return ('score', float(nums.group()) if nums else None)
    if label == '板块':
        return ('market_segment', value)
    if label == '行业':
        return ('industry', value)
    if label == '概念':
        return ('concept', value)
    if label == '推荐理由':
        return ('recommendation_reason', value)
    if label == '仓位建议':
        return ('position_sizing', value)
    if label == '止损位':
        return ('stop_loss', value)
    if label == '止盈位':
        return ('take_profit', value)
    if label == '时间止损':
        return ('time_stop', value)
    return None


def main():
    init_db()
    paths = sorted(glob.glob(os.path.join(REPORTS_DIR, '股票推荐报告_*.txt')))
    paths = [p for p in paths if not p.endswith('.bak')]
    if not paths:
        print('未找到历史报告')
        return
    total = 0
    for path in paths:
        try:
            trade_date, stocks = parse_report(path)
            if trade_date and stocks:
                save_daily_recommendations(trade_date, stocks)
                print(f'{os.path.basename(path)} -> {trade_date}: 导入 {len(stocks)} 只')
                total += len(stocks)
        except Exception as e:
            print(f'{os.path.basename(path)} 解析失败: {e}')
    print(f'完成，共导入 {total} 条推荐记录')


if __name__ == '__main__':
    main()
