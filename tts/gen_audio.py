"""每日短文 -> 逐段语音 (edge-tts)
用法:
  python gen_audio.py 20261108                     # 全部段落
  python gen_audio.py 20261108 --passage 1         # 只生成短文1
  python gen_audio.py 20261108 --passage 1 --para 2 3   # 指定段落
  python gen_audio.py 20261108 --voice en-GB-RyanNeural --rate -10%
"""
import argparse, asyncio, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

import edge_tts

VOICE_DEFAULT = "en-US-ChristopherNeural"   # 选定：美式新闻权威男声
RATE_DEFAULT = "+0%"

class PassageParser(HTMLParser):
    """提取 div.passage 的纯文本段落，排除 details.trans（中文翻译）。"""
    def __init__(self):
        super().__init__()
        self.passages, self._bufs = [], []
        self._div_stack = []    # 每层 div 是否属于当前 passage 内部
        self._in_passage = False
        self._ptitle_depth = 0
        self._skip = 0          # details 嵌套计数（跳过翻译）

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            inside = self._in_passage
            self._div_stack.append(inside)
            if not inside and "passage" in (a.get("class") or "").split():
                self._in_passage = True
                self._bufs.append([])
            elif inside and (a.get("class") or "").split() == ["ptitle"]:
                self._ptitle_depth += 1
                self._skip += 1   # 丢弃 "短文 N" 标题
        elif tag == "details":
            self._skip += 1
        elif tag == "br" and self._in_passage and not self._skip:
            self._bufs[-1].append("\n\n")   # <br> 作分段锚点

    def handle_endtag(self, tag):
        if tag == "div" and self._div_stack:
            was_inside = self._div_stack.pop()
            if was_inside and self._ptitle_depth:
                self._ptitle_depth -= 1
                self._skip -= 1
            elif not was_inside and self._in_passage:
                # passage 根 div 关闭
                self._in_passage = False
                text = "".join(self._bufs.pop())
                paras = [re.sub(r"\s+", " ", p).strip()
                         for p in text.split("\n\n")]
                self.passages.append([p for p in paras if p])
        elif tag == "details" and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_passage and not self._skip:
            self._bufs[-1].append(data)

async def synth(text: str, out: Path, voice: str, rate: str):
    """单段合成，带重试（微软偶发 403/503 限流）。"""
    import asyncio as _aio
    for attempt in range(5):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
            return
        except Exception as e:
            if attempt == 4:
                raise
            wait = 3 * (attempt + 1)
            print(f"  重试 {attempt+1}/4（{type(e).__name__}，等待 {wait}s）")
            await _aio.sleep(wait)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="如 20261108，对应 {date}_passage.html")
    ap.add_argument("--passage", type=int)
    ap.add_argument("--para", type=int, nargs="+")
    ap.add_argument("--voice", default=VOICE_DEFAULT)
    ap.add_argument("--rate", default=RATE_DEFAULT, help="如 -15% 慢速")
    ap.add_argument("--src", help="直接指定HTML路径(优先于date)")
    ap.add_argument("--out", help="直接指定输出目录(默认 HTML同目录/audio/<日期>")
    args = ap.parse_args()

    if args.src:
        src = Path(args.src)
        outdir = Path(args.out) if args.out else src.parent / "audio" / re.sub(r"_passage$", "", src.stem)
    else:
        if not args.date:
            ap.error("需要 date 或 --src")
        src = Path(__file__).parent / f"{args.date}_passage.html"
        outdir = Path(args.out) if args.out else Path(__file__).parent / "audio" / args.date
    outdir.mkdir(parents=True, exist_ok=True)

    parser = PassageParser()
    src_text = src.read_text(encoding="utf-8")
    passages = None
    # 优先使用HTML内嵌的权威段落JSON(与<audio>标签严格一致)
    m = re.search(r'<script type="application/json" id="paras-json">(.*?)</script>', src_text, re.S)
    if m:
        data = json.loads(m.group(1))
        passages = [data[k] for k in sorted(data, key=lambda x: int(x[1:]))]
        print(f"使用内嵌段落JSON: {sum(len(v) for v in passages)} 段")
    if passages is None:
        parser.feed(src_text)
        passages = parser.passages
    if not passages:
        sys.exit("未解析到短文，检查 HTML 结构")

    manifest = []
    for pi, paras in enumerate(passages, 1):
        if args.passage and pi != args.passage:
            continue
        for si, text in enumerate(paras, 1):
            if args.para and si not in args.para:
                continue
            out = outdir / f"p{pi}_para{si}.mp3"
            print(f"[{out.name}] {text[:50]}...")
            asyncio.run(synth(text, out, args.voice, args.rate))
            manifest.append({"file": out.name, "passage": pi,
                             "para": si, "chars": len(text),
                             "preview": text[:60], "voice": args.voice})
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{len(manifest)} 段 -> {outdir}")

if __name__ == "__main__":
    main()
