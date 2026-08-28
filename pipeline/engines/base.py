# -*- coding: utf-8 -*-
"""采集引擎共享工具与候选数据结构。"""
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

import requests

# 社交媒体站点（非新闻源，降噪过滤）
SOCIAL_SITES = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "x.com", "youtube.com", "tiktok.com", "reddit.com", "medium.com",
)


def site_from_url(url):
    try:
        return urlparse(url or "").netloc
    except Exception:  # noqa: BLE001
        return ""


def is_social(url):
    return any(s in (site_from_url(url) or "").lower() for s in SOCIAL_SITES)


def http_post(url, headers, body, timeout=30):
    """用 urllib 直发 POST（与旧实现一致，可控代理）。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code}
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}


def http_post_req(url, headers, body, timeout=30):
    """requests 版 POST（备用，走系统代理）。"""
    try:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code != 200:
            return {"__http_error__": r.status_code, "__text__": r.text[:200]}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}
