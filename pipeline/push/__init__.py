# -*- coding: utf-8 -*-
"""推送层：每路独立可插拔，缺 key 则跳过并告警，不阻塞其它路。"""
from . import email, ima, wechat_draft, wecom


def push_all(reports, date_str=""):
    """reports: dict[report_name -> markdown]。逐路推送，返回各通道状态。"""
    results = {}
    for name, md in reports.items():
        results[name] = {}
        results[name]["email"] = email.send_report(name, md, date_str)
        results[name]["wecom"] = wecom.send_report(name, md)
        results[name]["ima"] = ima.send_report(name, md)
        results[name]["wechat_draft"] = wechat_draft.send_report(name, md)
    return results
