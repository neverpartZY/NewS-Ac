# -*- coding: utf-8 -*-
"""公众号草稿箱推送 —— 只建草稿、绝不发表（铁律，发表由团队负责）。

主路径·服务器直跑（2026-09-08 用户拍板：全自动化，不在本地电脑跑任何环节）：
  NewS-Ac 跑在白名单服务器上，publish_article_multi.py 就在同一台机的
  /home/ubuntu/（AppID/Secret 在 wx_accounts.json，均在服务器）——
  prepare 渲染 HTML+封面+meta 后直接本地调脚本建稿，无需 ssh 绕行。

备用路径·本机 scp+ssh（本机驱动时才用，需 .env 的 WECHAT_SSH_KEY）：
  1. 本地把 markdown 渲染成微信兼容 HTML（复用 render.py 的内联样式）
  2. 准备 publish_meta.json + 封面图 + HTML
  3. scp 到白名单服务器 {host}:/home/ubuntu/
  4. ssh 跑 `python3 publish_article_multi.py publish_meta.json` 建草稿

两者都不可用时降级为「交接文件」模式（生成 publish_meta.json + 指令说明）。
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import config
from . import render

WORK_DIR_NAME = "debug-final.html"

# 服务器直跑标记：建稿脚本与 NewS-Ac 同机（服务器克隆）时成立
_DIRECT_SCRIPT = Path("/home/ubuntu/publish_article_multi.py")


def _ssh_key():
    k = config.get_key("WECHAT_SSH_KEY")
    if k:
        return k
    cand = Path(r"D:\AppData\TestPrograme\ppwr+drf_dify\txun.pem")  # 本机已知位置
    return str(cand) if cand.exists() else ""


def _host():
    return config.get_key("WECHAT_RELAY_HOST") or config.WECHAT_RELAY_HOST


def _cover(report_name, date_str):
    """封面图：优先复用 config/cover.png；否则生成品牌色占位图（纯标准库 PNG）。"""
    brand = config.CONFIG_DIR / "cover.png"
    if brand.exists():
        return str(brand)
    w, h = 900, 383
    row = b"\x00" + bytes([20, 54, 92] * w)  # 深蓝 rgb(20,54,92)
    raw = row * h

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    p = config.REPORT_DIR / f"cover_{report_name}_{date_str}.png"
    p.write_bytes(png)
    return str(p)


def _run(cmd, timeout=90, cwd="", env=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd or None, env=env)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def _parse_result(text):
    """从 publish_article_multi.py 的多行输出提取草稿 media_id。

    真实输出形如：
      COVER {...}
      == draft/add ==
      DRAFT {"errcode":0,...,"media_id":"..."}
      DRAFT_ONLY_DONE media_id=xxx account=feiliao_newview
    """
    t = text or ""
    m = re.search(r"DRAFT_ONLY_DONE\s+media_id=(\S+)", t)
    if m:
        return m.group(1)
    # 兜底：逐行找 "DRAFT " 前缀的 JSON（不能跨行截取，COVER 行的 JSON 会污染）
    for ln in t.splitlines():
        s = ln.strip()
        if s.startswith("DRAFT "):
            try:
                d = json.loads(s[len("DRAFT "):])
                if d.get("media_id"):
                    return d["media_id"]
            except Exception:  # noqa: BLE001
                continue
    return None


_CLEANUP_SCRIPT = Path(__file__).parent / "server_scripts" / "cleanup_drafts.py"


def _cleanup_old_drafts(host, key, account, media_id, title):
    """草稿箱只留最新一篇：删同账号同标题旧草稿（best-effort，失败只记录）。"""
    try:
        rc1, o1, e1 = _run(["scp", "-i", key, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new",
                            str(_CLEANUP_SCRIPT), f"{host}:/home/ubuntu/"])
        if rc1 != 0:
            return f"cleanup scp failed: {(e1 or o1)[:120]}"
        cmd = f"cd /home/ubuntu && python3 cleanup_drafts.py {account} {media_id} \"{title}\""
        rc2, o2, e2 = _run(["ssh", "-i", key, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new", host, cmd])
        tail = ((o2 or "") + (e2 or "")).strip().splitlines()
        return tail[-1][:120] if tail else "cleanup done"
    except Exception as e:  # noqa: BLE001
        return f"cleanup error: {str(e)[:120]}"


def _send_direct(report_name, markdown, date_str):
    """服务器直跑：本机即白名单服务器，prepare 后直接调 publish_article_multi.py。

    脚本按 meta 文件所在目录解析 content_html/cover_img（相对路径），
    所以在 workdir 里以「publish_meta.json」相对路径调用。建稿成功后照常
    执行「草稿箱只留最新一篇」清理（best-effort）。
    """
    meta_path, files = prepare(report_name, markdown, date_str)
    workdir = Path(meta_path).parent
    # scp 模式下封面被平铺拷到 /home/ubuntu/；直跑没有这一步，需把封面落进 workdir
    cover_src = Path(files[1])
    if cover_src.parent != workdir:
        shutil.copy2(cover_src, workdir / cover_src.name)
    rc, out, err = _run([sys.executable, str(_DIRECT_SCRIPT), "publish_meta.json"],
                        timeout=180, cwd=str(workdir))
    media_id = _parse_result(out + err)
    if rc != 0 or not media_id:
        return {"status": "error",
                "reason": f"服务器直跑建草稿失败: {(err or out)[:500]}"}

    account = config.REPORT_MP_MAP.get(report_name, "")
    title = f"{report_name} · {date_str}"
    # cleanup_drafts.py 依赖 /home/ubuntu/wx_relay_multi；脚本在 server_scripts/ 下，
    # sys.path 只加脚本目录，需 PYTHONPATH 补上 /home/ubuntu（同旧 scp 路径的 cd /home/ubuntu）
    cleanup_env = {**os.environ, "PYTHONPATH": str(_DIRECT_SCRIPT.parent)}
    rc2, out2, err2 = _run([sys.executable, str(_CLEANUP_SCRIPT), account, media_id, title],
                           timeout=120, env=cleanup_env)
    tail = ((out2 or "") + (err2 or "")).strip().splitlines()
    cleanup = tail[-1][:120] if tail else ("cleanup done" if rc2 == 0 else "cleanup failed")
    return {"status": "ok", "media_id": media_id, "cleanup": cleanup}


def prepare(report_name, markdown, date_str):
    """渲染 HTML + 封面 + publish_meta.json，返回工作目录路径。"""
    html = render.render_html(markdown, report_name, date_str)
    workdir = config.REPORT_DIR / f"wechat_{report_name}_{date_str}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / WORK_DIR_NAME).write_text(html, encoding="utf-8")
    cover = _cover(report_name, date_str)
    meta = {
        "mp_account": config.REPORT_MP_MAP.get(report_name, ""),
        "content_html": WORK_DIR_NAME,
        "cover_img": Path(cover).name,
        "body_img": "",
        "body_rel": "",
        "title": f"{report_name} · {date_str}",
        "author": "塑料循环经济日报",
        "digest": markdown[:100].replace("\n", " "),
        "content_source_url": "",
    }
    meta_path = workdir / "publish_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    files = [str(workdir / WORK_DIR_NAME), cover, str(meta_path)]
    return str(meta_path), files


def send_report(report_name, markdown, date_str=""):
    date_str = date_str or config.today_str()
    if not config.REPORT_MP_MAP.get(report_name):
        return {"status": "skip", "reason": f"{report_name} 无公众号映射"}
    if _DIRECT_SCRIPT.exists():  # 服务器上：直跑主路径（用户 2026-09-08 拍板全自动化）
        return _send_direct(report_name, markdown, date_str)
    key = _ssh_key()
    if not key:
        # 降级：交接文件模式（无私钥环境）
        meta = {
            "mp_account": config.REPORT_MP_MAP.get(report_name, ""),
            "content_html": WORK_DIR_NAME,
            "cover_img": "cover.png",
            "title": f"{report_name} · {date_str}",
            "author": "塑料循环经济日报",
            "digest": markdown[:100].replace("\n", " "),
        }
        out = config.REPORT_DIR / f"{report_name}_{date_str}_publish_meta.json"
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "handoff",
                "reason": f"无 SSH 私钥（WECHAT_SSH_KEY），已生成 {out.name}；"
                          f"排版后 scp + ssh 到 {_host()} 跑 publish_article_multi.py"}
    if not Path(key).exists():
        return {"status": "error", "reason": f"SSH 私钥不存在: {key}"}

    meta_path, files = prepare(report_name, markdown, date_str)
    host = _host()
    rc1, out1, err1 = _run(["scp", "-i", key, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new"] + files + [f"{host}:/home/ubuntu/"])
    if rc1 != 0:
        return {"status": "error", "reason": f"scp 失败: {(err1 or out1)[:200]}"}
    rc2, out2, err2 = _run(["ssh", "-i", key, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new", host,
                            "cd /home/ubuntu && python3 publish_article_multi.py publish_meta.json"])
    media_id = _parse_result(out2 + err2)
    if rc2 != 0 or not media_id:
        return {"status": "error", "reason": f"建草稿失败: {(err2 or out2)[:200]}"}

    # 草稿箱只留最新一篇：删除同账号同标题的旧草稿（best-effort，失败不影响主流程）
    account = config.REPORT_MP_MAP.get(report_name, "")
    title = f"{report_name} · {date_str}"
    cleanup = _cleanup_old_drafts(host, key, account, media_id, title)
    return {"status": "ok", "media_id": media_id, "cleanup": cleanup}
