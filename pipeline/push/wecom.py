# -*- coding: utf-8 -*-
"""企业微信推送：智能文档链接模式（铁律：群里禁止一切纯文字消息，每条必带文档链接）。

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
from . import state
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


_last_auth_link = ""  # 最近一次 850003 带出的机器人授权链接（help_message），供 no_doc reason 引用


def _help_message(text):
    """从 CLI 错误输出提取 help_message（850003 类型②「机器人文档权限过期」才有）。

    这类过期重扫码无效，必须由机器人创建者走 help_message 里的授权链接
    （或企微「工作台-智能机器人」）重新授权。wecom.py 此前把报错截断到 200 字符，
    链接被吞掉，告警邮件只会给出「重新扫码」的错误指引。
    """
    if not text:
        return ""
    m = re.search(r'"help_message":\s*"((?:[^"\\]|\\.)*)"', text)
    if not m:
        return ""
    try:
        return json.loads(f'"{m.group(1)}"')
    except Exception:  # noqa: BLE001
        return ""


def _auth_link(text):
    m = re.search(r'https://work\.weixin\.qq\.com/ai/aiHelper/authorizationList[^\s)"\\]*',
                  text or "")
    return m.group(0) if m else ""


def doc_name(report_name, date_str):
    """智能文档命名：中文名 + 中文括号日期（wecom 规范，禁用下划线英文日期）。"""
    return f"塑料循环经济日报·{report_name}（{date_str}）"


def create_doc(md_path, name):
    """wecom-cli smartpage import 建智能文档。成功返回 {"url","docid"}，失败 None。"""
    global _last_auth_link
    payload = json.dumps({"name": name, "file_path": str(md_path)}, ensure_ascii=False)
    try:
        rc, out, err = _run(["smartpage", "import", "--json", payload])
    except Exception as e:  # noqa: BLE001
        print(f"  [wecom] smartpage import 异常: {e}")
        return None
    url = _parse_url(out + err)
    if url:
        return {"url": url, "docid": ""}
    full = out + err
    print(f"  [wecom] smartpage import 失败: {full[:200]}")
    help_msg = _help_message(full)
    if help_msg:
        # 完整 help_message（含授权链接）进日志：850003 类型②重扫码无效，告警邮件要引用链接
        print(f"  [wecom] {help_msg}")
        _last_auth_link = _auth_link(help_msg)
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
    """建智能文档（CLI 可用时）→ webhook 发「标题+摘要+链接」。

    铁律（用户 2026-09-03 拍板，绝对禁止）：企微群**不准发纯文字消息**。
    文档建不出来就什么都不发，状态记 no_doc，由 run.sh 私发邮箱告警，
    授权恢复后补推。群里出现过的每一条消息都必须带智能文档链接。
    防重复（push_state）：今日已发过文档链接 → 直接跳过。
    """
    date_str = date_str or config.today_str()
    groups = config.WEBHOOK.get("groups", [])
    if not groups:
        return {"status": "skip", "reason": "webhook_groups 为空"}

    prev = state.get(date_str, report_name, "wecom")
    if prev and prev.get("status") == "ok_doc_link":
        return {"status": "skip", "reason": "今日已推送过智能文档链接（push_state 防重复）"}

    digest = _digest(markdown)
    doc = None
    if cli_ready():
        doc = create_doc(_md_path(report_name, markdown, date_str), doc_name(report_name, date_str))
    else:
        print("  [wecom] wecom-cli 未安装/未授权 → 群消息不发（纯文字绝对禁止），等授权恢复后补推")

    if not doc:
        # 建不出文档：群里什么都不发。记 no_doc 供 run.sh email_alert 与授权后补推
        state.record(date_str, report_name, "wecom", status="no_doc")
        reason = "智能文档创建失败，按铁律不发纯文字，已等授权恢复补推"
        if _last_auth_link:
            reason += f"；机器人文档权限过期（重扫码无效），授权链接: {_last_auth_link}"
        return {"status": "no_doc",
                "reason": reason,
                "handoff": str(write_handoff(report_name, markdown, date_str))}

    content = (f"**♻️ {report_name}（{date_str}）**\n{digest}\n"
               f"📄 [打开智能文档]({doc['url']})")
    sent = 0
    for g in groups:
        url = g.get("webhook_url", "")
        if not url:
            continue
        r = http_post_json(url, {"Content-Type": "application/json"},
                           {"msgtype": "markdown", "markdown": {"content": content[:4000]}})
        if "__error__" not in r and "__http_error__" not in r:
            sent += 1
    state.record(date_str, report_name, "wecom", status="ok_doc_link", doc_url=doc["url"])
    return {"status": "ok_doc_link", "sent": sent, "doc_url": doc["url"]}
