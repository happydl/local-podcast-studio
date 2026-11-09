#!/usr/bin/env python3
"""把文章 Markdown 渲染成单页站点（含播放器、封面、数据表）。"""
import re
import sys
from pathlib import Path

import mistune

TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="本地语音合成实测：2112 字中文稿 → 10 分钟播客，2.7 倍实时，零云端调用。">
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
  .hero {{ display:flex; gap:28px; align-items:center; margin-bottom:40px; }}
  .hero img {{ width:148px; height:148px; border-radius:14px; box-shadow:0 10px 40px rgba(0,0,0,.5); }}
  .kicker {{ font:12px/1.4 ui-monospace,Menlo,monospace; letter-spacing:.18em;
            text-transform:uppercase; color:var(--accent); margin:0 0 10px; }}
  h1 {{ font-size:30px; line-height:1.35; margin:0 0 10px; letter-spacing:-.01em; }}
  h2 {{ font-size:22px; margin:52px 0 14px; padding-top:8px; }}
  h3 {{ font-size:17px; margin:30px 0 8px; color:#cfd8df; }}
  p, li {{ color:#d8dee3; }}
  strong {{ color:#fff; }}
  a {{ color:var(--accent); text-decoration:none; border-bottom:1px solid rgba(86,208,168,.3); }}
  a:hover {{ border-color:var(--accent); }}
  blockquote {{ margin:26px 0; padding:16px 20px; background:var(--panel);
                border-left:3px solid var(--accent); border-radius:6px; color:var(--muted); }}
  blockquote p {{ margin:0; color:#b9c3ca; }}
  table {{ width:100%; border-collapse:collapse; margin:20px 0; font-size:14.5px; }}
  th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; font-size:13px; letter-spacing:.02em; }}
  tr:hover td {{ background:#141a1e; }}
  code {{ font:13.5px/1.6 ui-monospace,Menlo,monospace; background:#1b2227;
          padding:2px 6px; border-radius:5px; color:#a9e8cf; }}
  pre {{ background:#11171b; border:1px solid var(--line); border-radius:10px;
         padding:16px 18px; overflow:auto; }}
  pre code {{ background:none; padding:0; color:#cfe6dc; font-size:13px; }}
  hr {{ border:none; border-top:1px solid var(--line); margin:44px 0; }}
  .player {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
             padding:18px 20px; margin:0 0 44px; }}
  .player .label {{ font:12px/1.4 ui-monospace,Menlo,monospace; color:var(--muted);
                    letter-spacing:.1em; text-transform:uppercase; margin-bottom:10px; }}
  audio {{ width:100%; }}
  .meta {{ color:var(--muted); font-size:14px; }}
  footer {{ margin-top:64px; padding-top:24px; border-top:1px solid var(--line);
            color:var(--muted); font-size:13.5px; }}
  @media (max-width:620px) {{
    .hero {{ flex-direction:column; align-items:flex-start; gap:18px; }}
    .hero img {{ width:110px; height:110px; }}
    h1 {{ font-size:24px; }}
    .wrap {{ padding:32px 18px 72px; }}
  }}
</style>
</head>
<body>
<main class="wrap">
  <div class="hero">
    <img src="cover.jpg" alt="封面">
    <div>
      <p class="kicker">Local First · Episode 01</p>
      <h1>{title}</h1>
      <p class="meta">2026-11-10 · Apple Silicon M1 Max · 全离线 · 0 次云端调用</p>
    </div>
  </div>

  <div class="player">
    <div class="label">本期音频 · 本机生成 · 10 分 16 秒</div>
    <audio controls preload="metadata" src="ep01.m4a"></audio>
    <p class="meta" style="margin:10px 0 0">
      订阅：<a href="feed.xml">RSS</a> ·
      代码：<a href="scripts/tts_pipeline.py">tts_pipeline.py</a>
    </p>
  </div>

  {body}

  <footer>
    本页与本期音频由同一套本地流水线生成：文稿 → 切句 → 本地 TTS → 拼接 → RSS。
    数据为本机实测，原始逐段记录见 <a href="episodes/ep01/ep01.report.json">ep01.report.json</a>。
  </footer>
</main>
</body>
</html>
"""


def main() -> int:
    md_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    md = md_path.read_text(encoding="utf-8")
    # 站内路径改写：文章在仓库的 article/ 目录，站点在根目录
    md = md.replace("(../../episodes/ep01/ep01.m4a)", "(ep01.m4a)")
    md = md.replace("(../../scripts/", "(scripts/")
    md = re.sub(r"^# .*\n", "", md, count=1)          # 标题已在 hero 里
    md = re.sub(r"^> .*\n", "", md, flags=re.M, count=3)

    html = mistune.create_markdown(escape=False, plugins=["table", "strikethrough"])(
        md, )
    title = "一台 Mac 做中文播客：本地语音合成的实测账本"
    out_path.write_text(TEMPLATE.format(title=title, body=html), encoding="utf-8")
    print("wrote", out_path, len(html), "bytes of html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
