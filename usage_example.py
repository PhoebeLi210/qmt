#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Baostock股票数据下载优化解决方案 - 使用示例

此脚本展示如何使用优化后的股票数据下载系统，包含以下功能：
1. 基本的全量下载
2. 增量更新
3. 断点续传
4. 缓存管理
5. 定时任务配置示例
"""

import os
import sys
import datetime
import subprocess
from baostock_connection_manager import connection_manager
from cache_manager import CacheManager

# 配置基本参数
DATA_DIR = "all_stock"
START_DATE = "2020-01-01"  # 默认起始日期
TODAY = datetime.date.today().strftime('%Y-%m-%d')


def run_full_download(start_date=START_DATE, end_date=TODAY):
    """
    执行全量下载
    """
    print(f"\n===== 执行全量下载（{start_date} 到 {end_date}）=====")
    cmd = [
        sys.executable,
        "optimized_stock_downloader.py",
        "--start-date", start_date,
        "--end-date", end_date,
        "--data-dir", DATA_DIR
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("全量下载完成!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"全量下载失败，错误码: {e.returncode}")
        return False


def run_incremental_update():
    """
    执行增量更新（只下载今天的数据）
    """
    today = TODAY
    print(f"\n===== 执行增量更新（{today}）=====")
    
    # 检查是否已有缓存数据
    cache_manager = CacheManager(data_dir=DATA_DIR)
    stock_count = len(cache_manager.metadata)
    
    if stock_count == 0:
        print("未发现缓存数据，将执行全量下载...")
        return run_full_download()
    
    print(f"发现 {stock_count} 支股票的缓存数据，将执行增量更新")
    
    cmd = [
        sys.executable,
        "optimized_stock_downloader.py",
        "--start-date", today,
        "--end-date", today,
        "--data-dir", DATA_DIR
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("增量更新完成!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"增量更新失败，错误码: {e.returncode}")
        return False


def resume_download():
    """
    继续之前中断的下载
    """
    print(f"\n===== 尝试断点续传 =====")
    
    # 检查是否有进度文件
    progress_file = os.path.join(DATA_DIR, "remaining_stocks.txt")
    if not os.path.exists(progress_file):
        print("未发现进度文件，将执行增量更新...")
        return run_incremental_update()
    
    cmd = [
        sys.executable,
        "optimized_stock_downloader.py",
        "--start-date", START_DATE,
        "--end-date", TODAY,
        "--data-dir", DATA_DIR,
        "--resume"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("断点续传完成!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"断点续传失败，错误码: {e.returncode}")
        return False


def validate_cache():
    """
    验证缓存完整性
    """
    print(f"\n===== 验证缓存完整性 =====")
    
    cache_manager = CacheManager(data_dir=DATA_DIR)
    integrity = cache_manager.validate_cache_integrity()
    
    print(f"\n缓存完整性报告:")
    print(f"- 元数据记录数: {integrity['total_metadata']}")
    print(f"- 实际文件数: {integrity['total_files']}")
    print(f"- 缺失文件数: {len(integrity['missing_files'])}")
    print(f"- 孤立文件数: {len(integrity['orphaned_files'])}")
    print(f"- 无效文件数: {len(integrity['invalid_files'])}")
    
    if integrity['suggestions']:
        print("\n建议操作:")
        for suggestion in integrity['suggestions']:
            print(f"  - {suggestion}")
    
    # 生成详细报告
    report = cache_manager.generate_cache_report()
    print(f"\n详细缓存报告已保存至: {os.path.join(DATA_DIR, 'cache_report.txt')}")
    
    # 如果有缺失或无效文件，提供修复选项
    if integrity['missing_files'] or integrity['invalid_files']:
        fix = input("\n是否要重新下载缺失/无效的文件？(y/n): ").lower()
        if fix == 'y':
            fix_missing_files(integrity['missing_files'] + integrity['invalid_files'])


def fix_missing_files(stock_codes):
    """
    修复缺失或无效的文件
    """
    print(f"\n===== 开始修复 {len(stock_codes)} 个文件 =====")
    
    # 临时保存要修复的股票列表
    fix_file = os.path.join(DATA_DIR, "fix_stocks.txt")
    with open(fix_file, 'w') as f:
        for code in stock_codes:
            f.write(f"{code}\n")
    
    # 修改下载器以支持只下载指定股票
    # 这里简化处理，实际应用中可以扩展下载器支持过滤功能
    print(f"已保存需要修复的股票列表到 {fix_file}")
    print("建议：使用该列表配合下载器进行针对性修复")


def show_cache_statistics():
    """
    显示缓存统计信息
    """
    print(f"\n===== 缓存统计信息 =====")
    
    cache_manager = CacheManager(data_dir=DATA_DIR)
    stats = cache_manager.get_cache_statistics()
    
    print(f"- 缓存的股票总数: {stats['total_cached']}")
    print(f"- 缓存总大小: {stats['total_size_mb']:.2f} MB ({stats['total_size_gb']:.2f} GB)")
    print(f"- 缓存总记录数: {stats['total_records']:,}")
    
    if "avg_cache_age_days" in stats:
        print(f"- 平均缓存年龄: {stats['avg_cache_age_days']:.1f} 天")
    
    if stats["last_updated_stocks"]:
        print("\n最近更新的股票:")
        for i, stock_info in enumerate(stats["last_updated_stocks"], 1):
            print(f"  {i}. {stock_info['stock_code']}: "
                  f"{stock_info['update_time'].strftime('%Y-%m-%d %H:%M:%S')}")


def check_baostock_connection():
    """
    检查baostock连接状态
    """
    print(f"\n===== 检查baostock连接状态 =====")
    
    try:
        # 初始化连接
        if connection_manager.login():
            print("✅ baostock连接成功!")
            
            # 测试一个简单的查询
            import baostock as bs
            rs = bs.query_stock_basic(code_name="平安银行")
            if rs.error_code == '0':
                print("✅ 数据查询测试成功")
            else:
                print(f"❌ 数据查询测试失败: {rs.error_msg}")
            
            # 登出
            connection_manager.logout()
            return True
        else:
            print("❌ baostock连接失败")
            return False
    except Exception as e:
        print(f"❌ 连接测试时发生异常: {str(e)}")
        return False


def show_crontab_example():
    """
    显示Linux定时任务配置示例
    """
    print(f"\n===== Linux定时任务配置示例 =====")
    
    crontab_example = """
# 每天下午3:30自动执行增量更新（推荐使用）
30 15 * * * cd /path/to/chaogu && python usage_example.py --update

# 每周一早上8:00执行缓存验证
0 8 * * 1 cd /path/to/chaogu && python usage_example.py --validate

# 每月1日凌晨2:00执行全量下载（如果需要）
0 2 1 * * cd /path/to/chaogu && python usage_example.py --full

# 每天下午4:00执行断点续传（处理可能的中断）
0 16 * * * cd /path/to/chaogu && python usage_example.py --resume
    """
    
    print(crontab_example)
    print("使用方法：")
    print("1. 运行 'crontab -e' 编辑定时任务")
    print("2. 复制上面的示例，修改路径为实际项目路径")
    print("3. 保存并退出编辑器")


def print_usage():
    """
    打印使用帮助
    """
    usage = """
Baostock股票数据下载优化解决方案 - 使用示例

用法: python usage_example.py [选项]

选项:
  --help              显示此帮助信息
  --full              执行全量下载（从起始日期到今天）
  --update            执行增量更新（只下载今天的数据）
  --resume            继续之前中断的下载
  --validate          验证缓存完整性
  --stats             显示缓存统计信息
  --test              测试baostock连接
  --cron              显示Linux定时任务配置示例

示例:
  # 执行增量更新（推荐日常使用）
  python usage_example.py --update
  
  # 验证缓存完整性
  python usage_example.py --validate
  
  # 测试连接
  python usage_example.py --test
    """
    print(usage)


def main():
    """
    主函数
    """
    # 检查参数
    if len(sys.argv) <= 1:
        print_usage()
        return
    
    # 根据参数执行不同操作
    if "--help" in sys.argv:
        print_usage()
    elif "--full" in sys.argv:
        run_full_download()
    elif "--update" in sys.argv:
        run_incremental_update()
    elif "--resume" in sys.argv:
        resume_download()
    elif "--validate" in sys.argv:
        validate_cache()
    elif "--stats" in sys.argv:
        show_cache_statistics()
    elif "--test" in sys.argv:
        check_baostock_connection()
    elif "--cron" in sys.argv:
        show_crontab_example()
    else:
        print("未知选项!")
        print_usage()


if __name__ == "__main__":
    main()