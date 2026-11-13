# 网页服务（可选模块）

FastAPI 服务：手机上传当日单词 PDF，自动生成短文并在浏览器阅读，历史列表常驻。

## 安装

```bash
pip install -r webapp/requirements.txt   # fastapi, uvicorn
```

## 启动

```bash
python webapp/server.py
# 本机:   http://localhost:8000
# 手机:   http://<本机IP>:8000  (需同 WiFi, 或用内网穿透/公网 IP)
```

## 接口

| 方法 | 路径 | 作用 |
|------|------|------|
| GET  | `/` | 首页（上传 + 历史列表，PWA） |
| POST | `/api/upload` | 上传 PDF，返回 task_id |
| GET  | `/api/status/{id}` | 轮询生成进度 |
| GET  | `/api/list` | 历史短文列表 |
| GET  | `/doc/{id}` | 重定向到某篇短文 HTML |
| GET  | `/fs/{dir}/{file}` | 静态托管生成物（HTML/音频） |

## 工作流

1. 手机选 PDF → POST `/api/upload`
2. 后台线程：`extract_words` → 分组调 Claude → `render_html` → `generate_audio`
3. 前端每 2s 轮询 `/api/status/{id}`，完成后跳转 `/doc/{id}`

## 与飞书模块的关系

`feishu/feishu_bot.py` 默认把生成物写入 `webapp/generated/` 并登记到 `webapp/index.json`，
因此飞书生成的短文也会出现在网页历史列表里。若你不用飞书，本模块完全独立可用。
