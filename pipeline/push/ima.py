# -*- coding: utf-8 -*-
"""IMA 知识库上传 —— 由 ima-mcp MCP 连接器完成，不在本 Python 程序内执行。

独立 Python 程序无法直接调用 Claude Code 的 MCP 工具，故此处只做「交接提示」：
日报生成后，在 Claude Code 会话内通过 ima-mcp 连接器上传到
「国嘉基业·LLM Wiki」（id 7457220757303832）的 workbuddy 日报文件夹（folder 7471548801773576）。
"""


def send_report(report_name, markdown, date_str=""):
    return {"status": "handoff",
            "reason": "IMA 上传走 ima-mcp MCP 连接器（Claude Code 会话内执行），本程序不负责"}
