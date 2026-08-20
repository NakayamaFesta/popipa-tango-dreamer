#!/usr/bin/env python3
"""为 index.html 里的 VOCAB 单词批量生成日语朗读 mp3（edge-tts）。

用法:
  python gen_word_audio.py           # 生成全部缺失的（已存在的跳过）
  python gen_word_audio.py 1 2 3     # 只生成指定 id
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
HTML = HERE / "index.html"
OUT = HERE / "audio" / "words"
VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"
CONCURRENCY = 5


def load_vocab():
    text = HTML.read_text(encoding="utf-8")
    m = re.search(r"^const VOCAB = (\[.*\]);\s*$", text, re.M)
    if not m:
        sys.exit("在 HTML 里没找到 VOCAB 数组")
    return json.loads(m.group(1))


async def gen_one(sem, item):
    wid = item["id"]
    text = item.get("reading") or item["word"]
    path = OUT / f"{wid}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return wid, "skip"
    async with sem:
        for attempt in range(3):
            try:
                await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
                return wid, "ok"
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    return wid, f"fail: {e}"
                await asyncio.sleep(2 * (attempt + 1))


async def main():
    ids = {int(a) for a in sys.argv[1:]}
    vocab = load_vocab()
    if ids:
        vocab = [w for w in vocab if w["id"] in ids]
        if not vocab:
            sys.exit("指定 id 不在词表里")
    OUT.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(gen_one(sem, w) for w in vocab))
    good = sum(1 for _, s in results if s in ("ok", "skip"))
    fails = [(i, s) for i, s in results if s not in ("ok", "skip")]
    print(f"完成 {good}/{len(results)}，失败 {len(fails)}")
    for i, s in fails[:10]:
        print(f"  id={i}: {s}")


if __name__ == "__main__":
    asyncio.run(main())
