#!/usr/bin/env python3
"""声音克隆批量合成：用一段参考音频把音色钉死，整期节目同一个声音。

与 tts_pipeline.py 的差别：
  - 走 Base 权重的 ICL 克隆路径（ref_audio + ref_text），而不是 VoiceDesign 的文字描述
  - 因此段与段之间不再"重新采样出一个声音"，音色由参考音频决定
  - 仍然保留：切句、静音裁剪、定长停顿、响度归一、m4a 导出、逐段报告

用法:
    python3 tts_clone.py --script scripts/ep01_zh.txt --out audio/ep01 \
        --ref audio/ref_voice.wav --ref-text "参考音频对应的文字"
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_pipeline import (PARA_PAUSE, SENT_PAUSE, pack, parse_script,  # noqa: E402
                          trim_silence)

MODEL_PATH = "/Users/dylan/code/shared/model-server/models/Qwen3-TTS-12Hz-1.7B-Base-8bit"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", required=True, help="参考音频（建议 6–12 秒，干净、无背景音）")
    ap.add_argument("--ref-text", required=True, help="参考音频逐字稿（必须与音频内容一致）")
    ap.add_argument("--samples", type=int, default=1, help="每段合成次数，取语速最接近目标的一次")
    ap.add_argument("--target-cpm", type=float, default=220.0)
    ap.add_argument("--select", choices=["rate", "speaker"], default="speaker",
                    help="多采样时按什么择优：rate=语速，speaker=与参考音色的相似度（默认）")
    ap.add_argument("--max-units", type=int, default=0)
    args = ap.parse_args()

    import mlx.core as mx
    from mlx_audio.tts.utils import load_model

    t0 = time.perf_counter()
    model = load_model(MODEL_PATH)
    print(f"模型加载 {time.perf_counter() - t0:.1f}s", flush=True)

    ref_audio_arr, ref_rate = read_wav(Path(args.ref))
    ref_emb = np.asarray(model.extract_speaker_embedding(mx.array(ref_audio_arr)[None, :]))
    print(f"参考音色向量已就绪（{len(ref_audio_arr) / ref_rate:.1f}s）", flush=True)

    paragraphs = parse_script(Path(args.script))
    units = pack(paragraphs)
    if args.max_units:
        units = units[: args.max_units]

    out_base = Path(args.out)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    seg_dir = Path(f"{out_base}_segs")
    seg_dir.mkdir(parents=True, exist_ok=True)

    pieces, rows, rate = [], [], None
    wall = 0.0
    for i, (text, para_end) in enumerate(units, 1):
        best = None
        for si in range(max(1, args.samples)):
            t1 = time.perf_counter()
            chunks = []
            for result in model.generate(
                text=text, ref_audio=args.ref, ref_text=args.ref_text,
                lang_code="chinese", stream=False, max_tokens=1500,
            ):
                chunks.append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
                rate = result.sample_rate
            gen = time.perf_counter() - t1
            audio = np.concatenate(chunks)
            (seg_dir / f"seg_{i:03d}{'' if si == 0 else f'_s{si}'}.wav").write_bytes(
                to_wav_bytes(audio, rate))
            trimmed = polish(trim_silence(audio, rate), rate)
            dur = len(trimmed) / rate
            cpm = len(text) / dur * 60
            emb = np.asarray(model.extract_speaker_embedding(mx.array(trimmed)[None, :]))
            sim = cosine(emb, ref_emb)
            wall += gen
            off_rate = abs(cpm - args.target_cpm) / args.target_cpm
            # 语速超出 ±35% 的候选直接淘汰，再按指定指标择优
            ok = off_rate <= 0.35
            score = (0 if ok else 1, -(sim if args.select == "speaker" else -off_rate))
            if best is None or score < best[0]:
                best = (score, trimmed, dur, cpm, gen, len(audio) / rate, sim)
            if args.samples > 1:
                print(f"    采样 {si + 1}/{args.samples}: {dur:.2f}s ({cpm:.0f} 字/分) "
                      f"音色相似 {sim:.4f}{'' if ok else ' [语速超限]'}", flush=True)
        _, samples, dur_trim, cpm, gen1, dur_raw, sim_best = best
        rows.append({"index": i, "chars": len(text), "audio_seconds": round(dur_trim, 2),
                     "gen_seconds": round(gen1, 2), "rtf": round(gen1 / dur_raw, 3),
                     "chars_per_min": round(cpm, 1), "speaker_sim": round(float(sim_best), 4)})
        print(f"[{i}/{len(units)}] {len(text)}字 → {dur_trim:.1f}s，{cpm:.0f} 字/分，"
              f"音色 {sim_best:.3f}，耗时 {gen1:.1f}s (RTF {gen1 / dur_raw:.2f})", flush=True)
        pieces.append(samples)
        if i < len(units):
            gap = PARA_PAUSE if para_end else SENT_PAUSE
            pieces.append(np.zeros(int(rate * gap), dtype=np.float32))

    audio = np.concatenate(pieces)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = np.tanh(audio / peak) * 0.89
    wav_path = out_base.with_suffix(".wav")
    write_wav(wav_path, audio, rate)
    m4a_path = out_base.with_suffix(".m4a")
    subprocess.run(["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", "-q", "127",
                    str(wav_path), str(m4a_path)], check=True)

    duration = len(audio) / rate
    cpms = [r["chars_per_min"] for r in rows]
    report = {
        "mode": "voice_clone",
        "model": MODEL_PATH,
        "ref_audio": str(args.ref),
        "ref_text": args.ref_text,
        "script": str(args.script),
        "units": rows,
        "total_chars": sum(len(u[0]) for u in units),
        "audio_seconds": round(duration, 2),
        "wall_seconds": round(wall, 2),
        "speed_vs_realtime": round(duration / wall, 2),
        "chars_per_min_mean": round(statistics.mean(cpms), 1),
        "chars_per_min_cv": round(statistics.pstdev(cpms) / statistics.mean(cpms) * 100, 1),
        "speaker_sim_mean": round(statistics.mean(r["speaker_sim"] for r in rows), 4),
        "speaker_sim_min": min(r["speaker_sim"] for r in rows),
        "wav": str(wav_path.with_suffix(".wav").name),
        "m4a": str(m4a_path.name),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_base.with_suffix(".report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：{duration / 60:.1f} 分钟，{report['total_chars']} 字，"
          f"合成 {wall / 60:.1f} 分钟，{duration / wall:.2f}× 实时，"
          f"语速 CV {report['chars_per_min_cv']}%")
    return 0


TARGET_RMS = 0.085   # 每段统一到的响度（-21 dBFS 左右），避免"忽远忽近"
FADE = 0.012         # 段首尾淡入淡出，避免拼接爆音


def polish(a: np.ndarray, rate: int) -> np.ndarray:
    """逐段响度归一 + 首尾淡入淡出。这是"听起来像同一个人在同一个话筒前"的关键一步。"""
    rms = float(np.sqrt(np.mean(a ** 2))) or 1.0
    a = a * (TARGET_RMS / rms)
    a = np.clip(a, -0.99, 0.99)
    n = max(1, int(rate * FADE))
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    a[:n] *= ramp
    a[-n:] *= ramp[::-1]
    return a


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a, rate


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a_, b_ = a.reshape(-1).astype(np.float64), b.reshape(-1).astype(np.float64)
    return float(a_ @ b_ / (np.linalg.norm(a_) * np.linalg.norm(b_)))


def to_wav_bytes(audio: np.ndarray, rate: int) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    raise SystemExit(main())
