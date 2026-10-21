#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票交易量化系统

功能：
1. 从实时数据源采集全部A股市场股票数据（包括深、沪主板股票，科创板，创业板，去除ST股票）
2. 根据上涨趋势或者触底反弹K线形态选取股票
3. 对选取的股票进行基本面、技术面数据分析
4. 输出当日购买股票推荐清单（动态数量：根据分析股票总数确定5-15只）
"""

import os
import sys

# 禁止向系统Python目录写入.pyc字节码缓存（沙箱环境拦截会导致退出码1）
# 必须在导入pandas/akshare等重型库之前设置
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

import time
import logging
from datetime import datetime

# 设置系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入系统模块
from data_collector_optimized import OptimizedStockDataCollector
from stock_selector import StockSelector
from stock_analyzer import StockAnalyzer
from recommendation_engine import RecommendationEngine
from utils.logger import setup_logger

# 配置日志
logger = setup_logger('main', logging.DEBUG)


def generate_recommendation_report(recommendations):
    """生成推荐报告文件"""
    if not recommendations:
        return
    
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    today = datetime.now().strftime('%Y-%m-%d')
    report_filename = os.path.join(reports_dir, f'股票推荐报告_{today}.txt')
    
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + '\n')
            f.write(f"股票购买推荐报告\n")
            f.write(f"生成日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + '\n')
            
            f.write(f"共推荐 {len(recommendations)} 只股票\n")

            # v2.5 防守市提示
            regime = recommendations[0].get('market_regime') if recommendations else None
            if regime == 'risk_off':
                f.write("\n" + "!" * 60 + "\n")
                f.write("【大盘 risk_off 警告】上证跌破20日线且RSI<35，系统性风险高\n")
                f.write("本批为防守限流清单：信号门槛55、剔除反转型形态、仓位×0.5\n")
                f.write("!" * 60 + "\n")
            elif regime in ('bear', 'neutral'):
                f.write(f"\n[大盘择时: {regime}，仓位已×{0.7 if regime=='neutral' else 0.5}]\n\n")
            else:
                f.write("\n")

            for i, stock in enumerate(recommendations, 1):
                latest_price = stock.get('latest_price', 0.0)
                change_pct = stock.get('change_pct', 0.0)
                pattern = stock.get('pattern', '未识别')
                score = stock.get('score', 0.0)
                recommendation_reason = stock.get('recommendation_reason', '无推荐理由')

                price_str = f"{latest_price:.2f} 元" if latest_price > 0 else "数据缺失"
                change_str = f"{change_pct:.2f}%" if change_pct != 0 else "数据缺失"

                f.write(f"{i}. {stock['code']} - {stock['name']}\n")
                f.write(f"   价格: {price_str}\n")
                f.write(f"   涨幅: {change_str}\n")
                f.write(f"   形态: {pattern}\n")
                f.write(f"   评分: {score:.2f} 分\n")
                # 添加板块分类信息
                if stock.get('market_segment'):
                    f.write(f"   板块: {stock['market_segment']}\n")
                if stock.get('industry'):
                    f.write(f"   行业: {stock['industry']}\n")
                if stock.get('concept'):
                    f.write(f"   概念: {stock['concept']}\n")
                f.write(f"   推荐理由: {recommendation_reason}\n")
                # 添加仓位建议
                position_sizing = stock.get('position_sizing', '未提供')
                f.write(f"   仓位建议: {position_sizing}\n")
                # 止损止盈策略（v2新增）
                stop_loss = stock.get('stop_loss', '')
                take_profit = stock.get('take_profit', '')
                time_stop = stock.get('time_stop', '')
                if stop_loss:
                    f.write(f"   止损位: {stop_loss}\n")
                if take_profit:
                    f.write(f"   止盈位: {take_profit}\n")
                if time_stop:
                    f.write(f"   时间止损: {time_stop}\n")
                f.write("-" * 40 + '\n')
            
            f.write("\n" + "=" * 60 + "\n")
            f.write("次日分时验证要点（盘后选股 → 次日开盘验证清单）：\n")
            f.write("1. 开盘位置：高开>2%需警惕透支，低开>1%则放弃；平开或微幅高开0.5%-1.5%最佳\n")
            f.write("2. 首30分钟量价：观察是否放量（量比较昨日同时段>1.2），不放量则延迟介入\n")
            f.write("3. 分时回踩：若开盘后回踩昨日收盘价或5日线附近企稳，为较佳低吸点\n")
            f.write("4. 大盘开盘：若上证低开>0.5%，先观望30分钟再决策\n")
            f.write("5. 涨停板不追：若集合竞价已涨停，放弃该标的\n")
            f.write("\n风险提示：\n")
            f.write("1. 以上推荐基于历史数据和量化模型分析，仅供参考，不构成投资建议\n")
            f.write("2. 本系统已增加追高风险控制，过滤了以下股票：\n")
            f.write("   - 3日内累计涨幅超过15%的股票\n")
            f.write("   - RSI指标≥70的超买股票\n")
            f.write("   - 收盘价偏离5日均线超过8%的股票\n")
            f.write("3. 市场有风险，投资需谨慎。请结合自身风险承受能力做出投资决策\n")
            f.write("4. 建议设置合理的止盈止损位，避免盲目追高\n")
            f.write("5. 短期交易存在较高风险，请理性投资\n")
        
        logger.info(f"推荐报告已生成: {report_filename}")
        print(f"\n推荐报告已生成: {report_filename}")

        # 同步写入 Web 展示层数据库（可选组件：webapp 缺失或失败不影响扫描主流程）
        try:
            from webapp.db import init_db, save_daily_recommendations
            init_db()
            save_daily_recommendations(today, recommendations)
            logger.info("推荐清单已同步到 Web 数据库")
        except Exception as e:
            logger.debug(f"推荐清单同步 Web 数据库跳过: {str(e)}")

    except Exception as e:
        logger.warning(f"生成推荐报告失败: {str(e)}")


def main():
    """系统主函数"""
    try:
        logger.info("=== 股票交易量化系统启动 ===")
        start_time = time.time()
        
        # 1. 数据采集 - 获取A股市场全部数据进行分析
        logger.info("1. 开始采集股票数据...")
        collector = OptimizedStockDataCollector()
        logger.info("   正在获取A股市场全部股票数据...")
        stock_list = collector.get_all_stocks()  # 获取全部股票数据
        logger.info(f"   ✓ 数据采集完成: 共采集到 {len(stock_list)} 只股票数据")
        
        # 2. 股票筛选（根据K线形态）
        logger.info("2. 开始根据K线形态筛选股票...")
        selector = StockSelector(stock_list)
        selected_stocks = selector.select_by_kline_pattern()
        logger.info(f"   ✓ 形态筛选完成: 筛选出 {len(selected_stocks)} 只符合形态的股票 (筛选率: {len(selected_stocks)/len(stock_list)*100:.1f}%)")
        
        if not selected_stocks:
            logger.warning("未筛选出符合条件的股票")
            return
        
        # 3. 股票分析（基本面和技术面）
        logger.info("3. 开始进行基本面和技术面分析...")
        # 3.1 填充资金流+筹码因子（参与评分）
        try:
            from webapp.lab.holdings import enrich_stocks_with_fund_chip
            enrich_stocks_with_fund_chip(selected_stocks)
            logger.info("   ✓ 资金流+筹码因子已填充")
        except Exception as e:
            logger.warning(f"资金流/筹码因子填充失败，评分将使用中性值: {e}")
        analyzer = StockAnalyzer(selected_stocks)
        analyzed_stocks = analyzer.analyze_stocks()
        logger.info(f"   ✓ 股票分析完成: 完成 {len(analyzed_stocks)} 只股票的分析 (分析通过率: {len(analyzed_stocks)/len(selected_stocks)*100:.1f}%)")

        # v2.5 防守市信号门槛提升（lab归因2026-10：risk_off/bear下<55分信号胜率<10%）
        # 只影响全市场扫描信号与推荐；自选分析路径不经过此处，不受影响
        try:
            from market_timing import get_market_regime, DEFENSIVE_REGIMES
            _regime = get_market_regime()
            if _regime in DEFENSIVE_REGIMES and analyzed_stocks:
                _before = len(analyzed_stocks)
                analyzed_stocks = [s for s in analyzed_stocks
                                   if (s.get('final_score') or 0) >= 55]
                logger.info(f"   防守市({_regime})信号门槛提升至55: {_before} -> {len(analyzed_stocks)} 只")
        except Exception as _e:
            logger.debug(f"防守市门槛检查跳过: {_e}")

        if not analyzed_stocks:
            logger.warning("未分析出符合条件的股票")
            return
        
        # 4. 生成推荐清单
        logger.info("4. 开始生成股票推荐清单...")
        engine = RecommendationEngine(analyzed_stocks)
        recommendations = engine.generate_recommendations()
        logger.info(f"   生成了 {len(recommendations)} 只推荐股票")

        # 4.5 自优化实验室：全候选信号（含未推荐）结构化落库，供胜率追踪
        try:
            from webapp.lab.capture import capture_full_scan
            from webapp.db import init_db as _init_web_db
            _init_web_db()
            capture_full_scan(datetime.now().strftime('%Y-%m-%d'),
                              analyzed_stocks, recommendations, engine)
        except Exception as e:
            logger.debug(f"lab 信号落库跳过: {str(e)}")

        # 5. 输出结果
        logger.info("5. 输出结果...")
        output_recommendations(recommendations)
        
        # 6. 最终统计汇总
        end_time = time.time()
        total_time = end_time - start_time
        
        logger.info("="*60)
        logger.info("=== 系统运行统计汇总 ===")
        logger.info(f"总耗时: {total_time:.2f} 秒")
        logger.info(f"数据采集: {len(stock_list)} 只股票")
        logger.info(f"形态筛选: {len(selected_stocks)} 只 (筛选率: {len(selected_stocks)/len(stock_list)*100:.1f}%)")
        logger.info(f"股票分析: {len(analyzed_stocks)} 只 (分析率: {len(analyzed_stocks)/len(selected_stocks)*100:.1f}%)")
        logger.info(f"最终推荐: {len(recommendations)} 只 (推荐率: {len(recommendations)/len(analyzed_stocks)*100:.1f}%)")
        logger.info(f"=== 系统运行完成 ===")
        logger.info("="*60)
        
    except Exception as e:
        logger.warning(f"系统运行错误: {str(e)}")
        sys.exit(1)


def output_recommendations(recommendations):
    """输出推荐结果并生成专门的推荐报告文件"""
    if not recommendations:
        print("\n当日无推荐股票")
        return
    
    # 保持推荐引擎输出的顺序（低风险优先 → 中等风险 → 高风险，组内按多维度评分排序）
    # 不再截断为10只，推荐数量由引擎根据分析股票总数动态确定（5-15只）
    sorted_recommendations = recommendations
    
    # 输出到控制台
    print("\n" + "="*60)
    print(f"股票购买推荐清单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print(f"共推荐 {len(sorted_recommendations)} 只股票：")

    # v2.5 防守市醒目提示
    regime = sorted_recommendations[0].get('market_regime') if sorted_recommendations else None
    if regime == 'risk_off':
        print("!" * 60)
        print("【大盘 risk_off 警告】上证跌破20日线且RSI<35，系统性风险高")
        print("本批为防守限流清单：信号门槛55、剔除反转型形态、仓位×0.5")
        print("!" * 60)
    elif regime in ('bear', 'neutral'):
        factor = 0.7 if regime == 'neutral' else 0.5
        print(f"\n[大盘择时: {regime}，仓位已×{factor}]\n")
    else:
        print()

    for i, stock in enumerate(sorted_recommendations, 1):
            print(f"{i}. {stock['code']} - {stock['name']}")
            latest_price = stock.get('latest_price', 0.0)
            change_pct = stock.get('change_pct', 0.0)
            pattern = stock.get('pattern', '未识别')
            score = stock.get('score', 0.0)
            recommendation_reason = stock.get('recommendation_reason', '无推荐理由')

            price_str = f"{latest_price:.2f} 元" if latest_price > 0 else "数据缺失"
            change_str = f"{change_pct:.2f}%" if change_pct != 0 else "数据缺失"

            print(f"   价格: {price_str}")
            print(f"   涨幅: {change_str}")
            print(f"   形态: {pattern}")
            print(f"   评分: {score:.2f} 分")
            if stock.get('industry'):
                print(f"   行业: {stock['industry']}")
            if stock.get('concept'):
                print(f"   概念: {stock['concept']}")
            print(f"   推荐理由: {recommendation_reason}")
            # 添加仓位建议
            position_sizing = stock.get('position_sizing', '未提供')
            print(f"   仓位建议: {position_sizing}")
            print("-" * 40)
    
    print("\n风险提示：")
    print("1. 以上推荐基于历史数据和量化模型分析，仅供参考，不构成投资建议")
    print("2. 本系统已增加追高风险控制，过滤了以下股票：")
    print("   - 3日内累计涨幅超过15%的股票")
    print("   - RSI指标≥70的超买股票")
    print("   - 收盘价偏离5日均线超过8%的股票")
    print("3. 市场有风险，投资需谨慎。请结合自身风险承受能力做出投资决策")
    print("4. 建议设置合理的止盈止损位，避免盲目追高")
    print("5. 短期交易存在较高风险，请理性投资")
    
    # 生成推荐报告文件
    generate_recommendation_report(sorted_recommendations)


if __name__ == "__main__":
    main()
