#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志工具模块
"""

import os
import logging
import logging.handlers
import sys
from datetime import datetime


class _NoColorFormatter(logging.Formatter):
    """无颜色日志格式化器"""

    def format(self, record):
        record.levelname = record.levelname
        return super().format(record)


class LoggerManager:
    """日志管理器"""
    
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        self.loggers = {}
        
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 日志格式
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def get_logger(self, name, level=logging.INFO):
        """获取或创建日志记录器"""
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        
        # 禁用颜色输出
        class NoColorFormatter(logging.Formatter):
            def format(self, record):
                return super().format(record)
        
        # 控制台处理器（无颜色）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(NoColorFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(console_handler)
        
        # 文件处理器（按天滚动）
        log_file = os.path.join(self.log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8'
        )
        file_handler.setFormatter(NoColorFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
        
        self.loggers[name] = logger
        return logger


# 全局日志管理器
logger_manager = LoggerManager()


def setup_logger(name, level=logging.INFO):
    """设置日志记录器的便捷函数"""
    return logger_manager.get_logger(name, level)


if __name__ == "__main__":
    # 测试日志功能
    logger = setup_logger("test_logger", logging.DEBUG)
    logger.debug("调试信息")
    logger.info("普通信息")
    logger.warning("警告信息")
    logger.error("错误信息")
    logger.critical("严重错误信息")
