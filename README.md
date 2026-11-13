# DeepenWordMemory 📚

把每日背诵的**单词表 PDF** 变成一篇**带高亮、点击释义、逐段朗读音频**的英语短文，帮助巩固记忆。

核心思路：从词表 PDF 提取单词 → 调用 Claude 为每 30 个单词写一篇 250–350 词的小故事 → 渲染成交互式 HTML（词表词高亮、悬停/点击显示音标+释义、可折叠中文翻译、逐段 TTS 音频）→ 可生成单文件离线版。

---

## 架构

本仓库按**可选模块**组织，核心只依赖一个库：

| 模块 | 路径 | 作用 | 额外依赖 |
|------|------|------|----------|
| **核心** | `vocab_story.py` | 提词 → 生成短文 → 渲染 HTML → 离线包 | `pypdf` + 本机 `claude` CLI |
| **TTS** | `tts/` | 逐段语音合成（edge-tts） | `edge-tts` |
| **网页** | `webapp/` | 手机上传 PDF / 浏览历史（FastAPI + PWA） | `fastapi`, `uvicorn` |
| **飞书** | `feishu/` | 飞书机器人收 PDF → 回发离线 HTML（**独立模块**） | `lark-oapi` |

> 飞书是**额外能力，单独成模块**：不装 `lark-oapi`、不配飞书应用，核心与网页功能完全不受影响。

---

## 环境要求

- **Python 3.10+**（用了 `list[dict]` 等语法）
- **本机 `claude` CLI** 已登录（核心调用 `claude -p --model sonnet` 走 stdin 生成短文）。安装见 https://claude.ai/code
- Windows / macOS / Linux 均可（脚本用 `pathlib`，TTS venv 路径在非 Windows 上需自行调整 `Scripts/` → `bin/`）

---

## 安装

```bash
git clone https://github.com/ShawnShiBuilds/DeepenWordMemory.git
cd DeepenWordMemory

# 1) 核心依赖
pip install -r requirements.txt

# 2)（可选）TTS 音频
pip install -r tts/requirements.txt

# 3)（可选）网页服务
pip install -r webapp/requirements.txt

# 4)（可选）飞书机器人
pip install -r feishu/requirements.txt
```

---

## 使用

### A. 命令行（最基础）

```bash
# 完整流程：提词 → Claude 生成 → 渲染高亮 HTML → 合成音频
python vocab_story.py path/to/20261108.pdf

# 只生成 prompt 文件，手动粘贴到 Claude 网页版（不调用 CLI）
python vocab_story.py path/to/20261108.pdf --prompt
```

输出：`<日期>_passage.html`（在线版，音频为相对路径）+ `audio/<日期>/*.mp3`。
若 TTS 可用，还会合成逐段音频嵌入 HTML。

### B. 网页服务（手机上传）

```bash
cd webapp
python server.py
# 访问 http://<本机IP>:8000  (手机同 WiFi)
```

手机打开页面 → 上传当日单词 PDF → 自动生成 → 跳转阅读。历史短文列表常驻首页。
详见 [`webapp/README.md`](webapp/README.md)。

### C. 飞书机器人（独立模块）

在飞书开放平台创建一个自建应用，订阅 `im.message` 接收消息事件，把凭证填入配置：

```bash
cd feishu
cp feishu_config.example.json feishu_config.json   # 填入 app_id / app_secret
python feishu_bot.py
```

手机上给机器人发 PDF → 自动生成 → 回发一个**自包含离线 HTML**（音频 base64 内嵌，单文件即可离线查看播放）。
详见 [`feishu/README.md`](feishu/README.md)。

---

## 词表 PDF 格式要求

提取依赖**编号锚点**正则：`\d{1,3} 单词 /音标/`，例如：

```
1 involve /ɪnˈvɒlv/ 包含; 卷入
2 abundant /əˈbʌndənt/ 丰富的
...
```

要求：每词一行、有编号、紧跟音标（`/.../`）。兼容双栏交错排版。识别不足 10 词会报错。

---

## 项目结构

```
DeepenWordMemory/
├── vocab_story.py            # 核心：提词 / 生成 / 渲染 / 离线包
├── requirements.txt          # pypdf
├── tts/
│   ├── gen_audio.py          # edge-tts 逐段合成
│   └── requirements.txt
├── webapp/
│   ├── server.py             # FastAPI 上传/浏览服务
│   ├── static/               # PWA 首页 + 图标 + service worker
│   └── requirements.txt
├── feishu/
│   ├── feishu_bot.py         # 飞书机器人（收 PDF → 回发离线 HTML）
│   ├── feishu_doc.py         # 飞书云文档写入（备选投递方式）
│   ├── feishu_config.example.json
│   └── requirements.txt
└── docs/
    └── tts-design.md         # TTS 选型说明
```

---

## 安全提示 ⚠️

- `feishu/feishu_config.json` 含真实密钥，**已被 `.gitignore` 忽略**，切勿提交。仓库只提供 `feishu_config.example.json` 模板。
- 词表 PDF 属个人数据，同样被 `.gitignore` 忽略。
- 生成产物（`generated/`、`*_passage.html`、`audio/`、`index.json` 等）均不入库。

---

## 许可

个人学习用途，MIT。
