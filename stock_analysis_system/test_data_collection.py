import akshare as ak
import pandas as pd

# 详细测试获取平安银行的基本面数据
code = '000001'  # 平安银行
print(f'正在获取股票 {code} 的基本面数据...')
basic_info = ak.stock_individual_info_em(symbol=code)
print('=== 平安银行完整基本面数据 ===')
print(f'数据形状: {basic_info.shape}')
print(f'列名: {list(basic_info.columns)}')
print()
print('前10行数据:')
print(basic_info.head(10))
print()
print('所有数据:')
for _, row in basic_info.iterrows():
    item = str(row.get('项目', ''))
    value = str(row.get('值', ''))
    print(f'{item}: {value}')

print("\n=== 查找流通股本和行业信息 ===")
for _, row in basic_info.iterrows():
    item = str(row.get('项目', ''))
    value = str(row.get('值', ''))
    if '流通' in item or '股本' in item or '行业' in item or '所属' in item:
        print(f'✓ 找到相关字段: {item}: {value}')