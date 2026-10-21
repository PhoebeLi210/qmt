#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
缓存管理模块

负责管理数据缓存，包括缓存的保存、读取、过期清理等功能。
"""

import os
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from logger import logger
from config import config


class CacheManager:
    """缓存管理器
    
    管理数据缓存，提供缓存的保存、读取、过期清理等功能。
    
    支持多种数据类型的缓存：
    - 股票列表数据
    - 股票日线数据
    - 实时行情数据
    """
    
    def __init__(self):
        """初始化缓存管理器
        """
        self._logger = logger
        self._config = config
        
        # 缓存文件扩展名
        self._CACHE_EXTENSION = '.parquet'
        
        # 缓存类型配置
        self._CACHE_TYPES = {
            'stock_list': {'expiry_days': 1, 'folder': 'stock_list'},
            'daily': {'expiry_days': self._config.CACHE_EXPIRY_DAYS, 'folder': 'daily'},
            'realtime': {'expiry_days': 0.1, 'folder': 'realtime'}  # 实时数据缓存14.4分钟
        }
        
        # 确保缓存目录结构存在
        self._ensure_cache_structure()
        
        self._logger.info("缓存管理模块初始化完成")
    
    def _ensure_cache_structure(self):
        """确保缓存目录结构存在
        """
        for cache_type in self._CACHE_TYPES.values():
            folder_path = os.path.join(self._config.CACHE_DIR, cache_type['folder'])
            os.makedirs(folder_path, exist_ok=True)
    
    def _get_cache_file_path(self, symbol: str, data_type: str = 'daily') -> str:
        """获取缓存文件路径
        
        Args:
            symbol: 股票代码
            data_type: 数据类型
            
        Returns:
            缓存文件路径
        """
        cache_type = self._CACHE_TYPES.get(data_type, self._CACHE_TYPES['daily'])
        folder_path = os.path.join(self._config.CACHE_DIR, cache_type['folder'])
        
        if data_type == 'stock_list':
            # 股票列表使用固定文件名
            filename = f'stock_list{self._CACHE_EXTENSION}'
        else:
            # 其他数据使用股票代码作为文件名
            filename = f'{symbol}{self._CACHE_EXTENSION}'
        
        return os.path.join(folder_path, filename)
    
    def _is_cache_valid(self, file_path: str, data_type: str = 'daily') -> bool:
        """检查缓存是否有效
        
        Args:
            file_path: 缓存文件路径
            data_type: 数据类型
            
        Returns:
            缓存是否有效
        """
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return False
        
        # 获取缓存过期时间
        cache_type = self._CACHE_TYPES.get(data_type, self._CACHE_TYPES['daily'])
        expiry_days = cache_type['expiry_days']
        
        # 计算文件创建时间
        file_mtime = os.path.getmtime(file_path)
        file_age_days = (time.time() - file_mtime) / (24 * 3600)
        
        # 检查缓存是否过期
        if file_age_days > expiry_days:
            self._logger.debug(f"缓存已过期，文件: {file_path}, 过期时间: {expiry_days}天, 当前年龄: {file_age_days:.2f}天")
            return False
        
        return True
    
    def save_data(self, symbol: str, data: Any, data_type: str = 'daily') -> bool:
        """保存数据到缓存
        
        Args:
            symbol: 股票代码
            data: 要保存的数据
            data_type: 数据类型
            
        Returns:
            是否保存成功
        """
        try:
            file_path = self._get_cache_file_path(symbol, data_type)
            
            if data_type == 'stock_list':
                # 股票列表数据保存为DataFrame
                df = pd.DataFrame(data)
                df.to_parquet(file_path, engine='pyarrow', index=False)
            elif isinstance(data, pd.DataFrame):
                # DataFrame数据直接保存
                data.to_parquet(file_path, engine='pyarrow', index=False)
            elif isinstance(data, dict):
                # 字典数据转换为DataFrame保存
                df = pd.DataFrame([data])
                df.to_parquet(file_path, engine='pyarrow', index=False)
            else:
                self._logger.error(f"不支持的数据类型: {type(data).__name__}")
                return False
            
            self._logger.debug(f"数据已保存到缓存: {file_path}")
            return True
        except Exception as e:
            self._logger.error(f"保存缓存失败", error=str(e))
            return False
    
    def get_cached_data(self, symbol: str, data_type: str = 'daily', 
                       start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[Any]:
        """获取缓存数据
        
        Args:
            symbol: 股票代码
            data_type: 数据类型
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            缓存数据，如果缓存无效或不存在返回None
        """
        file_path = self._get_cache_file_path(symbol, data_type)
        
        # 检查缓存是否有效
        if not self._is_cache_valid(file_path, data_type):
            return None
        
        try:
            # 读取缓存数据
            df = pd.read_parquet(file_path, engine='pyarrow')
            
            if data_type == 'stock_list':
                # 股票列表数据转换为字典列表返回
                return df.to_dict('records')
            elif data_type == 'daily' and start_date and end_date:
                # 日线数据按日期范围过滤
                df['date'] = pd.to_datetime(df['date'])
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                
                filtered_df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                if filtered_df.empty:
                    return None
                return filtered_df
            elif data_type == 'realtime':
                # 实时数据转换为字典返回
                return df.iloc[0].to_dict() if not df.empty else None
            else:
                # 其他数据直接返回DataFrame
                return df
        except Exception as e:
            self._logger.error(f"读取缓存失败", error=str(e))
            return None
    
    def clean_expired_cache(self) -> int:
        """清理过期缓存
        
        Returns:
            清理的缓存文件数量
        """
        self._logger.info("开始清理过期缓存")
        cleaned_count = 0
        
        for data_type, config in self._CACHE_TYPES.items():
            folder_path = os.path.join(self._config.CACHE_DIR, config['folder'])
            expiry_days = config['expiry_days']
            
            # 遍历文件夹中的所有缓存文件
            for filename in os.listdir(folder_path):
                if filename.endswith(self._CACHE_EXTENSION):
                    file_path = os.path.join(folder_path, filename)
                    
                    # 检查缓存是否过期
                    file_mtime = os.path.getmtime(file_path)
                    file_age_days = (time.time() - file_mtime) / (24 * 3600)
                    
                    if file_age_days > expiry_days:
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                            self._logger.debug(f"清理过期缓存: {file_path}")
                        except Exception as e:
                            self._logger.error(f"清理缓存失败", error=str(e), file_path=file_path)
        
        self._logger.info(f"缓存清理完成，共清理了{cleaned_count}个过期缓存文件")
        return cleaned_count
    
    def delete_cache(self, symbol: str, data_type: str = 'daily') -> bool:
        """删除特定缓存
        
        Args:
            symbol: 股票代码
            data_type: 数据类型
            
        Returns:
            是否删除成功
        """
        file_path = self._get_cache_file_path(symbol, data_type)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                self._logger.debug(f"缓存已删除: {file_path}")
                return True
            except Exception as e:
                self._logger.error(f"删除缓存失败", error=str(e))
                return False
        
        return True
    
    def clear_all_cache(self) -> int:
        """清除所有缓存
        
        Returns:
            清除的缓存文件数量
        """
        self._logger.info("开始清除所有缓存")
        cleared_count = 0
        
        for data_type, config in self._CACHE_TYPES.items():
            folder_path = os.path.join(self._config.CACHE_DIR, config['folder'])
            
            # 遍历文件夹中的所有缓存文件
            for filename in os.listdir(folder_path):
                if filename.endswith(self._CACHE_EXTENSION):
                    file_path = os.path.join(folder_path, filename)
                    try:
                        os.remove(file_path)
                        cleared_count += 1
                        self._logger.debug(f"清除缓存: {file_path}")
                    except Exception as e:
                        self._logger.error(f"清除缓存失败", error=str(e), file_path=file_path)
        
        self._logger.info(f"所有缓存已清除，共清除了{cleared_count}个缓存文件")
        return cleared_count
    
    def get_cache_size(self) -> int:
        """获取缓存总大小
        
        Returns:
            缓存总大小（字节）
        """
        total_size = 0
        
        for data_type, config in self._CACHE_TYPES.items():
            folder_path = os.path.join(self._config.CACHE_DIR, config['folder'])
            
            # 遍历文件夹中的所有缓存文件
            for filename in os.listdir(folder_path):
                if filename.endswith(self._CACHE_EXTENSION):
                    file_path = os.path.join(folder_path, filename)
                    total_size += os.path.getsize(file_path)
        
        return total_size


# 创建全局缓存管理器实例
cache_manager = CacheManager()


if __name__ == "__main__":
    # 测试缓存管理器
    cache = CacheManager()
    
    # 测试保存和读取股票列表
    test_stock_list = [
        {'code': '600000', 'name': '浦发银行', 'industry': '银行', 'area': '上海', 'market': 'A股', 'exchange': 'sh'},
        {'code': '600004', 'name': '白云机场', 'industry': '机场', 'area': '广东', 'market': 'A股', 'exchange': 'sh'}
    ]
    
    cache.save_data('', test_stock_list, 'stock_list')
    cached_list = cache.get_cached_data('', 'stock_list')
    print(f"股票列表缓存测试: {'成功' if cached_list else '失败'}")
    if cached_list:
        print(f"缓存的股票数量: {len(cached_list)}")
    
    # 测试保存和读取日线数据
    import pandas as pd
    from datetime import datetime, timedelta
    
    dates = [datetime.now() - timedelta(days=i) for i in range(10)]
    test_data = pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'code': ['600000'] * 10,
        'open': [10.0 + i * 0.1 for i in range(10)],
        'high': [10.2 + i * 0.1 for i in range(10)],
        'low': [9.8 + i * 0.1 for i in range(10)],
        'close': [10.1 + i * 0.1 for i in range(10)]
    })
    
    cache.save_data('600000', test_data, 'daily')
    cached_data = cache.get_cached_data('600000', 'daily')
    print(f"日线数据缓存测试: {'成功' if cached_data is not None else '失败'}")
    if cached_data is not None:
        print(f"缓存的日线数据行数: {len(cached_data)}")
    
    # 测试清理过期缓存
    cleaned = cache.clean_expired_cache()
    print(f"清理过期缓存测试: 清理了{cleaned}个文件")
    
    # 测试清除所有缓存
    # cleared = cache.clear_all_cache()
    # print(f"清除所有缓存测试: 清除了{cleared}个文件")