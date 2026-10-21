#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
集中配置管理
"""

import os
from typing import List, Dict, Any


class Config:
    """配置管理类
    
    集中管理所有配置信息，包括项目路径、缓存配置、网络配置等。
    """
    
    def __init__(self):
        """初始化配置
        """
        # 项目路径配置
        self.PROJECT_ROOT = os.path.dirname(__file__)
        self.DATA_DIR = os.path.join(self.PROJECT_ROOT, 'data')
        self.CACHE_DIR = os.path.join(self.PROJECT_ROOT, 'cache')
        self.LOG_DIR = os.path.join(self.PROJECT_ROOT, 'logs')
        
        # 确保目录存在
        for dir_path in [self.DATA_DIR, self.CACHE_DIR, self.LOG_DIR]:
            os.makedirs(dir_path, exist_ok=True)
        
        # 缓存配置
        self.CACHE_EXPIRY_DAYS = 7  # 缓存过期时间（天）
        self.CACHE_SIZE_LIMIT = 10 * 1024 * 1024 * 1024  # 缓存大小限制（10GB）
        
        # 网络配置
        self.HTTP_TIMEOUT = 30  # HTTP请求超时时间（秒）
        self.MAX_RETRIES = 3  # 网络请求最大重试次数
        self.RETRY_DELAY = 2  # 重试延迟（秒）
        
        # 数据源配置
        self.VALID_STOCK_PREFIXES = ['60', '00', '30', '68']  # 有效的股票代码前缀
        self.BAOSTOCK_ENABLED = True  # 是否启用baostock数据源
        self.EASTMONEY_ENABLED = True  # 是否启用东方财富数据源
        self.NETEASE_ENABLED = True  # 是否启用网易财经数据源
        self.SINA_ENABLED = True  # 是否启用新浪财经数据源
        
        # 处理配置
        self.PROGRESS_INTERVAL = 100  # 进度输出间隔（只处理100只股票输出一次）
        self.BATCH_SIZE = 1  # 批处理大小（单线程设置为1）
        
        # 日志配置
        self.LOG_LEVEL = 'INFO'  # 日志级别
        self.LOG_FILE_ROTATION = 'daily'  # 日志文件轮换方式
        
        # 数据库配置（如果需要）
        self.DB_TYPE = 'sqlite'  # 数据库类型
        self.DB_PATH = os.path.join(self.DATA_DIR, 'stock_data.db')  # 数据库路径
        
        # 输出配置
        self.SAVE_TO_DB = False  # 是否保存到数据库
        self.SAVE_TO_CSV = False  # 是否保存到CSV文件
        
        # 分析配置
        self.ANALYSIS_PERIODS = [30, 60, 120, 250]  # 分析周期（天）
        
        self._logger = None  # 延迟初始化日志记录器
    
    @property
    def logger(self):
        """获取日志记录器
        
        Returns:
            日志记录器实例
        """
        if self._logger is None:
            from logger import logger
            self._logger = logger
        return self._logger


# 创建全局配置实例
config = Config()


if __name__ == "__main__":
    # 测试配置
    print("项目根目录:", config.PROJECT_ROOT)
    print("数据目录:", config.DATA_DIR)
    print("缓存目录:", config.CACHE_DIR)
    print("日志目录:", config.LOG_DIR)
    print("HTTP超时时间:", config.HTTP_TIMEOUT)
    print("最大重试次数:", config.MAX_RETRIES)