# -*- coding: utf-8 -*-
"""源站定向采集：对 sources_config.json 里的行业源站做 site: 定向搜索（走 Serper）。"""
import config
from . import serper as serper_engine


def collect():
    """返回 list[Candidate]。只跑 D1/D2 高频源站，避免一轮请求爆炸。"""
    docs = []
    for s in config.SOURCE_SITES:
        freq = s.get("freq", "D3")
        if freq not in ("D1", "D2"):
            continue
        site = s.get("site", "")
        kw = s.get("kw", "")
        if not site:
            continue
        q = f"site:{site} {kw}"
        lang = "zh" if _is_cn_site(site) else "en"
        docs += serper_engine.search(q, config.FRESH_DAYS, lang=lang)
    return docs


def _is_cn_site(site):
    return any(t in site for t in (".cn", ".org.cn", ".com.cn", "gov.cn", "mee.gov", "miit.gov", "ndrc.gov", "mofcom.gov"))
