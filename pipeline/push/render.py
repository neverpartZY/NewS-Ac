# -*- coding: utf-8 -*-
"""日报 markdown → 精美邮件 HTML（蓝色系，内联样式，兼容 Gmail/Outlook）。"""

import html as html_mod
import re

# ---- 配色 ----
DEEP_BLUE = "rgb(20,54,92)"        # 主标题/栏目标题/条目标题
ACCENT_BLUE = "rgb(29,95,168)"     # 强调蓝/链接/竖条/日期
BODY_GRAY = "rgb(43,47,58)"        # 正文
SMALL_GRAY = "rgb(140,148,140)"    # 来源/时间小字
LIGHT_BLUE = "rgb(238,244,251)"    # 浅蓝底
TABLE_BORDER = "rgb(214,224,236)"
TABLE_ROW_BORDER = "rgb(224,230,240)"
SEPARATOR = "rgb(238,241,245)"
WHITE = "#ffffff"


def _links(text):
    """条目标题内联处理：**加粗剥掉**（保持标题深蓝），[x](url) → 可点链接（月报格式链接内联在条目行）。"""
    t = html_mod.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  r'<a href="\2" style="color:' + ACCENT_BLUE + r';text-decoration:none;font-weight:600;">\1</a>', t)


def _inline(text):
    """转义 + 粗体（蓝色小标题）+ 链接 → 内联 HTML。"""
    t = html_mod.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*",
               r'<strong style="color:' + ACCENT_BLUE + r';font-weight:700;">\1</strong>', t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" style="color:' + ACCENT_BLUE + r';text-decoration:none;font-weight:600;">\1</a>', t)
    return t


def _link_button(line):
    """[查看原文](url) · 日期 → 灰色小字时间 + 蓝色「查看原文 →」按钮。"""
    m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
    url = m.group(2) if m else ""
    date = ""
    if m:
        rest = line[m.end():]
        dm = re.search(r"·\s*(.+)$", rest)
        if dm:
            date = dm.group(1).strip()
    time_html = (f'<span style="color:{SMALL_GRAY};font-size:13px;">{html_mod.escape(date)}</span>'
                 f'&nbsp;&nbsp;') if date else ""
    btn = f'<a href="{html_mod.escape(url)}" style="color:{ACCENT_BLUE};text-decoration:none;font-weight:600;">查看原文 →</a>'
    return time_html + btn


def _table(lines, i):
    """markdown 表格 → 完整边框表格（浅蓝表头、深蓝加粗、左对齐、可横向滚动）。"""
    rows = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append(cells)
        i += 1
    if not rows:
        return "", i
    body = [r for r in rows if not all(re.fullmatch(r":?-+:?", c or "-") for c in r)]
    if not body:
        return "", i
    head, data = body[0], body[1:]
    parts = ['<div style="overflow-x:auto;">',
             f'<table width="100%" cellpadding="10" cellspacing="0" style="border-collapse:collapse;">']
    parts.append(f'<thead><tr style="background:{LIGHT_BLUE};">')
    for c in head:
        parts.append(f'<th style="color:{DEEP_BLUE};font-weight:700;text-align:left;'
                     f'border:1px solid {TABLE_BORDER};padding:10px;font-size:14px;">{_inline(c)}</th>')
    parts.append("</tr></thead><tbody>")
    for row in data:
        parts.append("<tr>")
        for c in row:
            parts.append(f'<td style="font-size:14px;color:{BODY_GRAY};'
                         f'border:1px solid {TABLE_ROW_BORDER};padding:10px;">{_inline(c)}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts), i


def render_html(markdown, report_name="", date_str=""):
    lines = markdown.split("\n")
    title = report_name
    date_line = date_str
    i = 0
    if lines and lines[0].lstrip().startswith("# "):
        title = lines[0].lstrip()[2:].strip()
        i = 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        # 若 markdown 里带日期行且未显式传 date_str，则提取之
        if (not date_line) and i < len(lines) and lines[i].strip() and \
                not lines[i].lstrip().startswith("#") and re.match(r"^\d{4}", lines[i].strip()):
            date_line = lines[i].strip()
            i += 1

    body = []
    in_list = False
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            in_list = False
            i += 1
            continue
        if s.startswith("|"):
            t, i = _table(lines, i)
            body.append(t)
            in_list = False
            continue
        if s.startswith("### "):
            body.append(f'<h3 style="color:{DEEP_BLUE};font-weight:700;font-size:17px;margin:20px 0 8px;">{_inline(s[4:])}</h3>')
            in_list = False
        elif s.startswith("## "):
            body.append(
                f'<div style="margin:28px 0 14px;border-left:5px solid {ACCENT_BLUE};'
                f'background:linear-gradient(90deg,{LIGHT_BLUE},{WHITE});'
                f'border-radius:0 5px 5px 0;padding:8px 14px;">'
                f'<span style="font-size:19px;font-weight:700;color:{DEEP_BLUE};">{_inline(s[3:])}</span></div>')
            in_list = False
        elif s.startswith("# "):
            body.append(f'<h1 style="font-size:20px;font-weight:800;color:{DEEP_BLUE};margin:20px 0 10px;">{_inline(s[2:])}</h1>')
            in_list = False
        elif s.startswith("> "):
            body.append(f'<p style="color:{SMALL_GRAY};font-size:13px;line-height:1.7;">{_inline(s[2:])}</p>')
            in_list = False
        elif re.match(r"^\d+\.\s", s):
            # 条目标题：深蓝 800 17px；内联链接可点（月报格式）
            title_txt = re.sub(r"^\d+\.\s*", "", s)
            body.append(f'<div style="margin:18px 0;padding-bottom:16px;border-bottom:1px solid {SEPARATOR};">'
                        f'<div style="font-size:17px;font-weight:800;color:{DEEP_BLUE};margin-bottom:6px;">'
                        f'{_links(title_txt)}</div>')
            in_list = True
        elif in_list:
            if "[" in s and "](" in s:
                body.append(f'<div style="margin-top:8px;">{_link_button(s)}</div>')
            else:
                body.append(f'<p style="font-size:16px;line-height:1.9;letter-spacing:0.3px;'
                            f'color:{BODY_GRAY};margin:0 0 6px;">{_inline(s)}</p>')
        else:
            body.append(f'<p style="font-size:16px;line-height:1.9;letter-spacing:0.3px;'
                        f'color:{BODY_GRAY};margin:12px 0;">{_inline(s)}</p>')
            in_list = False
        i += 1

    body_html = "".join(body)
    footer = (f"📝 数据截至 {date_line or '今日'}，由 AI 多源采集并经语义去重，"
              f"仅供参考；每条附原文链接，可点击核实。")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f2f4f7;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#f2f4f7;padding:20px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" role="presentation" style="max-width:620px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e6e9ee;">
  <tr><td style="text-align:center;background:linear-gradient({LIGHT_BLUE},{WHITE});border-bottom:3px solid {ACCENT_BLUE};padding:28px 32px 18px;">
    <div style="font-size:24px;font-weight:800;color:{DEEP_BLUE};">{html_mod.escape(title)}</div>
    <div style="font-size:14px;font-weight:700;color:{ACCENT_BLUE};margin-top:8px;">{html_mod.escape(date_line)}</div>
  </td></tr>
  <tr><td style="padding:26px 32px 20px;">
    {body_html}
  </td></tr>
  <tr><td style="padding:16px 32px;color:{SMALL_GRAY};font-size:13px;border-top:1px solid {SEPARATOR};">
    {footer}
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""
