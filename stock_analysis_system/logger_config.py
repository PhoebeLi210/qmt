#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志配置模块
实现日志的配置、轮换和清理机制
"""

import logging
import logging.handlers
import os
import sys
from config import LOG_LEVEL, LOG_FILE


class NoColorFormatter(logging.Formatter):
    """无颜色日志格式化器"""
    def format(self, record):
        return super().format(record)


def setup_logger():
    """
    设置日志配置
    - 日志级别：INFO（可通过config.py配置）
    - 日志格式：包含时间、模块名、日志级别和日志信息
    - 日志输出：同时输出到控制台和文件
    - 日志轮换：按大小轮换，最大100MB，最多保留10个文件
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    if logger.handlers:
        return logger
    
    formatter = NoColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.encoding = 'utf-8'
    logger.addHandler(console_handler)
    
    if LOG_FILE:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=100 * 1024 * 1024,
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def setup_timed_logger():
    """
    设置按时间轮换的日志配置
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    if logger.handlers:
        return logger
    
    formatter = NoColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.encoding = 'utf-8'
    logger.addHandler(console_handler)
    
    if LOG_FILE:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE,
            when='D',
            interval=1,
            backupCount=7,
            encoding='utf-8',
            delay=False,
            utc=False
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def cleanup_old_logs(log_dir, days_to_keep=7):
    """清理旧日志文件"""
    import time
    import glob
    
    if not os.path.exists(log_dir):
        return
    
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    
    log_files = glob.glob(os.path.join(log_dir, '*.log*'))
    
    for log_file in log_files:
        try:
            mtime = os.path.getmtime(log_file)
            if mtime < cutoff:
                os.remove(log_file)
                logging.info(f"已删除旧日志文件: {log_file}")
        except Exception as e:
            logging.error(f"清理日志文件失败 {log_file}: {e}")
