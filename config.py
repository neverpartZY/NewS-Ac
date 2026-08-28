# -*- coding: utf-8 -*-
"""集中配置：读 .env / 环境变量（Windows 注册表兜底）、阈值、领域 config JSON。"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 日报日期/时效统一按北京时间（中国无夏令时，固定 UTC+8），
# 避免服务器在 UTC 等其它时区时，日报日期与「3 天」窗口算错。
TZ_OFFSET = timezone(timedelta(hours=8))

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
REF_DIR = BASE_DIR / "references"

# ---- 阈值（可调） ----
FRESH_DAYS = 3            # 新闻统一时效窗口（用户要求 3 天以内）
PRICE_DAYS = 2            # 价格更严
RELEVANCE_THRESHOLD = 0.7  # LLM 主题相关性打分阈值
DEDUP_HIGH = 0.88          # embedding 余弦 ≥ 此值 → 判重
DEDUP_LOW = 0.72           # 0.72 ~ 0.88 → 交 LLM 仲裁
MAX_RESULTS_PER_QUERY = 10
LINK_TIMEOUT = 4           # 链接探活超时（秒）
LINK_WORKERS = 10          # 链接探活并发线程数

# 3 份分报 → 公众号映射（草稿箱交接用，mp_account 见 gjb-wechat-draft skill）
REPORT_MP_MAP = {
    "综合日报": "feiliao_newview",
    "化学循环日报": "feiliao_newview",
    "再生PET日报": "regen_pet",
}
# mp_account → 公众号名（参考）
MP_ACCOUNTS = {
    "gjb_pkg_cycle": "国嘉基业包装循环圈",
    "feiliao_circle": "废塑料圈子",
    "feiliao_newview": "废塑料新观察",
    "regen_pet": "再生PET",
}
# 公众号草稿箱白名单中转服务器
WECHAT_RELAY_HOST = "ubuntu@43.128.140.186"


def _load_dotenv():
    """极简 .env 加载：不覆盖已存在的环境变量。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def get_key(name):
    """读 key：优先环境变量，兜底读 Windows 注册表 HKCU\\Environment。
    原因：SetEnvironmentVariable(...,'User') 不广播 WM_SETTINGCHANGE，
    当前会话进程树读不到新变量，但注册表已写入，故兜底读注册表。"""
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            v, _ = winreg.QueryValueEx(k, name)
        return (v or "").strip()
    except Exception:
        return ""


def load_json(name):
    p = CONFIG_DIR / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---- 领域 config（从旧 skill 提取，直接复用） ----
COLLECTION = load_json("collection_config.json")
SOURCES = load_json("sources_config.json")
PRICE = load_json("price_config.json")
PERPLEXITY = load_json("perplexity_config.json")
REPORT = load_json("report_config.json")
EMAIL = load_json("email_recipients.json")
WEBHOOK = load_json("webhook_groups.json")

# 常用字段的便捷别名
FRESH_WINDOWS = COLLECTION.get("fresh_windows", {})
NOISE_WORDS = COLLECTION.get("noise_words", [])
HARD_NOISE_WORDS = COLLECTION.get("hard_noise_words", [])
CONTENT_NOISE_WORDS = COLLECTION.get("content_noise_words", [])
DOMAIN_WORDS = COLLECTION.get("domain_words", [])
SIGNALS = COLLECTION.get("signals", {})
TASKS = COLLECTION.get("tasks", [])
PRICE_ITEMS = PRICE.get("price_items", [])
SOURCE_SITES = SOURCES.get("sources", [])
BOARD_ORDER = REPORT.get("board_order", [])
SIG_PRIORITY = REPORT.get("sig_priority", {})

# LLM 配置（先加载 .env 再取 key，否则 .env 里的 key 读不到）
_load_dotenv()
LLM_API_KEY = get_key("LLM_API_KEY") or get_key("DEEPSEEK_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


def ensure_dirs():
    for d in (DATA_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def today_local():
    """北京时间今天的 date（服务器可能非中国时区）。"""
    return datetime.now(TZ_OFFSET).date()


def today_str():
    return today_local().strftime("%Y-%m-%d")


def now_local_str():
    """北京时间当前时间字符串（用于 collected_at 等）。"""
    return datetime.now(TZ_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(ds):
    """解析发布日期 → date；支持绝对日期 + 相对时间（中英文 'X天前'/'X days ago'/'昨天'）。

    搜索引擎对中文结果常返回「5天前」，对英文结果返回「5 days ago」，
    若不识别会被误判为「无日期旧闻」而放行。无法解析返回 None。
    """
    if not (ds or "").strip():
        return None
    s = ds.strip().lower()
    today = today_local()
    # 中文相对时间：X天前 / X小时前 / X周前 / X个月前 / X年前
    cm = re.search(r"(\d+)\s*(天|小时|周|个月|月|年)前", s)
    if cm:
        n, unit = int(cm.group(1)), cm.group(2)
        if unit == "小时":
            return today
        if unit == "天":
            return today - timedelta(days=n)
        if unit == "周":
            return today - timedelta(days=n * 7)
        if unit in ("个月", "月"):
            return today - timedelta(days=n * 30)
        return today - timedelta(days=n * 365)  # 年
    # 中文口语相对时间
    if "前天" in s:
        return today - timedelta(days=2)
    if "昨天" in s:
        return today - timedelta(days=1)
    if "今天" in s or "刚刚" in s:
        return today
    # 英文相对时间：X days/hours/weeks/months ago
    m = re.search(r"(\d+)\s*(day|week|hour|month)s?\s*ago", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "hour":
            return today
        if unit == "day":
            return today - timedelta(days=n)
        if unit == "week":
            return today - timedelta(days=n * 7)
        return today - timedelta(days=n * 30)
    # 绝对日期
    ds2 = ds[:10].replace("/", "-")
    try:
        return datetime.strptime(ds2, "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


def date_from_url(url):
    """从 URL 提取发布日期（.../2026-08-27/... 或 .../20260823...）。取不到返回空串。"""
    m = re.search(r"(20\d{2})[/\-]?(0[1-9]|1[0-2])[/\-]?(0[1-9]|[12]\d|3[01])", url or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    try:
        datetime.strptime(f"{y}-{mo}-{d}", "%Y-%m-%d")
        return f"{y}-{mo}-{d}"
    except ValueError:
        return ""


ensure_dirs()
