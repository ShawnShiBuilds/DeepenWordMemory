# -*- coding: utf-8 -*-
"""每日单词短文 - 手机上传PDF/浏览服务
启动: python server.py  (手机同WiFi访问 http://本机IP:8000)
"""
import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import vocab_story as vs

HERE = Path(__file__).parent
GEN = HERE / "generated"
GEN.mkdir(exist_ok=True)
INDEX = HERE / "index.json"

app = FastAPI()
TASKS = {}  # id -> {status, done, total, error, date, title, dir}


def load_index():
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return []


def save_index(rows):
    INDEX.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def run_task(task_id: str, pdf_path: Path, title: str):
    t = TASKS[task_id]
    try:
        words = vs.extract_words(pdf_path)
        if len(words) < 10:
            raise RuntimeError(f"PDF解析失败, 只识别到 {len(words)} 个单词")
        chunks = [words[i : i + 30] for i in range(0, len(words), 30)]
        t.update(total=len(chunks), status="running", words=len(words))
        passages = []
        for prompt in (vs.build_prompt(c) for c in chunks):
            passages.append(vs.parse_output(vs.call_claude(prompt)))
            t["done"] += 1
        html_path = pdf_path.parent / (pdf_path.stem + "_passage.html")
        html_path.write_text(vs.render_html(words, passages, pdf_path), encoding="utf-8")
        t.update(status="audio", html=html_path.name)
        vs.generate_audio(html_path)
        t.update(status="done", html=html_path.name)
        rows = load_index()
        rows.insert(0, {"id": task_id, "date": t["date"], "title": title,
                        "words": len(words), "html": html_path.name, "dir": str(pdf_path.parent.relative_to(GEN))})
        save_index(rows)
    except Exception as e:
        t.update(status="error", error=str(e)[:300])


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "只能上传PDF")
    task_id = uuid.uuid4().hex[:10]
    d = GEN / task_id
    d.mkdir(exist_ok=True)
    pdf_path = d / file.filename
    with pdf_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    TASKS[task_id] = {"status": "queued", "done": 0, "total": 0, "error": "",
                      "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                      "title": Path(file.filename).stem, "dir": task_id}
    threading.Thread(target=run_task, args=(task_id, pdf_path, Path(file.filename).stem), daemon=True).start()
    return {"id": task_id}


@app.get("/api/status/{task_id}")
def status(task_id: str):
    t = TASKS.get(task_id)
    if not t:
        raise HTTPException(404)
    return t


@app.get("/api/list")
def list_docs():
    return load_index()


@app.get("/doc/{task_id}")
def doc(task_id: str):
    rows = [r for r in load_index() if r["id"] == task_id]
    if not rows:
        raise HTTPException(404)
    from fastapi.responses import RedirectResponse
    # 重定向到 /fs 路径结构, 保证HTML内相对音频路径(audio/...)可用
    return RedirectResponse(f"/fs/{rows[0]['dir']}/{rows[0]['html']}")


@app.get("/fs/{d}/{f:path}")
def fs_doc(d: str, f: str):
    # 飞书机器人生成的文档 (防止路径穿越)
    p = (GEN / d / f).resolve()
    if not str(p).startswith(str(GEN.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="text/html")


app.mount("/", StaticFiles(directory=str(HERE / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("启动: http://localhost:8000  (手机访问 http://本机IP:8000)")
    uvicorn.run(app, host="0.0.0.0", port=8000)
