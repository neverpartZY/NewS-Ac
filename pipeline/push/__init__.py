# -*- coding: utf-8 -*-
"""推送层：每路独立可插拔，缺 key 则跳过并告警，不阻塞其它路。"""
from . import email, ima, wechat_draft, wecom


def push_all(reports, date_str=""):
    """reports: dict[report_name -> markdown]。逐路推送，返回各通道状态。

    邮件通道：全部报告合并为一封合刊（email.send_merged，一次只发一封）；
    企微/IMA/公众号仍逐报推送（各自独立建文档/发群）。
    """
    results = {}
    for name, md in reports.items():
        results[name] = {
            "wecom": wecom.send_report(name, md),
            "ima": ima.send_report(name, md),
            "wechat_draft": wechat_draft.send_report(name, md),
        }
    results["邮件合刊"] = {"email": email.send_merged(reports, date_str)}
    return results
