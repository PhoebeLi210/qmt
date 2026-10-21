#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试评分修复效果
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer import StockAnalyzer
import random

def test_scoring_system():
    """测试评分系统的区分度"""
    print("=== 测试评分系统修复效果 ===\n")
    
    # 创建测试股票列表
    test_stocks = [
        # 高分股票（技术指标丰富）
        {
            'code': 'test001',
            'name': '优质股票',
            'pe': 20,
            'pb': 2.5,
            'liquid_shares': 1000000000,  # 10亿
            'industry': '人工智能',
            'change_pct': 3.5,
            'turnover_rate': 8.0,
            'latest_price': 50.0
        },
        # 中分股票（技术指标一般）
        {
            'code': 'test002',
            'name': '普通股票',
            'pe': 30,
            'pb': 4.0,
            'liquid_shares': 500000000,  # 5亿
            'industry': '传统制造业',
            'change_pct': 1.5,
            'turnover_rate': 3.0,
            'latest_price': 25.0
        },
        # 低分股票（技术指标稀少）
        {
            'code': 'test003',
            'name': '一般股票',
            'pe': 50,
            'pb': 6.0,
            'liquid_shares': 50000000,  # 0.5亿
            'industry': '夕阳行业',
            'change_pct': 0.5,
            'turnover_rate': 1.0,
            'latest_price': 10.0
        }
    ]
    
    # 为每只股票添加不同数量的技术指标
    test_stocks[0]['positive_indicators'] = ['MACD金叉', '放量突破', '均线多头', 'RSI超买', 'KDJ金叉']
    test_stocks[1]['positive_indicators'] = ['放量上涨', '趋势向上']
    test_stocks[2]['positive_indicators'] = ['价格稳定']
    
    # 创建分析器
    analyzer = StockAnalyzer(test_stocks)
    
    # 手动测试评分计算
    for i, stock in enumerate(test_stocks):
        print(f"测试股票 {i+1}: {stock['name']}")
        print(f"  技术指标数量: {len(stock['positive_indicators'])}")
        print(f"  行业: {stock['industry']}")
        print(f"  PE: {stock['pe']}, PB: {stock['pb']}")
        
        # 模拟基本面和技术面得分
        if i == 0:  # 优质股票
            fundamental_score = 80
            technical_score = 85
        elif i == 1:  # 普通股票
            fundamental_score = 60
            technical_score = 50
        else:  # 一般股票
            fundamental_score = 40
            technical_score = 30
        
        # 测试评分计算
        score = analyzer._calculate_multi_factor_score(
            stock, fundamental_score, technical_score, stock['positive_indicators']
        )
        
        print(f"  基础评分: {(fundamental_score * 0.3 + technical_score * 0.7):.1f}")
        print(f"  最终评分: {score:.1f}")
        print("-" * 40)
    
    print("\n测试完成！检查评分是否有区分度。")
    print("期望：不同股票应该得到不同的评分，不再都是100分。")

if __name__ == "__main__":
    test_scoring_system()