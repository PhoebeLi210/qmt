#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金流向数据采集（自优化实验室阶段一：只落库观察，不参与评分）

数据源：新浪 MoneyFlow.ssl_bkzj_ssggzj 全市场个股资金流排行
（东财 push2 系列在云服务器 IP 被限流，新浪机房可达，且一次请求返回全市场）。

口径（新浪字段，金额单位：元；比率为小数）：
- netamount/ratioamount 全部委托单净流入额/占成交额比
- r0_* 超大单，r3_* 大单；"主力"约定 = 超大单 + 大单
只采集信号日当日快照；3/5 日主力净流入日后由多日快照聚合，
避免在扫描链路里发多组请求。

进程内按自然日缓存：全市场扫描 ~290 只只发 1 次 HTTP。
任何失败返回空 dict，调用方必须容忍（不得影响扫描主流程）。
"""

import logging
import time
from datetime import datetime

import requests

logger = logging.getLogger('webapp.lab.fund_flow')

_URL = ('https://vip.stock.finance.sina.com.cn/quotes_service/'
        'api/json_v2.php/MoneyFlow.ssl_bkzj_ssggzj')
_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'),
    'Referer': 'https://vip.stock.finance.sina.com.cn/',
}
_PAGE_SIZE = 6000      # 一次拉全市场（实测 0.7s 返回 6000 行）
_TIMEOUT = 12
_MAX_PAGES = 3        # 安全上限（A股总数 < 6000，正常 1 页足够）

_cache = {'date': None, 'map': None}


def _to_float(v):
    try:
        if v in (None, '', '--'):
            return None
        f = float(v)
        # 新浪缺失值有时给极大负数
        return f if -1e15 < f < 1e15 else None
    except (TypeError, ValueError):
        return None


def _row_to_factor(row):
    """新浪单行 → 因子 dict。主力 = 超大单(r0) + 大单(r3)。"""
    r0_net = _to_float(row.get('r0_net'))
    r3_net = _to_float(row.get('r3_net'))
    r0_ratio = _to_float(row.get('r0_ratio'))
    r3_ratio = _to_float(row.get('r3_ratio'))
    main_net = (r0_net + r3_net) if (r0_net is not None and r3_net is not None) else None
    main_ratio = (r0_ratio + r3_ratio) if (r0_ratio is not None and r3_ratio is not None) else None
    return {
        'mf_net': _to_float(row.get('netamount')),          # 全部单净流入（元）
        'mf_ratio': _to_float(row.get('ratioamount')),     # 净流入占成交额比
        'mf_main_net': main_net,                            # 主力（超大+大）净额（元）
        'mf_main_ratio': main_ratio,                        # 主力净占比
        'mf_super_net': r0_net,                             # 超大单净额（元）
        'mf_super_ratio': r0_ratio,
        'mf_big_net': r3_net,                               # 大单净额（元）
        'mf_big_ratio': r3_ratio,
        'mf_amount': _to_float(row.get('amount')),          # 成交额（元）
    }


def _fetch_once(session):
    """拉取全市场资金流，返回原始行列表。

    必须翻到空页为止：新浪在被限流时会对第 2 页返回空数组，
    若 len(data) < num 就提前结束会静默丢掉排在第 2 页的股票；
    触达页数上限仍满页时视为截断，抛错交由外层重试。
    """
    rows = []
    prev_len = None
    for page in range(1, _MAX_PAGES + 1):
        resp = session.get(
            _URL, params={'page': page, 'num': _PAGE_SIZE},
            headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            # 上一页还是满页、本页就空：被限流截断，抛错走重试
            if prev_len is not None and prev_len >= _PAGE_SIZE:
                raise RuntimeError('资金流分页疑似截断（满页后遇空页）')
            break
        rows.extend(data)
        prev_len = len(data)
        if page == _MAX_PAGES and prev_len >= _PAGE_SIZE:
            raise RuntimeError('资金流页数触达上限，疑似截断')
    return rows


def fetch_market_fund_map(force=False):
    """返回 {6位代码: 因子dict}；按自然日缓存。失败返回 {}。

    force=True 用于测试或强制刷新。
    """
    today = datetime.now().strftime('%Y-%m-%d')
    if not force and _cache['date'] == today and _cache['map'] is not None:
        return _cache['map']

    out = {}
    try:
        session = requests.Session()
        try:
            rows = _fetch_once(session)
        except Exception:
            # 冷却 2 秒后重试一次（新浪偶发连接重置）
            time.sleep(2)
            rows = _fetch_once(session)
        for row in rows:
            symbol = (row.get('symbol') or '').strip()
            digits = symbol[2:] if len(symbol) > 2 else symbol
            if len(digits) == 6 and digits.isdigit():
                out[digits] = _row_to_factor(row)
        logger.info('资金流快照拉取成功: %d 只（%s）', len(out), today)
    except Exception:
        logger.exception('资金流快照拉取失败，本日资金因子留空（不影响扫描）')
        out = {}

    _cache['date'] = today
    _cache['map'] = out
    return out


def get_fund_factor(code, fund_map=None):
    """按 sh.600000 / 600000 两种形态取该股资金因子；无数据返回 None。"""
    if not fund_map:
        return None
    digits = (code or '').split('.')[-1]
    return fund_map.get(digits)


def reset_cache():
    """测试用。"""
    _cache['date'] = None
    _cache['map'] = None
