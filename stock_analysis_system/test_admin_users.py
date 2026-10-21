# -*- coding: utf-8 -*-
"""账号管理功能测试：期限拦截、管理员权限、账号 CRUD 与级联删除"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from webapp import db


class AdminUsersTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db.DATA_DIR = self.tmpdir.name
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False, dir=self.tmpdir.name)
        self.tmp.close()
        db.DB_PATH = self.tmp.name
        os.environ['CHAOGU_DISABLE_SCHEDULER'] = '1'
        db.init_db()
        # 首个用户自动成为管理员
        self.admin_id = db.create_user('admin1', generate_password_hash('secret1'))
        db.init_db()  # 幂等：再次迁移不应重复/报错
        from webapp.app import create_app
        self.app = create_app(start_jobs=False)
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        import gc
        self.app = None
        self.client = None
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass
        try:
            self.tmpdir.cleanup()
        except OSError:
            pass

    def login(self, username, password):
        return self.client.post('/login',
                                data={'username': username, 'password': password},
                                follow_redirects=False)

    def test_first_user_auto_admin(self):
        u = db.get_user_by_id(self.admin_id)
        self.assertEqual(u['is_admin'], 1)

    def test_register_closed(self):
        resp = self.client.get('/register')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])
        resp = self.client.post('/register',
                                data={'username': 'x', 'password': 'yyyyyy'})
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(db.get_user_by_name('x'))

    def test_admin_page_requires_admin(self):
        # 普通用户访问 403
        db.create_user('normal', generate_password_hash('secret1'), expires_at=None)
        self.login('normal', 'secret1')
        resp = self.client.get('/admin')
        self.assertEqual(resp.status_code, 403)

    def test_admin_sees_page_and_creates_user(self):
        self.login('admin1', 'secret1')
        resp = self.client.get('/admin')
        self.assertEqual(resp.status_code, 200)
        expiry = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')
        resp = self.client.post('/admin/user/create', data={
            'username': 'newbie', 'password': 'pw1234', 'expires_at': expiry})
        self.assertEqual(resp.status_code, 302)
        u = db.get_user_by_name('newbie')
        self.assertIsNotNone(u)
        self.assertEqual(u['expires_at'], expiry)
        self.assertEqual(u['is_admin'], 0)

    def test_create_duplicate_user_rejected(self):
        self.login('admin1', 'secret1')
        resp = self.client.post('/admin/user/create', data={
            'username': 'admin1', 'password': 'pw1234', 'expires_at': ''})
        self.assertEqual(resp.status_code, 302)

    def test_expired_user_cannot_login(self):
        past = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        db.create_user('expired', generate_password_hash('secret1'), expires_at=past)
        resp = self.login('expired', 'secret1')
        self.assertEqual(resp.status_code, 200)  # 停在登录页
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    def test_expiry_enforced_after_login(self):
        # 登录时有效，登录后被管理员改为过期 → 下次请求被踢
        future = (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')
        uid = db.create_user('later', generate_password_hash('secret1'), expires_at=future)
        self.login('later', 'secret1')
        self.assertEqual(self.client.get('/watchlist').status_code, 200)
        db.set_user_expiry(uid, (date.today() - timedelta(days=2)).strftime('%Y-%m-%d'))
        resp = self.client.get('/watchlist')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

    def test_today_is_last_valid_day(self):
        # 到期当日仍可登录，次日才拦截
        today = date.today().strftime('%Y-%m-%d')
        db.create_user('edge', generate_password_hash('secret1'), expires_at=today)
        resp = self.login('edge', 'secret1')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/recommendations', resp.headers['Location'])

    def test_admin_never_expires(self):
        past = (date.today() - timedelta(days=10)).strftime('%Y-%m-%d')
        # 管理员即便误设期限也不受限
        db.set_user_expiry(self.admin_id, past)
        resp = self.login('admin1', 'secret1')
        self.assertEqual(resp.status_code, 302)

    def test_set_expiry_and_reset_password(self):
        self.login('admin1', 'secret1')
        uid = db.create_user('bob', generate_password_hash('oldpw12'))
        new_exp = (date.today() + timedelta(days=90)).strftime('%Y-%m-%d')
        self.client.post('/admin/user/expiry',
                         data={'user_id': uid, 'expires_at': new_exp})
        self.assertEqual(db.get_user_by_id(uid)['expires_at'], new_exp)
        # 设为永久
        self.client.post('/admin/user/expiry',
                         data={'user_id': uid, 'expires_at': ''})
        self.assertIsNone(db.get_user_by_id(uid)['expires_at'])
        # 重置密码后新密码可登录
        self.client.post('/admin/user/password',
                         data={'user_id': uid, 'password': 'newpw99'})
        self.assertIsNotNone(self.login('bob', 'newpw99'))

    def test_cannot_delete_self_or_last_admin(self):
        self.login('admin1', 'secret1')
        resp = self.client.post('/admin/user/delete',
                                data={'user_id': self.admin_id})
        self.assertEqual(resp.status_code, 302)
        self.assertIsNotNone(db.get_user_by_id(self.admin_id))
        # 第二个管理员，删除原管理员仍被阻止（删后将无管理员）
        uid2 = db.create_user('admin2', generate_password_hash('secret1'), is_admin=1)
        resp = self.client.post('/admin/user/delete',
                                data={'user_id': self.admin_id})
        self.assertIsNotNone(db.get_user_by_id(self.admin_id))
        # admin2 可被删除（admin1 仍在）
        self.client.post('/admin/user/delete', data={'user_id': uid2})
        self.assertIsNone(db.get_user_by_id(uid2))

    def test_delete_cascades_private_data(self):
        self.login('admin1', 'secret1')
        uid = db.create_user('victim', generate_password_hash('secret1'))
        db.add_watch(uid, 'sh.600000', '浦发银行')
        db.create_position(uid, 'sh.600000', cost=10.0)
        today = date.today().strftime('%Y-%m-%d')
        db.upsert_analysis_row(uid, 'sh.600000', today, '浦发银行', 'done')
        self.client.post('/admin/user/delete', data={'user_id': uid})
        self.assertIsNone(db.get_user_by_id(uid))
        self.assertEqual(db.list_watch(uid), [])
        rows, _closed = db.list_positions(uid)
        self.assertEqual(len(rows), 0)
        with db.get_db() as conn:
            n_ar = conn.execute(
                'SELECT COUNT(*) FROM analysis_results WHERE user_id=?', (uid,)).fetchone()[0]
            n_al = conn.execute(
                'SELECT COUNT(*) FROM alerts WHERE user_id=?', (uid,)).fetchone()[0]
        self.assertEqual(n_ar, 0)
        self.assertEqual(n_al, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
