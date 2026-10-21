#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试推荐引擎的基本面数据使用情况
"""

import sys
sys.path.append('.')
from recommendation_engine import RecommendationEngine

def test_recommendation_with_fundamental():
    """测试包含基本面数据的股票推荐"""
    
    # 创建模拟的股票数据，包含各种基本面情况
    mock_stocks = [
        {
            'code': 'sh.600036',
            'name': '招商银行',
            'pattern': 'bottom_rebound',
            'score': 85,
            'pe': 6.96,      # 合理PE
            'pb': 0.97,      # 低PB
            'positive_indicators': ['MACD金叉', '放量', '上涨趋势']
        },
        {
            'code': 'sh.600519',
            'name': '贵州茅台',
            'pattern': 'upward_trend',
            'score': 90,
            'pe': 25.0,      # 合理PE
            'pb': 5.0,       # 较高PB
            'positive_indicators': ['多头排列', '温和放量']
        },
        {
            'code': 'sz.000001',
            'name': '平安银行',
            'pattern': 'bottom_rebound',
            'score': 78,
            'pe': 4.39,      # 合理PE
            'pb': 0.5,       # 低PB
            'positive_indicators': ['KDJ金叉', '超卖']
        },
        {
            'code': 'sz.002415',
            'name': '海康威视',
            'pattern': 'upward_trend',
            'score': 88,
            'pe': 21.83,     # 合理PE
            'pb': 3.46,      # 正常PB
            'positive_indicators': ['MACD金叉', 'RSI正常']
        },
        {
            'code': 'sz.300059',
            'name': '东方财富',
            'pattern': 'bottom_rebound',
            'score': 82,
            'pe': 30.42,     # 边界PE
            'pb': 4.15,      # 正常PB
            'positive_indicators': ['放量', '上涨趋势']
        },
        {
            'code': 'sh.688036',
            'name': '传音控股',
            'pattern': 'upward_trend',
            'score': 85,
            'pe': 27.03,     # 合理PE
            'pb': 3.79,      # 正常PB
            'positive_indicators': ['多头排列', '温和放量']
        }
    ]
    
    print("=== 测试推荐引擎的基本面数据使用 ===\n")
    
    # 初始化推荐引擎
    engine = RecommendationEngine(mock_stocks)
    
    # 生成推荐清单
    recommendations = engine.generate_recommendations()
    
    print(f"生成了 {len(recommendations)} 只股票的推荐清单:\n")
    
    # 显示每只股票的推荐理由
    for i, stock in enumerate(recommendations, 1):
        print(f"{i}. {stock['code']} {stock['name']} (评分: {stock['score']})")
        print(f"   推荐理由: {stock['recommendation_reason']}")
        
        # 检查是否包含基本面理由
        reason = stock['recommendation_reason']
        has_pe_reason = '市盈率合理' in reason
        has_pb_reason = '市净率' in reason
        
        print(f"   PE: {stock.get('pe', 'N/A')}, PB: {stock.get('pb', 'N/A')}")
        print(f"   是否包含市盈率理由: {'✓' if has_pe_reason else '✗'}")
        print(f"   是否包含市净率理由: {'✓' if has_pb_reason else '✗'}")
        print()
    
    # 统计基本面理由覆盖率
    total_stocks = len(recommendations)
    stocks_with_pe_reason = sum(1 for stock in recommendations if '市盈率合理' in stock['recommendation_reason'])
    stocks_with_pb_reason = sum(1 for stock in recommendations if '市净率' in stock['recommendation_reason'])
    
    print("=== 基本面理由覆盖率统计 ===")
    print(f"总推荐股票数: {total_stocks}")
    print(f"包含市盈率理由的股票: {stocks_with_pe_reason} ({stocks_with_pe_reason/total_stocks*100:.1f}%)")
    print(f"包含市净率理由的股票: {stocks_with_pb_reason} ({stocks_with_pb_reason/total_stocks*100:.1f}%)")
    
    # 检查PE/PB数据可用性
    stocks_with_pe = sum(1 for stock in recommendations if stock.get('pe') and stock.get('pe') > 0)
    stocks_with_pb = sum(1 for stock in recommendations if stock.get('pb') and stock.get('pb') > 0)
    
    print(f"\n有PE数据的股票: {stocks_with_pe} ({stocks_with_pe/total_stocks*100:.1f}%)")
    print(f"有PB数据的股票: {stocks_with_pb} ({stocks_with_pb/total_stocks*100:.1f}%)")
    
    # 如果有PE数据但没有市盈率理由，需要修复
    if stocks_with_pe > 0 and stocks_with_pe_reason == 0:
        print("\n⚠️  警告: 有PE数据但没有生成市盈率理由，需要修复推荐引擎!")
    elif stocks_with_pe > 0 and stocks_with_pe_reason < stocks_with_pe:
        print(f"\n⚠️  警告: 有{stocks_with_pe}只股票有PE数据，但只有{stocks_with_pe_reason}只生成了市盈率理由")
    else:
        print("\n✅ 推荐引擎正确使用基本面数据!")

if __name__ == "__main__":
    test_recommendation_with_fundamental()