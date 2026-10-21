#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""baostock连接管理器 - 管理baostock API连接，处理连接池和错误重试"""

import logging
import time
import threading
import importlib
import sys
from typing import Optional, Any

# 初始化日志记录器
logger = logging.getLogger('BaostockConnectionManager')

try:
    import baostock as bs
    BAOSTOCK_AVAILABLE = True
except ImportError:
    BAOSTOCK_AVAILABLE = False


class BaostockConnectionManager:
    """baostock连接管理器"""
    
    def __init__(self):
        self._connected = False
        self._lock = threading.RLock()
        self._last_login_time = None
        self._connection_health = True
        self._max_retries = 5  # 增加重试次数
        self._retry_delay = 3.0  # 增加初始重试延迟
        self._connection_timeout = 120  # 增加连接超时时间（秒）
        self._max_connections = 1
        self._active_connections = 0
        
    def login(self) -> bool:
        """登录baostock，带重试机制"""
        with self._lock:
            if self._connected and self._connection_health:
                # 检查连接是否过期
                if self._last_login_time and (time.time() - self._last_login_time) < self._connection_timeout:
                    return True
                else:
                    # 连接已过期，重新登录
                    self.logout()
            
            for attempt in range(self._max_retries):
                try:
                    if not BAOSTOCK_AVAILABLE:
                        logging.error("baostock库不可用")
                        return False
                    
                    logging.info(f"尝试登录baostock (尝试 {attempt + 1}/{self._max_retries})")
                    
                    # 重置baostock模块状态，避免连接问题
                    if attempt > 0:
                        self._reset_baostock_module()
                    
                    # 登录
                    lg = bs.login()
                    if lg.error_code == '0':
                        self._connected = True
                        self._connection_health = True
                        self._last_login_time = time.time()
                        logging.info("baostock登录成功")
                        return True
                    else:
                        error_info = f"登录失败: {lg.error_msg} (错误码: {lg.error_code})"
                        logging.error(error_info)
                        if attempt < self._max_retries - 1:
                            retry_delay = self._retry_delay * (attempt + 1)  # 指数退避
                            logging.info(f"{retry_delay:.1f}秒后重试...")
                            time.sleep(retry_delay)
                except Exception as e:
                    error_info = f"登录异常: {str(e)}"
                    logging.error(error_info)
                    if attempt < self._max_retries - 1:
                        retry_delay = self._retry_delay * (attempt + 1)
                        logging.info(f"{retry_delay:.1f}秒后重试...")
                        time.sleep(retry_delay)
            
            # 所有尝试都失败
            self._connected = False
            self._connection_health = False
            logging.error("baostock登录失败，已尝试所有重试")
            return False
    
    def logout(self) -> bool:
        """安全登出baostock"""
        with self._lock:
            if not self._connected:
                return True
            
            try:
                # 尝试登出
                for attempt in range(self._max_retries):
                    try:
                        result = bs.logout()
                        if result.error_code == '0':
                            self._connected = False
                            self._active_connections = 0
                            logging.info("baostock登出成功")
                            return True
                        else:
                            logging.warning(f"登出失败: {result.error_msg} (尝试 {attempt + 1}/{self._max_retries})")
                    except Exception as e:
                        logging.warning(f"登出异常: {str(e)} (尝试 {attempt + 1}/{self._max_retries})")
                    
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay)
                
                # 所有尝试都失败，重置状态
                self._connected = False
                self._active_connections = 0
                self._connection_health = False
                logging.warning("baostock强制登出，已重置连接状态")
                return True
            except Exception:
                # 最终的安全网
                self._connected = False
                self._active_connections = 0
                self._connection_health = False
                logging.error("baostock登出严重失败，已重置连接状态")
                return True
    
    def execute_query(self, query_function, *args, **kwargs) -> Optional[Any]:
        """执行baostock查询，带重试和连接恢复机制"""
        with self._lock:
            if not self._connected:
                logging.info("连接未建立，尝试登录")
                if not self.login():
                    logging.error("登录失败，无法执行查询")
                    return None
            
            query_name = getattr(query_function, '__name__', str(query_function))
            
            # 提取股票代码，用于更友好的日志
            stock_code = None
            if 'code' in kwargs:
                stock_code = kwargs['code']
            elif args:
                for arg in args:
                    if isinstance(arg, str) and (arg.startswith('sh.') or arg.startswith('sz.')):
                        stock_code = arg
                        break
            
            for attempt in range(self._max_retries):
                try:
                    # 检查连接健康状态
                    if not self._connection_health:
                        logging.info("检测到连接异常，尝试重新连接")
                        if not self.reconnect():
                            logging.error("重新连接失败")
                            return None
                    
                    # 执行查询，添加超时保护
                    import traceback
                    import baostock as bs
                    import io
                    import sys
                    
                    # 根据查询类型和参数设置不同的超时时间
                    # 股票历史数据查询可能需要更长时间，特别是对于数据量较大的股票
                    timeout = 150.0  # 默认超时时间
                    if query_name == 'query_history_k_data_plus':
                        # 为特定股票或科创板股票设置更长的超时时间
                        timeout = 240.0  # 默认股票历史数据查询超时时间
                        if stock_code:
                            # 检查是否为科创板股票（688开头），忽略市场前缀
                            if '.' in stock_code:
                                code_part = stock_code.split('.')[1]
                                if code_part.startswith('688'):
                                    timeout = 300.0  # 科创板股票增加超时时间到300秒
                            else:
                                # 没有市场前缀的情况
                                if stock_code.startswith('688'):
                                    timeout = 300.0
                            # 为历史上经常超时的股票设置更长时间
                            problematic_stocks = ['sh.002234']  # 可以根据实际情况添加更多股票
                            if stock_code in problematic_stocks:
                                timeout = 360.0  # 特别问题股票增加超时时间到360秒
                    
                    # 使用线程池包装查询，提供额外的异常隔离
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        # 提交查询任务
                        future = executor.submit(query_function, *args, **kwargs)
                        try:
                            # 等待查询结果，添加超时保护
                            result = future.result(timeout=timeout)
                            
                            # 检查结果是否有效
                            if result is None:
                                raise Exception("查询返回None")
                        except UnicodeDecodeError as e:
                            # 捕获查询执行过程中的编码错误
                            logger.warning(f"查询执行过程中出现编码错误，尝试重置连接: {e}")
                            # 重置连接，避免影响后续请求
                            self._connection_health = False
                            self.reconnect()
                            # 跳过当前股票，继续处理其他股票
                            return None
                        except Exception as e:
                            # 捕获其他异常
                            logger.warning(f"查询执行过程中出现异常: {e}")
                            # 尝试重新连接
                            self._connection_health = False
                            self.reconnect()
                            # 继续重试
                            continue
                    
                    # 对于baostock返回的结果对象，检查error_code
                    if hasattr(result, 'error_code'):
                        # 安全地处理error_msg，避免编码错误
                        error_msg = "未知"
                        if hasattr(result, 'error_msg'):
                            try:
                                if isinstance(result.error_msg, bytes):
                                    # 尝试多种编码方式解码
                                    encodings = ['utf-8', 'gbk', 'gb18030', 'latin-1']
                                    for encoding in encodings:
                                        try:
                                            error_msg = result.error_msg.decode(encoding)
                                            break
                                        except UnicodeDecodeError:
                                            continue
                                    else:
                                        # 所有编码都失败，尝试忽略错误
                                        error_msg = result.error_msg.decode('utf-8', errors='replace')
                                else:
                                    # 如果是字符串，确保它是有效的utf-8
                                    if isinstance(result.error_msg, str):
                                        # 尝试编码解码以确保有效性
                                        error_msg = result.error_msg.encode('utf-8', errors='replace').decode('utf-8')
                                    else:
                                        error_msg = str(result.error_msg)
                            except Exception as e:
                                logging.warning(f"解析错误信息时发生异常: {e}")
                                error_msg = "无法解析的错误信息"
                        
                        # 特别处理网络接收错误（错误码10002007）
                        if result.error_code == '10002007':
                            stock_msg = f" (股票: {stock_code})" if stock_code else ""
                            logging.warning(f"baostock网络接收错误{stock_msg}，将跳过此股票，继续处理其他股票")
                            # 立即返回None，不再重试，避免无限循环
                            # 只在必要时重置连接
                            if attempt > 1:  # 只有在多次尝试失败后才重置
                                self._connection_health = False
                                self.reconnect()
                            return None
                        
                        if result.error_code != '0':
                            # 对于其他错误，不再重试，直接返回None
                            stock_msg = f" (股票: {stock_code})" if stock_code else ""
                            logging.warning(f"baostock查询失败{stock_msg}，错误码: {result.error_code}，将跳过此股票")
                            return None
                    
                    # 查询成功，不记录详细日志，减少日志噪音
                    return result
                    
                except UnicodeDecodeError as e:
                    # 捕获所有UnicodeDecodeError，包括query_function内部的
                    stock_msg = f" (股票: {stock_code})" if stock_code else ""
                    logging.warning(f"baostock编码错误{stock_msg}，将跳过此股票，继续处理其他股票")
                    # 立即重置连接，避免影响后续请求
                    self._connection_health = False
                    self.reconnect()
                    # 返回None，让上层调用者处理
                    return None
                except Exception as e:
                    error_info = str(e)
                    stock_msg = f" (股票: {stock_code})" if stock_code else ""
                    
                    # 检查是否是连接问题
                    if any(err_str in error_info.lower() for err_str in ['connection', '网络', 'socket', 'connect', 'timeout', 'winerror 10060', 'winerror 10054', '远程主机', '强迫关闭']):
                        if attempt == 0:  # 只在第一次失败时记录
                            logging.warning(f"baostock连接异常{stock_msg}，正在尝试恢复连接")
                        self._connection_health = False
                        if not self.reconnect():
                            logging.error("重新连接失败，将跳过此股票")
                            return None
                    
                    # 其他错误，等待后重试
                    if attempt < self._max_retries - 1:
                        # 只在第一次失败时记录
                        if attempt == 0:
                            logging.warning(f"baostock查询异常{stock_msg}，正在重试...")
                        retry_delay = self._retry_delay * (attempt + 1)
                        time.sleep(retry_delay)
                    else:
                        logging.warning(f"baostock查询失败{stock_msg}，已尝试所有重试，将跳过此股票")
            
            # 查询最终失败
            stock_msg = f" (股票: {stock_code})" if stock_code else ""
            logging.warning(f"baostock查询{stock_msg}最终失败，返回None")
            return None
    
    def reconnect(self) -> bool:
        """重新建立连接"""
        with self._lock:
            logging.info("尝试重新连接baostock")
            
            # 先登出当前连接（如果存在）
            self.logout()
            
            # 重置baostock模块
            self._reset_baostock_module()
            
            # 重新登录
            return self.login()
    
    def _reset_baostock_module(self):
        """重置baostock模块，清除可能的连接状态"""
        try:
            # 尝试重新加载baostock模块
            if 'baostock' in sys.modules:
                logging.info("重置baostock模块")
                importlib.reload(bs)
                # 更新全局引用
                globals()['bs'] = bs
        except Exception as e:
            logging.warning(f"重置baostock模块失败: {str(e)}")
    
    def close(self):
        """关闭管理器，清理资源"""
        self.logout()
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        with self._lock:
            return self._connected and self._connection_health
    
    @property
    def login_success(self) -> bool:
        """
        连接状态属性 - 兼容根目录版本的连接管理器
        返回is_connected的值，确保代码兼容性
        """
        return self.is_connected
    
    def check_connection_health(self) -> bool:
        """检查连接健康状态"""
        with self._lock:
            if not self._connected:
                return False
            
            # 检查连接是否过期
            if self._last_login_time and (time.time() - self._last_login_time) >= self._connection_timeout:
                logging.info("连接已过期，需要重新登录")
                return False
            
            # 尝试执行一个简单的查询检查连接
            try:
                # 使用execute_query方法执行一个简单查询
                result = self.execute_query(bs.query_stock_basic, code_name="")
                if result is None:
                    self._connection_health = False
                    return False
                
                # 消耗查询结果
                result.data
                
                self._connection_health = True
                return True
            except Exception as e:
                logging.error(f"连接健康检查失败: {str(e)}")
                self._connection_health = False
                return False


# 创建全局连接管理器实例
connection_manager = BaostockConnectionManager()


# 确保程序退出时关闭连接
def _cleanup_on_exit():
    try:
        connection_manager.close()
        logging.info("baostock连接管理器已清理")
    except Exception:
        pass


# 注册退出处理器
try:
    import atexit
    atexit.register(_cleanup_on_exit)
except Exception:
    logging.warning("无法注册退出处理器")


if __name__ == "__main__":
    # 简单测试
    logging.basicConfig(level=logging.INFO)
    print("测试baostock连接管理器...")
    
    # 测试登录
    if connection_manager.login():
        print("登录成功")
        
        # 测试简单查询
        result = connection_manager.execute_query(
            bs.query_stock_basic, 
            code_name="", 
            fields="code,code_name,industry,market"
        )
        
        if result:
            print(f"查询成功，返回数据类型: {type(result)}")
        
        # 测试登出
        connection_manager.logout()
        print("测试完成")
    else:
        print("登录失败")
