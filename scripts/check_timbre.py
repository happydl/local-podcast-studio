#!/usr/bin/env python3
"""音色一致性检测：用 Base 权重自带的说话人编码器（ECAPA）量化段间音色漂移。

A/B 对比两种合成方式：
  A. VoiceDesign：每段用文字描述生成（当前流水线）
  B. VoiceClone：同一段参考音频克隆（修复方案）

输出：每段的说话人向量两两余弦相似度（越高越像同一个人），以及两组对比。
"""
from __future__ import annotations

import json
import sys
import urllib.request
import wave
from itertools import combinations
from pathlib import Path

import numpy as np

BASE_MODEL = "/Users/dylan/code/shared/model-server/models/Qwen3-TTS-12Hz-1.7B-Base-8bit"
VOICEDESIGN_URL = "http://127.0.0.1:5091/v1/audio/speech"
VOICEDESIGN_MODEL = "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
VOICE = ("成年男性，低沉清晰，标准普通话，语速适中偏慢，"
         "不要夸张的播音腔，像在认真讲一件事，句子之间留一点呼吸感。")

TEXTS = [
    "这一集我想聊第三种可能。",
    "机器是一台苹果芯片的笔记本，内存六十四 G。",
    "第一次测速，五十四个字的句子，生成了十点六秒音频。",
    "真正值得本地跑的理由，是另外三条。",
    "第一是无限次重来，稿子改一个字，就重新生成一遍。",
    "第三是可控性，语速和停顿都能用自然语言去调。",
    "工具能解决的是摩擦，不是品质。",
    "今天就到这里，晚安。",
]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a, rate


def cos(a: np.ndarray, b: np.ndarray) -> float:
    a = a.reshape(-1).astype(np.float64)
    b = b.reshape(-1).astype(np.float64)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def stats(name: str, embs: list[np.ndarray]) -> dict:
    sims = [cos(a, b) for a, b in combinations(embs, 2)]
    mean_emb = np.mean(np.vstack([e.reshape(-1) for e in embs]), axis=0)
    to_mean = [cos(e, mean_emb) for e in embs]
    out = {
        "name": name, "segments": len(embs),
        "pairwise_mean": round(float(np.mean(sims)), 4),
        "pairwise_min": round(float(np.min(sims)), 4),
        "pairwise_p10": round(float(np.percentile(sims, 10)), 4),
        "to_centroid_mean": round(float(np.mean(to_mean)), 4),
        "to_centroid_min": round(float(np.min(to_mean)), 4),
    }
    print(f"{name}: 段数 {len(embs)} 两两相似 均值 {out['pairwise_mean']} "
          f"最低 {out['pairwise_min']} | 与质心 均值 {out['to_centroid_mean']} "
          f"最低 {out['to_centroid_min']}", flush=True)
    return out


def main() -> int:
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model

    out_dir = Path("experiment/timbre")
    out_dir.mkdir(parents=True, exist_ok=True)

    # A. VoiceDesign（现状）
    print("== A. VoiceDesign（当前流水线）==", flush=True)
    for i, text in enumerate(TEXTS):
        body = json.dumps({"model": VOICEDESIGN_MODEL, "input": text,
                           "instructions": VOICE, "response_format": "wav"}).encode()
        req = urllib.request.Request(VOICEDESIGN_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        (out_dir / f"vd_{i:02d}.wav").write_bytes(urllib.request.urlopen(req, timeout=300).read())
        print(f"  A{i}: {len(text)}字 ok", flush=True)

    # B. VoiceClone（修复方案）
    print("== B. VoiceClone（参考音频克隆）==", flush=True)
    model = load_model(BASE_MODEL)
    ref = "ref/cand_0.wav"
    ref_text = "这段话用来确定音色，之后所有内容都用同一个声音来读，听起来才像同一个人。"
    for i, text in enumerate(TEXTS):
        chunks, rate = [], None
        for result in model.generate(text=text, ref_audio=ref, ref_text=ref_text,
                                     lang_code="chinese", stream=False, max_tokens=1500):
            chunks.append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
            rate = result.sample_rate
        audio = np.concatenate(chunks)
        path = out_dir / f"vc_{i:02d}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        print(f"  B{i}: {len(text)}字 {len(audio) / rate:.2f}s", flush=True)

    # 度量
    print("== 说话人向量一致性 ==", flush=True)
    result = {"texts": TEXTS, "ref": ref, "ref_text": ref_text}
    for tag, prefix in (("voice_design", "vd"), ("voice_clone", "vc")):
        embs = []
        for i in range(len(TEXTS)):
            a, rate = read_wav(out_dir / f"{prefix}_{i:02d}.wav")
            if rate != 24000:
                raise RuntimeError(f"需要 24 kHz 音频，得到 {rate}")
            embs.append(np.asarray(model.extract_speaker_embedding(mx.array(a)[None, :])))
        result[tag] = stats(tag, embs)
        np.save(out_dir / f"emb_{prefix}.npy", np.vstack([e.reshape(-1) for e in embs]))

    vd = np.load(out_dir / "emb_vd.npy")
    vc = np.load(out_dir / "emb_vc.npy")
    cross = float(np.mean([cos(a, b) for a in vd for b in vc]))
    result["cross_mean"] = round(cross, 4)
    print(f"两组之间平均相似度: {cross:.4f}")
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nwrote", out_dir / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
