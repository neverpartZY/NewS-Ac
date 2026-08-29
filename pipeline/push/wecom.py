# -*- coding: utf-8 -*-
"""企业微信推送：智能文档链接模式（铁律：任何情况不发全文长文本）。

主路径（服务器已实测 2026-08-29）：
  wecom-cli smartpage import 建智能文档 → 群机器人 webhook 发「标题+摘要+📄链接」短消息
  - 服务器安装：npm install -g @wecom/cli（二进制在 ~/.npm-global/bin，node 在 nvm bin，
    代码自动注入 PATH，cron 窄 PATH 也可用）
  - 授权一次：wecom-cli auth init --noninteractive（企业微信扫码）

降级路径（CLI 未装/未授权）：只发 webhook 短消息（标题+摘要+完整版见邮件），
并生成智能文档交接文件 reports/*_wecom_handoff.json（供 OpenClaw agent 创建）。
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import config
from .base_push import http_post_json

# 服务器 wecom-cli / node 所在目录（不存在时自动跳过注入）
_CLI_EXTRA_PATH = "/home/ubuntu/.npm-global/bin:/home/ubuntu/.nvm/versions/node/v22.23.1/bin"
_CLI_CANDIDATE = Path.home() / ".workbuddy" / "binaries" / "node" / "cli-connector-packages" / "wecom-cli.cmd"
_auth_cache = None


def _cli():
    p = config.get_key("WECOM_CLI_PATH")
    if p:
        return p
    if _CLI_CANDIDATE.exists():
        return str(_CLI_CANDIDATE)
    return "wecom-cli"


def _cli_env():
    """子进程环境：Linux 服务器注入 wecom-cli 与 node 所在目录（cron PATH 窄时必需）。"""
    env = dict(os.environ)
    first = _CLI_EXTRA_PATH.split(":")[0]
    if os.path.isdir(first) and _CLI_EXTRA_PATH not in env.get("PATH", ""):
        env["PATH"] = _CLI_EXTRA_PATH + ":" + env.get("PATH", "")
    return env


def _run(args, timeout=180):
    r = subprocess.run([_cli()] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=_cli_env())
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def cli_ready():
    """wecom-cli 已安装且已授权（进程内缓存）。词边界匹配：unauthorized 含子串 authorized，裸 in 会误判。"""
    global _auth_cache
    if _auth_cache is not None:
        return _auth_cache
    try:
        rc, out, err = _run(["auth", "show", "--status"], timeout=30)
        _auth_cache = bool(re.search(r"\bauthorized\b", (out + err).lower()))
    except Exception:  # noqa: BLE001
        _auth_cache = False
    return _auth_cache


def _parse_url(text):
    m = re.search(r"https://doc\.weixin\.qq\.com[^\s\"'\\]+", text or "")
    return m.group(0) if m else ""


def doc_name(report_name, date_str):
    """智能文档命名：中文名 + 中文括号日期（wecom 规范，禁用下划线英文日期）。"""
    return f"塑料循环经济日报·{report_name}（{date_str}）"


def create_doc(md_path, name):
    """wecom-cli smartpage import 建智能文档。成功返回 {"url","docid"}，失败 None。"""
    payload = json.dumps({"name": name, "file_path": str(md_path)}, ensure_ascii=False)
    try:
        rc, out, err = _run(["smartpage", "import", "--json", payload])
    except Exception as e:  # noqa: BLE001
        print(f"  [wecom] smartpage import 异常: {e}")
        return None
    url = _parse_url(out + err)
    if url:
        return {"url": url, "docid": ""}
    print(f"  [wecom] smartpage import 失败: {(out or err)[:200]}")
    return None


def _clean(s, limit):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return text[:limit] + ("…" if len(text) > limit else "")


def _digest(markdown, limit=140):
    """取「今日/本月/本周核心叙事/综述」首段作短摘要（剥掉 **加粗**）。"""
    in_head = False
    for ln in markdown.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            in_head = ("核心叙事" in s) or ("综述" in s)
            continue
        if s.startswith("#") or s.startswith("|") or s.startswith(">"):
            continue
        if in_head and s and not re.match(r"^\*\*[^*]+\*\*[：:]", s):
            return _clean(s, limit)
    for ln in markdown.splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "|", ">")) and not re.match(r"^\d{4}[-年/.]", s):
            return _clean(s, limit)
    return "详情见邮件"


def write_handoff(report_name, markdown, date_str):
    """CLI 不可用时的交接文件（OpenClaw agent 照单建文档）。"""
    md_path = config.REPORT_DIR / f"{report_name}_{date_str}.md"
    handoff = {
        "tool": "wecom_mcp.smartpage_create",
        "title": doc_name(report_name, date_str),
        "pages": [{"page_title": report_name, "content_type": 1,
                   "page_filepath": str(md_path) if md_path.exists() else ""}],
        "note": "执行成功取返回 url 发企微群；msg 品类未开通（846610），链接由 agent/人工转发",
    }
    out = config.REPORT_DIR / f"{report_name}_{date_str}_wecom_handoff.json"
    out.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _md_path(report_name, markdown, date_str):
    p = config.REPORT_DIR / f"{report_name}_{date_str}.md"
    if p.exists():
        return str(p)
    tmp = Path(tempfile.gettempdir()) / f"newsac_{report_name}_{date_str}.md"
    tmp.write_text(markdown, encoding="utf-8")
    return str(tmp)


def send_report(report_name, markdown, date_str=""):
    """建智能文档（CLI 可用时）→ webhook 发「标题+摘要+链接」短消息。"""
    date_str = date_str or config.today_str()
    groups = config.WEBHOOK.get("groups", [])
    if not groups:
        return {"status": "skip", "reason": "webhook_groups 为空"}
    digest = _digest(markdown)

    doc = None
    if cli_ready():
        doc = create_doc(_md_path(report_name, markdown, date_str), doc_name(report_name, date_str))
    else:
        print("  [wecom] wecom-cli 未安装/未授权，降级短消息（授权一次可升级为文档链接）")

    if doc:
        content = (f"**♻️ {report_name}（{date_str}）**\n{digest}\n"
                   f"📄 [打开智能文档]({doc['url']})")
        status = "ok_doc_link"
    else:
        content = f"**♻️ {report_name}（{date_str}）**\n{digest}\n（完整版见邮件）"
        status = "ok_short"

    sent = 0
    for g in groups:
        url = g.get("webhook_url", "")
        if not url:
            continue
        r = http_post_json(url, {"Content-Type": "application/json"},
                           {"msgtype": "markdown", "markdown": {"content": content[:4000]}})
        if "__error__" not in r and "__http_error__" not in r:
            sent += 1
    result = {"status": status, "sent": sent}
    if doc:
        result["doc_url"] = doc["url"]
    else:
        result["handoff"] = write_handoff(report_name, markdown, date_str).name
    return result
