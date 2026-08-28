# -*- coding: utf-8 -*-
"""语义去重：URL 精确 → embedding 余弦 → LLM 临界仲裁（对已收录列表）。

核心要求落地：不能只按标题相同判断，换标题/换角度报道同一事件也要被识别。
"""
import numpy as np

import config
from . import llm, storage
from .models import Candidate

ARBITRATE_SYS = (
    "你是新闻去重仲裁官。判断两条新闻是否报道「同一事件/同一事实」，即使标题措辞不同、"
    "来源不同、角度不同，只要核心事实相同就判为重复。只输出 JSON："
    "{\"duplicate\":true/false,\"reason\":\"一句话\"}"
)


def exact_dedup(docs):
    """URL 精确去重：对库内已存在的 url_hash 直接丢弃。"""
    kept, skipped = [], 0
    for d in docs:
        if not d.url:
            skipped += 1
            continue
        h = storage.url_hash(d.url)
        if storage.url_exists(h):
            skipped += 1
            continue
        d.url_hash = h
        kept.append(d)
    return kept, skipped


def _embed_docs(docs):
    texts = [(d.title + " " + d.snippet)[:600] for d in docs]
    vecs = llm.embed(texts)
    if vecs is None:
        return None
    for d, v in zip(docs, vecs):
        d.embedding = v
    return docs


def semantic_dedup(docs):
    """对候选 docs 做语义去重（对已收录列表）。返回 (keep, duplicates)。

    - embedding 失败：保守保留（不因去重能力缺失而丢新闻）。
    - sim ≥ 0.88 判重；0.72~0.88 交 LLM 仲裁；< 0.72 新内容。
    """
    if not docs:
        return [], []
    stored = storage.load_for_dedup()
    stored_vecs = np.array([s["embedding"] for s in stored if s.get("embedding") is not None],
                           dtype=np.float32) if stored else np.empty((0, 0), dtype=np.float32)
    stored_meta = [s for s in stored if s.get("embedding") is not None]

    keep, dups = [], []
    for d in docs:
        vec = d.embedding
        if vec is None or stored_vecs.shape[0] == 0:
            keep.append(d)
            continue
        q = np.asarray(vec, dtype=np.float32)
        sims = _cosine(q, stored_vecs)
        if sims.size == 0:
            keep.append(d)
            continue
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim >= config.DEDUP_HIGH:
            d.dup_sim = best_sim
            dups.append(d)
            continue
        if best_sim >= config.DEDUP_LOW:
            if _arbitrate(d, stored_meta[best_idx]):
                d.dup_sim = best_sim
                dups.append(d)
                continue
        keep.append(d)
    return keep, dups


def dedup(docs):
    """完整去重：URL 精确 + embedding 语义 + LLM 临界仲裁。返回 (keep, dups, skipped_exact)。"""
    docs, skipped = exact_dedup(docs)
    _embed_docs(docs)
    keep, dups = semantic_dedup(docs)
    return keep, dups, skipped


def _cosine(q, matrix):
    qn = q / (np.linalg.norm(q) + 1e-9)
    mn = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return mn @ qn


def _arbitrate(new, old):
    """LLM 仲裁临界重复：比较两条新闻是否同一事件。fail-soft：LLM 不可用 → 保守保留。"""
    if not llm.available():
        return False
    prompt = (
        f"新闻A（新候选）：\n标题：{new.title}\n摘要：{(new.snippet or '')[:300]}\n\n"
        f"新闻B（已收录）：\n标题：{old.get('title_zh') or old.get('title', '')}\n"
        f"摘要：{(old.get('summary_zh') or '')[:300]}"
    )
    out = llm.chat_json([
        {"role": "system", "content": ARBITRATE_SYS},
        {"role": "user", "content": prompt},
    ], max_tokens=500)
    if not out:
        return False
    return bool(out.get("duplicate"))
