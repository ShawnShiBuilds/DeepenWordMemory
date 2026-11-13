# -*- coding: utf-8 -*-
"""飞书机器人: 手机发PDF给机器人 -> 自动生成单词短文 -> 回发链接+HTML文件
配置: 同目录 feishu_config.json  {"app_id":"...","app_secret":"...","public_url":"http://<host>:8000"}
启动: python feishu_bot.py
"""
import io
import json
import threading
import uuid
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1, ReplyMessageRequest, ReplyMessageRequestBody,
    CreateFileRequest, CreateFileRequestBody, CreateMessageRequest,
    CreateMessageRequestBody, GetMessageResourceRequest,
)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import vocab_story as vs

HERE = Path(__file__).parent
REPO = HERE.resolve().parent  # 仓库根目录, 用于定位 vocab_story 与共享数据
CONF = json.loads((HERE / "feishu_config.json").read_text(encoding="utf-8"))
APP_ID, APP_SECRET = CONF["app_id"], CONF["app_secret"]
PUBLIC_URL = CONF.get("public_url", "http://localhost:8000").rstrip("/")
# 生成物写入 webapp/generated, 并登记到 webapp/index.json, 使网页端可同步展示历史。
# 若不使用网页端, 这两个目录会被自动创建, 不影响飞书功能本身。
GEN = REPO / "webapp" / "generated"
INDEX = REPO / "webapp" / "index.json"

client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()


def send_text(message_id: str, text: str):
    req = ReplyMessageRequest.builder().message_id(message_id).request_body(
        ReplyMessageRequestBody.builder().content(
            json.dumps({"text": text}, ensure_ascii=False)
        ).msg_type("text").build()
    ).build()
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        print("send_text failed:", resp.code, resp.msg)


def send_file(message_id: str, chat_id: str, path: Path):
    try:
        with path.open("rb") as f:
            up = client.im.v1.file.create(
                CreateFileRequest.builder().request_body(
                    CreateFileRequestBody.builder().file_type("stream")
                    .file_name(path.name).file(f).build()
                ).build()
            )
        if not up.success():
            print(f"upload failed: {up.code} {up.msg}")
            return False
        resp = client.im.v1.message.create(
            CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                CreateMessageRequestBody.builder().receive_id(chat_id)
                .msg_type("file")
                .content(json.dumps({"file_key": up.data.file_key}))
                .build()
            ).build()
        )
        if not resp.success():
            print(f"send file msg failed: {resp.code} {resp.msg}")
            return False
        return True
    except Exception as e:
        print(f"send_file error: {type(e).__name__} {e}")
        return False


def download_pdf(message_id: str, file_key: str) -> bytes:
    resp = client.im.v1.message_resource.get(
        GetMessageResourceRequest.builder().message_id(message_id)
        .file_key(file_key).type("file").build()
    )
    if not resp.success():
        raise RuntimeError(f"下载文件失败: {resp.code} {resp.msg}")
    return resp.file.read()


def handle_pdf(message_id: str, chat_id: str, file_key: str, file_name: str, open_id: str = ""):
    d = GEN / uuid.uuid4().hex[:10]
    d.mkdir(parents=True, exist_ok=True)
    pdf_path = d / file_name
    pdf_path.write_bytes(download_pdf(message_id, file_key))
    try:
        words = vs.extract_words(pdf_path)
        if len(words) < 10:
            raise RuntimeError(f"PDF解析失败, 只识别到 {len(words)} 个单词")
        chunks = [words[i : i + 30] for i in range(0, len(words), 30)]
        passages = []
        for c in chunks:
            passages.append(vs.parse_output(vs.call_claude(vs.build_prompt(c))))
        # 网页版(在线链接备用, 同时登记网页历史)
        html_path = d / (pdf_path.stem + "_passage.html")
        html_path.write_text(vs.render_html(words, passages, pdf_path), encoding="utf-8")
        vs.generate_audio(html_path)
        # 登记到网页历史列表
        from datetime import datetime as _dt
        rows = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []
        rows.insert(0, {"id": d.name, "date": _dt.now().strftime("%Y-%m-%d %H:%M"),
                        "title": pdf_path.stem[-16:], "words": len(words),
                        "html": html_path.name, "dir": d.name})
        INDEX.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        # 最终交付: 单个离线HTML文件(高亮+点击释义+音频全部内嵌)
        offline = vs.make_offline_html(html_path)
        send_file(message_id, chat_id, offline)
    except Exception as e:
        send_text(message_id, f"❌ 生成失败: {e}")


def on_message(data: P2ImMessageReceiveV1):
    try:
        msg = data.event.message
        sender = (data.event.sender and data.event.sender.sender_id
                  and data.event.sender.sender_id.open_id) or ""
        if msg.message_type == "file":
            content = json.loads(msg.content)
            threading.Thread(
                target=handle_pdf,
                args=(msg.message_id, msg.chat_id, content.get("file_key"),
                      content.get("file_name", "words.pdf"), sender),
                daemon=True,
            ).start()
        elif msg.message_type == "text":
            # 待投递文件: pending_doc.json 存在时直接发送
            pending = HERE / "pending_doc.json"
            if pending.exists():
                try:
                    info = json.loads(pending.read_text(encoding="utf-8"))
                    print(f"[delivery] chat={msg.chat_id} file={info.get('file')}")
                    ok = send_file(msg.message_id, msg.chat_id, Path(info["file"]))
                    if ok:
                        pending.unlink()
                    else:
                        send_text(msg.message_id, "❌ 文件发送失败, 请查看电脑端日志")
                    return
                except Exception as e:
                    print(f"[delivery] error: {e}")
            send_text(msg.message_id, "请直接发送当日的单词 PDF 文件 📄")
    except Exception:
        import traceback; traceback.print_exc()


handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message).build()
ws = lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO)


def _setup_logging():
    """后台运行(计划任务)时 stdout 是黑洞, 统一重定向到 bot.log (UTF-8, 追加)"""
    import logging
    log_path = HERE / "bot.log"
    stream = open(log_path, "a", buffering=1, encoding="utf-8")
    sys.stdout = stream
    sys.stderr = stream
    # lark SDK 的日志走 logging 模块, 接到同一文件
    lark_log = logging.getLogger("lark_oapi")
    lark_log.setLevel(logging.INFO)
    if not lark_log.handlers:
        lark_log.addHandler(logging.StreamHandler(stream))


if __name__ == "__main__":
    _setup_logging()
    print("飞书机器人已启动, 等待消息... (手机上给机器人发PDF即可)")
    ws.start()
