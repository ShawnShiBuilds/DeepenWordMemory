# TTS 音频合成（可选模块）

为 `vocab_story.py` 生成的 HTML 合成**逐段朗读音频**，使用微软 edge-tts（免费、无需 API key）。

## 安装

```bash
pip install -r tts/requirements.txt   # edge-tts
```

或建独立 venv（与核心环境隔离，推荐）：

```bash
python -m venv tts/.venv
# Windows
tts/.venv/Scripts/python -m pip install edge-tts
# macOS/Linux
tts/.venv/bin/python -m pip install edge-tts
```

`vocab_story.generate_audio()` 会优先用 `tts/.venv`，找不到时回退到当前解释器。

## 用法

通常无需直接调用——`vocab_story.py` 和 `webapp/server.py` 会自动调用。

手动为某个 HTML 补音频：

```bash
python tts/gen_audio.py --src path/to/20261108_passage.html
# 或按日期
python tts/gen_audio.py 20261108
# 指定短文/段落、换声音、调语速
python tts/gen_audio.py 20261108 --passage 1 --para 2 3 --voice en-GB-RyanNeural --rate -10%
```

输出：HTML 同目录下 `audio/<日期>/p{N}_para{M}.mp3` + `manifest.json`。

## 默认声音

`en-US-ChristopherNeural`（美式男声）。更多声音见 `edge-tts --list-voices`。
选型理由见 [`../docs/tts-design.md`](../docs/tts-design.md)。
