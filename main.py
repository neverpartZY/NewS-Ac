# -*- coding: utf-8 -*-
"""塑料回收新闻采集 + AI 加工系统 —— 单入口。

分工（2026-08-28 定）：本程序负责 采集→筛选→去重→加工→出 3 份日报，
产物落到 reports/（markdown + 标准运行清单 run_<period>_<date>.json）。
发送/分发不属于本程序职责——外部（服务器 OpenClaw / 团队通道）按标准清单接手。

用法：
  python main.py --once            跑完整一轮（采集→过滤→去重→加工→生成→落库），默认不推送
  python main.py --dry-run         只采集+打印，不落库
  python main.py --push            （选装）走内置四通道推送：邮件/企微/IMA交接/公众号交接
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
    ap.add_argument("--push", action="store_true",
                    help="（选装）推送四通道：邮件/企微/IMA交接/公众号交接。默认不推送——发送属外部职责")
    ap.add_argument("--full", action="store_true", help="跑全量 auto 任务（否则只跑 D1）")
    ap.add_argument("--weekly", action="store_true", help="生成周报（过去7天精选，不重新采集）")
    ap.add_argument("--monthly", action="store_true", help="生成月报（过去30天汇总，不重新采集）")
    args = ap.parse_args()

    if args.weekly:
        result = runner.run_periodic("weekly", do_push=args.push)
        print("\n=== 汇总 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.monthly:
        result = runner.run_periodic("monthly", do_push=args.push)
        print("\n=== 汇总 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    freqs = None if args.full else {"D1"}
    result = runner.run(dry_run=args.dry_run, do_push=args.push, freqs=freqs)

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
