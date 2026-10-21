#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速验证行业映射表构建 + 对9/22推荐股票的行业字段填充"""

import os
import sys

deps = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.deps')
if os.path.isdir(deps):
    sys.path.insert(0, deps)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
from data_collector_optimized import OptimizedStockDataCollector

# 9/22 v2 推荐的 15 只股票（验证行业是否能正确填充）
RECOMMENDED = [
    ('sh.002332', '仙琚制药'), ('sz.002961', '瑞达期货'), ('sh.605003', '众望布艺'),
    ('sz.000561', '烽火电子'), ('sh.603506', '南都物业'), ('sz.301223', '中荣股份'),
    ('sz.300729', '乐歌股份'), ('sh.688455', '科捷智能'), ('sz.000514', '渝开发'),
    ('sh.603231', '索宝蛋白'), ('sh.603201', '常润股份'), ('sz.300778', '新城市'),
    ('sz.300988', '津荣天宇'), ('sz.003028', '振邦智能'), ('sz.000045', '深纺织A'),
]

print('=== 验证行业映射表构建 ===')
start = time.time()
c = OptimizedStockDataCollector()
# 修正：sz.002332 不对，应是 sh.600332 还是 sz.002332？从推荐报告看是 sz.002332
# 但我们传入的代码格式是 sz.002332，映射表里按6位数字存
m = c._build_industry_map()
elapsed = time.time() - start
print(f'构建耗时: {elapsed:.1f}s, 覆盖股票数: {len(m)}')
if not m:
    print('映射表为空，构建失败')
    sys.exit(1)

print()
print('=== 9/22 推荐15只股票的行业字段验证 ===')
hit = 0
for code, name in RECOMMENDED:
    ind = c._get_industry_from_map(code)
    tag = '✓' if ind else '✗'
    print(f'  {tag} {code} {name}: {ind or "(未找到)"}')
    if ind:
        hit += 1
print(f'\n命中率: {hit}/{len(RECOMMENDED)} = {hit/len(RECOMMENDED)*100:.0f}%')

# 检查缓存文件
cache_file = os.path.join('cache', 'industry_map.json')
if os.path.exists(cache_file):
    size_kb = os.path.getsize(cache_file) / 1024
    print(f'缓存文件: {cache_file} ({size_kb:.1f} KB)')
