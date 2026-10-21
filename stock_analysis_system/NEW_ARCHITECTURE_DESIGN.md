# 股票分析系统新架构设计

## 1. 架构目标

- **稳定性优先**：确保程序不会因单个股票的数据问题而卡住
- **简化并发**：使用更可靠的并发模型，避免死锁
- **强错误处理**：完善的编码错误和连接错误处理
- **可调试性**：详细的日志记录，便于问题定位
- **高性能**：优化的数据获取和缓存策略

## 2. 核心架构设计

### 2.1 模块化设计

| 模块 | 功能 | 设计要点 |
|------|------|----------|
| `main.py` | 程序入口 | 单线程控制流程，避免复杂的多线程协调 |
| `data_collector.py` | 数据采集 | 简化并发模型，使用队列+单线程处理 |
| `connection_manager.py` | 连接管理 | 自动重试+连接重置机制 |
| `cache_manager.py` | 缓存管理 | 智能缓存策略，减少重复请求 |
| `data_analyzer.py` | 数据分析 | 单线程处理，避免并发问题 |
| `logger.py` | 日志系统 | 结构化日志，详细的错误信息 |
| `config.py` | 配置管理 | 集中配置，便于调整参数 |

### 2.2 核心流程设计

```
1. 初始化配置和日志
2. 加载股票列表
3. 遍历股票列表（单线程）
   a. 检查缓存
   b. 获取实时行情数据
   c. 获取历史数据
   d. 获取财务数据
   e. 保存到数据库
4. 执行数据分析
5. 生成报告
```

### 2.3 并发模型设计

- **单线程遍历股票列表**：避免复杂的线程协调
- **异步数据获取**：每个股票内部使用异步IO获取数据
- **连接池管理**：统一的连接池，避免频繁创建连接
- **超时机制**：所有网络请求都设置超时

### 2.4 错误处理设计

- **编码错误**：立即跳过当前股票，记录错误，继续处理下一只
- **连接错误**：自动重试+连接重置，最多重试3次
- **超时错误**：跳过当前请求，尝试其他数据源
- **数据为空**：跳过当前股票，继续处理下一只

## 3. 关键模块设计

### 3.1 数据采集模块

```python
class DataCollector:
    def __init__(self):
        self.connection_manager = ConnectionManager()
        self.cache_manager = CacheManager()
        
    def get_stock_data(self, symbol):
        """获取单只股票的完整数据"""
        # 检查缓存
        cached_data = self.cache_manager.get_cached_data(symbol)
        if cached_data:
            return cached_data
        
        # 获取数据（带超时和重试）
        try:
            # 获取实时行情
            real_time_data = self.get_real_time_data(symbol)
            # 获取历史数据
            history_data = self.get_history_data(symbol)
            # 获取财务数据
            financial_data = self.get_financial_data(symbol)
            
            # 合并数据
            data = self.merge_data(real_time_data, history_data, financial_data)
            
            # 保存缓存
            self.cache_manager.save_data(symbol, data)
            
            return data
        except Exception as e:
            logger.error(f"获取股票{symbol}数据失败: {e}")
            return None
```

### 3.2 连接管理模块

```python
class ConnectionManager:
    def __init__(self):
        self.connections = {}
        self.max_retries = 3
        
    def get_connection(self, service):
        """获取连接，自动处理连接错误"""
        for attempt in range(self.max_retries):
            try:
                if service not in self.connections or not self._is_healthy(self.connections[service]):
                    self.connections[service] = self._create_connection(service)
                return self.connections[service]
            except Exception as e:
                logger.error(f"创建{service}连接失败 (尝试{attempt+1}/{self.max_retries}): {e}")
                time.sleep(1 * (attempt + 1))  # 指数退避
        return None
    
    def _is_healthy(self, connection):
        """检查连接健康状态"""
        # 实现连接健康检查逻辑
        return True
    
    def _create_connection(self, service):
        """创建新连接"""
        # 实现具体的连接创建逻辑
        pass
```

### 3.3 缓存管理模块

```python
class CacheManager:
    def __init__(self):
        self.cache_dir = "cache"
        self.cache_expiry = 3600  # 缓存有效期（秒）
        
    def get_cached_data(self, symbol):
        """获取缓存数据"""
        # 实现缓存读取逻辑
        pass
    
    def save_data(self, symbol, data):
        """保存数据到缓存"""
        # 实现缓存保存逻辑
        pass
```

### 3.4 日志系统设计

```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, name, level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # 配置控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 配置文件输出
        file_handler = logging.FileHandler(f"logs/{name}_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler.setLevel(level)
        
        # 结构化日志格式
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def info(self, message, **kwargs):
        self.logger.info(self._format_message(message, **kwargs))
    
    def error(self, message, **kwargs):
        self.logger.error(self._format_message(message, **kwargs))
    
    def warning(self, message, **kwargs):
        self.logger.warning(self._format_message(message, **kwargs))
    
    def _format_message(self, message, **kwargs):
        if kwargs:
            return f"{message} | {json.dumps(kwargs, ensure_ascii=False)}"
        return message
```

## 4. 实现计划

1. **优先实现核心模块**：logger.py → config.py → connection_manager.py → cache_manager.py
2. **重构数据采集模块**：简化并发，增强错误处理
3. **重构主程序**：单线程控制流程，避免复杂的多线程协调
4. **优化数据分析模块**：单线程处理，避免并发问题
5. **测试和验证**：全面测试各种错误场景

## 5. 预期效果

- **程序不会卡住**：单个股票的数据问题不会影响整体运行
- **错误处理完善**：编码错误和连接错误能被正确处理
- **调试方便**：详细的结构化日志，便于问题定位
- **性能优化**：智能缓存策略，减少重复请求
- **代码可维护性**：模块化设计，便于扩展和修改