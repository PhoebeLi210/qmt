#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试东方财富API解析逻辑"""

import sys
import os
sys.path.append('c:\\Users\\毛蛋\\Documents\\trae_projects\\chaogu\\backup_20251218')

from data_collector import DataCollector
from config import config
from logger import logger


def test_eastmoney_api():
    """测试东方财富API"""
    print("测试东方财富API解析逻辑...")
    
    collector = DataCollector()
    
    # 测试股票代码603107（之前出现错误的股票）
    symbol = "603107"
    start_date = "2025-12-15"
    end_date = "2025-12-23"
    
    try:
        data = collector._get_data_from_eastmoney(symbol, start_date, end_date)
        if data is not None and not data.empty:
            print(f"\n测试成功！获取到股票{symbol}的数据：")
            print(data.head())
            print(f"共{len(data)}条记录")
        else:
            print(f"\n测试失败：未能获取到股票{symbol}的数据")
    except Exception as e:
        print(f"\n测试出错：{str(e)}")


if __name__ == "__main__":
    test_eastmoney_api()