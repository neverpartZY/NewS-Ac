# -*- coding: utf-8 -*-
"""推送状态记录：防止重复推送 / 支持降级后的精准补推。

状态文件 reports/push_state_<日期>.json，结构：
  {报告名: {通道: {"status": ..., ...其它字段}}}

用法（email/wecom 的 send_report）：
  prev = state.get(date, report, channel)   # 今日该通道已发过什么
  ...发送后 state.record(date, report, channel, status=..., doc_url=...)
"""
import json

import config


def _path(date_str):
    return config.REPORT_DIR / f"push_state_{date_str}.json"


def load(date_str):
    try:
        return json.loads(_path(date_str).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 文件不存在/损坏 → 视为无状态
        return {}


def get(date_str, report_name, channel):
    return load(date_str).get(report_name, {}).get(channel)


def record(date_str, report_name, channel, **fields):
    data = load(date_str)
    data.setdefault(report_name, {})[channel] = fields
    _path(date_str).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
