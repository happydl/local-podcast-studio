#!/usr/bin/env python3
"""实验：同一段文字、同一音色，重复合成 N 次，量化"语速不稳定"并验证修正策略。

输出：experiment/pacing.json
"""
import json
import statistics
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

URL = "http://127.0.0.1:5091/v1/audio/speech"
MODEL = "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
VOICE = ("成年男性，低沉清晰，标准普通话，语速适中偏慢，"
         "不要夸张的播音腔，像在认真讲一件事，句子之间留一点呼吸感。")
REPEATS = 8

TEXTS = {
    "short_24": "本地合成的成本，其实只有电费。",
    "mid_45": "把整期节目跑完，五十段语音的实时率全部落在零点四附近，最快最慢之间只差百分之十几。",
    "long_90": ("这一堆问题的答案，其实藏在三个地方。第一是切句，切在哪里直接决定听感。"
                "第二是响度，分句生成再拼接，每句音量都有细微差异。"
                "第三是节奏，同一段文字重复生成，长度可能相差两成到四成，这才是最麻烦的一个。"),
}
OUT = Path("experiment")


def synth(text: str) -> tuple[bytes, float]:
    body = json.dumps({"model": MODEL, "input": text, "instructions": VOICE,
                       "response_format": "wav"}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    data = urllib.request.urlopen(req, timeout=300).read()
    return data, time.perf_counter() - t0


def decode(data: bytes) -> tuple[np.ndarray, int]:
    tmp = Path("/tmp/_exp.wav")
    tmp.write_bytes(data)
    with wave.open(str(tmp)) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a, rate


def trim(a: np.ndarray, rate: int, db: float = -38.0, keep: float = 0.06) -> np.ndarray:
    thr = 10 ** (db / 20)
    idx = np.where(np.abs(a) > thr)[0]
    if idx.size == 0:
        return a
    k = int(rate * keep)
    return a[max(0, idx[0] - k):min(len(a), idx[-1] + k)]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    result = {"voice": VOICE, "repeats": REPEATS, "items": {}}
    for name, text in TEXTS.items():
        rows = []
        for i in range(REPEATS):
            data, gen = synth(text)
            a, rate = decode(data)
            (OUT / f"{name}_{i:02d}.wav").write_bytes(data)
            a2 = trim(a, rate)
            rows.append({
                "run": i,
                "raw_seconds": round(len(a) / rate, 3),
                "trimmed_seconds": round(len(a2) / rate, 3),
                "gen_seconds": round(gen, 2),
            })
            print(f"{name} #{i}: raw {rows[-1]['raw_seconds']:.2f}s "
                  f"trim {rows[-1]['trimmed_seconds']:.2f}s gen {gen:.1f}s", flush=True)
        dur = [r["trimmed_seconds"] for r in rows]
        cpm = [len(text) / d * 60 for d in dur]
        result["items"][name] = {
            "chars": len(text),
            "runs": rows,
            "duration_mean": round(statistics.mean(dur), 3),
            "duration_sd": round(statistics.pstdev(dur), 3),
            "duration_cv": round(statistics.pstdev(dur) / statistics.mean(dur), 4),
            "duration_min": min(dur), "duration_max": max(dur),
            "spread_pct": round((max(dur) - min(dur)) / statistics.mean(dur) * 100, 1),
            "chars_per_min_mean": round(statistics.mean(cpm), 1),
            "chars_per_min_min": round(min(cpm), 1),
            "chars_per_min_max": round(max(cpm), 1),
        }
        print(f"  → 时长 {statistics.mean(dur):.2f}s ± {statistics.pstdev(dur):.2f}s "
              f"(CV {result['items'][name]['duration_cv'] * 100:.1f}%, 极差 "
              f"{result['items'][name]['spread_pct']}%)", flush=True)
    (OUT / "pacing.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nwrote", OUT / "pacing.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
