#!/usr/bin/env python3
"""成片音色一致性统计（含长度偏差校正）：短段（<3s）的说话人向量噪声大，单独统计。"""
import json, subprocess, sys, wave
from itertools import combinations
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_pipeline import PARA_PAUSE, SENT_PAUSE, pack, parse_script
BASE="/Users/dylan/code/shared/model-server/models/Qwen3-TTS-12Hz-1.7B-Base-8bit"

def decode(p):
    t=Path("/tmp/_ts.wav"); subprocess.run(["/usr/bin/afconvert","-f","WAVE","-d","LEI16",str(p),str(t)],check=True)
    with wave.open(str(t)) as w:
        return np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768, w.getframerate()

def cos(a,b):
    a,b=a.reshape(-1).astype(np.float64),b.reshape(-1).astype(np.float64)
    return float(a@b/(np.linalg.norm(a)*np.linalg.norm(b)))

def main():
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    model=load_model(BASE)
    for spec in sys.argv[1:]:
        audio_p, rep_p, script_p = spec.split(":")
        a,rate=decode(Path(audio_p))
        rep=json.loads(Path(rep_p).read_text()); durs=[u["audio_seconds"] for u in rep["units"]]
        units=pack(parse_script(Path(script_p)))
        embs=[];lens=[];cur=0.0
        for i,(text,para_end) in enumerate(units):
            n=int(round(durs[i]*rate)); seg=a[int(cur*rate):int(cur*rate)+n]
            cur += durs[i] + ((PARA_PAUSE if para_end else SENT_PAUSE) if i<len(units)-1 else 0)
            embs.append(np.asarray(model.extract_speaker_embedding(mx.array(seg)[None,:])).reshape(-1)); lens.append(n/rate)
        E=np.vstack(embs); c=E.mean(axis=0)
        to_c=np.array([cos(e,c) for e in E])
        long_idx=[i for i,L in enumerate(lens) if L>=3.0]
        pairs_all=[cos(E[i],E[j]) for i,j in combinations(range(len(E)),2)]
        pairs_long=[cos(E[i],E[j]) for i,j in combinations(long_idx,2)]
        print(f"\n{audio_p}: {len(units)} 段（≥3s 的 {len(long_idx)} 段）")
        print(f"  全部: 两两均值 {np.mean(pairs_all):.4f} 最低 {np.min(pairs_all):.4f} | 与质心最低 {to_c.min():.4f}")
        print(f"  ≥3s : 两两均值 {np.mean(pairs_long):.4f} 最低 {np.min(pairs_long):.4f} | 与质心最低 {to_c[long_idx].min():.4f}")
if __name__=="__main__": main()
