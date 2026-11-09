#!/usr/bin/env python3
"""生成播客 RSS（iTunes 命名空间），输出可直接被播客客户端订阅的 feed.xml。

用法:
    python3 make_feed.py --base https://example.github.io/repo --out repo/feed.xml
"""
from __future__ import annotations

import argparse
import json
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

SHOW = {
    "title": "本地优先 · Local First",
    "link": "",
    "description": "用一台 Mac 和本地模型，把文字变成可以听的节目。"
                   "每期一个实测：成本、速度、边界，以及踩过的坑。",
    "author": "happydl",
    "email": "happydl@example.com",
    "language": "zh-cn",
    "category": "Technology",
    "explicit": "false",
}


def probe_duration(path: Path) -> float:
    """读音频时长：wav 直接用 wave，m4a 用 macOS 的 afinfo。"""
    if path.suffix != ".m4a":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    out = subprocess.run(["/usr/bin/afinfo", str(path)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "estimated duration" in line:
            return float(line.split(":")[1].strip().split()[0])
    raise RuntimeError(f"无法读取时长: {path}")


def duration_str(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="站点根地址，例如 https://user.github.io/repo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--episodes", nargs="+", required=True, help="音频文件路径（按集数顺序）")
    ap.add_argument("--titles", nargs="+", required=True)
    args = ap.parse_args()

    base = args.base.rstrip("/")
    items = []
    for audio, title in zip(args.episodes, args.titles):
        p = Path(audio)
        dur = probe_duration(p)
        size = p.stat().st_size
        pub = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        items.append(f"""    <item>
      <title>{escape(title)}</title>
      <description>{escape(title)}</description>
      <enclosure url="{base}/{p.as_posix()}" length="{size}" type="audio/mp4"/>
      <guid isPermaLink="false">{base}/{p.as_posix()}</guid>
      <pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
      <itunes:duration>{duration_str(dur)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(SHOW['title'])}</title>
    <link>{base}</link>
    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{escape(SHOW['description'])}</description>
    <language>{SHOW['language']}</language>
    <itunes:author>{SHOW['author']}</itunes:author>
    <itunes:summary>{escape(SHOW['description'])}</itunes:summary>
    <itunes:explicit>{SHOW['explicit']}</itunes:explicit>
    <itunes:category text="{SHOW['category']}"/>
    <itunes:image href="{base}/cover.jpg"/>
    <image><url>{base}/cover.jpg</url><title>{escape(SHOW['title'])}</title><link>{base}</link></image>
{chr(10).join(items)}
  </channel>
</rss>
"""
    Path(args.out).write_text(xml, encoding="utf-8")
    print("wrote", args.out, f"({len(items)} episode(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
