# -*- coding: utf-8 -*-
"""塑料回收新闻采集 + AI 加工系统 —— 单入口。

用法：
  python main.py --once            跑完整一轮（采集→过滤→去重→加工→生成→落库→推送）
  python main.py --dry-run         只采集+打印，不落库不推送
  python main.py --no-push         落库+生成日报，但不推送
  python main.py --full            跑全量 auto 任务（默认只跑 D1 高频任务）
"""
import argparse
import json
import sys

import config
from pipeline import runner


def main():
    ap = argparse.ArgumentParser(description="塑料回收新闻采集 + AI 加工")
    ap.add_argument("--once", action="store_true", help="跑完整一轮")
    ap.add_argument("--dry-run", action="store_true", help="只采集打印，不落库不推送")
    ap.add_argument("--no-push", action="store_true", help="不推送")
    ap.add_argument("--full", action="store_true", help="跑全量 auto 任务（否则只跑 D1）")
    args = ap.parse_args()

    freqs = None if args.full else {"D1"}
    result = runner.run(dry_run=args.dry_run, do_push=not args.no_push, freqs=freqs)

    if args.dry_run:
        print("\n=== 候选样本（前 20 条）===")
        for d in result.get("docs", [])[:20]:
            print(f"- [{d.engine}] {d.title} | {d.date} | {d.url}")
        print(f"\n=== 价格点（前 20 个）===")
        for p in result.get("price_points_data", [])[:20]:
            print(f"- {p.get('item')} {p.get('price')}{p.get('unit')} {p.get('trend')} | {p.get('source')}")
        return

    print("\n=== 汇总 ===")
    print(json.dumps({k: v for k, v in result.items() if k not in ("docs", "price_points_data")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
