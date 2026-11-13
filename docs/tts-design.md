# 英文短文 → 语音文件 完整实现方案

> 版本：2026-11-08 · 已实测验证（Windows 11，音频样本见 `tts/` 测试输出）

## 1. 目标

- 输入：`English/` 下的每日单词短文 HTML（如 `20261108_passage.html`，含 6 篇短文，每篇按 `<br><br>` 分段）
- 输出：**每个段落一个独立 WAV/MP3 文件**，可单独点播、单独重生成
- 声音：**en-US-ChristopherNeural**（美式新闻权威男声，无电流声）
- 支持按段落选择音色 / 语速 / 音调

## 2. 技术选型（本机实测结论）

| 方案 | 结论 |
|---|---|
| **edge-tts（微软 Edge 神经语音）** | ✅ **采用**。音质高、400+ 音色、免费无 key。缺点：需联网 |
| VoiceStudio / KittenTTS（本地离线） | ❌ 80MB 模型底噪明显（"电流声"），仅适合快速预览 |
| VoiceStudio / OmniVoice（本地离线 2.4GB） | 备选。音质好、可克隆+风格指令，但要装数 GB 依赖；以后要离线再启用 |

**版本坑（重要）**：edge-tts ≤7.2.8 会被微软 403 拦截，必须用最新版（`pip install -U edge-tts`）。

## 3. 环境准备（一次性）

```powershell
# 建议独立 venv，避免污染其他项目
python -m venv D:\AIProject\study\English\.venv-tts
D:\AIProject\study\English\.venv-tts\Scripts\pip.exe install -U edge-tts
```

无需 GPU、无需 ffmpeg（edge-tts 直接输出 mp3/wav）。

## 4. 目录与命名规范

```
English/
├── 20261108_passage.html          # 源文件
├── docs/                          # 本方案文档
├── .venv-tts/                     # TTS 专用虚拟环境
└── audio/
    └── 20261108/                  # 按日期分目录
        ├── p1_para1.mp3           # 短文1 第1段
        ├── p1_para2.mp3
        ├── ...
        ├── p6_para5.mp3
        └── manifest.json          # 段落元数据（见 §7）
```

命名：`p{短文号}_para{段落号}.mp3`（如需多音色：`p1_para1_christopher.mp3`）。

## 5. 段落提取逻辑

HTML 中每篇短文在 `<div class="passage">` 内，正文按 `<br><br>` 分段；中文翻译在
`<details class="trans">` 内，**必须排除**。提取规则：

1. 用 `html.parser`（标准库，无依赖）取每个 `div.passage`；
2. 删除其中 `details.trans` 节点；
3. `get_text()` 后按 `\n\n` / 双换行切分段落；
4. 每段 `re.sub(r'\s+', ' ', ...)` 压成单行文本。

## 6. 生成脚本（已实测，源码即 `English/gen_audio.py`）

> 本文档的脚本以 `English/gen_audio.py` 为准（此处不重复粘贴）。
> 实测踩坑记录（已修复在脚本里）：
> 1. **嵌套 div**：`.passage` 内还有 `.ptitle` 等子 div，关闭标签时要用栈式深度计数，否则短文在第一个 `</div>` 就被提前截断；
> 2. **"短文 N" 标题**（`div.ptitle`）要跳过，否则混入首段；
> 3. **限流重试**：微软偶发 403/503，`synth()` 内置 5 次指数退避重试（3/6/9/12s）；
> 4. 实测该 HTML 为 **7 篇短文 / 共 30 段**（页首 meta 写 6 篇是旧数据）。

## 7. 点播页面（可选增强）

在 `audio/20261108/` 下生成一个 `player.html`：读取 `manifest.json`，渲染
"短文 N ▸ 段落列表"，每段一个 ▶ 按钮（`new Audio('p1_para2.mp3').play()`），
音色/语速下拉即时切换（调 `gen_audio.py --voice/--rate` 重新生成对应段）。
也可直接把 `<audio controls src>` 标签插入原 `20261108_passage.html` 每段末尾。

## 8. 推荐音色表（备选/混搭）

| 场景 | voice | 特点 |
|---|---|---|
| **默认** | `en-US-ChristopherNeural` | 新闻权威男声（已选定） |
| 英式 BBC 风 | `en-GB-RyanNeural` | 英式男主播 |
| 纪录片旁白 | `en-GB-ThomasNeural` | 英式沉稳 |
| 女主播 | `en-US-MichelleNeural` | 早间新闻亲切感 |
| 慢速跟读 | `--rate -15%` 任意音色 | 学习用 |

## 9. 局限与后续

- **需联网**：edge-tts 走微软云；文本会发往微软（短文内容无敏感性，可接受）。
- 若将来要求纯离线：启用 VoiceStudio 默认引擎 OmniVoice（约 2.4GB，支持 CUDA 推理），接口层不变，仅替换 `synth()` 实现。
- 微软偶尔更新接口导致 403：升级 edge-tts 即可（历史上已发生一次，见 §2）。
