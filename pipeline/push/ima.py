# -*- coding: utf-8 -*-
"""IMA 知识库推送：直接调腾讯 IMA OpenAPI（create_media → COS → add_knowledge）。

凭证：env `IMA_OPENAPI_CLIENTID`/`IMA_OPENAPI_APIKEY` 优先，兜底读 `~/.config/ima/client_id` + `api_key`。
文档见旧 ima-skill 的 knowledge-base/references/api.md。
"""
from pathlib import Path

import requests

import config

BASE = "https://ima.qq.com"
BASE_PATH = "/openapi/wiki/v1"

MEDIA_TYPE_MARKDOWN = 7
CONTENT_TYPE_MARKDOWN = "text/markdown"


def _read(p):
    try:
        return Path(p).expanduser().read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def _creds():
    cid = config.get_key("IMA_OPENAPI_CLIENTID") or _read("~/.config/ima/client_id")
    key = config.get_key("IMA_OPENAPI_APIKEY") or _read("~/.config/ima/api_key")
    return cid, key


SKILL_VERSION = "1.1.8"  # 对齐 ima-skill meta.json；服务端校验 skill_version 头（缺失报 200002 skill auth failed）


def _headers(cid, key):
    return {
        "ima-openapi-clientid": cid,
        "ima-openapi-apikey": key,
        "ima-openapi-ctx": f"skill_version={SKILL_VERSION}",
        "Content-Type": "application/json",
    }


def _post(path, body, headers):
    try:
        r = requests.post(f"{BASE}{path}", headers=headers, json=body, timeout=60)
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"code": -1, "msg": str(e)[:200]}


def _cos_upload(data, cred, content_type):
    """用 create_media 返回的临时凭证上传到 COS（cos-python-sdk-v5）。"""
    try:
        from qcloud_cos import CosConfig, CosS3Client
        cfg = CosConfig(Region=cred["region"], SecretId=cred["secret_id"],
                        SecretKey=cred["secret_key"], Token=cred.get("token", ""))
        client = CosS3Client(cfg)
        client.put_object(Bucket=cred["bucket_name"], Body=data, Key=cred["cos_key"],
                          ContentType=content_type)
        return True
    except ImportError:
        print("  [ima] 缺少 cos-python-sdk-v5，跳过 COS 上传")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  [ima] COS 上传异常: {e}")
        return False


def _upload(text, title, kb_id, folder_id, cid, key):
    headers = _headers(cid, key)
    data = text.encode("utf-8")
    fname = f"{title}.md"
    fsize = len(data)

    r = _post(f"{BASE_PATH}/create_media", {
        "file_name": fname, "file_size": fsize, "content_type": CONTENT_TYPE_MARKDOWN,
        "knowledge_base_id": kb_id, "file_ext": "md",
    }, headers)
    if r.get("code") != 0:
        return {"status": "error", "detail": r}
    media_id = r["data"]["media_id"]
    cred = r["data"]["cos_credential"]

    if not _cos_upload(data, cred, CONTENT_TYPE_MARKDOWN):
        return {"status": "error", "detail": "COS 上传失败"}

    r2 = _post(f"{BASE_PATH}/add_knowledge", {
        "media_type": MEDIA_TYPE_MARKDOWN, "media_id": media_id, "title": fname,
        "knowledge_base_id": kb_id, "folder_id": folder_id,
        "file_info": {"cos_key": cred["cos_key"], "file_size": fsize, "file_name": fname},
    }, headers)
    if r2.get("code") != 0:
        return {"status": "error", "detail": r2}
    return {"status": "ok", "media_id": media_id}


def send_report(report_name, markdown, date_str=""):
    """把一份日报 markdown 上传到 IMA 知识库。"""
    cid, key = _creds()
    if not cid or not key:
        return {"status": "skip", "reason": "IMA 凭证未配置"}
    kb = config.get_key("IMA_KB_ID") or "7457220757303832"
    folder = config.get_key("IMA_FOLDER_ID") or ""
    title = f"{report_name}_{date_str or config.today_str()}"
    return _upload(markdown, title, kb, folder, cid, key)
