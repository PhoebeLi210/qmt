#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask 应用工厂与路由

页面：
- /recommendations  共享推荐清单（v2.5 全市场扫描结果，全员同一份）
- /watchlist        我的自选股（每人独立）
- /analysis/<id>    自选股个股分析详情（完整评分/信号/止损止盈）
- /settings         推送渠道配置
"""

import os
import json
import secrets
import logging
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, abort, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

from webapp import db, push as push_mod
from webapp.analysis_service import (
    normalize_code, start_analysis, AnalysisError, segment_of, lookup_name)
from webapp import monitor

logger = logging.getLogger('webapp')

TOP_SIGNALS = {'看跌吞没', '黄昏之星', '巨量长上影'}

# 注册邀请码（小圈子使用；部署时用环境变量覆盖）
INVITE_CODE = os.environ.get('CHAOGU_INVITE_CODE', 'chaogu2026')


def _load_or_create_secret():
    secret_file = os.path.join(db.DATA_DIR, '.secret_key')
    os.makedirs(db.DATA_DIR, exist_ok=True)
    if os.path.exists(secret_file):
        with open(secret_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(secret_file, 'w', encoding='utf-8') as f:
        f.write(key)
    return key


def _user_expired(user):
    """账号是否已过期；管理员与未设期限（NULL）永不过期"""
    if not user or user['is_admin']:
        return False
    expires_at = user['expires_at']
    if not expires_at:
        return False
    try:
        expire_date = datetime.strptime(expires_at[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return False
    return datetime.now().date() > expire_date


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.path))
        # 每次请求校验账号是否仍有效（期限可能已被管理员调整）
        user = db.get_user_by_id(session['user_id'])
        if user is None:
            session.clear()
            return redirect(url_for('login'))
        if _user_expired(user):
            session.clear()
            flash('账号已过使用期限，请联系管理员续期', 'error')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.path))
        user = db.get_user_by_id(session['user_id'])
        if user is None or not user['is_admin']:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def create_app(start_jobs=True):
    app = Flask(__name__)
    app.secret_key = os.environ.get('CHAOGU_SECRET_KEY') or _load_or_create_secret()
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    if os.environ.get('CHAOGU_COOKIE_SECURE') == '1':
        app.config['SESSION_COOKIE_SECURE'] = True

    db.init_db()

    @app.template_filter('from_json')
    def _from_json(s):
        try:
            return json.loads(s) if s else {}
        except (TypeError, ValueError):
            return {}

    @app.context_processor
    def _inject_admin_flag():
        # 模板导航按 session 中的管理员标记显示入口
        return {'session_is_admin': bool(session.get('is_admin'))}

    if start_jobs and os.environ.get('CHAOGU_DISABLE_SCHEDULER') != '1':
        try:
            from webapp.scheduler import start_scheduler
            start_scheduler()
        except Exception:
            logger.exception('定时任务启动失败（不影响 Web 使用）')

    # ---------------- 认证 ----------------

    @app.route('/')
    def index():
        return redirect(url_for('recommendations'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = db.get_user_by_name(username)
            if user and check_password_hash(user['password_hash'], password):
                if _user_expired(user):
                    flash('账号已过使用期限，请联系管理员续期', 'error')
                    return render_template('login.html')
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = bool(user['is_admin'])
                return redirect(request.args.get('next') or url_for('recommendations'))
            flash('用户名或密码错误', 'error')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        # 公开注册已关闭，账号统一由管理员在后台创建
        flash('公开注册已关闭，请联系管理员开通账号', 'error')
        return redirect(url_for('login'))

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ---------------- 账号管理（管理员） ----------------

    def _parse_expiry(raw):
        """解析期限表单值：空串=永久(None)，否则校验 YYYY-MM-DD"""
        raw = (raw or '').strip()
        if not raw:
            return None
        return datetime.strptime(raw, '%Y-%m-%d').strftime('%Y-%m-%d')

    @app.route('/admin')
    @admin_required
    def admin_users():
        today = datetime.now().date()
        users = []
        for u in db.list_users():
            status = '永久'
            days_left = None
            if u['expires_at']:
                try:
                    exp = datetime.strptime(u['expires_at'][:10], '%Y-%m-%d').date()
                    days_left = (exp - today).days
                    status = '已过期' if days_left < 0 else f'剩余{days_left}天'
                except ValueError:
                    status = '日期异常'
            users.append({'u': u, 'status': status, 'days_left': days_left})
        return render_template('admin.html', users=users, today=today.strftime('%Y-%m-%d'))

    @app.route('/admin/user/create', methods=['POST'])
    @admin_required
    def admin_user_create():
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        try:
            expires_at = _parse_expiry(request.form.get('expires_at'))
        except ValueError:
            flash('期限日期格式不正确', 'error')
            return redirect(url_for('admin_users'))
        if len(username) < 2 or len(password) < 6:
            flash('用户名至少2个字符，密码至少6位', 'error')
        elif db.get_user_by_name(username):
            flash('用户名已存在', 'error')
        else:
            db.create_user(username, generate_password_hash(password),
                           expires_at=expires_at)
            flash(f'已创建账号 {username}' +
                  (f'，有效期至 {expires_at}' if expires_at else '，永久有效'), 'ok')
        return redirect(url_for('admin_users'))

    @app.route('/admin/user/expiry', methods=['POST'])
    @admin_required
    def admin_user_expiry():
        uid = request.form.get('user_id', type=int)
        user = db.get_user_by_id(uid) if uid else None
        if user is None:
            abort(404)
        try:
            expires_at = _parse_expiry(request.form.get('expires_at'))
        except ValueError:
            flash('期限日期格式不正确', 'error')
            return redirect(url_for('admin_users'))
        db.set_user_expiry(uid, expires_at)
        tip = '设为永久有效' if expires_at is None else f'有效期至 {expires_at}'
        flash(f'{user["username"]} 已{tip}', 'ok')
        return redirect(url_for('admin_users'))

    @app.route('/admin/user/password', methods=['POST'])
    @admin_required
    def admin_user_password():
        uid = request.form.get('user_id', type=int)
        new_pw = request.form.get('password', '')
        user = db.get_user_by_id(uid) if uid else None
        if user is None:
            abort(404)
        if len(new_pw) < 6:
            flash('新密码至少6位', 'error')
        else:
            db.set_user_password(uid, generate_password_hash(new_pw))
            flash(f'{user["username"]} 的密码已重置', 'ok')
        return redirect(url_for('admin_users'))

    @app.route('/admin/user/delete', methods=['POST'])
    @admin_required
    def admin_user_delete():
        uid = request.form.get('user_id', type=int)
        user = db.get_user_by_id(uid) if uid else None
        if user is None:
            abort(404)
        if uid == session['user_id']:
            flash('不能删除当前登录的管理员账号', 'error')
        elif user['is_admin'] and db.count_admins(exclude_user_id=uid) == 0:
            flash('至少保留一个管理员账号', 'error')
        else:
            db.delete_user_cascade(uid)
            flash(f'账号 {user["username"]} 及其私有数据已删除', 'ok')
        return redirect(url_for('admin_users'))

    # ---------------- 共享推荐清单 ----------------

    @app.route('/recommendations')
    @login_required
    def recommendations():
        dates = db.list_recommendation_dates()
        trade_date = request.args.get('date') or (dates[0] if dates else None)
        rows = db.get_recommendations(trade_date) if trade_date else []
        regime = rows[0]['market_regime'] if rows else None
        return render_template('recommendations.html',
                               dates=dates, trade_date=trade_date,
                               rows=rows, regime=regime,
                               today=datetime.now().strftime('%Y-%m-%d'))

    # ---------------- 自优化实验室 ----------------

    @app.route('/lab')
    @login_required
    def lab():
        from webapp.lab import stats
        src = request.args.get('source', 'all')
        sources = [src] if src in stats.SOURCES else list(stats.SOURCES)
        regime = request.args.get('regime') or None
        if regime == 'all':
            regime = None
        pat = request.args.get('pat') or None
        band = request.args.get('band', type=int)

        ov = stats.overview(sources, regime)
        mat = stats.matrix(sources, regime)
        samples = None
        if pat and pat in stats.PATTERN_LABELS and band in stats.BAND_LABELS:
            samples = stats.cell_samples(pat, band, sources, regime)
        proposals = db.list_proposals()
        p1 = stats.p1_monitor()
        return render_template(
            'lab.html', ov=ov, mat=mat, samples=samples, proposals=proposals,
            p1=p1,
            patterns=stats.PATTERN_ORDER + ['other'],
            pat_labels=stats.PATTERN_LABELS,
            bands=stats.BAND_ORDER, band_labels=stats.BAND_LABELS,
            sources=sources, source=src,
            source_labels=stats.SOURCE_LABELS,
            regime=regime or 'all', pat=pat, band=band,
            min_sample=stats.MIN_SAMPLE,
            today=datetime.now().strftime('%Y-%m-%d'))

    @app.route('/lab/proposal/<int:pid>/decide', methods=['POST'])
    @login_required
    def lab_decide(pid):
        status = request.form.get('status')
        note = request.form.get('note')
        if status not in ('approved', 'rejected'):
            flash('状态无效', 'error')
            return redirect(url_for('lab'))
        ok = db.decide_proposal(pid, status, note)
        flash('提案已' + ('批准' if status == 'approved' else '拒绝')
              if ok else '提案不存在', 'ok' if ok else 'error')
        return redirect(url_for('lab'))

    # ---------------- 自选股 ----------------

    @app.route('/watchlist')
    @login_required
    def watchlist():
        uid = session['user_id']
        rows = db.list_watch(uid)
        armed = set(db.get_latest_passed_map(uid).keys())  # 买点提醒已布防的股票
        return render_template('watchlist.html', rows=rows, armed_codes=armed)

    @app.route('/watchlist/add', methods=['POST'])
    @login_required
    def watchlist_add():
        raw_code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip() or None
        try:
            code = normalize_code(raw_code)
        except AnalysisError as e:
            flash(str(e), 'error')
            return redirect(url_for('watchlist'))
        if not name:
            try:
                name = lookup_name(code)
            except Exception:
                name = None
        db.add_watch(session['user_id'], code, name)
        flash(f'已添加自选 {name or code}', 'ok')
        return redirect(url_for('watchlist'))

    @app.route('/watchlist/delete', methods=['POST'])
    @login_required
    def watchlist_delete():
        code = request.form.get('code', '').strip()
        db.remove_watch(session['user_id'], code)
        flash('已移除', 'ok')
        return redirect(url_for('watchlist'))

    @app.route('/watchlist/analyze', methods=['POST'])
    @login_required
    def watchlist_analyze():
        raw_code = request.form.get('code', '').strip()
        notify = request.form.get('notify') == '1'
        try:
            code, _ = start_analysis(session['user_id'], raw_code, notify=notify)
            flash(f'{code} 分析已在后台开始，约需30-90秒，请稍后刷新查看', 'ok')
        except AnalysisError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.exception('触发分析失败')
            flash(f'触发失败: {e}', 'error')
        return redirect(url_for('watchlist'))

    # ---------------- 持仓（二期/三期） ----------------

    def _parse_pct(raw, default):
        """表单百分数 -> 小数；非法/越界用默认值，范围 0~50%"""
        try:
            v = abs(float(raw)) / 100.0
            return v if 0 < v <= 0.5 else default
        except (TypeError, ValueError):
            return default

    @app.route('/positions')
    @login_required
    def positions():
        uid = session['user_id']
        rows, closed = db.list_positions(uid, include_closed=True)
        spot = monitor.get_quotes([p['code'] for p in rows]) if rows else {}

        # 资金流 + 筹码（日缓存；失败各字段为 None，页面降级显示）
        try:
            from webapp.lab.holdings import get_ext_map
            ext_map = get_ext_map([p['code'] for p in rows]) if rows else {}
        except Exception:
            logger.debug('持仓扩展数据获取失败', exc_info=True)
            ext_map = {}

        view = []
        for p in rows:
            s = spot.get(p['code'].split('.')[-1]) or {}
            price = s.get('price')
            stop_line = p['cost'] * (1 - p['stop_pct'])
            take_line = p['cost'] * (1 + p['take_pct'])
            peak = p['peak_price'] or p['cost']
            trail_armed = bool(p['trail_pct']) and peak / p['cost'] - 1 >= p['trail_pct']
            trail_line = max(stop_line, peak * (1 - p['trail_pct'])) \
                if trail_armed else None
            pnl_pct = ((price / p['cost'] - 1) * 100) if price else None
            view.append(dict(p, price=price, pct=s.get('pct'),
                             stop_line=stop_line, take_line=take_line,
                             peak=peak, trail_line=trail_line,
                             pnl_pct=pnl_pct,
                             ext=ext_map.get(p['code']) or {},
                             mv=(price * p['shares'] if price and p['shares'] else None)))
        return render_template('positions.html', rows=view, closed=closed)

    @app.route('/positions/add', methods=['POST'])
    @login_required
    def positions_add():
        uid = session['user_id']
        raw_code = request.form.get('code', '').strip()
        try:
            code = normalize_code(raw_code)
            cost = float(request.form.get('cost', ''))
            if cost <= 0:
                raise ValueError
        except (AnalysisError, ValueError):
            flash('代码或成本价无效', 'error')
            return redirect(url_for('positions'))
        shares = request.form.get('shares', '').strip()
        try:
            shares = max(0, int(float(shares))) if shares else 0
        except ValueError:
            shares = 0
        stop_pct = _parse_pct(request.form.get('stop_pct'), 0.07)
        take_pct = _parse_pct(request.form.get('take_pct'), 0.15)
        trail_pct = _parse_pct(request.form.get('trail_pct'), 0.05)
        opened_at = request.form.get('opened_at', '').strip() or None
        note = request.form.get('note', '').strip() or None
        existing = db.get_watch(uid, code)
        name = (existing['name'] if existing else None)
        if not name:
            try:
                name = lookup_name(code)
            except Exception:
                name = None
        try:
            db.create_position(uid, code, cost, shares=shares, name=name,
                               stop_pct=stop_pct, take_pct=take_pct,
                               trail_pct=trail_pct, opened_at=opened_at, note=note)
            flash(f'已建仓 {name or code}，盘中监控自动布防', 'ok')
        except Exception:
            flash('该股票已有未平仓持仓，请先平仓再新建', 'error')
        return redirect(url_for('positions'))

    @app.route('/positions/close', methods=['POST'])
    @login_required
    def positions_close():
        pid = request.form.get('id', type=int)
        if pid and db.close_position(pid, session['user_id']):
            flash('已平仓', 'ok')
        else:
            flash('平仓失败：记录不存在或已平仓', 'error')
        return redirect(url_for('positions'))

    @app.route('/positions/delete', methods=['POST'])
    @login_required
    def positions_delete():
        pid = request.form.get('id', type=int)
        if pid and db.delete_position(pid, session['user_id']):
            flash('持仓记录已删除', 'ok')
        return redirect(url_for('positions'))

    @app.route('/alerts')
    @login_required
    def alerts():
        rows = db.list_alerts(session['user_id'], limit=100)
        return render_template('alerts.html', rows=rows,
                               type_names=db.ALERT_TYPES)

    # ---------------- 个股分析详情 ----------------

    @app.route('/analysis/<int:row_id>')
    @login_required
    def analysis_detail(row_id):
        row = db.get_analysis(row_id)
        if not row or row['user_id'] != session['user_id']:
            abort(404)
        indicators = db.parse_json_field(row['positive_indicators'], [])
        detail = db.parse_json_field(row['pattern_detail'], {})
        fail_reasons = db.parse_json_field(row['fail_reasons'], [])

        from stock_analyzer import NEUTRAL_INDICATORS
        positive = [i for i in indicators
                    if i not in NEUTRAL_INDICATORS and i not in TOP_SIGNALS]
        neutral = [i for i in indicators if i in NEUTRAL_INDICATORS and i not in TOP_SIGNALS]
        top_signals = [i for i in indicators if i in TOP_SIGNALS]

        # 底反弹九条件按 c1..c9 顺序展示
        conditions = sorted(
            ((k, v) for k, v in detail.items() if k.startswith('c')),
            key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 99)
        combos = detail.get('bullish_combo', [])
        extras = {k: v for k, v in detail.items()
                  if not k.startswith('c') and k != 'bullish_combo'}

        return render_template(
            'stock_detail.html', r=row, indicators=indicators,
            positive=positive, neutral=neutral, top_signals=top_signals,
            fail_reasons=fail_reasons, conditions=conditions,
            combos=combos, extras=extras,
            fund=db.parse_json_field(row['fund_json'], None),
            chip_data=db.parse_json_field(row['chip_json'], None))

    # ---------------- 推送设置 ----------------

    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        user = db.get_user_by_id(session['user_id'])
        if request.method == 'POST':
            push_type = request.form.get('push_type', '').strip() or None
            push_target = request.form.get('push_target', '').strip() or None
            db.update_push_config(session['user_id'], push_type, push_target)
            flash('推送配置已保存', 'ok')
            return redirect(url_for('settings'))
        return render_template('settings.html', user=user)

    @app.route('/settings/test', methods=['POST'])
    @login_required
    def settings_test():
        push_type = request.form.get('push_type', '').strip()
        push_target = request.form.get('push_target', '').strip()
        if not push_type or not push_target:
            return jsonify(ok=False, msg='请先选择渠道并填写 webhook/key')
        ok, msg = push_mod.send(push_type, push_target,
                                'chaogu 推送测试', '这是一条测试消息，收到说明配置成功。')
        return jsonify(ok=ok, msg=msg)

    # ---------------- 轻量状态接口（自选页轮询） ----------------

    @app.route('/api/analysis_status/<int:row_id>')
    @login_required
    def analysis_status(row_id):
        row = db.get_analysis(row_id)
        if not row or row['user_id'] != session['user_id']:
            return jsonify(ok=False), 404
        return jsonify(ok=True, status=row['status'],
                       redirect=url_for('analysis_detail', row_id=row_id)
                       if row['status'] in ('done', 'failed') else None)

    # 静态资源版本：取 style.css 修改时间，发版后自动破浏览器缓存
    try:
        _css_mtime = int(os.path.getmtime(
            os.path.join(os.path.dirname(__file__), 'static', 'style.css')))
    except OSError:
        _css_mtime = 0

    @app.context_processor
    def inject_user():
        uid = session.get('user_id')
        return {'current_username': session.get('username') if uid else None,
                'asset_ver': _css_mtime}

    @app.template_filter('fmtnum')
    def fmtnum(value, digits=2):
        try:
            return f'{float(value):.{digits}f}'
        except (TypeError, ValueError):
            return '—'

    return app
