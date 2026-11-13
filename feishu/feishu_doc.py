# -*- coding: utf-8 -*-
"""创建飞书云文档版本的每日短文(飞书内直接阅读, 无需下载跳转)"""
import json
import re
import time
import urllib.request
from pathlib import Path

DOMAIN = "https://open.feishu.cn"

_token_cache = {"token": "", "exp": 0}


def _token(app_id: str, app_secret: str) -> str:
    if _token_cache["exp"] > time.time() + 60:
        return _token_cache["token"]
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(f"{DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
                                 data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=15).read())
    _token_cache.update(token=r["tenant_access_token"], exp=time.time() + r.get("expire", 7200))
    return _token_cache["token"]


def _api(method: str, path: str, body: dict, app_id: str, app_secret: str) -> dict:
    req = urllib.request.Request(
        f"{DOMAIN}/open-apis{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_token(app_id, app_secret)}"},
        method=method,
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if resp.get("code") != 0:
        raise RuntimeError(f"飞书API {path}: {resp.get('code')} {resp.get('msg')}")
    return resp.get("data", {})


def _runs(text: str, vocab: set) -> list[dict]:
    """把段落切成 text_run 列表, 词表单词加粗"""
    out = []
    for tok in re.split(r"([A-Za-z][A-Za-z'’\-]*)", text):
        if not tok:
            continue
        t = tok.lower()
        plain = t
        for suf in ("s", "es", "ed", "ing"):
            if plain.endswith(suf) and plain[: -len(suf)] in vocab:
                plain = plain[: -len(suf)]
                break
        style = {"bold": True} if plain in vocab else {}
        out.append({"text_run": {"content": tok, "text_element_style": style} if style else {"content": tok}})
    return out


def _para(runs: list[dict]) -> dict:
    return {"block_type": 2, "text": {"elements": runs}}


def _heading(level: int, text: str) -> dict:
    key = f"heading{min(level, 9)}"
    return {"block_type": 2 + min(level, 9), key: {"elements": [
        {"text_run": {"content": text, "text_element_style": {"bold": True}}}
    ]}}


def create_doc(app_id: str, app_secret: str, title: str,
               passages: list[dict], vocab: set) -> str:
    """创建飞书文档并写入短文, 返回文档链接"""
    doc = _api("POST", "/docx/v1/documents", {"title": title}, app_id, app_secret)
    doc_id = doc["document"]["document_id"]

    children = []
    for i, p in enumerate(passages, 1):
        if not p.get("passage"):
            continue
        children.append(_heading(2, f"短文 {i}"))
        for para in [q.strip() for q in re.split(r"\n\s*\n", p["passage"]) if q.strip()]:
            children.append(_para(_runs(re.sub(r"\s+", " ", para), vocab)))
        if p.get("translation"):
            children.append(_heading(3, "中文翻译"))
            for para in [q.strip() for q in p["translation"].split("\n") if q.strip()]:
                children.append(_para(_runs(para, set())))

    # 分批写入(每批最多50个block)
    for idx in range(0, len(children), 50):
        _api("POST", f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
             f"?document_revision_id=-1",
             {"children": children[idx : idx + 50], "index": idx}, app_id, app_secret)
    return f"https://feishu.cn/docx/{doc_id}", doc_id


def grant_view(app_id: str, app_secret: str, doc_token: str, open_id: str):
    """授权阅读者, 使链接在飞书内可打开"""
    _api("POST", f"/drive/v1/permissions/{doc_token}/members?type=docx",
         {"member_type": "openid", "member_id": open_id, "perm": "view",
          "type": "docx"}, app_id, app_secret)
