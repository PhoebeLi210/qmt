#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试东方财富API响应解析逻辑"""

import json
import pandas as pd
from datetime import datetime

# 模拟DataCollector类的_get_data_from_eastmoney方法的核心解析逻辑
def parse_eastmoney_response(data, symbol):
    """解析东方财富API响应
    
    Args:
        data: API响应数据
        symbol: 股票代码
        
    Returns:
        解析后的数据列表
    """
    data_list = []
    
    # 处理标准JSON格式响应
    if isinstance(data, dict) and data.get('data') and data['data'].get('klines'):
        klines = data['data']['klines']
        for kline in klines:
            parts = kline.split(',')
            if len(parts) >= 15:
                data_list.append({
                    'date': parts[0],
                    'code': symbol,
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                    'amount': float(parts[6]),
                    'pctChg': float(parts[8]),
                    'turn': float(parts[12]),
                    'preclose': float(parts[13]),
                    'adjustflag': 3
                })
    # 处理嵌套列表格式响应（可能是多条数据）
    elif isinstance(data, list) and data and all(isinstance(item, list) for item in data):
        for item in data:
            if len(item) >= 15:
                data_list.append({
                    'date': item[0],
                    'code': symbol,
                    'open': float(item[1]),
                    'close': float(item[2]),
                    'high': float(item[3]),
                    'low': float(item[4]),
                    'volume': float(item[5]),
                    'amount': float(item[6]),
                    'pctChg': float(item[8]),
                    'turn': float(item[12]),
                    'preclose': float(item[13]),
                    'adjustflag': 3
                })
    # 处理列表格式响应（单条数据）
    elif isinstance(data, list) and len(data) >= 15:
        data_list.append({
            'date': data[0],
            'code': symbol,
            'open': float(data[1]),
            'close': float(data[2]),
            'high': float(data[3]),
            'low': float(data[4]),
            'volume': float(data[5]),
            'amount': float(data[6]),
            'pctChg': float(data[8]),
            'turn': float(data[12]),
            'preclose': float(data[13]),
            'adjustflag': 3
        })
    
    return data_list


def test_parser():
    """测试解析器"""
    symbol = "603107"
    print("测试东方财富API响应解析逻辑...")
    
    # 测试1: 标准JSON格式响应
    print("\n1. 测试标准JSON格式响应:")
    json_response = {
        "data": {
            "klines": [
                "2025-12-15,10.5,11.0,11.5,10.0,1000000,10500000,0.0,5.0,0.0,0.0,0.0,2.0,10.5,0.0"
            ]
        }
    }
    result1 = parse_eastmoney_response(json_response, symbol)
    print(f"   解析结果: {len(result1)} 条记录")
    if result1:
        print(f"   日期: {result1[0]['date']}, 开盘价: {result1[0]['open']}, 收盘价: {result1[0]['close']}")
    
    # 测试2: 单条列表格式响应
    print("\n2. 测试单条列表格式响应:")
    list_response = ["2025-12-15", "10.5", "11.0", "11.5", "10.0", "1000000", "10500000", "0.0", "5.0", "0.0", "0.0", "0.0", "2.0", "10.5", "0.0"]
    result2 = parse_eastmoney_response(list_response, symbol)
    print(f"   解析结果: {len(result2)} 条记录")
    if result2:
        print(f"   日期: {result2[0]['date']}, 开盘价: {result2[0]['open']}, 收盘价: {result2[0]['close']}")
    
    # 测试3: 嵌套列表格式响应（多条数据）
    print("\n3. 测试嵌套列表格式响应:")
    nested_list_response = [
        ["2025-12-15", "10.5", "11.0", "11.5", "10.0", "1000000", "10500000", "0.0", "5.0", "0.0", "0.0", "0.0", "2.0", "10.5", "0.0"],
        ["2025-12-16", "11.0", "11.5", "12.0", "10.8", "1200000", "13800000", "0.0", "4.5", "0.0", "0.0", "0.0", "2.2", "11.0", "0.0"]
    ]
    result3 = parse_eastmoney_response(nested_list_response, symbol)
    print(f"   解析结果: {len(result3)} 条记录")
    for i, item in enumerate(result3, 1):
        print(f"   记录 {i}: 日期: {item['date']}, 开盘价: {item['open']}, 收盘价: {item['close']}")
    
    # 测试4: 空数据情况
    print("\n4. 测试空数据情况:")
    empty_response = {"data": {"klines": []}}
    result4 = parse_eastmoney_response(empty_response, symbol)
    print(f"   解析结果: {len(result4)} 条记录")
    
    # 测试5: 数据格式不完整情况
    print("\n5. 测试数据格式不完整情况:")
    incomplete_response = ["2025-12-15", "10.5", "11.0", "11.5", "10.0", "1000000", "10500000"]  # 长度不足15
    result5 = parse_eastmoney_response(incomplete_response, symbol)
    print(f"   解析结果: {len(result5)} 条记录")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_parser()