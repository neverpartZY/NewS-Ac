# -*- coding: utf-8 -*-
"""Serper（Google 官方索引）采集。"""
import config
from ..models import Candidate
from .base import http_post, is_social, site_from_url

HOST = "https://google.serper.dev/search"


def search(query, days, lang="zh"):
    """返回 list[Candidate]：{title,url,date,site,snippet,engine='serper',lang}。"""
    key = config.get_key("SERPER_API_KEY")
    if not key:
        return []
    tbs = "qdr:d" if days <= 1 else ("qdr:w" if days <= 7 else "qdr:m")
    headers = {"X-API-KEY": key, "Content-Type": "application/json"}
    body = {
        "q": query,
        "num": config.MAX_RESULTS_PER_QUERY,
        "tbs": tbs,
        "gl": "cn" if lang == "zh" else "us",
        "hl": "zh-cn" if lang == "zh" else "en",
    }
    r = http_post(HOST, headers, body)
    if "__http_error__" in r or "__error__" in r:
        return []
    docs = []
    for it in (r.get("organic") or []):
        link = it.get("link", "")
        site = it.get("source", "") or site_from_url(link)
        if is_social(link):
            continue
        docs.append(Candidate(
            title=it.get("title", ""),
            url=link,
            date=it.get("date", ""),
            site=site,
            snippet=(it.get("snippet", "") or "")[:300],
            engine="serper",
            lang=lang,
        ))
    return docs
