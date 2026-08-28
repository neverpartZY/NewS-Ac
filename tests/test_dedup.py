# -*- coding: utf-8 -*-
"""去重层纯函数单测（numpy 余弦、URL hash，不依赖 LLM/embedding）。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import dedup, storage  # noqa: E402


def test_url_hash_stable():
    assert storage.url_hash("https://example.com/a") == storage.url_hash("https://example.com/a")
    assert storage.url_hash("https://example.com/a") != storage.url_hash("https://example.com/b")
    assert len(storage.url_hash("https://example.com/a")) == 32


def test_cosine_identical_and_orthogonal():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    matrix = np.array([b, c], dtype=np.float32)
    sims = dedup._cosine(a, matrix)
    assert sims[0] > 0.99
    assert abs(sims[1]) < 0.001


def test_cosine_semantic_threshold_shape():
    # 仅验证函数形状与数值范围，不测真实语义
    q = np.random.rand(128).astype(np.float32)
    m = np.random.rand(10, 128).astype(np.float32)
    sims = dedup._cosine(q, m)
    assert sims.shape == (10,)
    assert ((sims >= -1.0) & (sims <= 1.0)).all()
