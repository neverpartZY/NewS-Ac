# -*- coding: utf-8 -*-
"""SQLite「已收录列表」+ embedding 持久化（语义去重的记忆库）。"""
import hashlib
import json
import sqlite3
from datetime import datetime

import numpy as np

import config
from .models import Article

DB_PATH = config.DATA_DIR / "news.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url_hash     TEXT PRIMARY KEY,
    title        TEXT,
    title_zh     TEXT,
    summary_zh   TEXT,
    category     TEXT,
    scope        TEXT,          -- chemical / rpet / general
    importance   INTEGER,
    tags         TEXT,          -- JSON array
    source       TEXT,
    site         TEXT,
    url          TEXT,
    published_at TEXT,
    collected_at TEXT,
    embedding    BLOB,          -- float32 向量
    is_price     INTEGER DEFAULT 0
);
"""


def url_hash(url):
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:32]


def _conn():
    config.ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def url_exists(h):
    with _conn() as conn:
        cur = conn.execute("SELECT 1 FROM articles WHERE url_hash = ?", (h,))
        return cur.fetchone() is not None


def insert(article: Article):
    emb = article.embedding
    emb_blob = np.asarray(emb, dtype=np.float32).tobytes() if emb else None
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO articles
            (url_hash, title, title_zh, summary_zh, category, scope, importance, tags,
             source, site, url, published_at, collected_at, embedding, is_price)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                article.url_hash,
                article.title,
                article.title_zh,
                article.summary_zh,
                article.category,
                article.scope,
                article.importance,
                json.dumps(article.tags, ensure_ascii=False),
                article.source,
                article.site,
                article.url,
                article.published_at,
                article.collected_at,
                emb_blob,
                1 if article.is_price else 0,
            ),
        )
        conn.commit()


def load_for_dedup():
    """载入全部已收录条目，供语义去重比对。返回 list[dict]，每个含 embedding(numpy)。"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT url_hash, title, title_zh, summary_zh, url, embedding FROM articles"
        ).fetchall()
    out = []
    for h, title, title_zh, summary_zh, url, emb_blob in rows:
        emb = np.frombuffer(emb_blob, dtype=np.float32) if emb_blob else None
        out.append({
            "url_hash": h, "title": title or "", "title_zh": title_zh or "",
            "summary_zh": summary_zh or "", "url": url or "", "embedding": emb,
        })
    return out


def load_articles(since_date=""):
    """载入已收录条目为 Article 列表（可选按采集日期 collected_at >= since_date 过滤）。"""
    sql = ("SELECT url_hash, title, title_zh, summary_zh, category, scope, importance, tags, "
           "source, site, url, published_at, collected_at, embedding, is_price FROM articles")
    params = ()
    if since_date:
        sql += " WHERE collected_at >= ?"
        params = (since_date,)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        emb = np.frombuffer(r[13], dtype=np.float32).tolist() if r[13] else None
        out.append(Article(
            url_hash=r[0], title=r[1], title_zh=r[2], summary_zh=r[3],
            category=r[4], scope=r[5], importance=r[6], tags=json.loads(r[7] or "[]"),
            source=r[8], site=r[9], url=r[10], published_at=r[11], collected_at=r[12],
            embedding=emb, is_price=bool(r[14]),
        ))
    return out


def count():
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


def recent_urls(days=14):
    """近 N 天收录的 URL（快速黑名单，可选）。"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT url FROM articles WHERE collected_at >= ?",
            ((datetime.now().strftime("%Y-%m-%d")),),
        ).fetchall()
    return {r[0] for r in rows if r[0]}
