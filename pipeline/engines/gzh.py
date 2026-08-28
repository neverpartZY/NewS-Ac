# -*- coding: utf-8 -*-
"""公众号采集：weixinzs.org（mp-article-subscription）商业 API。

动态读订阅列表，逐号采当日/近 N 天文章；排除自家媒体（再生PET / 废塑料新观察 / 国嘉基业）。
"""
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html import unescape as _html_unescape
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


# ---- 正文抓取（weixinzs 接口不带摘要，当天热点必须有正文才能过相关性判断/进日报）----

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _html_to_text(html):
    """微信文章 HTML → 纯文本（去 script/style/标签、解实体、压空白）。"""
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", html)
    html = re.sub(r"<[^>]+>", " ", html)
    text = _html_unescape(html)
    return re.sub(r"\s+", " ", text).strip()


def fetch_content(url, timeout=15):
    """抓取公众号文章正文纯文本（前 800 字）。失败返回空串（不抛异常）。"""
    if not url:
        return ""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 微信直连
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        raw = opener.open(req, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    i = raw.find("js_content")  # 微信正文容器，从其后的标签内容取正文
    if i > 0:
        raw = raw[i:]
    return _html_to_text(raw)[:800]


def enrich_same_day(docs, workers=10):
    """给当天的公众号候选抓正文填 snippet（只抓当天，控制抓取量）。"""
    today = config.today_str()
    todo = [d for d in docs if d.engine == "gzh" and (d.date or "")[:10] == today and d.url]
    if not todo:
        return docs
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for d, t in zip(todo, ex.map(fetch_content, [d.url for d in todo])):
            if t:
                d.snippet = t[:500]
    return docs
