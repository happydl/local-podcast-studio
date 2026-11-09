#!/usr/bin/env python3
"""生成播客封面 1400x1400：标题 + 真实波形（取自本期音频）。"""
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_MONO = "/System/Library/Fonts/SFNSMono.ttf"

W = H = 1400
BG = (17, 20, 24)
ACCENT = (86, 208, 168)
TEXT = (238, 240, 242)
MUTED = (150, 158, 166)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def load_wave(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    return data, rate


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("out")
    ap.add_argument("--episode", default="EPISODE 01")
    ap.add_argument("--title", default="一台 Mac\n做中文播客")
    ap.add_argument("--subtitle", default="本地语音合成的实测账本")
    ap.add_argument("--stats", nargs="*", default=["2.5×|实时速度", "¥0.03|整期电费", "0|云端调用"],
                    help="形如 值|标签，最多 3 组")
    args = ap.parse_args()
    wav, out = Path(args.wav), Path(args.out)
    samples, rate = load_wave(wav)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 背景：真实波形带（取自本期音频 RMS）
    bars = 96
    chunk = len(samples) // bars
    rms = np.array([np.sqrt(np.mean(samples[i * chunk:(i + 1) * chunk] ** 2)) or 1
                    for i in range(bars)])
    rms = rms / rms.max()
    mid = 712
    for i, v in enumerate(rms):
        x = 80 + i * ((W - 160) / bars)
        h = 10 + v * 96
        d.rounded_rectangle([x, mid - h, x + 6, mid + h], radius=3,
                            fill=(32, 52, 46) if i % 2 else (25, 40, 36))

    # 顶部小字
    d.text((80, 88), "LOCAL  ·  TTS  ·  " + args.episode, font=font(FONT_MONO, 28), fill=ACCENT)

    # 标题
    title = args.title
    y = 168
    for line in title.split("\n"):
        d.text((80, y), line, font=font(FONT_BOLD, 118), fill=TEXT)
        y += 142

    sub = args.subtitle
    d.text((80, y + 16), sub, font=font(FONT_BOLD, 56), fill=ACCENT)

    # 数据条
    y2 = 940
    d.line([80, y2 - 48, W - 80, y2 - 48], fill=(52, 60, 66), width=2)
    stats = [tuple(s.split("|", 1)) for s in args.stats][:3]
    for i, (big, label) in enumerate(stats):
        x = 80 + i * 420
        d.text((x, y2), big, font=font(FONT_MONO, 86), fill=TEXT)
        d.text((x, y2 + 100), label, font=font(FONT_BOLD, 34), fill=MUTED)

    d.text((80, 1292), "Qwen3-TTS 1.7B · 8-bit · MLX · Apple Silicon", font=font(FONT_MONO, 26), fill=MUTED)
    img.save(out, quality=92)
    print("saved", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
