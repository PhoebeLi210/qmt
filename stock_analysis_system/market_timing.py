# -*- coding: utf-8 -*-
"""大盘择时（v2.5）：基于上证指数 MA20/RSI 判定市场状态，进程内按日缓存

状态定义（与 recommendation_engine v2.4 口径一致）：
  bull      : 收盘 > MA20 且 MA20 上行
  neutral   : 收盘 > MA20 但 MA20 走平/下行
  bear      : 收盘 < MA20 且 RSI>=35
  risk_off  : 收盘 < MA20 且 RSI<35

v2.5 防守市规则（lab 归因 2026-10：防守市信号胜率仅 8.7%，反转型形态 0 胜）：
  - risk_off/bear 统称防守市（DEFENSIVE_REGIMES）
  - 全市场扫描信号门槛提升至 55（main.py）
  - bear 暂停全市场推荐；risk_off 限流精选并剔除反转型形态（recommendation_engine.py）
"""
import logging
from utils.logger import setup_logger

logger = setup_logger('market_timing', logging.INFO)

DEFENSIVE_REGIMES = ('risk_off', 'bear')
# 反转型/抄底型形态：防守市禁入推荐（归因：v_rebound 0胜46负、double_bottom 0胜5负）
COUNTER_TREND_PATTERNS = ('v_rebound', 'double_bottom', 'bottom_rebound')

_state = {'date': None, 'regime': None}


def get_market_regime(force_refresh=False):
    """返回当前大盘状态字符串；数据不可用时降级 'neutral'。同交易日进程内缓存。"""
    import datetime
    today = datetime.date.today().isoformat()
    if not force_refresh and _state['date'] == today and _state['regime']:
        return _state['regime']

    regime = 'neutral'
    try:
        import akshare as ak
        import pandas as pd
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty and 'close' in df.columns:
            closes = pd.to_numeric(df['close'], errors='coerce').dropna().reset_index(drop=True)
            if len(closes) >= 21:
                latest_close = float(closes.iloc[-1])
                ma20_now = float(closes.tail(20).mean())
                ma20_5d_ago = float(closes.iloc[-25:-5].mean()) if len(closes) >= 25 else ma20_now
                ma20_trending_up = ma20_now > ma20_5d_ago

                # RSI 14
                delta = closes.diff()
                gain = delta.where(delta > 0, 0).rolling(window=14, min_periods=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=14).mean()
                rsi = 50.0
                if len(closes) >= 15 and loss.iloc[-1] > 0:
                    rs = gain.iloc[-1] / loss.iloc[-1]
                    rsi = 100 - 100 / (1 + rs)

                above_ma = latest_close > ma20_now
                if not above_ma and rsi < 35:
                    regime = 'risk_off'
                elif not above_ma:
                    regime = 'bear'
                elif ma20_trending_up:
                    regime = 'bull'
                else:
                    regime = 'neutral'
                logger.info(f"大盘择时: {regime} (close={latest_close:.0f}, MA20={ma20_now:.0f}, "
                            f"MA20上行={ma20_trending_up}, RSI={rsi:.1f})")
            else:
                logger.warning("上证指数数据不足21根，大盘择时降级 neutral")
        else:
            logger.warning("上证指数数据为空，大盘择时降级 neutral")
    except Exception as e:
        logger.warning(f"大盘择时数据不可用，使用neutral: {e}")

    _state['date'] = today
    _state['regime'] = regime
    return regime
