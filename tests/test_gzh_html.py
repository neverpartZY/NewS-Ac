# -*- coding: utf-8 -*-
"""公众号正文抓取的文本清洗单测（纯函数，不联网）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.engines.gzh import _html_to_text  # noqa: E402


def test_html_to_text_strips_scripts_and_tags():
    html = ('<div><script>var x=1;</script><p>再生塑料价格</p>'
            '<style>.a{color:red}</style><b>上涨</b><!--注释--></div>')
    assert _html_to_text(html) == "再生塑料价格 上涨"


def test_html_to_text_unescapes_and_collapses():
    html = "<p>惠城环保&nbsp;&amp;东粤化学</p>\n<p>20万吨装置</p>"
    assert _html_to_text(html) == "惠城环保 &东粤化学 20万吨装置"


def test_html_to_text_empty():
    assert _html_to_text("") == ""
