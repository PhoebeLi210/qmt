#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试app.py的analyze路由
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from flask.testing import FlaskClient

def test_analyze_route():
    """测试analyze路由"""
    print("开始测试analyze路由...")
    
    # 创建测试客户端
    client = app.test_client()
    
    # 测试股票代码
    stock_code = '600519'
    
    try:
        # 发送GET请求到analyze路由
        response = client.get(f'/analyze/{stock_code}')
        
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容类型: {response.content_type}")
        
        # 检查响应内容
        content = response.data.decode('utf-8')
        print(f"\n响应内容前500个字符:")
        print(content[:500])
        
        # 搜索'incomplete format'错误
        if 'incomplete format' in content:
            print(f"\n✗ 发现'incomplete format'错误")
            # 找到错误的上下文
            error_index = content.index('incomplete format')
            start = max(0, error_index - 100)
            end = min(len(content), error_index + 100)
            print(f"\n错误上下文:")
            print(content[start:end])
            return False
        else:
            print(f"\n✓ 未发现'incomplete format'错误")
            return True
            
    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_analyze_route()
    sys.exit(0 if success else 1)