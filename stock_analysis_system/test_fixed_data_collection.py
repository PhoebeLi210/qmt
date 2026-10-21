import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def test_data_collection():
    """测试修复后的数据收集逻辑"""
    stock_code = '000001'  # 直接使用股票代码，不需要分割
    
    print(f'正在测试股票 {stock_code} 的数据收集...')
    
    # 1. 获取基本面数据
    basic_info = ak.stock_individual_info_em(symbol=stock_code)
    print(f'基本面数据结构: {list(basic_info.columns)}')
    print('完整数据:')
    for _, row in basic_info.iterrows():
        item = str(row.get('item', ''))
        value = str(row.get('value', ''))
        print(f'  {item}: {value}')
    
    print('\n=== 测试解析逻辑 ===')
    pe_ratio = None
    pb_ratio = None
    market_cap = None
    liquid_shares = None
    industry = None
    
    # 解析数据
    for _, row in basic_info.iterrows():
        item = str(row.get('item', ''))
        value = str(row.get('value', ''))
        
        print(f'解析: {item} = {value}')
        
        if pe_ratio is None and '市盈率' in item and value != '--':
            try:
                pe_ratio = float(value)
                print(f'  ✓ PE比率: {pe_ratio}')
            except:
                pe_ratio = 20.0
                print(f'  ✗ PE解析失败，使用默认值: {pe_ratio}')
        elif pb_ratio is None and '市净率' in item and value != '--':
            try:
                pb_ratio = float(value)
                print(f'  ✓ PB比率: {pb_ratio}')
            except:
                pb_ratio = 2.0
                print(f'  ✗ PB解析失败，使用默认值: {pb_ratio}')
        elif market_cap is None and '总市值' in item and value != '--':
            try:
                if '万' in value:
                    market_cap = float(value.replace('万', '')) * 10000
                elif '亿' in value:
                    market_cap = float(value.replace('亿', '')) * 100000000
                else:
                    market_cap = float(value)
                print(f'  ✓ 总市值: {market_cap:,.0f}')
            except:
                market_cap = 100000000
                print(f'  ✗ 市值解析失败，使用默认值: {market_cap:,.0f}')
        elif liquid_shares is None and ('流通股' in item or ('流通' in item and '股本' in item)) and value != '--':
            try:
                liquid_shares = float(value)
                print(f'  ✓ 流通股数: {liquid_shares:,.0f}')
            except:
                liquid_shares = 500000000
                print(f'  ✗ 流通股数解析失败，使用默认值: {liquid_shares:,.0f}')
        elif industry is None and ('行业' in item or '所属' in item) and value != '--':
            industry = value
            print(f'  ✓ 行业: {industry}')
    
    # 设置默认值
    if pe_ratio is None:
        pe_ratio = 20.0
        print(f'PE比率设置默认值: {pe_ratio}')
    if pb_ratio is None:
        pb_ratio = 2.0
        print(f'PB比率设置默认值: {pb_ratio}')
    if market_cap is None:
        market_cap = 100000000
        print(f'总市值设置默认值: {market_cap:,.0f}')
    if liquid_shares is None:
        liquid_shares = 500000000
        print(f'流通股数设置默认值: {liquid_shares:,.0f}')
    if industry is None:
        industry = '未知'
        print(f'行业设置默认值: {industry}')
    
    print('\n=== 最终结果 ===')
    print(f'PE比率: {pe_ratio}')
    print(f'PB比率: {pb_ratio}')
    print(f'总市值: {market_cap:,.0f}')
    print(f'流通股数: {liquid_shares:,.0f}')
    print(f'行业: {industry}')
    
    # 检查是否使用了真实数据
    real_data_count = 0
    if pe_ratio != 20.0:
        real_data_count += 1
    if pb_ratio != 2.0:
        real_data_count += 1
    if market_cap != 100000000:
        real_data_count += 1
    if liquid_shares != 500000000:
        real_data_count += 1
    if industry != '未知':
        real_data_count += 1
    
    print(f'\n使用了 {real_data_count}/5 个真实数据字段')
    
    return {
        'pe': pe_ratio,
        'pb': pb_ratio,
        'market_cap': market_cap,
        'liquid_shares': liquid_shares,
        'industry': industry
    }

if __name__ == '__main__':
    result = test_data_collection()