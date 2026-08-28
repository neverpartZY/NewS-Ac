# -*- coding: utf-8 -*-
"""链接探活单测：只判 404/410 为死链，其余（403/200/超时）视为可用。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import linkcheck  # noqa: E402


class _Resp:
    def __init__(self, code):
        self.status_code = code


def test_is_dead_codes(monkeypatch):
    import requests

    def fake_head(url, **kwargs):
        return _Resp({"a": 404, "b": 410, "c": 403, "d": 200}[url])

    monkeypatch.setattr(requests, "head", fake_head)
    assert linkcheck._is_dead("a") is True
    assert linkcheck._is_dead("b") is True
    assert linkcheck._is_dead("c") is False  # 反爬 403 不判死
    assert linkcheck._is_dead("d") is False


def test_is_dead_timeout_kept(monkeypatch):
    import requests

    def fake_head_timeout(url, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "head", fake_head_timeout)
    assert linkcheck._is_dead("http://x") is False
