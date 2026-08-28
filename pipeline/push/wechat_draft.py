# -*- coding: utf-8 -*-
"""公众号草稿箱 —— 交接型通道（白名单服务器中转），不在本机直连。

真实流程（见 gjb-wechat-draft skill）：
  1. 本地 `wechat-mp/publish.py draft` 把 markdown 排成微信兼容 HTML（3 套 CSS 风格）
  2. scp HTML + 封面图 + publish_meta.json 到白名单服务器 43.128.140.186
  3. ssh 跑 `publish_article_multi.py publish_meta.json` → 只建草稿、不发表

本模块只负责：按分报→公众号映射生成 publish_meta.json 交接文件，并输出 scp/ssh 指令。
AppSecret 只在服务器 wx_accounts.json，本地不接触明文。
"""
import json

import config


def send_report(report_name, markdown, date_str=""):
    mp_account = config.REPORT_MP_MAP.get(report_name)
    if not mp_account:
        return {"status": "skip", "reason": f"{report_name} 无公众号映射"}
    meta = {
        "mp_account": mp_account,
        "content_html": "debug-final.html",
        "cover_img": "cover.png",
        "body_img": "正文图.png",
        "body_rel": "./正文图.png",
        "title": f"{report_name} · {date_str or '今日'}",
        "author": "塑料循环经济日报",
        "digest": markdown[:100].replace("\n", " "),
    }
    out = config.REPORT_DIR / f"{report_name}_{date_str or 'today'}_publish_meta.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "handoff",
            "reason": f"公众号草稿箱走 gjb-wechat-draft 白名单服务器中转；已生成 {out.name}",
            "meta_file": str(out),
            "hint": (f"排版后 scp {out.name} + debug-final.html + cover.png 到 "
                     f"{config.WECHAT_RELAY_HOST}，再 ssh 跑 publish_article_multi.py")}
