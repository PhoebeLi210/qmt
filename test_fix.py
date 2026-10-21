from stock_analysis_system.detailed_stock_analyzer import DetailedStockAnalyzer

# 创建分析器实例
analyzer = DetailedStockAnalyzer()

# 测试获取实时数据
stock_code = "600036"
real_time_data = analyzer.get_real_time_data(stock_code)

print(f"股票代码: {stock_code}")
print(f"当前价格: {real_time_data.get('current_price')}")
print(f"平均成本: {real_time_data.get('avg_cost')}")
print(f"所有实时数据: {real_time_data}")
