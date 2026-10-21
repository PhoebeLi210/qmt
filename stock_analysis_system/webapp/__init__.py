#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chaogu Web 展示层（一期）

- 共享推荐清单：读取每日全市场扫描入库的 v2.5 推荐结果
- 多用户自选股：每人独立股票池，盘后用 chaogu v2.5 同一套模型分析
- 推送：分析结论按用户配置推送到飞书/钉钉/Bark

核心选股/评分/止损止盈逻辑全部复用 stock_analysis_system 现有模块，本包只做持久化、Web 与调度。
"""
