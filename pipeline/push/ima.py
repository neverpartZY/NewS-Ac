# -*- coding: utf-8 -*-
"""IMA 知识库推送 —— 交接模式（唯一路径，用户 2026-08-28 定案：选一个稳定的就好）。

生成 ima_handoff.json（目标库 + 完整 markdown），由服务器 OpenClaw 的 ima-mcp
连接器（团队账号，可达国嘉基业·LLM Wiki）执行上传——即旧系统的稳定链路。
Python 程序不做直连上传（原直连实现见 git 历史，可随时找回）。
"""
import json

import config


def _handoff(report_name, markdown, date_str):
    out = config.REPORT_DIR / f"{report_name}_{date_str}_ima_handoff.json"
    out.write_text(json.dumps({
        "tool": "ima-mcp 上传（服务器 OpenClaw，团队账号）",
        "kb_id": config.get_key("IMA_KB_ID") or "cbS6_lBGSoDYC6oH9t2e-7yN6SbUQkGodQAstAulh5s=",
        "folder_id": config.get_key("IMA_FOLDER_ID") or "7471548801773576",
        "file_name": f"{report_name}_{date_str}.md",
        "content_markdown": markdown,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def send_report(report_name, markdown, date_str=""):
    date_str = date_str or config.today_str()
    p = _handoff(report_name, markdown, date_str)
    return {"status": "handoff",
            "reason": f"已生成交接文件 {p.name}（服务器 OpenClaw ima-mcp 上传 → 国嘉基业·LLM Wiki）"}
