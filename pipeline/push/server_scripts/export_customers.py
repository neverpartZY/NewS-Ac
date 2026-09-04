# -*- coding: utf-8 -*-
"""从日报网站后端（ppwr-backend/ppwr.db users 表）刷新客户邮件名单。

每日 run.sh 在 main.py 之前调用，保证客户注册/停用自动同步到日报收件人：
  python3 pipeline/push/server_scripts/export_customers.py [ppwr.db 路径]

规则：is_active=1 且 email 非空，排除 test@example.com 与 @replas.org.cn（内邮名单已有）。
只增删 recipients 数组，enabled 开关保持人工设置不变。
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_DEFAULT = "/home/ubuntu/ppwr-backend/ppwr.db"
OUT = Path(__file__).resolve().parents[3] / "config" / "email_recipients_customers.json"
EXCLUDE = {"test@example.com"}


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_DEFAULT
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = db.execute(
        "select email from users "
        "where is_active=1 and email is not null and email != '' "
        "order by lower(email)"
    ).fetchall()
    emails = sorted({
        r[0].strip() for r in rows
        if r[0].strip() and r[0].strip().lower() not in EXCLUDE
        and not r[0].strip().lower().endswith("@replas.org.cn")
    })

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    cfg = {"description": old.get("description", "日报网站注册客户收件人"),
           "enabled": old.get("enabled", True), "recipients": emails}
    OUT.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[customers] {db_path} -> {OUT.name}: {len(emails)} 个客户邮箱")


if __name__ == "__main__":
    main()
