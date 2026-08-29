#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除指定公众号草稿箱中与标题相同的旧草稿（保留 new_media_id 那篇）。

规则（gjb-wechat-draft）：改文案后重建草稿会拿到新 media_id，旧草稿要删掉——草稿箱只留最新一篇。
在白名单服务器上运行（token 绑服务器 IP）：
  python3 cleanup_drafts.py <mp_account> <new_media_id> <title>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wx_relay_multi import get_access_token

import urllib.request as urlreq

API = "https://api.weixin.qq.com"


def batchget(account, offset=0, count=20):
    token = get_access_token(account)
    url = "%s/cgi-bin/draft/batchget?access_token=%s" % (API, token)
    req = urlreq.Request(url, data=json.dumps({"offset": offset, "count": count}).encode("utf-8"),
                         method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    with urlreq.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def delete(account, media_id):
    token = get_access_token(account)
    url = "%s/cgi-bin/draft/delete?access_token=%s" % (API, token)
    req = urlreq.Request(url, data=json.dumps({"media_id": media_id}).encode("utf-8"),
                         method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    with urlreq.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    account, new_id, title = sys.argv[1], sys.argv[2], sys.argv[3]
    deleted, offset = 0, 0
    while True:
        data = batchget(account, offset=offset)
        items = data.get("item", [])
        if not items:
            break
        for it in items:
            mid = it.get("media_id", "")
            if not mid or mid == new_id:
                continue
            art = (it.get("content", {}).get("articles") or [{}])[0]
            if art.get("title", "").strip() == title.strip():
                res = delete(account, mid)
                ok = res.get("errcode", -1) == 0
                print(("DELETED " if ok else "FAIL ") + mid[:24] + " " + json.dumps(res, ensure_ascii=False)[:120])
                deleted += 1 if ok else 0
        total = data.get("total_count", 0)
        offset += len(items)
        if offset >= total:
            break
    print("CLEANUP_DONE deleted=%d" % deleted)


if __name__ == "__main__":
    main()
