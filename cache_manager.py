import os
import json
import logging
import pandas as pd
import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CacheManager')

class CacheManager:
    """
    股票数据缓存管理器
    负责智能缓存控制、避免重复下载、缓存元数据管理等功能
    """
    
    def __init__(self, data_dir="all_stock", meta_file="cache_metadata.json"):
        """
        初始化缓存管理器
        :param data_dir: 数据缓存目录
        :param meta_file: 元数据文件名
        """
        self.data_dir = data_dir
        self.meta_file = os.path.join(data_dir, meta_file)
        self.metadata = {}
        self._ensure_directory()
        self._load_metadata()
    
    def _ensure_directory(self):
        """
        确保数据目录存在
        """
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            logger.info(f"创建缓存目录: {self.data_dir}")
    
    def _load_metadata(self):
        """
        加载缓存元数据
        """
        if os.path.exists(self.meta_file):
            try:
                with open(self.meta_file, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f"成功加载缓存元数据，包含 {len(self.metadata)} 条记录")
            except Exception as e:
                logger.error(f"加载缓存元数据失败: {str(e)}")
                self.metadata = {}
    
    def _save_metadata(self):
        """
        保存缓存元数据
        """
        try:
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.debug(f"成功保存缓存元数据")
        except Exception as e:
            logger.error(f"保存缓存元数据失败: {str(e)}")
    
    def get_file_path(self, stock_code, file_extension=".csv"):
        """
        获取股票数据文件路径
        :param stock_code: 股票代码
        :param file_extension: 文件扩展名
        :return: 文件路径
        """
        return os.path.join(self.data_dir, f"{stock_code}{file_extension}")
    
    def is_cached(self, stock_code):
        """
        检查股票数据是否已缓存
        :param stock_code: 股票代码
        :return: 是否已缓存
        """
        return stock_code in self.metadata
    
    def get_cache_info(self, stock_code):
        """
        获取股票缓存信息
        :param stock_code: 股票代码
        :return: 缓存信息字典
        """
        return self.metadata.get(stock_code, {})
    
    def update_cache_info(self, stock_code, **kwargs):
        """
        更新股票缓存信息
        :param stock_code: 股票代码
        :param kwargs: 要更新的缓存信息
        """
        if stock_code not in self.metadata:
            self.metadata[stock_code] = {
                "first_downloaded": datetime.datetime.now().isoformat(),
                "file_size": 0,
                "record_count": 0,
                "last_update": None,
                "last_date": None
            }
        
        # 更新缓存信息
        self.metadata[stock_code].update({
            "last_update": datetime.datetime.now().isoformat(),
            **kwargs
        })
        
        # 保存元数据
        self._save_metadata()
    
    def check_need_update(self, stock_code, target_date):
        """
        智能检查是否需要更新缓存
        :param stock_code: 股票代码
        :param target_date: 目标日期
        :return: 需要更新的开始日期，如果不需要更新则返回None
        """
        # 确保日期格式正确
        if isinstance(target_date, str):
            target_date = datetime.datetime.strptime(target_date, '%Y-%m-%d').date()
        elif isinstance(target_date, datetime.datetime):
            target_date = target_date.date()
        
        # 检查是否存在缓存
        if not self.is_cached(stock_code):
            logger.debug(f"{stock_code} 无缓存记录，需要完整下载")
            return None  # 表示需要完整下载
        
        # 检查文件是否存在
        file_path = self.get_file_path(stock_code)
        if not os.path.exists(file_path):
            logger.warning(f"{stock_code} 元数据存在但文件不存在，需要重新下载")
            # 从元数据中移除
            if stock_code in self.metadata:
                del self.metadata[stock_code]
                self._save_metadata()
            return None
        
        # 获取缓存信息
        cache_info = self.get_cache_info(stock_code)
        
        # 检查缓存的最后日期
        if "last_date" not in cache_info or not cache_info["last_date"]:
            # 缓存信息不完整，需要重新检查文件
            try:
                df = pd.read_csv(file_path)
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    last_date = df['date'].max().date()
                    
                    # 更新元数据
                    self.update_cache_info(
                        stock_code,
                        last_date=last_date.isoformat(),
                        record_count=len(df),
                        file_size=os.path.getsize(file_path)
                    )
                    
                    # 检查是否需要更新
                    if last_date >= target_date:
                        logger.debug(f"{stock_code} 数据已是最新 (最后日期: {last_date})")
                        return "SKIP"  # 不需要更新
                    
                    # 计算需要更新的开始日期
                    next_date = (last_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                    logger.debug(f"{stock_code} 需要更新，从 {next_date} 开始")
                    return next_date
            except Exception as e:
                logger.warning(f"检查 {stock_code} 文件内容失败: {str(e)}，需要重新下载")
                return None
        else:
            # 使用缓存的最后日期
            last_date_str = cache_info["last_date"]
            try:
                # 处理不同格式的日期字符串
                if isinstance(last_date_str, str):
                    if 'T' in last_date_str:  # ISO格式
                        last_date = datetime.datetime.fromisoformat(last_date_str).date()
                    else:
                        last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()
                else:
                    last_date = datetime.date.today()
                
                # 检查是否需要更新
                if last_date >= target_date:
                    logger.debug(f"{stock_code} 数据已是最新 (最后日期: {last_date})")
                    return "SKIP"  # 不需要更新
                
                # 计算需要更新的开始日期
                next_date = (last_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                logger.debug(f"{stock_code} 需要更新，从 {next_date} 开始")
                return next_date
            except Exception as e:
                logger.warning(f"解析 {stock_code} 缓存日期失败: {str(e)}")
                return None
    
    def update_after_download(self, stock_code, df, append_mode=False):
        """
        下载后更新缓存信息
        :param stock_code: 股票代码
        :param df: 下载的数据DataFrame
        :param append_mode: 是否为追加模式
        """
        file_path = self.get_file_path(stock_code)
        
        try:
            # 获取文件信息
            file_size = os.path.getsize(file_path)
            
            # 获取最后日期
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                last_date = df['date'].max().date()
                
                # 如果是追加模式，获取总记录数
                if append_mode:
                    total_df = pd.read_csv(file_path)
                    record_count = len(total_df)
                else:
                    record_count = len(df)
                
                # 更新缓存信息
                self.update_cache_info(
                    stock_code,
                    last_date=last_date.isoformat(),
                    record_count=record_count,
                    file_size=file_size,
                    append_mode=append_mode
                )
                
                logger.debug(f"更新 {stock_code} 缓存信息: 最后日期={last_date}, 记录数={record_count}")
        except Exception as e:
            logger.error(f"更新 {stock_code} 缓存信息失败: {str(e)}")
    
    def get_cache_statistics(self):
        """
        获取缓存统计信息
        :return: 统计信息字典
        """
        stats = {
            "total_cached": len(self.metadata),
            "total_size_bytes": 0,
            "total_records": 0,
            "last_updated_stocks": [],
            "oldest_cached": None
        }
        
        # 计算统计信息
        now = datetime.datetime.now()
        oldest_date = now
        
        for stock_code, info in self.metadata.items():
            # 累加文件大小
            if "file_size" in info:
                stats["total_size_bytes"] += info["file_size"]
            
            # 累加记录数
            if "record_count" in info:
                stats["total_records"] += info["record_count"]
            
            # 找出最近更新的股票
            if "last_update" in info:
                update_time = datetime.datetime.fromisoformat(info["last_update"])
                if len(stats["last_updated_stocks"]) < 5:
                    stats["last_updated_stocks"].append({
                        "stock_code": stock_code,
                        "update_time": update_time
                    })
                elif update_time > stats["last_updated_stocks"][-1]["update_time"]:
                    # 替换最新的5个中的最旧的
                    stats["last_updated_stocks"].sort(key=lambda x: x["update_time"], reverse=True)
                    stats["last_updated_stocks"].pop()
                    stats["last_updated_stocks"].append({
                        "stock_code": stock_code,
                        "update_time": update_time
                    })
            
            # 找出最旧的缓存
            if "first_downloaded" in info:
                first_time = datetime.datetime.fromisoformat(info["first_downloaded"])
                if first_time < oldest_date:
                    oldest_date = first_time
                    stats["oldest_cached"] = {
                        "stock_code": stock_code,
                        "first_downloaded": first_time
                    }
        
        # 排序最近更新的股票
        stats["last_updated_stocks"].sort(key=lambda x: x["update_time"], reverse=True)
        
        # 格式化统计信息
        stats["total_size_mb"] = stats["total_size_bytes"] / (1024 * 1024)
        stats["total_size_gb"] = stats["total_size_bytes"] / (1024 * 1024 * 1024)
        
        # 计算平均缓存年龄
        if oldest_date != now:
            avg_age_days = (now - oldest_date).total_seconds() / (24 * 3600)
            stats["avg_cache_age_days"] = avg_age_days
        
        return stats
    
    def clean_expired_cache(self, days_threshold=365):
        """
        清理过期的缓存数据
        :param days_threshold: 缓存保留天数阈值
        :return: 清理的文件数量
        """
        cleaned_count = 0
        expired_date = datetime.datetime.now() - datetime.timedelta(days=days_threshold)
        
        logger.info(f"开始清理 {days_threshold} 天前的缓存数据")
        
        # 找出过期的缓存
        expired_stocks = []
        for stock_code, info in self.metadata.items():
            if "last_update" in info:
                last_update = datetime.datetime.fromisoformat(info["last_update"])
                if last_update < expired_date:
                    expired_stocks.append(stock_code)
        
        # 清理过期文件
        for stock_code in expired_stocks:
            file_path = self.get_file_path(stock_code)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.debug(f"已清理过期缓存: {stock_code}")
                except Exception as e:
                    logger.error(f"清理 {stock_code} 缓存失败: {str(e)}")
            
            # 从元数据中移除
            if stock_code in self.metadata:
                del self.metadata[stock_code]
        
        # 保存更新后的元数据
        if expired_stocks:
            self._save_metadata()
        
        logger.info(f"清理完成，共删除 {cleaned_count} 个过期缓存文件")
        return cleaned_count
    
    def validate_cache_integrity(self):
        """
        验证缓存完整性，检查元数据和实际文件是否一致
        :return: 完整性报告字典
        """
        report = {
            "total_metadata": len(self.metadata),
            "total_files": 0,
            "missing_files": [],
            "orphaned_files": [],
            "invalid_files": []
        }
        
        logger.info("开始验证缓存完整性")
        
        # 检查元数据中的文件是否存在
        for stock_code in self.metadata:
            file_path = self.get_file_path(stock_code)
            if not os.path.exists(file_path):
                report["missing_files"].append(stock_code)
            
        # 检查目录中的CSV文件
        csv_files = [f for f in os.listdir(self.data_dir) if f.endswith('.csv')]
        report["total_files"] = len(csv_files)
        
        for csv_file in csv_files:
            stock_code = csv_file[:-4]  # 移除.csv扩展名
            
            # 检查是否有对应的元数据
            if stock_code not in self.metadata:
                report["orphaned_files"].append(stock_code)
            else:
                # 检查文件是否有效
                file_path = self.get_file_path(stock_code)
                try:
                    df = pd.read_csv(file_path)
                    # 检查必要的列
                    if 'date' not in df.columns or 'code' not in df.columns:
                        report["invalid_files"].append(stock_code)
                except Exception as e:
                    logger.warning(f"验证 {stock_code} 文件内容失败: {str(e)}")
                    report["invalid_files"].append(stock_code)
        
        # 生成修复建议
        report["suggestions"] = []
        if report["missing_files"]:
            report["suggestions"].append(f"有 {len(report['missing_files'])} 个文件在元数据中但实际不存在，建议重新下载")
        if report["orphaned_files"]:
            report["suggestions"].append(f"有 {len(report['orphaned_files'])} 个文件无对应的元数据，建议重建元数据")
        if report["invalid_files"]:
            report["suggestions"].append(f"有 {len(report['invalid_files'])} 个文件格式无效，建议重新下载")
        
        logger.info(f"缓存完整性验证完成: 元数据 {report['total_metadata']}, 文件 {report['total_files']}, "
                  f"缺失 {len(report['missing_files'])}, 孤立 {len(report['orphaned_files'])}, 无效 {len(report['invalid_files'])}")
        
        return report
    
    def rebuild_metadata(self):
        """
        重建元数据
        :return: 重建的元数据数量
        """
        logger.info("开始重建缓存元数据")
        
        # 清空现有元数据
        self.metadata = {}
        
        # 获取所有CSV文件
        csv_files = [f for f in os.listdir(self.data_dir) if f.endswith('.csv')]
        logger.info(f"找到 {len(csv_files)} 个CSV文件")
        
        # 逐个处理文件
        processed_count = 0
        for csv_file in csv_files:
            stock_code = csv_file[:-4]  # 移除.csv扩展名
            file_path = self.get_file_path(stock_code)
            
            try:
                # 读取文件信息
                df = pd.read_csv(file_path)
                file_size = os.path.getsize(file_path)
                
                # 获取最后日期
                last_date = None
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    last_date = df['date'].max().date().isoformat()
                
                # 添加到元数据
                self.metadata[stock_code] = {
                    "first_downloaded": datetime.datetime.now().isoformat(),
                    "last_update": datetime.datetime.now().isoformat(),
                    "last_date": last_date,
                    "file_size": file_size,
                    "record_count": len(df)
                }
                
                processed_count += 1
                
                # 进度报告
                if processed_count % 100 == 0 or processed_count == len(csv_files):
                    logger.info(f"已处理 {processed_count}/{len(csv_files)} 个文件")
                    
            except Exception as e:
                logger.warning(f"处理 {stock_code} 文件失败: {str(e)}")
        
        # 保存重建的元数据
        self._save_metadata()
        
        logger.info(f"元数据重建完成，成功处理 {processed_count} 个文件")
        return processed_count
    
    def generate_cache_report(self, report_file="cache_report.txt"):
        """
        生成缓存报告
        :param report_file: 报告文件名
        :return: 报告内容
        """
        # 获取统计信息
        stats = self.get_cache_statistics()
        
        # 获取完整性报告
        integrity = self.validate_cache_integrity()
        
        # 生成报告内容
        report_lines = [
            f"=== 股票数据缓存报告 ===",
            f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"缓存目录: {self.data_dir}",
            f"\n--- 统计信息 ---",
            f"缓存的股票总数: {stats['total_cached']}",
            f"缓存总大小: {stats['total_size_mb']:.2f} MB ({stats['total_size_gb']:.2f} GB)",
            f"缓存总记录数: {stats['total_records']:,}",
        ]
        
        # 添加平均缓存年龄
        if "avg_cache_age_days" in stats:
            report_lines.append(f"平均缓存年龄: {stats['avg_cache_age_days']:.1f} 天")
        
        # 添加最近更新的股票
        if stats["last_updated_stocks"]:
            report_lines.append(f"\n--- 最近更新的股票 ---")
            for i, stock_info in enumerate(stats["last_updated_stocks"], 1):
                report_lines.append(f"{i}. {stock_info['stock_code']}: "
                                   f"{stock_info['update_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 添加完整性报告
        report_lines.append(f"\n--- 完整性检查 --- ")
        report_lines.append(f"元数据记录数: {integrity['total_metadata']}")
        report_lines.append(f"实际文件数: {integrity['total_files']}")
        report_lines.append(f"缺失文件数: {len(integrity['missing_files'])}")
        report_lines.append(f"孤立文件数: {len(integrity['orphaned_files'])}")
        report_lines.append(f"无效文件数: {len(integrity['invalid_files'])}")
        
        # 添加建议
        if integrity["suggestions"]:
            report_lines.append(f"\n--- 建议 ---")
            for suggestion in integrity["suggestions"]:
                report_lines.append(f"- {suggestion}")
        
        # 添加使用提示
        report_lines.append(f"\n--- 使用提示 ---")
        report_lines.append(f"1. 定期运行验证以确保缓存完整性")
        report_lines.append(f"2. 对长期未使用的数据进行清理")
        report_lines.append(f"3. 如发现大量缺失或无效文件，考虑重新下载数据")
        
        # 组合报告内容
        report_content = "\n".join(report_lines)
        
        # 保存报告文件
        report_path = os.path.join(self.data_dir, report_file)
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"缓存报告已保存至: {report_path}")
        except Exception as e:
            logger.error(f"保存缓存报告失败: {str(e)}")
        
        return report_content

# 示例用法
def example_usage():
    """
    缓存管理器示例用法
    """
    # 创建缓存管理器实例
    cache_manager = CacheManager(data_dir="all_stock")
    
    # 检查是否需要更新
    need_start_date = cache_manager.check_need_update("sh.600000", datetime.date.today())
    if need_start_date == "SKIP":
        print("数据已是最新，不需要更新")
    elif need_start_date:
        print(f"需要更新，从 {need_start_date} 开始")
    else:
        print("需要完整下载")
    
    # 生成缓存报告
    report = cache_manager.generate_cache_report()
    print(report)
    
    # 验证缓存完整性
    integrity = cache_manager.validate_cache_integrity()
    print(f"缓存验证: 发现 {len(integrity['invalid_files'])} 个无效文件")
    
    # 清理过期缓存
    # cache_manager.clean_expired_cache(days_threshold=180)
    
    # 重建元数据
    # cache_manager.rebuild_metadata()

if __name__ == "__main__":
    example_usage()