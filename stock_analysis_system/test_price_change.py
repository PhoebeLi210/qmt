#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试涨幅数据计算
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_collector_optimized import OptimizedStockDataCollector

def test_price_change_calculation():
    """测试涨幅数据计算"""
    print("=== 测试涨幅数据计算 ===")
    
    collector = OptimizedStockDataCollector()
    
    # 测试几个知名股票
    test_stocks = [
        "sh.600519",  # 贵州茅台
        "sz.000858",  # 五粮液
        "sz.000001",  # 平安银行
        "sh.600036"   # 招商银行
    ]
    
    for stock_code in test_stocks:
        print(f"\n测试股票: {stock_code}")
        try:
            stock_data = collector._get_stock_detail_optimized(stock_code)
            if stock_data:
                latest_price = stock_data.get('latest_price', 0)
                change_pct = stock_data.get('change_pct', 0)
                kline_data = stock_data.get('kline_data', [])
                
                print(f"  最新价格: {latest_price:.2f}")
                print(f"  涨幅百分比: {change_pct}")
                print(f"  K线数据条数: {len(kline_data)}")
                
                if len(kline_data) >= 2:
                    latest_close = kline_data[-1]['close']
                    previous_close = kline_data[-2]['close']
                    print(f"  昨日收盘价: {previous_close:.2f}")
                    print(f"  今日收盘价: {latest_close:.2f}")
                    if previous_close > 0:
                        calculated_change = (latest_close - previous_close) / previous_close * 100
                        print(f"  重新计算的涨幅: {calculated_change:.2f}%")
                
                print(f"  change_pct状态: {type(change_pct)} = {change_pct}")
                
            else:
                print("  数据获取失败")
        except Exception as e:
            print(f"  错误: {str(e)}")

if __name__ == "__main__":
    test_price_change_calculation()