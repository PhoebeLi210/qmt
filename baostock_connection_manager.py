import baostock as bs
import logging
import time
import threading
import random
from contextlib import contextmanager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('BaostockConnectionManager')

class BaostockConnectionManager:
    """
    统一的baostock连接管理器
    提供线程安全的连接管理、完善的错误处理和重试机制
    """
    
    # 单例模式
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BaostockConnectionManager, cls).__new__(cls)
                cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化连接管理器"""
        self.login_success = False
        self.last_login_time = 0
        self.query_count = 0
        self.max_query_per_session = 1000  # 每个会话最大查询次数
        self.connection_timeout = 1800  # 连接超时时间（秒）
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2  # 重试基础延迟（秒）
        self.min_request_interval = 0.3  # 最小请求间隔
        self.max_request_interval = 0.8  # 最大请求间隔
        self.last_request_time = 0
    
    def login(self, force_reconnect=False):
        """
        登录baostock
        :param force_reconnect: 是否强制重新连接
        :return: 登录是否成功
        """
        with self._lock:
            # 如果已经登录且不强制重新连接，则检查连接状态
            if self.login_success and not force_reconnect:
                if self._check_connection_health():
                    logger.debug("使用现有连接")
                    return True
                else:
                    logger.info("连接状态异常，需要重新登录")
            
            # 先登出可能存在的连接
            if self.login_success:
                self.logout()
            
            # 尝试登录，带重试机制
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"尝试登录baostock（尝试 {attempt + 1}/{self.max_retries}）...")
                    lg = bs.login()
                    
                    if lg.error_code == '0':
                        self.login_success = True
                        self.last_login_time = time.time()
                        self.query_count = 0
                        logger.info("baostock登录成功!")
                        return True
                    else:
                        error_msg = f"登录失败，错误代码: {lg.error_code}，错误信息: {lg.error_msg}"
                        logger.error(error_msg)
                        
                        # 根据错误类型决定等待时间
                        if lg.error_code == '10002007':  # 网络接收错误
                            wait_time = (attempt + 1) * 5
                        else:
                            wait_time = (attempt + 1) * self.retry_delay
                        
                        if attempt < self.max_retries - 1:
                            logger.info(f"{wait_time}秒后重试...")
                            time.sleep(wait_time)
                except Exception as e:
                    logger.error(f"登录时发生异常: {str(e)}")
                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * self.retry_delay
                        logger.info(f"{wait_time}秒后重试...")
                        time.sleep(wait_time)
            
            self.login_success = False
            logger.error("登录失败，已达到最大重试次数")
            return False
    
    def logout(self):
        """
        安全登出baostock
        """
        with self._lock:
            if self.login_success:
                try:
                    logger.info("尝试登出baostock...")
                    lg = bs.logout()
                    if lg.error_code == '0':
                        logger.info("baostock登出成功!")
                    else:
                        logger.warning(f"登出失败，错误代码: {lg.error_code}，错误信息: {lg.error_msg}")
                except Exception as e:
                    logger.warning(f"登出时发生异常: {str(e)}")
                finally:
                    self.login_success = False
                    self.query_count = 0
    
    def _check_connection_health(self):
        """
        检查连接健康状态
        :return: 连接是否健康
        """
        # 检查是否已登录
        if not self.login_success:
            return False
        
        # 检查查询次数是否过多
        if self.query_count >= self.max_query_per_session:
            logger.info(f"查询次数已达上限({self.max_query_per_session})，需要重新连接")
            return False
        
        # 检查连接是否超时
        current_time = time.time()
        if current_time - self.last_login_time > self.connection_timeout:
            logger.info(f"连接已持续{(current_time - self.last_login_time):.0f}秒，超过超时时间")
            return False
        
        return True
    
    def ensure_healthy_connection(self):
        """
        确保连接健康，如果不健康则重新连接
        :return: 连接是否健康
        """
        with self._lock:
            if not self._check_connection_health():
                logger.info("连接不健康，尝试重新连接...")
                return self.login(force_reconnect=True)
            return True
    
    def _throttle_request(self):
        """
        请求节流，避免请求过快
        """
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # 计算需要等待的时间
        min_interval = random.uniform(self.min_request_interval, self.max_request_interval)
        if time_since_last < min_interval:
            wait_time = min_interval - time_since_last
            logger.debug(f"请求节流，等待{wait_time:.2f}秒")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
        self.query_count += 1
    
    @contextmanager
    def get_connection(self):
        """
        上下文管理器，提供安全的连接使用方式
        使用示例:
            with connection_manager.get_connection():
                # 执行baostock操作
        """
        # 确保连接健康
        if not self.ensure_healthy_connection():
            raise ConnectionError("无法建立健康的baostock连接")
        
        try:
            # 请求节流
            self._throttle_request()
            yield self
        except Exception as e:
            # 处理特定错误
            if isinstance(e, Exception):
                error_str = str(e)
                if "WinError 10038" in error_str:
                    logger.error("检测到WinError 10038错误，标记连接为不健康")
                    self.login_success = False
            raise
    
    def execute_query(self, query_func, *args, **kwargs):
        """
        执行查询，带重试机制
        :param query_func: 查询函数
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 查询结果
        """
        for attempt in range(self.max_retries):
            try:
                with self.get_connection():
                    logger.debug(f"执行查询（尝试 {attempt + 1}/{self.max_retries}）")
                    result = query_func(*args, **kwargs)
                    
                    # 检查结果是否成功
                    if hasattr(result, 'error_code'):
                        if result.error_code != '0':
                            error_msg = f"查询失败，错误代码: {result.error_code}，错误信息: {result.error_msg}"
                            logger.error(error_msg)
                            
                            # 根据错误类型决定是否重试
                            if result.error_code in ['10002007', '10001002']:  # 网络错误或服务器错误
                                if attempt < self.max_retries - 1:
                                    wait_time = (attempt + 1) * 3
                                    logger.info(f"网络错误，{wait_time}秒后重试...")
                                    # 强制重新连接
                                    self.login(force_reconnect=True)
                                    time.sleep(wait_time)
                                    continue
                            raise Exception(error_msg)
                    
                    return result
                    
            except ConnectionError:
                # 连接错误，尝试重新连接
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.info(f"连接错误，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                logger.error(f"查询时发生异常: {str(e)}")
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.info(f"{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise
        
        raise Exception(f"查询失败，已达到最大重试次数({self.max_retries})")
    
    def close(self):
        """
        关闭管理器，清理资源
        """
        self.logout()
        logger.info("baostock连接管理器已关闭")
    
    @property
    def is_connected(self):
        """
        连接状态属性 - 兼容其他版本的连接管理器
        返回login_success的值，确保代码兼容性
        """
        return self.login_success

# 全局连接管理器实例
connection_manager = BaostockConnectionManager()

# 使用示例
def example_usage():
    """
    示例用法
    """
    try:
        # 初始化连接
        if not connection_manager.login():
            print("初始化连接失败")
            return
        
        # 方式1：使用上下文管理器
        with connection_manager.get_connection():
            rs = bs.query_stock_basic(code_name="平安银行")
            if rs.error_code == '0':
                while rs.next():
                    print(rs.get_row_data())
        
        # 方式2：使用execute_query方法
        rs = connection_manager.execute_query(
            bs.query_history_k_data_plus,
            "sz.000001",
            "date,open,close,high,low",
            start_date='2025-11-15',
            end_date='2025-11-19',
            frequency="d",
            adjustflag="2"
        )
        
        if rs.error_code == '0':
            while rs.next():
                print(rs.get_row_data())
                
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        # 确保登出
        connection_manager.close()

if __name__ == "__main__":
    example_usage()