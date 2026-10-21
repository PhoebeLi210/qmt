#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消息推送（飞书自定义机器人 / 钉钉自定义机器人 / Bark）

配置只保存每个用户自己的 webhook 或 Bark key；推送内容互不可见。
"""

import logging
from urllib.parse import quote

import requests

logger = logging.getLogger('webapp.push')

TIMEOUT = 8

DISCLAIMER = '【模型信号仅供参考，非投资建议，买卖决策与风险由本人承担】'


def send(push_type, push_target, title, content):
    """统一发送入口。

    push_type: feishu / dingtalk / bark
    push_target: 飞书/钉钉为机器人 webhook 完整 URL；Bark 为 app key
    返回 (ok: bool, msg: str)
    """
    text = f'{title}\n\n{content}\n\n{DISCLAIMER}'
    try:
        if push_type == 'feishu':
            return _send_feishu(push_target, text)
        if push_type == 'dingtalk':
            return _send_dingtalk(push_target, text)
        if push_type == 'bark':
            return _send_bark(push_target, title, f'{content}\n\n{DISCLAIMER}')
        return False, '未配置推送渠道'
    except requests.RequestException as e:
        logger.warning(f'推送失败({push_type}): {e}')
        return False, f'网络错误: {e}'


def _send_feishu(webhook, text):
    resp = requests.post(webhook, json={'msg_type': 'text', 'content': {'text': text}},
                         timeout=TIMEOUT)
    data = resp.json()
    # 飞书成功 code=0；若机器人开启了签名校验会返回 19021，提示用户改用关键词或IP白名单
    if data.get('code', 0) == 0:
        return True, 'ok'
    return False, f"飞书返回: {data.get('msg') or data}"


def _send_dingtalk(webhook, text):
    resp = requests.post(webhook, json={'msgtype': 'text', 'text': {'content': text}},
                         timeout=TIMEOUT)
    data = resp.json()
    if data.get('errcode', 0) == 0:
        return True, 'ok'
    return False, f"钉钉返回: {data.get('errmsg') or data}"


def _send_bark(key, title, body):
    url = f'https://api.day.app/{key}/{quote(title)}/{quote(body)}'
    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code == 200:
        return True, 'ok'
    return False, f'Bark HTTP {resp.status_code}'


def push_to_user(user, title, content):
    """按用户配置推送；未配置则跳过。user 为 users 表行"""
    push_type = user['push_type'] if isinstance(user, dict) else user['push_type']
    push_target = user['push_target'] if isinstance(user, dict) else user['push_target']
    if not push_type or not push_target:
        return False, '未配置推送渠道'
    return send(push_type, push_target, title, content)
