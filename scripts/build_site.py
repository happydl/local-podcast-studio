#!/usr/bin/env python3
"""把文章 Markdown 渲染成单页站点（含播放器、封面、数据表）。

用法: python3 build_site.py <md> <out.html> [--ep 01] [--audio ep01.m4a]
                            [--title 标题] [--duration 09:43] [--page ep02.html]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import mistune

EPISODES = [
    ("ep01.html", "01", "一台 Mac 做中文播客：本地语音合成的实测账本", "09:43"),
    ("ep02.html", "02", "同一句话，两次生成差 40%：语音合成的语速抖动实测", "05:04"),
]

TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="本地语音合成实测：2128 字中文稿 → 10 分钟播客，2.5 倍实时，零云端调用。">
<meta property="og:title" content="{title}">
<meta property="og:image" content="https://happydl.github.io/local-podcast-studio/cover.jpg">
<link rel="alternate" type="application/rss+xml" title="本地优先 Local First" href="feed.xml">
<style>
  :root {{
    --bg:#0f1215; --panel:#161b1f; --text:#e9edf0; --muted:#9aa4ad;
    --accent:#56d0a8; --line:#232b31;
  }}
  * {{ box-sizing:border-box; }}
  html {{ background:var(--bg); }}
  body {{
    margin:0; color:var(--text); background:var(--bg);
    font:16px/1.85 -apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:760px; margin:0 auto; padding:56px 22px 96px; }}
  .hero {{ display:flex; gap:28px; align-items:center; margin-bottom:28px; }}
  .hero img {{ width:148px; height:148px; border-radius:14px; box-shadow:0 10px 40px rgba(0,0,0,.5); }}
  .kicker {{ font:12px/1.4 ui-monospace,Menlo,monospace; letter-spacing:.18em;
            text-transform:uppercase; color:var(--accent); margin:0 0 10px; }}
  h1 {{ font-size:29px; line-height:1.35; margin:0 0 10px; letter-spacing:-.01em; }}
  h2 {{ font-size:22px; margin:52px 0 14px; padding-top:8px; }}
  h3 {{ font-size:17px; margin:30px 0 8px; color:#cfd8df; }}
  p, li {{ color:#d8dee3; }}
  strong {{ color:#fff; }}
  a {{ color:var(--accent); text-decoration:none; border-bottom:1px solid rgba(86,208,168,.3); }}
  a:hover {{ border-color:var(--accent); }}
  blockquote {{ margin:26px 0; padding:16px 20px; background:var(--panel);
                border-left:3px solid var(--accent); border-radius:6px; }}
  blockquote p {{ margin:0; color:#b9c3ca; }}
  table {{ width:100%; border-collapse:collapse; margin:20px 0; font-size:14.5px; }}
  th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; font-size:13px; }}
  tr:hover td {{ background:#141a1e; }}
  code {{ font:13.5px/1.6 ui-monospace,Menlo,monospace; background:#1b2227;
          padding:2px 6px; border-radius:5px; color:#a9e8cf; }}
  pre {{ background:#11171b; border:1px solid var(--line); border-radius:10px;
         padding:16px 18px; overflow:auto; }}
  pre code {{ background:none; padding:0; color:#cfe6dc; font-size:13px; }}
  hr {{ border:none; border-top:1px solid var(--line); margin:44px 0; }}
  .player {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
             padding:18px 20px; margin:0 0 20px; }}
  .player .label {{ font:12px/1.4 ui-monospace,Menlo,monospace; color:var(--muted);
                    letter-spacing:.1em; text-transform:uppercase; margin-bottom:10px; }}
  audio {{ width:100%; }}
  .meta {{ color:var(--muted); font-size:14px; }}
  .eplist {{ border-top:1px solid var(--line); margin:28px 0 40px; }}
  .eplist h3 {{ font:12px/1.4 ui-monospace,Menlo,monospace; letter-spacing:.16em;
                color:var(--muted); margin:18px 0 10px; text-transform:uppercase; }}
  .eplist a {{ display:flex; gap:14px; align-items:baseline; padding:11px 0;
               border-bottom:1px solid var(--line); color:#d8dee3; border-radius:0; }}
  .eplist a:hover {{ color:#fff; }}
  .eplist .no {{ font:12px ui-monospace,Menlo,monospace; color:var(--accent); min-width:22px; }}
  .eplist .dur {{ margin-left:auto; font:12px ui-monospace,Menlo,monospace; color:var(--muted); }}
  footer {{ margin-top:64px; padding-top:24px; border-top:1px solid var(--line);
            color:var(--muted); font-size:13.5px; }}
  @media (max-width:620px) {{
    .hero {{ flex-direction:column; align-items:flex-start; gap:18px; }}
    .hero img {{ width:110px; height:110px; }}
    h1 {{ font-size:23px; }}
    .wrap {{ padding:32px 18px 72px; }}
  }}
</style>
</head>
<body>
<main class="wrap">
  <div class="hero">
    <img src="{cover}" alt="封面">
    <div>
      <p class="kicker">Local First · Episode {no}</p>
      <h1>{title}</h1>
      <p class="meta">2026-11-10 · Apple Silicon M1 Max · 全离线 · 0 次云端调用</p>
    </div>
  </div>

  <div class="player">
    <div class="label">本期音频 {dur} · 本机生成</div>
    <audio controls preload="metadata" src="{audio}"></audio>
    <p class="meta" style="margin:10px 0 0">
      订阅：<a href="feed.xml">RSS</a> ·
      代码：<a href="scripts/tts_pipeline.py">tts_pipeline.py</a>
    </p>
  </div>

  <nav class="eplist"><h3>全部节目</h3>{eplist}</nav>

  {body}

  <footer>
    本页与本期音频由同一套本地流水线生成：文稿 → 切句 → 本地 TTS → 拼接 → RSS。
    数据为本机实测，原始记录见 <a href="episodes/{no}/ep{no}.report.json">ep{no}.report.json</a>。
  </footer>
</main>
</body>
</html>
"""


def build_eplist(current: str) -> str:
    out = []
    for href, no, title, dur in EPISODES:
        mark = " ·" if href == current else ""
        out.append(f'<a href="{href}"><span class="no">{no}</span>'
                   f'<span>{title}{mark}</span><span class="dur">{dur}</span></a>')
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("out")
    ap.add_argument("--no", default="01")
    ap.add_argument("--audio", default="ep01.m4a")
    ap.add_argument("--cover", default="cover.jpg")
    ap.add_argument("--title", default="一台 Mac 做中文播客：本地语音合成的实测账本")
    ap.add_argument("--duration", default="09:43")
    args = ap.parse_args()

    md = Path(args.md).read_text(encoding="utf-8")
    md = re.sub(r"\((\.\./){1,2}(episodes|scripts|experiment)/", r"(", md)
    md = md.replace("(episodes/ep01/ep01.m4a)", "(ep01.m4a)")
    md = re.sub(r"^# .*\n", "", md, count=1)
    md = re.sub(r"^(> .*\n)+", "", md, count=1)

    body = mistune.create_markdown(escape=False, plugins=["table", "strikethrough"])(md)
    html = TEMPLATE.format(title=args.title, body=body, no=args.no, audio=args.audio,
                           cover=args.cover, dur=args.duration,
                           eplist=build_eplist(Path(args.out).name))
    Path(args.out).write_text(html, encoding="utf-8")
    print("wrote", args.out, len(html), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
