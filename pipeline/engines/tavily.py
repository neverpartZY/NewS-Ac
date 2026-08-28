# -*- coding: utf-8 -*-
"""Tavily AI 搜索采集（news 模式）。"""
import config
from ..models import Candidate
from .base import http_post, is_social

HOST = "https://api.tavily.com/search"


def search(query, days, lang="zh"):
    """返回 list[Candidate]：{title,url,date,site,snippet,engine='tavily',lang}。"""
    key = config.get_key("TAVILY_API_KEY")
    if not key:
        return []
    body = {
        "api_key": key,
        "query": query,
        "topic": "news",
        "max_results": config.MAX_RESULTS_PER_QUERY,
        "search_depth": "basic",
        "days": min(days, 7),  # Tavily time 窗口
    }
    headers = {"Content-Type": "application/json"}
    r = http_post(HOST, headers, body)
    if "__http_error__" in r or "__error__" in r:
        return []
    docs = []
    for it in (r.get("results") or []):
        url = it.get("url", "")
        if is_social(url):
            continue
        docs.append(Candidate(
            title=it.get("title", ""),
            url=url,
            date=it.get("published_date", ""),
            site="",
            snippet=(it.get("content", "") or "")[:300],
            engine="tavily",
            lang=lang,
        ))
    return docs
