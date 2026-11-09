#!/usr/bin/env python3
"""把中文稿子变成播客音频：切句 -> 本地 TTS -> 拼接 -> 统一响度 -> 导出。

只依赖标准库 + numpy，语音服务是本地 HTTP（Qwen3-TTS VoiceDesign）。
用法:
    python3 tts_pipeline.py --script scripts/episode01_zh.txt --out audio/episode01
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

TTS_URL = "http://127.0.0.1:5091/v1/audio/speech"
MODEL = "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
MAX_CHARS = 460          # 服务端硬上限 500，留出余量
SENT_PAUSE = 0.14        # 句间停顿（秒）
PARA_PAUSE = 0.46        # 段间停顿（秒）
TRIM_DB = -38.0          # 裁剪每段首尾静音的门限
TRIM_KEEP = 0.06         # 裁剪后保留的余量（秒），避免吞字


def parse_script(path: Path) -> list[list[str]]:
    """读取文稿，返回按段落分组的句子列表。以 [正文] 之后的内容为准。"""
    raw = path.read_text(encoding="utf-8")
    if re.search(r"^\s*\[正文\]\s*$", raw, re.M):
        raw = re.split(r"^\s*\[正文\]\s*$", raw, maxsplit=1, flags=re.M)[1]
    raw = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("#"))
    paragraphs: list[list[str]] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        block = " ".join(block.split())
        if not block:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[。！？；])", block) if s.strip()]
        paragraphs.append(sentences)
    return paragraphs


def pack(paragraphs: list[list[str]]) -> list[tuple[str, bool]]:
    """把句子打包成不超过 MAX_CHARS 的合成单元，并标记是否段尾。"""
    units: list[tuple[str, bool]] = []
    for sentences in paragraphs:
        buf = ""
        for i, s in enumerate(sentences):
            if buf and len(buf) + len(s) > MAX_CHARS:
                units.append((buf, False))
                buf = ""
            buf += s
            if len(buf) >= MAX_CHARS * 0.85:
                units.append((buf, False))
                buf = ""
        if buf:
            units.append((buf, True))
    return units


def synth(text: str, voice: str, retries: int = 3, timeout: int = 300) -> tuple[bytes, float]:
    payload = json.dumps({
        "model": MODEL,
        "input": text,
        "instructions": voice,
        "response_format": "wav",
    }).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(TTS_URL, data=payload, headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            return data, time.perf_counter() - t0
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            print(f"  重试 {attempt + 1}/{retries}: {exc}", flush=True)
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"合成失败: {last}")


def trim_silence(samples: np.ndarray, rate: int, threshold_db: float = TRIM_DB) -> np.ndarray:
    """裁掉首尾静音，但保留 TRIM_KEEP 秒余量，防止吞掉起音和尾音。"""
    thr = 10 ** (threshold_db / 20)
    idx = np.where(np.abs(samples) > thr)[0]
    if idx.size == 0:
        return samples
    keep = int(rate * TRIM_KEEP)
    start = max(0, idx[0] - keep)
    end = min(len(samples), idx[-1] + keep)
    return samples[start:end]


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    tmp = Path("/tmp/_tts_chunk.wav")
    tmp.write_bytes(data)
    with wave.open(str(tmp)) as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0, rate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voice", default=(
        "成年男性，低沉清晰，标准普通话，语速适中偏慢，"
        "不要夸张的播音腔，像在认真讲一件事，句子之间留一点呼吸感。"))
    ap.add_argument("--max-units", type=int, default=0, help="只合成前 N 段，用于试跑")
    ap.add_argument("--reassemble", action="store_true",
                    help="不重新合成，改用缓存的分段音频重新拼接（改停顿/裁剪时用）")
    ap.add_argument("--cache-dir", default="", help="分段音频缓存目录，默认 <out>_segs")
    ap.add_argument("--samples", type=int, default=1,
                    help="每段合成次数，取语速最接近目标的一次（默认 1，建议 2–3）")
    ap.add_argument("--target-cpm", type=float, default=220.0,
                    help="目标语速（字/分钟），用于在多次采样中择优")
    args = ap.parse_args()

    out_base = Path(args.out)
    out_base.parent.mkdir(parents=True, exist_ok=True)

    paragraphs = parse_script(Path(args.script))
    units = pack(paragraphs)
    if args.max_units:
        units = units[: args.max_units]

    total_chars = sum(len(u[0]) for u in units)
    print(f"段落 {len(paragraphs)} 个，合成单元 {len(units)} 个，共 {total_chars} 字", flush=True)

    cache = Path(args.cache_dir) if args.cache_dir else Path(f"{out_base}_segs")
    cache.mkdir(parents=True, exist_ok=True)

    pieces: list[np.ndarray] = []
    rate = None
    rows = []
    wall = 0.0
    for i, (text, para_end) in enumerate(units, 1):
        seg_path = cache / f"seg_{i:03d}.wav"
        if args.reassemble and seg_path.exists():
            samples, rate = read_wav(seg_path.read_bytes())
            gen = 0.0
            raw_dur = len(samples) / rate
            samples = trim_silence(samples, rate)
            print(f"[{i}/{len(units)}] 复用缓存 {raw_dur:.1f}s → 裁剪后 {len(samples) / rate:.1f}s", flush=True)
            rows.append({"index": i, "chars": len(text), "audio_seconds": round(len(samples) / rate, 2),
                         "gen_seconds": 0.0, "rtf": 0.0, "raw_seconds": round(raw_dur, 2)})
            pieces.append(samples)
            if i < len(units):
                gap = PARA_PAUSE if para_end else SENT_PAUSE
                pieces.append(np.zeros(int(rate * gap), dtype=np.float32))
            continue

        best = None
        for si in range(max(1, args.samples)):
            cand_path = seg_path if si == 0 else cache / f"seg_{i:03d}_s{si}.wav"
            if args.reassemble and cand_path.exists():
                audio, gen = cand_path.read_bytes(), 0.0
            else:
                audio, gen = synth(text, args.voice)
                cand_path.write_bytes(audio)
            c_samples, r = read_wav(audio)
            c_trim = trim_silence(c_samples, r)
            c_dur = len(c_trim) / r
            c_cpm = len(text) / c_dur * 60
            wall += gen
            score = abs(c_cpm - args.target_cpm)
            if best is None or score < best[0]:
                best = (score, c_trim, r, c_dur, c_cpm, gen, len(c_samples) / r)
            if args.samples > 1:
                print(f"    采样 {si + 1}/{args.samples}: {c_dur:.2f}s "
                      f"({c_cpm:.0f} 字/分，偏离 {score:.0f})", flush=True)
        _, samples, r, dur_trim, cpm, gen1, dur_raw = best
        rate = r
        dur = dur_raw
        rows.append({"index": i, "chars": len(text), "audio_seconds": round(dur_trim, 2),
                     "gen_seconds": round(gen1, 2), "rtf": round(gen1 / dur, 3),
                     "raw_seconds": round(dur, 2), "chars_per_min": round(cpm, 1),
                     "samples": max(1, args.samples)})
        print(f"[{i}/{len(units)}] {len(text)}字 → {dur:.1f}s 音频，裁剪后 {dur_trim:.1f}s，"
              f"{cpm:.0f} 字/分，耗时 {gen1:.1f}s (RTF {gen1 / dur:.2f})", flush=True)
        pieces.append(samples)
        # 句间/段间停顿（最后一段不加）
        if i < len(units):
            gap = PARA_PAUSE if para_end else SENT_PAUSE
            pieces.append(np.zeros(int(rate * gap), dtype=np.float32))

    audio = np.concatenate(pieces)
    # 统一响度：峰值归一 + 轻微限幅，避免各段拼接处音量跳变
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = np.tanh(audio / peak * 1.0) * 0.89
    wav_path = out_base.with_suffix(".wav")
    with wave.open(str(wav_path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())

    m4a_path = out_base.with_suffix(".m4a")
    subprocess.run(["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", "-q", "127",
                    str(wav_path), str(m4a_path)], check=True)

    duration = len(audio) / rate
    report = {
        "script": str(args.script),
        "voice": args.voice,
        "units": rows,
        "total_chars": total_chars,
        "audio_seconds": round(duration, 2),
        "wall_seconds": round(wall, 2),
        "speed_vs_realtime": round(duration / wall, 2) if wall else None,
        "raw_audio_seconds": round(sum(r["raw_seconds"] for r in rows), 2),
        "reassembled": bool(args.reassemble),
        "wav": str(wav_path),
        "m4a": str(m4a_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_base.with_suffix(".report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    speed = f"{duration / wall:.2f}× 实时" if wall else "复用缓存"
    print(f"\n完成：{duration / 60:.1f} 分钟音频，{total_chars} 字，合成耗时 {wall / 60:.1f} 分钟，{speed}")
    print(f"输出：{wav_path} / {m4a_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
