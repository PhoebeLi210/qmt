#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
结构化日志系统
"""

import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class NoColorFormatter(logging.Formatter):
    """无颜色日志格式化器"""
    def format(self, record):
        return super().format(record)


class StructuredLogger:
    """结构化日志记录器
    
    提供结构化的日志记录功能，支持控制台和文件输出，
    并提供统一的日志格式。
    """
    
    def __init__(self, name: str, level: int = logging.INFO):
        """初始化日志记录器
        
        Args:
            name: 日志名称
            level: 日志级别，默认INFO
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False
        
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        formatter = NoColorFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def debug(self, msg: str, **kwargs) -> None:
        """记录DEBUG级别日志
        
        Args:
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs) -> None:
        """记录INFO级别日志
        
        Args:
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs) -> None:
        """记录WARNING级别日志
        
        Args:
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs) -> None:
        """记录ERROR级别日志
        
        Args:
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        self._log(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs) -> None:
        """记录CRITICAL级别日志
        
        Args:
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        self._log(logging.CRITICAL, msg, **kwargs)
    
    def _log(self, level: int, msg: str, **kwargs) -> None:
        """内部日志记录方法
        
        Args:
            level: 日志级别
            msg: 日志消息
            **kwargs: 额外的结构化参数
        """
        if kwargs:
            # 将额外参数转换为格式化字符串
            extra_str = ' '.join([f'{k}={v}' for k, v in kwargs.items()])
            full_msg = f"{msg} {extra_str}"
        else:
            full_msg = msg
        
        self.logger.log(level, full_msg)


# 创建全局日志记录器实例
logger = StructuredLogger('root')


if __name__ == "__main__":
    # 测试日志记录器
    test_logger = StructuredLogger('test')
    test_logger.debug("这是一条DEBUG日志")
    test_logger.info("这是一条INFO日志", key1="value1", key2=123)
    test_logger.warning("这是一条WARNING日志")
    test_logger.error("这是一条ERROR日志", error="测试错误")
    test_logger.critical("这是一条CRITICAL日志")