#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查akshare数据结构兼容性
"""

import akshare as ak
import pandas as pd

def check_akshare_structure():
    print("=== 检查akshare数据结构 ===")
    
    try:
        # 获取实时行情数据
        print("1. 检查ak.stock_zh_a_spot_em()数据结构:")
        quote_df = ak.stock_zh_a_spot_em()
        
        if quote_df is not None and not quote_df.empty:
            print(f"数据形状: {quote_df.shape}")
            print(f"列名: {list(quote_df.columns)}")
            print("\n前3行数据:")
            print(quote_df.head(3))
            
            # 查找市盈率相关列
            pe_columns = [col for col in quote_df.columns if '市盈率' in str(col) or 'PE' in str(col)]
            pb_columns = [col for col in quote_df.columns if '市净率' in str(col) or 'PB' in str(col)]
            
            print(f"\n市盈率相关列: {pe_columns}")
            print(f"市净率相关列: {pb_columns}")
            
        else:
            print("未获取到数据")
            
    except Exception as e:
        print(f"获取akshare数据失败: {str(e)}")
    
    try:
        # 获取股票基本信息
        print("\n2. 检查ak.stock_individual_info_em()数据结构:")
        stock_detail = ak.stock_individual_info_em(symbol="600036")
        
        if stock_detail is not None and not stock_detail.empty:
            print(f"数据形状: {stock_detail.shape}")
            print(f"列名: {list(stock_detail.columns)}")
            print("\n前10行数据:")
            print(stock_detail.head(10))
            
        else:
            print("未获取到股票详情数据")
            
    except Exception as e:
        print(f"获取股票详情失败: {str(e)}")

if __name__ == "__main__":
    check_akshare_structure()