import os
import sys
from flask import Flask, render_template, request, redirect, url_for

# 添加项目根目录和stock_analysis_system目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'stock_analysis_system'))

# 导入现有的分析器和数据采集器
from stock_analysis_system.detailed_stock_analyzer import DetailedStockAnalyzer
from stock_analysis_system.data_collector import DataCollector
from stock_analysis_system.baostock_connection_manager import BaostockConnectionManager
import baostock as bs

# 创建Flask应用
app = Flask(__name__)

# 设置模板文件夹路径
app.template_folder = 'templates'

# 首页路由
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 获取用户输入的股票代码
        stock_code = request.form.get('stock_code')
        if stock_code:
            # 重定向到分析页面
            return redirect(url_for('analyze', stock_code=stock_code))
    # GET请求显示输入表单
    return render_template('index.html')

# 处理Vite客户端请求的路由（避免404错误）
@app.route('/@vite/client')
def vite_client():
    # 返回空响应，避免404错误
    return '', 204

# 分析页面路由
@app.route('/analyze/<stock_code>')
def analyze(stock_code):
    try:
        print(f"开始分析股票: {stock_code}")
        
        # 创建分析器实例
        print("1. 创建分析器实例")
        analyzer = DetailedStockAnalyzer(report_dir='reports')
        
        # 准备股票信息
        print("2. 准备股票信息")
        stock_info = {'code': stock_code, 'name': '未知股票', 'industry': '未知'}
        
        # 尝试从DataCollector获取股票基本信息
        print("3. 尝试获取股票基本信息")
        try:
            # 从stock_analysis_system.data_collector导入StockDataAPI
            from stock_analysis_system.data_collector import StockDataAPI
            
            # 只获取用户查询的那一只股票的基本信息
            # 我们可以通过baostock的接口直接获取单只股票的基本信息
            import baostock as bs
            from baostock_connection_manager import BaostockConnectionManager
            
            # 使用连接管理器获取单只股票的基本信息
            try:
                connection_manager = BaostockConnectionManager()
                
                # 格式化股票代码
                formatted_code = f"sh.{stock_code}" if stock_code.startswith('6') else f"sz.{stock_code}"
                
                # 查询单只股票的基本信息
                rs = connection_manager.execute_query(
                    bs.query_stock_basic,
                    code=formatted_code
                )
                
                if rs and hasattr(rs, 'error_code') and rs.error_code == '0':
                    while rs.next():
                        row = rs.get_row_data()
                        # 更新股票名称
                        stock_info['name'] = row[1] if len(row) > 1 else '未知股票'
                        break
            except Exception as e:
                print(f"使用baostock获取单只股票基本信息失败: {e}")
            
            # 使用StockDataAPI获取行业信息
            try:
                industry = StockDataAPI.get_stock_industry(stock_code)
                if industry != '未知':
                    stock_info['industry'] = industry
                print(f"获取到的行业信息: {industry}")
            except Exception as e:
                print(f"使用StockDataAPI获取行业信息失败: {e}")
                
            # 如果baostock失败，尝试使用简单的股票名称映射
            # 这只是一个示例，实际应用中可以使用更完善的映射表
            simple_name_map = {
                '600036': '招商银行',
                '000001': '平安银行',
                '601318': '中国平安',
                '600519': '贵州茅台'
            }
            
            if stock_info['name'] == '未知股票' and stock_code in simple_name_map:
                stock_info['name'] = simple_name_map[stock_code]
                
        except Exception as e:
            print(f"获取股票基本信息失败: {e}")
        
        # 执行分析
        print("4. 执行股票分析")
        print(f"股票信息: {stock_info}")
        analysis_result = analyzer.analyze_stock(stock_info)
        
        # 提取关键信息
        stock_data = {
            'code': analysis_result.get('code', stock_code),
            'name': analysis_result.get('name', '未知股票'),
            'industry': analysis_result.get('industry', '未知'),
            'current_price': analysis_result.get('current_price', 0),
            'change_pct': analysis_result.get('change_pct', 0),
            'turnover_rate': analysis_result.get('turnover_rate', 0),
            'market_sentiment': analysis_result.get('market_sentiment', '未知')
        }
        
        # 交易信号信息
        trading_signal = analysis_result.get('trading_signal', {})
        signal_info = {
            'signal': trading_signal.get('signal', '无'),
            'high_price': trading_signal.get('high_price', 0),
            'low_price': trading_signal.get('low_price', 0),
            'historical_volatility': trading_signal.get('historical_volatility', 0),
            'technical_support': trading_signal.get('technical_support', 0),
            'technical_resistance': trading_signal.get('technical_resistance', 0)
        }
        
        # 主力资金分析
        main_analysis = analysis_result.get('main_analysis', {})
        main_info = {
            'main_trend': main_analysis.get('main_trend', '未知'),
            'trend_strength': main_analysis.get('trend_strength', '未知'),
            'price_trend': main_analysis.get('price_trend', '未知')
        }
        
        # 散户流向分析
        retail_analysis = analysis_result.get('retail_analysis', {})
        retail_info = {
            'retail_trend': retail_analysis.get('retail_trend', '未知'),
            'concentration': retail_analysis.get('concentration', '未知'),
            'price_impact': retail_analysis.get('price_impact', '未知')
        }
        
        # 主力持仓分析
        holding_analysis = analysis_result.get('holding_analysis', {})
        holding_info = {
            'holding_trend': holding_analysis.get('holding_trend', '未知'),
            'avg_cost': holding_analysis.get('avg_cost', 0),
            'cost_diff': holding_analysis.get('cost_diff', 0),
            'cost_diff_pct': holding_analysis.get('cost_diff_pct', 0),
            'trend_impact': holding_analysis.get('trend_impact', '未知')
        }
        
        # Level-2指标分析
        level2_indicators = analysis_result.get('level2_indicators', {})
        
        # 处理tick_data_analysis，确保所有字段都有默认值
        tick_data_analysis = level2_indicators.get('tick_data_analysis', {})
        # 重命名large_order_ratio为large_trade_ratio以匹配模板
        if 'large_order_ratio' in tick_data_analysis:
            # 转换为百分比字符串
            tick_data_analysis['large_trade_ratio'] = f"{tick_data_analysis['large_order_ratio'] * 100:.2f}%"
        else:
            tick_data_analysis['large_trade_ratio'] = "0.00%"
        
        tick_data_analysis = {
            'activity_level': tick_data_analysis.get('activity_level', 'N/A'),
            'trading_speed': tick_data_analysis.get('trading_speed', 'N/A'),
            **tick_data_analysis
        }
        
        # 处理high_frequency_prediction，确保所有字段都有默认值
        high_frequency_prediction = level2_indicators.get('high_frequency_prediction', {})
        # 转换为百分比字符串
        high_frequency_prediction = {
            'price_prediction': f"{high_frequency_prediction.get('price_prediction', 0.0) * 100:.2f}%",
            'volatility': f"{high_frequency_prediction.get('volatility', 0.0) * 100:.2f}%",
            'confidence': f"{high_frequency_prediction.get('confidence', 0.0) * 100:.2f}%",
            **high_frequency_prediction
        }
        
        level2_info = {
            'order_imbalance': level2_indicators.get('order_imbalance', 0),
            'trade_imbalance': level2_indicators.get('trade_imbalance', 0),
            'depth_imbalance': level2_indicators.get('depth_imbalance', 0),
            'vwap': level2_indicators.get('vwap', 0),
            'twap': level2_indicators.get('twap', 0),
            'micro_price': level2_indicators.get('micro_price', 0),
            'bid_ask_pressure': level2_indicators.get('bid_ask_pressure', 0),
            'price_strength': level2_indicators.get('price_strength', 0),
            'large_order_ratio': level2_indicators.get('large_order_ratio', 0),
            'order_flow_imbalance': level2_indicators.get('order_flow_imbalance', 0),
            'market_maker_behaviors': level2_indicators.get('market_maker_behaviors', []),
            'order_book_analysis': level2_indicators.get('order_book_analysis', {}),
            'tick_data_analysis': tick_data_analysis,
            'high_frequency_prediction': high_frequency_prediction,
            'capital_flow': level2_indicators.get('capital_flow', {}),
            'breakout_signals': level2_indicators.get('breakout_signals', {})
        }
        
        # 渲染分析结果页面
        return render_template(
            'analyze.html',
            stock_data=stock_data,
            signal_info=signal_info,
            main_info=main_info,
            retail_info=retail_info,
            holding_info=holding_info,
            level2_info=level2_info
        )
    except Exception as e:
        # 处理错误
        import traceback
        print(f"分析过程中发生错误: {e}")
        traceback.print_exc()
        return render_template('error.html', error=str(e), stock_code=stock_code)

if __name__ == '__main__':
    # 确保templates目录存在
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # 运行Flask应用
    app.run(debug=True, host='0.0.0.0', port=5000)
