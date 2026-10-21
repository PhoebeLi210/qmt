#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用缓存刷新 9/22 推荐报告的行业字段（无需重跑扫描）"""

import os
import sys
import json
import re

BASE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(BASE, 'reports', '股票推荐报告_2026-09-22.txt')
CACHE = os.path.join(BASE, 'cache', 'industry_map.json')

# 1. 加载行业映射缓存
with open(CACHE, 'r', encoding='utf-8') as f:
    cached = json.load(f)
ind_map = cached['map']
print(f'加载行业映射缓存: {len(ind_map)} 只股票, 日期={cached.get("date")}')

# 2. 读取原报告
with open(REPORT, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

# 3. 扫描每只股票代码，遇到"板块:"行后插入"行业:"行
out_lines = []
inserted = 0
for i, line in enumerate(lines):
    out_lines.append(line)
    # 检测"板块:"行
    if line.strip().startswith('板块:'):
        # 往回找最近的"X. xxx.xxx - 名称"行
        code = None
        for j in range(i - 1, max(i - 10, -1), -1):
            m = re.match(r'\d+\.\s+(?:sh|sz)\.(\d{6})\s+-', lines[j])
            if m:
                code = m.group(1)
                break
        if code:
            industry = ind_map.get(code)
            if industry:
                # 检查下一行是否已经是"行业:"
                if i + 1 < len(lines) and lines[i + 1].strip().startswith('行业:'):
                    continue  # 已存在，不重复插入
                out_lines.append(f'   行业: {industry}')
                inserted += 1
                print(f'  插入 {code} -> {industry}')
        # 没找到代码不插入

# 4. 写回报告（保留备份）
backup = REPORT + '.bak'
if not os.path.exists(backup):
    with open(backup, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'原报告已备份: {backup}')

with open(REPORT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))

print(f'\n完成: 插入 {inserted} 行行业字段')
print(f'刷新后报告: {REPORT}')
