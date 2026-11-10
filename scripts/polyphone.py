#!/usr/bin/env python3
"""朗读稿多音字校准：TTS 不接受拼音/SSML，只能在文本层解决。

两种策略，按优先级：
  1) 上下文改写（首选）：把多音字换成意思相同、读音唯一的词，例如「量了一下」→「测量了一下」
  2) 同音字替换（次选）：保留原句，把字换成单音同音字，例如「逐段量了一遍」→「逐段良了一遍」
     —— 只影响朗读稿，不影响字幕/文章；副作用是稿子不再能当文字稿用

用法:
    python3 polyphone.py --check scripts/episode01_zh.txt
    python3 polyphone.py --apply scripts/episode01_zh.txt      # 写出 *.calibrated.txt + 报告
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# (正则, 替换, 读音, 策略, 置信度, 说明)
RULES: list[tuple[str, str, str, str, str, str]] = [
    # 量：liáng（测量） / liàng（数量）
    (r"量了一下", "测量了一下", "liáng", "rewrite", "high", "动词'量'读二声，模型常读四声"),
    (r"量了一遍", "测量了一遍", "liáng", "rewrite", "high", "同上"),
    (r"量一量", "测量一下", "liáng", "rewrite", "high", "同上"),
    (r"量过", "测量过", "liáng", "rewrite", "mid", "同上"),
    (r"逐段量", "逐段测", "liáng", "rewrite", "high", "同上"),
    (r"量尺寸", "测量尺寸", "liáng", "rewrite", "high", "同上"),
    # 长：cháng（长短） / zhǎng（生长）
    (r"长大", "长大", "zhǎng", "note", "mid", "应为 zhǎng，若听成 cháng 改写为'成长'"),
    (r"增长", "增长", "zēng zhǎng", "note", "high", "通常正确，仅登记"),
    # 还：hái（还是） / huán（归还）
    (r"归还", "归还", "huán", "note", "high", "若读 hái，改写为'还给'"),
    # 得：dé / děi / de
    (r"得说清楚", "得说清楚", "děi", "homophone", "mid", "déi 无单音同音字，建议上下文改写"),
    (r"跑得快", "跑得快", "de", "note", "mid", "轻声 de，若读 dé 改写为'跑得很快'"),
    # 数：shù / shǔ
    (r"数了一下", "数了一遍", "shǔ", "rewrite", "high", "动词'数'读三声"),
    (r"数了数", "数了一遍", "shǔ", "rewrite", "high", "同上"),
    # 重：zhòng / chóng
    (r"重跑", "重新跑", "chóng", "rewrite", "high", "'重'表 again 读 chóng"),
    (r"重做", "重新做", "chóng", "rewrite", "high", "同上"),
    (r"重写", "重新写", "chóng", "rewrite", "high", "同上"),
    # 分：fēn / fèn
    (r"分不清", "分不清", "fēn", "note", "high", "通常正确"),
    (r"本分", "本分", "fèn", "note", "mid", "四声，易错"),
    # 干：gān / gàn
    (r"干净", "干净", "gān", "note", "high", "通常正确"),
    (r"干活", "干活", "gàn", "note", "mid", "四声，易错"),
    # 露：lù / lòu
    (r"露馅", "露馅", "lòu", "note", "mid", "口语 lòu，易读 lù"),
    (r"露脸", "露脸", "lòu", "note", "mid", "同上"),
    # 着：zhe / zháo / zhuó
    (r"着火", "着火", "zháo", "note", "mid", "易读 zhe"),
    (r"着手", "着手", "zhuó", "note", "mid", "易读 zhe"),
    # 地：de / dì
    (r"慢慢地", "慢慢地", "de", "note", "high", "轻声"),
    # 载：zǎi / zài
    (r"下载", "下载", "xià zài", "note", "high", "四声，易读三声"),
    (r"记载", "记载", "zǎi", "note", "mid", "三声"),
    # 转：zhuǎn / zhuàn
    (r"转了一圈", "转了一圈", "zhuàn", "note", "mid", "四声"),
    # 发：fā / fà
    (r"发型", "发型", "fà", "note", "mid", "四声"),
    # 觉：jué / jiào
    (r"睡觉", "睡觉", "jiào", "note", "high", "四声"),
    # 血：xuè / xiě
    (r"流血", "流血", "xiě", "note", "mid", "口语 xiě"),
    # 薄：báo / bó
    (r"薄片", "薄片", "báo", "note", "mid", "口语 báo"),
    # 了：le / liǎo
    (r"了解", "了解", "liǎo", "note", "high", "三声"),
    # 和：hé / huò / hè
    (r"附和", "附和", "hè", "note", "mid", "四声"),
    # 差：chā / chà / chāi
    (r"差一点", "差一点", "chà", "note", "mid", "四声"),
    (r"出差", "出差", "chāi", "note", "mid", "chāi"),
]


def audit(text: str) -> list[dict]:
    hits = []
    for pattern, repl, reading, strategy, confidence, note in RULES:
        for m in re.finditer(pattern, text):
            hits.append({
                "match": m.group(0), "start": m.start(), "reading": reading,
                "strategy": strategy, "confidence": confidence, "replacement": repl,
                "note": note, "context": text[max(0, m.start() - 12):m.end() + 12],
            })
    hits.sort(key=lambda h: h["start"])
    return hits


def apply(text: str) -> tuple[str, list[dict]]:
    """应用改写。命中区间重叠时按"起点更靠前、匹配更长"优先，重叠的直接丢弃。"""
    hits = sorted((h for h in audit(text) if h["strategy"] in ("rewrite", "homophone")),
                  key=lambda h: (h["start"], -len(h["match"])))
    chosen: list[dict] = []
    cursor = 0
    for h in hits:
        if h["start"] < cursor:
            continue
        chosen.append(h)
        cursor = h["start"] + len(h["match"])
    out, cursor = [], 0
    for h in chosen:
        out.append(text[cursor:h["start"]])
        out.append(h["replacement"])
        cursor = h["start"] + len(h["match"])
    out.append(text[cursor:])
    return "".join(out), chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    path = Path(args.script)
    text = path.read_text(encoding="utf-8")

    if args.apply:
        new, applied = apply(text)
        out_path = path.with_suffix(".calibrated.txt")
        out_path.write_text(new, encoding="utf-8")
        report = path.with_suffix(".polyphone.json")
        report.write_text(json.dumps(applied, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已改写 {len(applied)} 处 → {out_path}")
        for h in applied:
            print(f"  {h['match']} → {h['replacement']}  ({h['reading']}, {h['confidence']})")
        print(f"报告: {report}")
        return 0

    hits = audit(text)
    todo = [h for h in hits if h["strategy"] in ("rewrite", "homophone")]
    notes = [h for h in hits if h["strategy"] == "note"]
    print(f"命中 {len(hits)} 处：需改写 {len(todo)} 处，仅提示 {len(notes)} 处\n")
    for h in hits:
        flag = "改写" if h["strategy"] in ("rewrite", "homophone") else "提示"
        print(f"[{flag}] {h['match']} → {h['reading']}  {h['confidence']:<4} | {h['context']}")
    if todo:
        print(f"\n可自动改写 {len(todo)} 处，运行 --apply 生成 *.calibrated.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
