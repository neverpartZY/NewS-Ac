# -*- coding: utf-8 -*-
"""LLM（DeepSeek / OpenAI 兼容）与 Embedding（SiliconFlow bge-m3）客户端。"""
import json
import os
import time

import requests

import config

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

# ---- 统一 fail-soft 契约（P1-3）----
# LLM 不可用或调用失败时，各环节一律「保守保留原始数据 + 标注降级」，绝不静默丢弃：
#   - 相关性判断失败  → 保留候选（靠关键词/后续环节兜底）
#   - 加工(refine)失败 → 用原标题/摘要兜底，不丢条目
#   - 报告生成失败    → 输出降级版（候选清单），不产出空文件
# 判断 LLM 是否可用的唯一入口是 available()；判断单次结果是否失败用 is_error()。


def available() -> bool:
    """LLM 是否可用（已配 key）。"""
    return bool(config.LLM_API_KEY)


def is_error(result) -> bool:
    """判断 chat()/embed() 的返回是否为失败标记。"""
    return isinstance(result, dict) and ("__error__" in result or "__http_error__" in result)


def _post_json(url, headers, body, timeout=60):
    try:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code != 200:
            return {"__error__": f"HTTP {r.status_code}: {r.text[:200]}"}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}


def chat(messages, temperature=0.2, max_tokens=2500, json_mode=False, retries=3):
    """调用 LLM，返回文本内容。json_mode=True 时要求返回纯 JSON。"""
    if not config.LLM_API_KEY:
        return {"__error__": "LLM_API_KEY/DEEPSEEK_API_KEY 未配置"}
    url = f"{config.LLM_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    for attempt in range(retries):
        r = _post_json(url, headers, payload)
        if "__error__" in r:
            time.sleep(1 + attempt)
            continue
        try:
            return r["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            time.sleep(1 + attempt)
    return {"__error__": "LLM 调用失败"}


def chat_json(messages, temperature=0.1, max_tokens=3000, retries=3):
    """调用 LLM 并解析 JSON；失败返回 None。"""
    out = chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True, retries=retries)
    if isinstance(out, dict):
        return None
    return _parse_json(out)


def _parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        # 尝试截取首个 { ... } 块
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:  # noqa: BLE001
                return None
        return None


def embed(texts):
    """bge-m3 嵌入，返回 list[list[float]]（1024 维）。"""
    key = config.get_key("SILICONFLOW_API_KEY")
    if not key:
        return None
    if not texts:
        return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": EMBED_MODEL, "input": texts, "encoding_format": "float"}
    r = _post_json(EMBED_URL, headers, body)
    if "__error__" in r:
        return None
    data = r.get("data", [])
    data.sort(key=lambda x: x.get("index", 0))
    return [d.get("embedding", []) for d in data]


def embed_one(text):
    vecs = embed([text])
    return vecs[0] if vecs else None
