# -*- coding: utf-8 -*-
"""
vocab_story.py — 每日背诵单词巩固工具
用法:
    python vocab_story.py English\20261108.pdf        # 完整流程: 提取单词 -> claude生成短文 -> 生成高亮HTML
    python vocab_story.py English\20261108.pdf --prompt  # 只输出prompt文件(手动粘贴到Claude网页版)
"""
import json
import re
import shutil
import subprocess
import sys
import html
from pathlib import Path

import pypdf

HERE = Path(__file__).parent

# 编号锚点: "23 involve" 后跟音标 /.../
ANCHOR = re.compile(r"(\d{1,3})\s+([A-Za-z][A-Za-z.'’\-]*)\s+(/[^/]+?/)")


def extract_words(pdf_path: Path) -> list[dict]:
    """从词表PDF提取 [{word, phonetic, meaning}] (按编号锚点分段, 兼容双栏交错排版)"""
    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join(p.extract_text() for p in reader.pages)
    anchors = list(ANCHOR.finditer(text))
    best: dict[int, dict] = {}
    for i, m in enumerate(anchors):
        n = int(m.group(1))
        if n in best:  # 同编号重复匹配取首次
            continue
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(text)
        meaning = text[m.end() : end]
        # 去掉段尾混入的下一个左栏词条编号开头(如 "21 tie /ta ɪ/" 出现在右栏词义中间)
        meaning = re.sub(r"\n?\d{1,3}\s+[A-Za-z][A-Za-z'’\-]*\s+/[^/\n]+/\s*$", "", meaning)
        meaning = re.sub(r"\s+", " ", meaning).strip(" ,")
        best[n] = {"word": m.group(2), "phonetic": m.group(3).strip(), "meaning": meaning}
    return [best[n] for n in sorted(best)]


def build_prompt(words: list[dict]) -> str:
    word_list = "\n".join(
        f"{i}. {w['word']} {w['phonetic']} {w['meaning']}" for i, w in enumerate(words, 1)
    )
    return f"""你是一位英语老师。请根据下面的单词表写一篇英语短文, 帮助学生巩固今日背诵的单词。

要求:
1. 短文长度 250-350 词, 讲一个连贯有趣的小故事。
2. 每个单词至少使用一次, 尽量使用其词表中的释义; 用不到的词可以在文末单独造一个短句补充。
3. 难度适合中学生, 除词表单词外的词汇尽量简单。
4. 严格按以下格式输出三段, 不要输出其他内容:

<passage>
短文正文(纯文本, 不要加粗或标记)
</passage>

<translation>
上文的逐句中文翻译
</translation>

<extra>
未用到的单词: 每个词一句简短例句, 没有则留空
</extra>

<glossary>
一个JSON对象, 包含短文中所有不属于上面单词表的英文单词(小写、去重、含词形还原, 专有名词也可包含):
{{"word1": "音标 中文释义", "word2": "音标 中文释义"}}
</glossary>

单词表:
{word_list}"""


def _claude_cmd() -> list[str]:
    """定位 claude CLI: 优先 PATH, 回退常见安装位置(计划任务/服务环境 PATH 不含用户目录)"""
    if shutil.which("claude"):
        return ["claude"]
    for cand in (Path.home() / ".local" / "bin" / "claude.exe",
                 Path.home() / ".local" / "bin" / "claude",
                 Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"):
        if cand.exists():
            return [str(cand)]
    return ["claude"]  # 找不到就按原名调用, 报错信息更直观


def call_claude(prompt: str) -> str:
    """调用本机 claude CLI (prompt 走 stdin, 10分钟超时, 失败重试一次)"""
    cmd = _claude_cmd()
    last_err = ""
    for _ in range(2):
        try:
            proc = subprocess.run(
                cmd + ["-p", "--model", "sonnet"],
                input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600,
            )
            if proc.returncode == 0:
                return proc.stdout
            last_err = proc.stderr[:500]
        except subprocess.TimeoutExpired:
            last_err = "claude CLI 超时(10分钟)"
    raise RuntimeError(f"claude CLI 失败: {last_err}")


def parse_output(out: str) -> dict:
    def grab(tag):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", out, re.S)
        return m.group(1).strip() if m else ""

    glossary = {}
    g = grab("glossary").strip().strip("`")
    if g.startswith("{") or g.find("{") >= 0:
        import json
        start, end = g.find("{"), g.rfind("}")
        if start >= 0 and end > start:
            try:
                glossary = {k.lower(): v for k, v in json.loads(g[start : end + 1]).items()}
            except Exception:
                pass
    return {"passage": grab("passage"), "translation": grab("translation"),
            "extra": grab("extra"), "glossary": glossary}


def render_html(words: list[dict], passages: list[dict], pdf_path: Path) -> str:
    """生成HTML: 高亮词表单词, 点击/悬停显示音标+释义; 每篇短文后附可折叠中文翻译"""
    lex = {w["word"].lower(): w for w in words}
    # 合并各组glossary: 非词表词 -> "音标 中文释义"
    gloss = {}
    for p in passages:
        for k, v in p.get("glossary", {}).items():
            gloss.setdefault(k.lower(), v)

    def stem(tok: str):
        t = tok.lower().strip(".,!?;:\"'()")
        for cand in (t, t[:-1] if t.endswith("e") else None,
                     t[:-3] + "ie" if t.endswith("ies") else None,
                     t[:-3] + "y" if t.endswith("ied") else None,
                     t[:-2] if t.endswith("ed") else None,
                     t[:-1] if t.endswith("s") else None,
                     t[:-2] if t.endswith("es") else None,
                     t[:-3] if t.endswith("ing") else None,
                     t[:-3] + "e" if t.endswith("ing") else None):
            if cand and cand in lex:
                return cand
        return None

    def glookup(tok: str):
        t = tok.lower().strip(".,!?;:\"'()")
        for cand in (t, t[:-1] if t.endswith("s") else None,
                     t[:-2] if t.endswith("es") else None,
                     t[:-2] if t.endswith("ed") else None,
                     t[:-3] + "y" if t.endswith("ied") else None,
                     t[:-3] if t.endswith("ing") else None):
            if cand and cand in gloss:
                return cand
        return None

    token_re = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
    used = set()

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        key = stem(tok)
        if key:
            used.add(key)
            w = lex[key]
            tip = html.escape(f"{w['word']} {w['phonetic']}\n{w['meaning']}")
            cls = "vw"
        else:
            gk = glookup(tok)
            if not gk:
                return tok
            tip = html.escape(gloss[gk])
            cls = "vw g2"
        return (f'<span class="{cls}" tabindex="0" data-tip="{tip}">'
                f"{tok}<span class='tip'></span></span>")

    def html_body(s: str) -> str:
        return token_re.sub(repl, html.escape(s).replace("\n", "<br>"))

    blocks = []
    paras_manifest = {}
    audio_stem = re.sub(r"_passage\.html$", "", pdf_path.stem)
    for i, p in enumerate(passages, 1):
        if not p.get("passage"):
            continue
        trans = p.get("translation", "")
        # 按空行分段, 每段后附 <audio>
        paras = [q for q in re.split(r"\n\s*\n", p["passage"]) if q.strip()]
        paras_manifest[f"p{i}"] = [re.sub(r"\s+", " ", q).strip() for q in paras]
        body = "".join(
            html_body(q) + f'<br><audio controls preload="none" class="au" src="audio/{audio_stem}/p{i}_para{si}.mp3"></audio>'
            for si, q in enumerate(paras, 1)
        )
        body += (f'<details class="trans"><summary>📖 中文翻译（点击展开）</summary>'
                 f"<div>{html.escape(trans).replace(chr(10), '<br>')}</div></details>"
                 if trans else "")
        blocks.append(f'<div class="passage"><div class="ptitle">短文 {i}</div>{body}</div>')
    extra = "\n".join(p.get("extra", "") for p in passages if p.get("extra"))
    html_extra = html_body(extra) if extra else ""
    word_cards = "\n".join(
        f'<div class="card{" miss" if w["word"].lower() not in used else ""}">'
        f"<b>{w['word']}</b> <span class='ph'>{html.escape(w['phonetic'])}</span>"
        f"<div class='mn'>{html.escape(w['meaning'])}</div></div>"
        for w in words
    )
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{pdf_path.stem} 每日单词短文</title>
<style>
:root{{--bg:#faf9f7;--fg:#2b2a28;--accent:#b45309;--hl:#fef3c7;--bd:#e5e1da;--tipbg:#2b2a28;--tipfg:#faf9f7}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1c1b19;--fg:#e8e4dd;--accent:#fbbf24;--hl:#4a3b12;--bd:#3a3733;--tipbg:#e8e4dd;--tipfg:#1c1b19}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.9 "Segoe UI",system-ui,sans-serif;padding:24px 16px}}
.wrap{{max-width:820px;margin:0 auto}}
h1{{font-size:20px;margin:0 0 4px}}
.meta{{color:var(--accent);font-size:13px;margin-bottom:18px}}
.passage{{background:var(--bg);border:1px solid var(--bd);border-radius:12px;padding:22px 26px;margin-bottom:22px}}
.ptitle{{font-size:13px;color:var(--accent);margin-bottom:8px}}
.au{{width:100%;height:36px;margin:6px 0 16px}}
.vw{{background:var(--hl);border-radius:3px;padding:0 2px;cursor:pointer;position:relative;outline:none}}
.vw b{{color:var(--accent);font-weight:600}}
.vw.g2{{background:transparent;text-decoration:underline dotted rgba(128,128,128,.6);text-underline-offset:3px}}
.vw .tip{{display:none;white-space:pre-wrap;position:absolute;left:0;top:130%;z-index:9;
  background:var(--tipbg);color:var(--tipfg);padding:10px 14px;border-radius:8px;font-size:13px;
  line-height:1.6;width:280px;box-shadow:0 4px 16px rgba(0,0,0,.3);font-weight:normal}}
.vw:hover .tip,.vw:focus .tip,.vw.open .tip{{display:block}}
details.trans{{margin-top:14px;border-top:1px dashed var(--bd);padding-top:8px}}
details.trans summary{{cursor:pointer;color:var(--accent);font-size:14px;user-select:none}}
details.trans div{{margin-top:8px;font-size:15px;opacity:.92}}
h2{{font-size:15px;margin:26px 0 10px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}}
.card{{border:1px solid var(--bd);border-radius:10px;padding:10px 14px;background:var(--bg)}}
.card.miss{{opacity:.55}}
.ph{{color:var(--accent);font-size:13px}}
.mn{{font-size:13px;opacity:.85}}
.extra{{border-left:3px solid var(--accent);padding:4px 14px;font-size:14px;opacity:.9}}
</style></head><body><div class="wrap">
<h1>每日单词巩固短文</h1>
<div class="meta">{pdf_path.stem} · 共 {len(words)} 词 · 短文覆盖 {len(used)} 词 · 未覆盖 {len(words)-len(used)} 词(卡片半透明)</div>
{''.join(blocks)}
{f'<h2>补充例句</h2><div class="extra">{html_extra}</div>' if html_extra else ''}
<h2>单词表（点击单词卡片外的正文高亮词可查看释义）</h2>
<div class="cards">{word_cards}</div>
<script type="application/json" id="paras-json">{json.dumps(paras_manifest, ensure_ascii=False)}</script>
<script>
document.querySelectorAll('.vw').forEach(el=>el.addEventListener('click',e=>{{
  const tip=el.querySelector('.tip');tip.textContent=el.dataset.tip;
  document.querySelectorAll('.vw.open').forEach(o=>{{if(o!==el)o.classList.remove('open')}});
  el.classList.toggle('open');e.stopPropagation();
}}));
document.addEventListener('click',()=>document.querySelectorAll('.vw.open').forEach(o=>o.classList.remove('open')));
document.querySelectorAll('.vw').forEach(el=>{{const tip=el.querySelector('.tip');tip.textContent=el.dataset.tip;}});
</script>
</div></body></html>"""


def generate_audio(html_path: Path) -> bool:
    """调用 tts/gen_audio.py 为已生成的HTML合成逐段音频(失败不阻塞)

    解释器选择: 优先用 tts/.venv 专用虚拟环境; 若不存在则回退到当前解释器
    (此时需保证 edge-tts 已随主环境安装)。
    """
    script = HERE / "tts" / "gen_audio.py"
    if not script.exists():
        print("⚠ 未找到 tts/gen_audio.py, 跳过音频生成")
        return False
    venv_py = HERE / "tts" / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    try:
        proc = subprocess.run([py, str(script), "--src", str(html_path)],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=1800)
        try:
            print((proc.stdout or "")[-500:])
        except UnicodeEncodeError:
            pass
        return proc.returncode == 0
    except Exception as e:
        try:
            print(f"TTS skipped/failed: {e}")
        except UnicodeEncodeError:
            pass
        return False


def make_offline_html(html_path: Path) -> Path:
    """生成自包含离线版HTML: 音频base64内嵌, 单文件可离线查看+播放"""
    import base64
    h = html_path.read_text(encoding="utf-8")

    def embed(m: re.Match) -> str:
        mp3 = html_path.parent / m.group(1)
        if not mp3.exists():
            return m.group(0)
        b64 = base64.b64encode(mp3.read_bytes()).decode()
        return f'src="data:audio/mpeg;base64,{b64}"'

    out = re.sub(r'src="((?:audio/)[^"]+\.mp3)"', embed, h)
    out_path = html_path.with_name(html_path.stem.replace("_passage", "") + "_offline.html")
    out_path.write_text(out, encoding="utf-8")
    return out_path


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        sys.exit(1)
    pdf_path = Path(args[0])
    words = extract_words(pdf_path)
    print(f"提取到 {len(words)} 个单词: {', '.join(w['word'] for w in words[:10])}...")
    if len(words) < 10:
        raise SystemExit("提取失败: 单词过少, 请检查PDF格式")

    chunks = [words[i : i + 30] for i in range(0, len(words), 30)]
    print(f"分为 {len(chunks)} 组, 每组生成一篇短文")

    prompts = [build_prompt(c) for c in chunks]
    (HERE / "prompt.txt").write_text("\n\n=====\n\n".join(prompts), encoding="utf-8")

    if "--prompt" in flags:
        print("prompt 已写入 prompt.txt, 可粘贴到 Claude 网页版")
        return
    passages = []
    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] 调用 claude 生成短文...")
        res = parse_output(call_claude(prompt))
        passages.append(res)
    out_html = pdf_path.with_name(pdf_path.stem + "_passage.html")
    out_html.write_text(render_html(words, passages, pdf_path), encoding="utf-8")
    print(f"完成: {out_html}")
    print("生成音频 (edge-tts)...")
    generate_audio(out_html)


if __name__ == "__main__":
    main()
