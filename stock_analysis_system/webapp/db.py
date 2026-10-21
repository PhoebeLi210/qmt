#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 持久化层

表设计：
- users                    用户（邀请码注册，各自保存推送配置）
- daily_recommendations    每日共享推荐清单（全市场扫描结果，全员共享同一份）
- watchlist                用户自选股（按 user_id 隔离）
- analysis_results         自选股盘后分析结果（一人一股一行，按交易日唯一）
- positions                用户持仓（成本/止损止盈比例/移动回撤/峰值价；未平仓每人每股唯一）
- alerts                   盘中预警记录（用户+股票+交易日+类型 唯一，天然去重）
"""

import os
import json
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'chaogu_web.db')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    push_type     TEXT,
    push_target   TEXT,
    expires_at    TEXT,                    -- 使用期限（YYYY-MM-DD），NULL=永久
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_recommendations (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date            TEXT NOT NULL,
    rank_no               INTEGER NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT,
    latest_price          REAL,
    change_pct            REAL,
    pattern               TEXT,
    score                 REAL,
    market_segment        TEXT,
    industry              TEXT,
    concept               TEXT,
    recommendation_reason TEXT,
    position_sizing       TEXT,
    stop_loss             TEXT,
    take_profit           TEXT,
    time_stop             TEXT,
    risk_level            TEXT,
    market_regime         TEXT,
    created_at            TEXT NOT NULL,
    UNIQUE(trade_date, code)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    code       TEXT NOT NULL,
    name       TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, code)
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    code                TEXT NOT NULL,
    trade_date          TEXT NOT NULL,
    name                TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    passed              INTEGER NOT NULL DEFAULT 0,
    fail_reasons        TEXT,
    latest_price        REAL,
    change_pct          REAL,
    pattern             TEXT,
    pattern_detail      TEXT,
    fundamental_score   REAL,
    technical_score     REAL,
    score               REAL,
    risk_score          REAL,
    final_score         REAL,
    threshold           REAL,
    positive_indicators TEXT,
    risk_level          TEXT,
    recommendation_reason TEXT,
    stop_loss           TEXT,
    take_profit         TEXT,
    time_stop           TEXT,
    market_regime       TEXT,
    fund_json           TEXT,
    chip_json           TEXT,
    error_msg           TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(user_id, code, trade_date)
);

CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT,
    shares      INTEGER NOT NULL DEFAULT 0,
    cost        REAL NOT NULL,
    stop_pct    REAL NOT NULL DEFAULT 0.07,
    take_pct    REAL NOT NULL DEFAULT 0.15,
    trail_pct   REAL NOT NULL DEFAULT 0.05,
    peak_price  REAL,
    note        TEXT,
    opened_at   TEXT NOT NULL,
    closed      INTEGER NOT NULL DEFAULT 0,
    closed_at   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_open
    ON positions(user_id, code) WHERE closed = 0;

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    code        TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    price       REAL,
    ref_price   REAL,
    detail      TEXT,
    pushed      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, code, trade_date, alert_type)
);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, created_at DESC);

-- ========== 自优化实验室（lab） ==========
CREATE TABLE IF NOT EXISTS param_versions (
    version     TEXT PRIMARY KEY,
    kind        TEXT NOT NULL DEFAULT 'baseline',  -- baseline/shadow/approved
    params_json TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date       TEXT NOT NULL,   -- 信号日（收盘后选股日）
    code              TEXT NOT NULL,
    name              TEXT,
    source            TEXT NOT NULL,   -- full_scan / watch / history
    pattern           TEXT,
    score             REAL,            -- 评分（页面对口径，总因子分）
    final_score       REAL,
    risk_score        REAL,
    fundamental_score REAL,
    technical_score   REAL,
    positive_count    INTEGER,
    market_regime     TEXT,
    ref_price         REAL,            -- 信号日收盘价（止损止盈基准）
    sl_pct            REAL,
    tp1_pct           REAL,
    tp2_pct           REAL,
    time_stop_days    INTEGER,
    recommended       INTEGER NOT NULL DEFAULT 0,
    rank_no           INTEGER,
    param_version     TEXT,
    factors_json      TEXT,            -- 因子拆解（指标/PE/PB/换手等）
    created_at        TEXT NOT NULL,
    UNIQUE(signal_date, code, source)
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signal_snapshots(signal_date);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    snapshot_id   INTEGER PRIMARY KEY REFERENCES signal_snapshots(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending/no_entry/closed
    entry_date    TEXT,
    entry_price   REAL,               -- T+1 开盘价
    exit_date     TEXT,
    exit_price    REAL,
    exit_reason   TEXT,               -- tp2 / sl / sl_after_tp1 / neutral
    path_result   TEXT,               -- win / loss / neutral
    tp1_touched   INTEGER NOT NULL DEFAULT 0,
    hold_days     INTEGER,
    realized_ret  REAL,               -- 路径口径收益（含费用，小数）
    ret_3d        REAL,
    ret_5d        REAL,
    ret_10d       REAL,
    ret_20d       REAL,               -- 窗口口径收盘收益（不含费用，小数）
    bench_ret_20d REAL,
    excess_20d    REAL,
    max_gain      REAL,
    max_loss      REAL,
    path_json     TEXT,              -- 未来20交易日OHLC（寻优回放用）
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_status ON signal_outcomes(status);

CREATE TABLE IF NOT EXISTS optimization_proposals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern          TEXT NOT NULL,
    score_band       INTEGER NOT NULL,
    n_samples        INTEGER NOT NULL,
    baseline_params  TEXT NOT NULL,   -- JSON
    baseline_stats   TEXT NOT NULL,   -- JSON
    proposed_params  TEXT NOT NULL,   -- JSON
    proposed_stats   TEXT NOT NULL,   -- JSON
    win_gain         REAL,
    ev_gain          REAL,
    bootstrap_stability REAL,
    walk_forward     TEXT,            -- JSON
    eligible         INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/shadow/active
    created_at       TEXT NOT NULL,
    decided_at       TEXT,
    note             TEXT,
    UNIQUE(pattern, score_band)
);
"""


def get_db():
    """获取数据库连接（行工厂为 sqlite3.Row）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """建表（幂等）+ 轻量列迁移（旧库补 path_json 等新列）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_db() as conn:
        conn.executescript(_SCHEMA)
        # 旧表补列（CREATE TABLE IF NOT EXISTS 不会改已存在表）
        existing = {r[1] for r in conn.execute('PRAGMA table_info(signal_outcomes)')}
        if 'path_json' not in existing:
            conn.execute('ALTER TABLE signal_outcomes ADD COLUMN path_json TEXT')
        ar_cols = {r[1] for r in conn.execute('PRAGMA table_info(analysis_results)')}
        if 'fund_json' not in ar_cols:
            conn.execute('ALTER TABLE analysis_results ADD COLUMN fund_json TEXT')
        if 'chip_json' not in ar_cols:
            conn.execute('ALTER TABLE analysis_results ADD COLUMN chip_json TEXT')
        # users 旧表补列（使用期限/管理员标记）
        user_cols = {r[1] for r in conn.execute('PRAGMA table_info(users)')}
        if 'expires_at' not in user_cols:
            conn.execute('ALTER TABLE users ADD COLUMN expires_at TEXT')
        if 'is_admin' not in user_cols:
            conn.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
        # 尚无管理员时，最早注册的账号自动成为管理员
        n_admin = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
        n_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if n_admin == 0 and n_users > 0:
            conn.execute('UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)')


# ---------------- 用户 ----------------

def create_user(username, password_hash, expires_at=None, is_admin=0):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, expires_at, is_admin, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (username, password_hash, expires_at, int(bool(is_admin)), now))
        return cur.lastrowid


def get_user_by_name(username):
    with get_db() as conn:
        return conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()


def list_users():
    with get_db() as conn:
        return conn.execute('SELECT * FROM users ORDER BY id').fetchall()


def get_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def update_push_config(user_id, push_type, push_target):
    with get_db() as conn:
        conn.execute('UPDATE users SET push_type = ?, push_target = ? WHERE id = ?',
                     (push_type or None, push_target or None, user_id))


def set_user_expiry(user_id, expires_at):
    """设置使用期限；expires_at 为 'YYYY-MM-DD' 字符串，None 表示永久"""
    with get_db() as conn:
        conn.execute('UPDATE users SET expires_at = ? WHERE id = ?',
                     (expires_at, user_id))


def set_user_password(user_id, password_hash):
    with get_db() as conn:
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                     (password_hash, user_id))


def count_admins(exclude_user_id=None):
    sql = 'SELECT COUNT(*) FROM users WHERE is_admin = 1'
    args = ()
    if exclude_user_id is not None:
        sql += ' AND id != ?'
        args = (exclude_user_id,)
    with get_db() as conn:
        return conn.execute(sql, args).fetchone()[0]


def delete_user_cascade(user_id):
    """删除账号及其全部私有数据（自选/持仓/分析结果/预警）"""
    with get_db() as conn:
        conn.execute('DELETE FROM watchlist WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM positions WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM analysis_results WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM alerts WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))


# ---------------- 每日共享推荐 ----------------

def save_daily_recommendations(trade_date, recommendations):
    """批量写入某日推荐清单（同日重复执行时整批替换）"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for rank, s in enumerate(recommendations, 1):
        rows.append((
            trade_date, rank,
            s.get('code'), s.get('name'),
            s.get('latest_price'), s.get('change_pct'),
            s.get('pattern'), s.get('score'),
            s.get('market_segment'), s.get('industry'), s.get('concept'),
            s.get('recommendation_reason'), s.get('position_sizing'),
            s.get('stop_loss'), s.get('take_profit'), s.get('time_stop'),
            s.get('risk_level'), s.get('market_regime'),
            now,
        ))
    with get_db() as conn:
        conn.execute('DELETE FROM daily_recommendations WHERE trade_date = ?', (trade_date,))
        conn.executemany(
            """INSERT INTO daily_recommendations
               (trade_date, rank_no, code, name, latest_price, change_pct, pattern, score,
                market_segment, industry, concept, recommendation_reason, position_sizing,
                stop_loss, take_profit, time_stop, risk_level, market_regime, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows)


def list_recommendation_dates():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT DISTINCT trade_date FROM daily_recommendations ORDER BY trade_date DESC'
        ).fetchall()
        return [r['trade_date'] for r in rows]


def get_recommendations(trade_date):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM daily_recommendations WHERE trade_date = ? ORDER BY rank_no',
            (trade_date,)).fetchall()


# ---------------- 自选股 ----------------

def add_watch(user_id, code, name=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute(
            """INSERT INTO watchlist (user_id, code, name, created_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, code) DO UPDATE SET name = COALESCE(excluded.name, watchlist.name)""",
            (user_id, code, name, now))


def remove_watch(user_id, code):
    with get_db() as conn:
        conn.execute('DELETE FROM watchlist WHERE user_id = ? AND code = ?', (user_id, code))


def list_watch(user_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT w.*,
                      (SELECT status FROM analysis_results a
                        WHERE a.user_id = w.user_id AND a.code = w.code
                        ORDER BY a.trade_date DESC LIMIT 1) AS last_status,
                      (SELECT trade_date FROM analysis_results a
                        WHERE a.user_id = w.user_id AND a.code = w.code
                        ORDER BY a.trade_date DESC LIMIT 1) AS last_date,
                      (SELECT id FROM analysis_results a
                        WHERE a.user_id = w.user_id AND a.code = w.code
                        ORDER BY a.trade_date DESC LIMIT 1) AS last_analysis_id,
                      (SELECT passed FROM analysis_results a
                        WHERE a.user_id = w.user_id AND a.code = w.code
                        ORDER BY a.trade_date DESC LIMIT 1) AS last_passed
               FROM watchlist w WHERE w.user_id = ? ORDER BY w.created_at DESC""",
            (user_id,)).fetchall()


def list_all_watch_codes():
    """全用户自选股去重（盘后批量分析用），返回 [(code, 最近使用的名称)]"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT code, MAX(name) AS name FROM watchlist GROUP BY code""").fetchall()
        return [(r['code'], r['name']) for r in rows]


def list_users_watching(code):
    """关注某只股票的全部用户 id"""
    with get_db() as conn:
        rows = conn.execute('SELECT user_id FROM watchlist WHERE code = ?', (code,)).fetchall()
        return [r['user_id'] for r in rows]


def get_watch(user_id, code):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM watchlist WHERE user_id = ? AND code = ?', (user_id, code)).fetchone()


# ---------------- 分析结果 ----------------

def upsert_analysis_row(user_id, code, trade_date, name, status, **fields):
    """创建/更新分析结果行，返回行 id"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute(
            """INSERT INTO analysis_results (user_id, code, trade_date, name, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, code, trade_date) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at""",
            (user_id, code, trade_date, name, status, now, now))
        row = conn.execute(
            'SELECT id FROM analysis_results WHERE user_id = ? AND code = ? AND trade_date = ?',
            (user_id, code, trade_date)).fetchone()
        row_id = row['id']
        if fields:
            cols = ', '.join(f'{k} = ?' for k in fields)
            conn.execute(
                f'UPDATE analysis_results SET {cols}, updated_at = ? WHERE id = ?',
                (*fields.values(), now, row_id))
        return row_id


def get_analysis(row_id):
    with get_db() as conn:
        return conn.execute('SELECT * FROM analysis_results WHERE id = ?', (row_id,)).fetchone()


def get_today_analysis(user_id, code, trade_date):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM analysis_results WHERE user_id = ? AND code = ? AND trade_date = ?',
            (user_id, code, trade_date)).fetchone()


def parse_json_field(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# ---------------- 持仓 ----------------

def create_position(user_id, code, cost, shares=0, name=None,
                    stop_pct=0.07, take_pct=0.15, trail_pct=0.05,
                    opened_at=None, note=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    opened_at = opened_at or datetime.now().strftime('%Y-%m-%d')
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO positions
               (user_id, code, name, shares, cost, stop_pct, take_pct, trail_pct,
                opened_at, note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, code, name, int(shares or 0), float(cost),
             float(stop_pct), float(take_pct), float(trail_pct),
             opened_at, note, now, now))
        return cur.lastrowid


def get_position(position_id, user_id=None):
    with get_db() as conn:
        if user_id is None:
            return conn.execute('SELECT * FROM positions WHERE id = ?',
                                (position_id,)).fetchone()
        return conn.execute('SELECT * FROM positions WHERE id = ? AND user_id = ?',
                            (position_id, user_id)).fetchone()


def list_positions(user_id, include_closed=False, limit_closed=30):
    """未平仓持仓（按建仓日倒序）；include_closed 时附带最近已平仓记录"""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM positions WHERE user_id = ? AND closed = 0 ORDER BY opened_at DESC, id DESC',
            (user_id,)).fetchall()
        closed = []
        if include_closed:
            closed = conn.execute(
                """SELECT * FROM positions WHERE user_id = ? AND closed = 1
                   ORDER BY closed_at DESC, id DESC LIMIT ?""",
                (user_id, limit_closed)).fetchall()
        return rows, closed


def list_all_open_positions():
    """全部用户未平仓持仓（盘中监控用）"""
    with get_db() as conn:
        return conn.execute('SELECT * FROM positions WHERE closed = 0').fetchall()


def close_position(position_id, user_id):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE positions SET closed = 1, closed_at = ?, updated_at = ? '
            'WHERE id = ? AND user_id = ? AND closed = 0',
            (now, now, position_id, user_id))
        return cur.rowcount > 0


def delete_position(position_id, user_id):
    with get_db() as conn:
        cur = conn.execute(
            'DELETE FROM positions WHERE id = ? AND user_id = ?',
            (position_id, user_id))
        return cur.rowcount > 0


def update_position_peak(position_id, peak_price):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute(
            'UPDATE positions SET peak_price = ?, updated_at = ? WHERE id = ?',
            (float(peak_price), now, position_id))


def get_latest_passed_map(user_id):
    """用户自选股中"最近一次分析且通过买点"的股票 -> 分析行（买点提醒布防用）。

    结果已排除已持仓股票。
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.* FROM analysis_results a
               JOIN (SELECT code, MAX(trade_date) AS md
                     FROM analysis_results
                     WHERE user_id = ?
                     GROUP BY code) lm
                 ON a.code = lm.code AND a.trade_date = lm.md
               WHERE a.user_id = ? AND a.status = 'done' AND a.passed = 1
                 AND NOT EXISTS (SELECT 1 FROM positions p
                                 WHERE p.user_id = a.user_id AND p.code = a.code
                                   AND p.closed = 0)""",
            (user_id, user_id)).fetchall()
        return {r['code']: r for r in rows}


# ---------------- 盘中预警 ----------------

ALERT_TYPES = {
    'stop_loss': '⛔ 跌破止损价',
    'take_profit': '🎯 到达止盈价',
    'trailing_stop': '📉 触发移动止损',
    'top_warning': '⚠️ 盘中冲高回落',
    'buy_point': '🔔 回到买点参考价',
    'fund_outflow': '💸 主力资金大幅流出',
}


def add_alert(user_id, code, trade_date, alert_type, price=None,
              ref_price=None, detail=None):
    """插入预警；同 用户+股+日+类型 已存在则返回 None（去重）。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with get_db() as conn:
            cur = conn.execute(
                """INSERT INTO alerts
                   (user_id, code, trade_date, alert_type, price, ref_price,
                    detail, pushed, created_at)
                   VALUES (?,?,?,?,?,?,?,0,?)""",
                (user_id, code, trade_date, alert_type, price, ref_price,
                 detail, now))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def mark_alert_pushed(alert_id):
    with get_db() as conn:
        conn.execute('UPDATE alerts SET pushed = 1 WHERE id = ?', (alert_id,))


def list_alerts(user_id, limit=100):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM alerts WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?',
            (user_id, limit)).fetchall()


# ---------------- 自优化实验室 ----------------

def ensure_param_version(version, kind, params_json, note=None):
    """登记参数版本（已存在则忽略）。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute(
            """INSERT INTO param_versions (version, kind, params_json, note, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(version) DO NOTHING""",
            (version, kind, params_json, note, now))


def save_signal_snapshot(signal_date, code, source, **f):
    """写入/替换一条信号快照（同日同股同源唯一）。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute(
            """INSERT INTO signal_snapshots
               (signal_date, code, name, source, pattern, score, final_score, risk_score,
                fundamental_score, technical_score, positive_count, market_regime, ref_price,
                sl_pct, tp1_pct, tp2_pct, time_stop_days, recommended, rank_no,
                param_version, factors_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_date, code, source) DO UPDATE SET
                 name=excluded.name, pattern=excluded.pattern, score=excluded.score,
                 final_score=excluded.final_score, risk_score=excluded.risk_score,
                 fundamental_score=excluded.fundamental_score,
                 technical_score=excluded.technical_score,
                 positive_count=excluded.positive_count,
                 market_regime=excluded.market_regime, ref_price=excluded.ref_price,
                 sl_pct=excluded.sl_pct, tp1_pct=excluded.tp1_pct, tp2_pct=excluded.tp2_pct,
                 time_stop_days=excluded.time_stop_days, recommended=excluded.recommended,
                 rank_no=excluded.rank_no, param_version=excluded.param_version,
                 factors_json=excluded.factors_json, created_at=excluded.created_at""",
            (signal_date, code, f.get('name'), source, f.get('pattern'),
             f.get('score'), f.get('final_score'), f.get('risk_score'),
             f.get('fundamental_score'), f.get('technical_score'),
             f.get('positive_count'), f.get('market_regime'), f.get('ref_price'),
             f.get('sl_pct'), f.get('tp1_pct'), f.get('tp2_pct'),
             f.get('time_stop_days'), 1 if f.get('recommended') else 0,
             f.get('rank_no'), f.get('param_version'), f.get('factors_json'), now))


def list_signals_without_outcome(limit, max_signal_date=None):
    """还没有 outcome 行、且信号日 <= max_signal_date 的信号（最旧优先）。"""
    sql = """SELECT s.* FROM signal_snapshots s
             LEFT JOIN signal_outcomes o ON o.snapshot_id = s.id
             WHERE o.snapshot_id IS NULL"""
    args = []
    if max_signal_date:
        sql += ' AND s.signal_date <= ?'
        args.append(max_signal_date)
    sql += ' ORDER BY s.signal_date, s.id LIMIT ?'
    args.append(limit)
    with get_db() as conn:
        return conn.execute(sql, args).fetchall()


def list_pending_outcomes(limit, stale_hours=20):
    """需要继续追踪的 pending 结果（距上次更新超过 stale_hours）。"""
    with get_db() as conn:
        return conn.execute(
            """SELECT s.*, o.status AS o_status, o.updated_at AS o_updated
               FROM signal_snapshots s
               JOIN signal_outcomes o ON o.snapshot_id = s.id
               WHERE o.status = 'pending'
                 AND o.updated_at <= datetime('now', 'localtime', ?)
               ORDER BY s.signal_date, s.id LIMIT ?""",
            (f'-{int(stale_hours)} hours', limit)).fetchall()


def upsert_outcome(snapshot_id, **f):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cols = ('status', 'entry_date', 'entry_price', 'exit_date', 'exit_price',
            'exit_reason', 'path_result', 'tp1_touched', 'hold_days', 'realized_ret',
            'ret_3d', 'ret_5d', 'ret_10d', 'ret_20d', 'bench_ret_20d', 'excess_20d',
            'max_gain', 'max_loss', 'path_json')
    vals = [f.get(c) for c in cols]
    vals[cols.index('tp1_touched')] = int(f.get('tp1_touched') or 0)
    with get_db() as conn:
        conn.execute(
            f"""INSERT INTO signal_outcomes (snapshot_id, {', '.join(cols)}, updated_at)
                VALUES (?, {', '.join('?' * len(cols))}, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                  {', '.join(f'{c}=excluded.{c}' for c in cols)},
                  updated_at=excluded.updated_at""",
            (snapshot_id, *vals, now))


# ---------------- 优化提案 ----------------

def save_proposal(pattern, score_band, n_samples, baseline_params, baseline_stats,
                  proposed_params, proposed_stats, win_gain, ev_gain,
                  bootstrap_stability, walk_forward, eligible, note=None):
    """写入/更新一条优化提案（同形态+分数段唯一）。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    import json as _json
    with get_db() as conn:
        conn.execute(
            """INSERT INTO optimization_proposals
               (pattern, score_band, n_samples, baseline_params, baseline_stats,
                proposed_params, proposed_stats, win_gain, ev_gain,
                bootstrap_stability, walk_forward, eligible, status,
                created_at, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)
               ON CONFLICT(pattern, score_band) DO UPDATE SET
                 n_samples=excluded.n_samples,
                 baseline_params=excluded.baseline_params,
                 baseline_stats=excluded.baseline_stats,
                 proposed_params=excluded.proposed_params,
                 proposed_stats=excluded.proposed_stats,
                 win_gain=excluded.win_gain, ev_gain=excluded.ev_gain,
                 bootstrap_stability=excluded.bootstrap_stability,
                 walk_forward=excluded.walk_forward,
                 eligible=excluded.eligible, note=excluded.note""",
            (pattern, score_band, n_samples,
             _json.dumps(baseline_params, ensure_ascii=False),
             _json.dumps(baseline_stats, ensure_ascii=False, default=str),
             _json.dumps(proposed_params, ensure_ascii=False),
             _json.dumps(proposed_stats, ensure_ascii=False, default=str),
             win_gain, ev_gain, bootstrap_stability,
             _json.dumps(walk_forward, ensure_ascii=False, default=str)
             if walk_forward else None,
             1 if eligible else 0, now, note))


def list_proposals():
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM optimization_proposals ORDER BY eligible DESC, ev_gain DESC'
        ).fetchall()


def decide_proposal(proposal_id, status, note=None):
    """批准/拒绝提案。status: approved/rejected。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE optimization_proposals SET status = ?, decided_at = ?, note = COALESCE(?, note) WHERE id = ?',
            (status, now, note, proposal_id))
        return cur.rowcount > 0
