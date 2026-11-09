#!/usr/bin/env python3
"""诊断实际成片：把已发布的 m4a 按已知分段时长切回去，逐段算说话人向量与音高。

用来回答："到底是哪几段听起来像换了个人？"
用法: python3 diagnose_episode.py audio/ep01.m4a episodes/ep01/ep01.report.json scripts/ep01_zh.txt
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_pipeline import PARA_PAUSE, SENT_PAUSE, pack, parse_script  # noqa: E402

BASE_MODEL = "/Users/dylan/code/shared/model-server/models/Qwen3-TTS-12Hz-1.7B-Base-8bit"


def decode_m4a(path: Path) -> tuple[np.ndarray, int]:
    tmp = Path("/tmp/_diag.wav")
    subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16", str(path), str(tmp)], check=True)
    with wave.open(str(tmp)) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a, rate


def f0_median(a: np.ndarray, rate: int) -> float:
    """粗糙基频估计：分帧自相关，取有声帧的中位数。"""
    frame, hop = int(0.04 * rate), int(0.02 * rate)
    lo, hi = int(rate / 400), int(rate / 70)  # 70–400 Hz
    vals = []
    for i in range(0, len(a) - frame, hop):
        f = a[i:i + frame]
        if np.sqrt((f ** 2).mean()) < 0.01:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, mode="full")[frame - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if seg.size == 0:
            continue
        lag = lo + int(np.argmax(seg))
        vals.append(rate / lag)
    return float(np.median(vals)) if vals else 0.0


def cos(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.reshape(-1).astype(np.float64), b.reshape(-1).astype(np.float64)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> int:
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model

    audio, rate = decode_m4a(Path(sys.argv[1]))
    report = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    paragraphs = parse_script(Path(sys.argv[3]))
    units = pack(paragraphs)
    durations = [u["audio_seconds"] for u in report["units"]]
    assert len(durations) == len(units)
    print(f"音频 {len(audio) / rate:.1f}s，{len(units)} 段", flush=True)

    model = load_model(BASE_MODEL)
    embs, f0s, starts, cursor = [], [], [], 0.0
    for i, (text, para_end) in enumerate(units):
        n = int(round(durations[i] * rate))
        seg = audio[int(cursor * rate):int(cursor * rate) + n]
        cursor += durations[i] + (PARA_PAUSE if para_end else SENT_PAUSE) if i < len(units) - 1 else durations[i]
        embs.append(np.asarray(model.extract_speaker_embedding(mx.array(seg)[None, :])))
        f0s.append(f0_median(seg, rate))
        starts.append((i, len(text), durations[i], f0s[-1]))

    e = np.vstack([x.reshape(-1) for x in embs])
    centroid = e.mean(axis=0)
    to_c = np.array([cos(x, centroid) for x in e])
    pairs = [cos(a, b) for a, b in combinations(e, 2)]

    print(f"说话人相似度：两两均值 {np.mean(pairs):.4f} 最低 {np.min(pairs):.4f}"
          f" | 与质心 均值 {np.mean(to_c):.4f} 最低 {np.min(to_c):.4f}", flush=True)
    print(f"基频中位数：{np.median(f0s):.1f} Hz，区间 {np.min(f0s):.0f}–{np.max(f0s):.0f} Hz，"
          f"标准差 {np.std(f0s):.1f} Hz", flush=True)

    order = np.argsort(to_c)[:8]
    print("\n最不像同一人的 8 段：")
    for i in order:
        idx, chars, dur, f0 = starts[i]
        print(f"  段 {idx + 1:>2} | {chars:>3} 字 | {dur:>5.1f}s | F0 {f0:>5.0f} Hz | "
              f"与质心 {to_c[i]:.3f}")

    out = Path("experiment/timbre")
    out.mkdir(parents=True, exist_ok=True)
    (out / "episode_diagnosis.json").write_text(json.dumps({
        "audio": str(sys.argv[1]),
        "segments": len(units),
        "pairwise_mean": round(float(np.mean(pairs)), 4),
        "pairwise_min": round(float(np.min(pairs)), 4),
        "to_centroid_mean": round(float(np.mean(to_c)), 4),
        "to_centroid_min": round(float(np.min(to_c)), 4),
        "f0_median_hz": round(float(np.median(f0s)), 1),
        "f0_std_hz": round(float(np.std(f0s)), 1),
        "worst": [{"index": int(starts[i][0]) + 1, "chars": starts[i][1],
                   "seconds": starts[i][2], "f0": round(starts[i][3], 1),
                   "cos_to_centroid": round(float(to_c[i]), 4)} for i in order],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote experiment/timbre/episode_diagnosis.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
