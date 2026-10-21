#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""chaogu Web 服务启动入口

环境变量（均有默认值，可不设）：
  CHAOGU_PORT           监听端口，默认 8000
  CHAOGU_INVITE_CODE    注册邀请码，默认 chaogu2026
  CHAOGU_SECRET_KEY     session 密钥，默认持久化到 webapp/data/.secret_key
  CHAOGU_DISABLE_SCHEDULER=1  关闭盘后定时任务（调试用）

PowerShell 运行：
  $env:PYTHONPATH = "$PWD\.deps"; py -3 run_web.py
"""

import os
import sys
import logging

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

from webapp.app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('CHAOGU_PORT', '8000'))
    print('=' * 56)
    print(f'chaogu Web 已启动: http://127.0.0.1:{port}')
    print('首次使用请先注册（邀请码见 CHAOGU_INVITE_CODE，默认 chaogu2026）')
    print('=' * 56)
    app.run(host='0.0.0.0', port=port, debug=False)
