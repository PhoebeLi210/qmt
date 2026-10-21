#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面验证基本面数据集成到推荐系统的效果
"""

import sys
sys.path.append('.')
from recommendation_engine import RecommendationEngine

def test_comprehensive_fundamental_integration():
    """全面测试基本面数据集成"""
    
    print("=== 全面验证基本面数据集成效果 ===\n")
    
    # 创建边界案例测试数据
    edge_case_stocks = [
        # PE边界测试
        {
            'code': 'test1',
            'name': 'PE=29.9(合理)',
            'pattern': 'bottom_rebound',
            'score': 80,
            'pe': 29.9,
            'pb': 1.5,
            'positive_indicators': ['MACD金叉']
        },
        {
            'code': 'test2', 
            'name': 'PE=30.0(边界)',
            'pattern': 'upward_trend',
            'score': 80,
            'pe': 30.0,
            'pb': 1.5,
            'positive_indicators': ['多头排列']
        },
        {
            'code': 'test3',
            'name': 'PE=34.9(合理)',
            'pattern': 'bottom_rebound', 
            'score': 80,
            'pe': 34.9,
            'pb': 1.5,
            'positive_indicators': ['KDJ金叉']
        },
        {
            'code': 'test4',
            'name': 'PE=35.0(边界)',
            'pattern': 'upward_trend',
            'score': 80, 
            'pe': 35.0,
            'pb': 1.5,
            'positive_indicators': ['放量']
        },
        
        # PB边界测试
        {
            'code': 'test5',
            'name': 'PB=2.9(低)',
            'pattern': 'bottom_rebound',
            'score': 80,
            'pe': 20.0,
            'pb': 2.9,
            'positive_indicators': ['RSI正常']
        },
        {
            'code': 'test6',
            'name': 'PB=3.0(边界)',
            'pattern': 'upward_trend', 
            'score': 80,
            'pe': 20.0,
            'pb': 3.0,
            'positive_indicators': ['上涨趋势']
        },
        {
            'code': 'test7',
            'name': 'PB=4.0(正常)',
            'pattern': 'bottom_rebound',
            'score': 80,
            'pe': 25.0,
            'pb': 4.0,
            'positive_indicators': ['温和放量']
        },
        
        # 完美基本面股票
        {
            'code': 'test8',
            'name': '优秀基本面',
            'pattern': 'upward_trend',
            'score': 95,
            'pe': 15.0,
            'pb': 1.2,
            'positive_indicators': ['多头排列', 'MACD金叉', '温和放量']
        }
    ]
    
    # 测试推荐引擎
    engine = RecommendationEngine(edge_case_stocks)
    recommendations = engine.generate_recommendations()
    
    print("=== 边界案例测试结果 ===")
    for i, stock in enumerate(recommendations, 1):
        pe = stock.get('pe', 'N/A')
        pb = stock.get('pb', 'N/A')
        reason = stock['recommendation_reason']
        
        print(f"{i}. {stock['name']} (PE={pe}, PB={pb})")
        print(f"   推荐理由: {reason}")
        
        # 检查是否应该包含基本面理由
        should_have_pe = pe != 'N/A' and pe > 0 and pe < 35
        should_have_pb = pb != 'N/A' and pb > 0 and pb < 3
        has_pe_reason = '市盈率合理' in reason
        has_pb_reason = '市净率低' in reason
        
        pe_status = '✓' if should_have_pe == has_pe_reason else '✗'
        pb_status = '✓' if should_have_pb == has_pb_reason else '✗'
        
        print(f"   PE理由: {pe_status} (应该: {should_have_pe}, 实际: {has_pe_reason})")
        print(f"   PB理由: {pb_status} (应该: {should_have_pb}, 实际: {has_pb_reason})")
        print()
    
    # 验证修复效果
    print("=== 修复效果验证 ===")
    
    # 测试修复前的问题案例
    fixed_cases = []
    
    # 东方财富案例 (之前PE=30.42被排除)
    dongfang_case = {
        'code': 'dongfang_test',
        'name': '东方财富(修复前被排除)',
        'pattern': 'bottom_rebound',
        'score': 82,
        'pe': 30.42,
        'pb': 4.15,
        'positive_indicators': ['放量', '上涨趋势']
    }
    
    engine_fixed = RecommendationEngine([dongfang_case])
    result = engine_fixed.generate_recommendations()
    
    if result and '市盈率合理' in result[0]['recommendation_reason']:
        print("✅ 东方财富案例已修复: PE=30.42 现在获得'市盈率合理'理由")
        fixed_cases.append("东方财富")
    else:
        print("❌ 东方财富案例未修复")
    
    # 海康威视案例 (PB=3.46应该获得市净率理由)
    hikvision_case = {
        'code': 'hikvision_test',
        'name': '海康威视(PB边界)',
        'pattern': 'upward_trend',
        'score': 88,
        'pe': 21.83,
        'pb': 3.46,
        'positive_indicators': ['MACD金叉', 'RSI正常']
    }
    
    engine_pb_test = RecommendationEngine([hikvision_case])
    result_pb = engine_pb_test.generate_recommendations()
    
    if result_pb and '市净率低' in result_pb[0]['recommendation_reason']:
        print("✅ 海康威视案例: PB=3.46 获得'市净率低'理由")
        fixed_cases.append("海康威视")
    else:
        print("❌ 海康威视案例: PB=3.46 未获得'市净率低'理由")
    
    print(f"\n=== 总结 ===")
    print(f"✅ 成功修复案例: {len(fixed_cases)}/2")
    print(f"修复的股票: {', '.join(fixed_cases)}")
    
    if len(fixed_cases) == 2:
        print("\n🎉 基本面数据集成问题已完全修复！")
        print("推荐引擎现在能正确识别和展示基本面优势。")
    else:
        print(f"\n⚠️  仍有 {2-len(fixed_cases)} 个案例需要进一步修复。")

if __name__ == "__main__":
    test_comprehensive_fundamental_integration()