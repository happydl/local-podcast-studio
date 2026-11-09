#!/usr/bin/env python3
"""从 report.json 反推章节时间轴：复算切句单元，按关键词对齐到段落起点。

用法: python3 make_chapters.py episodes/ep01/ep01.report.json episodes/ep01/script_zh.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_pipeline import PARA_PAUSE, SENT_PAUSE, pack, parse_script  # noqa: E402

CHAPTERS = [
    ("00:00", "开场：真正卡住你的不是选题", "如果要给"),
    ("", "测试环境：一台 Mac，全离线", "先说清楚测试环境"),
    ("", "速度实测：2.7 倍实时", "第一次测速"),
    ("", "成本账：省下的只有一块钱", "接下来是成本"),
    ("", "本地化到底买到了什么", "真正值得本地跑的理由"),
    ("", "音色是描述出来的，不是挑出来的", "说到音色"),
    ("", "四个必须自己缝的坑", "不过，工具能解决的是摩擦"),
    ("", "分发：RSS 就够了", "再说一件工程上的小事"),
    ("", "结论：适合谁，不适合谁", "最后说结论"),
    ("", "最小可行路径三步", "如果你也想试"),
    ("", "下期预告", "下一集"),
]


def fmt(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def main() -> int:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    paragraphs = parse_script(Path(sys.argv[2]))
    units = pack(paragraphs)
    durations = [u["audio_seconds"] for u in report["units"]]
    assert len(durations) == len(units), f"{len(durations)} != {len(units)}"

    # 单元 -> 起始时间（含停顿时长）
    starts, t = [], 0.0
    for i, (text, para_end) in enumerate(units):
        starts.append(t)
        t += durations[i]
        if i < len(units) - 1:
            t += PARA_PAUSE if para_end else SENT_PAUSE

    lines = []
    for stamp, title, anchor in CHAPTERS:
        idx = next((i for i, (text, _) in enumerate(units) if anchor in text), None)
        if idx is None:
            lines.append(f"- {stamp or '??:??'} {title}  <!-- anchor not found: {anchor} -->")
            continue
        lines.append(f"- `{fmt(starts[idx])}` {title}")
    print(f"总时长 {fmt(t)}\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
