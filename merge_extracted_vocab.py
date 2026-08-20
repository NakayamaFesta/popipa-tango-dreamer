#!/usr/bin/env python3
"""把 extracted_vocab/*.json 的新提取词汇合并进 vocab.json，并同步更新
词汇总表.md 和 index.html 里的 VOCAB 数据与硬编码计数。

规则：
- 原有 477 词 id 不变（学习进度按 id 关联，不能动）。
- 新词按 word 字符串去重：已存在的词只补充 songs 列表并更新 count；
  真正的新词分配新 id（从 max(id)+1 开始）。
- 同首歌提取结果内部也去重。
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT = HERE / "extracted_vocab"

vocab = json.load(open(HERE / "vocab.json", encoding="utf-8"))
manifest = json.load(open(EXT / "manifest.json", encoding="utf-8"))

by_word = {w["word"]: w for w in vocab}
next_id = max(w["id"] for w in vocab) + 1
added, merged = 0, 0

for k, meta in sorted(manifest.items(), key=lambda x: int(x[0])):
    title = meta["title"]
    items = json.load(open(EXT / f"{int(k):02d}.json", encoding="utf-8"))
    seen_in_song = set()
    for it in items:
        word = it["word"].strip()
        if not word or word in seen_in_song:
            continue
        seen_in_song.add(word)
        if word in by_word:
            w = by_word[word]
            if title not in w["songs"]:
                w["songs"].append(title)
                merged += 1
        else:
            w = {"id": next_id, "word": word, "reading": it["reading"].strip(),
                 "meaning": it["meaning"].strip(), "count": 0, "songs": [title]}
            if it.get("note"):
                w["note"] = it["note"]
            by_word[word] = w
            vocab.append(w)
            next_id += 1
            added += 1

for w in vocab:
    w["count"] = len(w["songs"])
    w["songs"].sort()

# 排序：出现歌曲数降序，同频次按读音五十音（保持原词表风格；id 不变）
vocab.sort(key=lambda w: (-w["count"], w["reading"]))

json.dump(vocab, open(HERE / "vocab.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

hi = [w for w in vocab if w["count"] >= 3]
mid = [w for w in vocab if w["count"] == 2]
lo = [w for w in vocab if w["count"] == 1]
total = len(vocab)
print(f"合并完成：总词数 {total}（新增 {added}，老词补充歌曲关联 {merged} 次）")
print(f"高频(≥3首) {len(hi)} · 中频(2首) {len(mid)} · 单首 {len(lo)}")

# ---------- 词汇总表.md ----------
def table(rows, start):
    out = ["| # | 单词 | 读音 | 释义 | 出现歌曲数 |", "|---|---|---|---|---|"]
    for i, w in enumerate(rows, start):
        note = "（惯用表达）" if w.get("note") else ""
        out.append(f"| {i} | {w['word']} | {w['reading']} | {w['meaning']}{note} | {w['count']} |")
    return "\n".join(out)

md = f"""# Poppin'Party 歌词词汇总表

> 来源：本文件夹 76 个歌词 md 的「日文歌词」栏目（2026-08-20 起由 LLM 全量穷尽提取，原为各 md「学唱词汇」栏目的 8 词精选）
> 去重合并后 **{total} 条**｜高频(≥3首) {len(hi)} 条、中频(2首) {len(mid)} 条、单首 {len(lo)} 条
> 排序：按出现歌曲数降序，同频次按五十音；标注「惯用表达」的为短语而非单词，背单词时可在页面设置里筛除
> 程序用数据见同目录 vocab.json（含每词出现的歌曲列表）


## 高频词（出现在 3 首及以上）（{len(hi)} 条）

{table(hi, 1)}

## 中频词（出现在 2 首）（{len(mid)} 条）

{table(mid, len(hi) + 1)}

## 单首词（出现在 1 首）（{len(lo)} 条）

{table(lo, len(hi) + len(mid) + 1)}
"""
open(HERE / "词汇总表.md", "w", encoding="utf-8").write(md)

# ---------- index.html ----------
html_path = HERE / "index.html"
html = html_path.read_text(encoding="utf-8")

vocab_js = json.dumps(vocab, ensure_ascii=False, separators=(",", ":"))
html, n = re.subn(r"^const VOCAB = \[.*\];\s*$", "const VOCAB = " + vocab_js + ";",
                  html, count=1, flags=re.M)
assert n == 1, "VOCAB 行替换失败"

html = html.replace("Poppin'Party 歌词词汇 · 477 词 · 76 首歌词",
                    f"Poppin'Party 歌词词汇 · {total} 词 · 76 首歌词")
html = html.replace('id="h-bar-meta">0 / 477<', f'id="h-bar-meta">0 / {total}<')
html = html.replace(f"🔥 高频词（3首以上，29 词）", f"🔥 高频词（3首以上，{len(hi)} 词）")
html = html.replace(f"⭐ 中频词（2首，60 词）", f"⭐ 中频词（2首，{len(mid)} 词）")
html = html.replace(f"🌱 单首词（388 词）", f"🌱 单首词（{len(lo)} 词）")
html_path.write_text(html, encoding="utf-8")
print("词汇总表.md 与 index.html 已更新")
