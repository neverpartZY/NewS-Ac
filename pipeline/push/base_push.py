# -*- coding: utf-8 -*-
"""推送共享工具。"""
import json

import requests


def http_post_json(url, headers, body, timeout=30):
    try:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code != 200:
            return {"__http_error__": r.status_code, "__text__": r.text[:300]}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}
