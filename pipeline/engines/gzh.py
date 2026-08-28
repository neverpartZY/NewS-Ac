# -*- coding: utf-8 -*-
"""公众号采集：weixinzs.org（mp-article-subscription）商业 API。

动态读订阅列表，逐号采当日/近 N 天文章；排除自家媒体（再生PET / 废塑料新观察 / 国嘉基业）。
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import config

from ..models import Candidate

BASE = "https://api.weixinzs.org/api"

# 自家媒体（自有公众号），采集后排除，绝不进日报正文。
OWN_MEDIA_BIZ = {
    "Mzg2ODc3MDUyMQ==": "再生PET",
    "MjM5MTM5NjM4NA==": "废塑料新观察",
    "MzcwNDQxMDU3MA==": "国嘉基业",
}
OWN_MEDIA_NAMES = ["再生PET", "废塑料新观察", "国嘉基业"]


def _key():
    k = config.get_key("WEIXINZS_API_KEY")
    if k:
        return k
    # 兜底读 mp-article-subscription skill 的 api_key.txt（多种技能目录位置）
    from pathlib import Path
    candidates = (
        Path.home() / ".openclaw" / "skills" / "mp-article-subscription" / "api_key.txt",
        Path.home() / ".workbuddy" / "skills" / "mp-article-subscription" / "api_key.txt",
        config.BASE_DIR / "mp-article-subscription" / "api_key.txt",
        config.BASE_DIR.parent / "mp-article-subscription" / "api_key.txt",
    )
    for cand in candidates:
        if cand.exists():
            return cand.read_text(encoding="utf-8").replace("﻿", "").strip()
    return ""


def _http_get(url, key):
    # 禁用代理：api.weixinzs.org 国内直连，走失效代理会 SSL 失败
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with opener.open(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _biz_from_url(url):
    if not url:
        return ""
    try:
        q = parse_qs(urlparse(url).query)
        return (q.get("__biz") or [""])[0]
    except Exception:  # noqa: BLE001
        return ""


def _is_own_media(name, biz=""):
    b = (biz or "").strip()
    if b and b in OWN_MEDIA_BIZ:
        return True
    n = (name or "").strip()
    if not n:
        return False
    return any(n.startswith(om) for om in OWN_MEDIA_NAMES)


def _subscribed(key):
    data = _http_get(BASE + "/v1/subscriptions", key)
    out = []
    for s in data:
        if s.get("status") not in ("following", "processing"):
            continue
        name = (s.get("account") or {}).get("nickname", "") or ""
        if _is_own_media(name):
            continue
        out.append({"id": str(s.get("id", "")), "name": name})
    return out


def collect(days=3):
    """采近 days 天公众号文章。返回 list[Candidate]。"""
    key = _key()
    if not key:
        return []
    try:
        gzhs = _subscribed(key)
    except Exception as e:  # noqa: BLE001
        print(f"  [gzh] 订阅列表获取失败: {e}")
        return []
    if not gzhs:
        return []
    end = datetime.now()
    start = end - timedelta(days=days)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    docs = []
    for g in gzhs:
        url = f"{BASE}/v1/articles?subscriptionId={g['id']}&startDate={start_s}&endDate={end_s}&pageSize=50"
        try:
            data = _http_get(url, key)
            arr = data.get("articles") or data.get("data") or data.get("list") or []
            for a in arr:
                aurl = a.get("url") or a.get("articleUrl") or a.get("link") or ""
                biz = _biz_from_url(aurl)
                if _is_own_media(g["name"], biz):
                    continue
                docs.append(Candidate(
                    title=a.get("title") or a.get("articleTitle") or "",
                    url=aurl,
                    date=(a.get("publishTime") or a.get("publishedAt") or a.get("createdAt") or "")[:10],
                    site=g["name"],
                    snippet="",
                    engine="gzh",
                    lang="zh",
                ))
        except Exception as e:  # noqa: BLE001
            print(f"  [gzh] {g['name']} 采集失败: {e}")
        time.sleep(0.3)
    return docs
