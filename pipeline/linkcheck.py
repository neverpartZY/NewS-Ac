# -*- coding: utf-8 -*-
"""轻量链接探活：HEAD 请求，只丢弃明确 404/410 的死链。

403/405/超时/连接错误一律视为「可用」——很多站拦自动请求返回 403（浏览器能开），
若据此丢弃会误杀正常链接，故只拿 404/410 这种明确「页面不存在」做判死依据。
"""
import concurrent.futures

import requests

import config

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _is_dead(url):
    if not url:
        return False
    try:
        r = requests.head(url, timeout=config.LINK_TIMEOUT, allow_redirects=True,
                          headers={"User-Agent": USER_AGENT})
        return r.status_code in (404, 410)
    except Exception:  # noqa: BLE001
        return False  # 无法判断 → 视为可用（保守，不误杀）


def drop_dead(docs):
    """对候选并发探活，返回 (alive, dead)。只丢 404/410。"""
    if not docs:
        return [], []
    urls = [d.url for d in docs]
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.LINK_WORKERS) as ex:
        flags = list(ex.map(_is_dead, urls))
    alive, dead = [], []
    for d, dead_flag in zip(docs, flags):
        (dead if dead_flag else alive).append(d)
    return alive, dead
