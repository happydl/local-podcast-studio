# local-podcast-studio

> 用一台 Mac、一个 1.7B 的本地语音模型，把中文稿子做成可以订阅的播客。
> 全离线 · 零边际成本 · 约 200 行 Python。

**[收听第 01 期](https://happydl.github.io/local-podcast-studio/)** · **[第 02 期](https://happydl.github.io/local-podcast-studio/ep02.html)** · **[RSS](https://happydl.github.io/local-podcast-studio/feed.xml)**

| 期 | 主题 | 时长 | 数据 |
|---|---|---|---|
| 01 | 一台 Mac 做中文播客：本地语音合成的实测账本 | 08:45 | 单候选 2.4× 实时；相似度最低 0.9708 |
| 02 | 同一句话，两次生成差 40%：语速抖动实测 | 04:47 | 24 次合成，CV 26.5% / 15.0% / 10.6% |
| 03 | 为什么你的 AI 播客像换了个人：音色漂移的根因与修复 | 04:57 | 相似度 0.9768 → 0.9928 |

> ⚠️ **第 01 期已重制**：首版用 VoiceDesign 权重逐段独立采样，音色会漂（最低一对相似度 0.9393）。
> 现改为 Base 权重 + 参考音频克隆 + 每段 3 次采样按说话人相似度择优，最低 **0.9691**。详见第 03 期。

---

## 实测数据（M1 Max / 64 GB，2026-11-10）

| 指标 | 单候选（VoiceDesign） | 克隆 + 3 候选择优（正式版） |
|---|---|---|
| 文稿 | 2128 字（50 段） | 2128 字（50 段） |
| 音频时长 | 9:43 | **8:45**（524.9 s） |
| 合成耗时 | 3:55 | 13:21（含 3 倍候选） |
| 等效速度 | 2.48× 实时 | 0.65× 实时 |
| 语速 | 219 字/分 | 250 字/分（CV 6.7%） |
| 段间说话人相似度 | 均值 0.9768 / 最低 0.9393 | **均值 0.9928 / 最低 0.9708** |
| 电费 | < ¥0.01 | < ¥0.02 |
| 云端调用 | 0 次 | 0 次 |

模型：`Qwen3-TTS-12Hz-1.7B-VoiceDesign`（8-bit），MLX 推理，24 kHz 单声道。

## 成本对比（同样 2128 字）

| 方案 | 成本 |
|---|---|
| 火山引擎（豆包 TTS，按量 3–5 元/万字） | ¥0.64 – ¥1.06 |
| ElevenLabs Flash（$0.04–0.05/千字符） | ≈ ¥0.75 |
| 本地（本机） | < ¥0.01 |

**结论：省钱不是理由（差额只有一块钱），改稿自由才是。**
商用按字符计费会改变你的写作习惯；本地重跑一百遍也不要钱。

## 核心发现 1：音色会漂，而且根因是"用错了权重"

| 指标 | VoiceDesign（旧） | Base + 克隆 + 择优（新） |
|---|---|---|
| 段间说话人相似度（均值） | 0.9768 | **0.9911** |
| 最低一对 | 0.9393 | **0.9691** |
| 语速 CV | 12.8% | **7.9%** |

VoiceDesign 权重没有 speaker encoder：**传 `ref_audio` 不会报错，但会被静默忽略**。要钉死音色，必须换 Base 权重走 ICL 克隆：

```bash
python3 scripts/tts_clone.py --script episodes/ep03/script_zh.txt \
    --out audio/ep03 --ref ref/cand_1.wav \
    --ref-text "参考音频的逐字稿（必须一致）" \
    --samples 3 --select speaker
python3 scripts/diagnose_episode.py audio/ep03.m4a audio/ep03.report.json episodes/ep03/script_zh.txt
```

附加发现：**参考音频的语速决定成片语速**（同一段文字，不同参考：279 / 221 字/分）。没有速度参数，就挑一段语速合适的参考。

## 核心发现 2：语速抖动比想象中大

同一段文字、同一音色描述，重复合成 8 次（[`experiment/pacing.json`](experiment/pacing.json)）：

| 文本长度 | 平均时长 | 变异系数 | 极差 | 语速区间 |
|---|---:|---:|---:|---:|
| 15 字 | 4.91 s | **26.5%** | 90.8% | 114 – 262 字/分 |
| 41 字 | 11.26 s | 15.0% | 47.5% | 164 – 254 字/分 |
| 98 字 | 24.52 s | 10.6% | 35.2% | 198 – 278 字/分 |

→ **句子越短越不稳**。对策：① 合并到 40 字以上再合成；② 每段采样 2–3 次择优（极差 33% → 10%）；③ 整期设目标语速，偏离 ±15% 重跑。

```bash
# 三次采样，取语速最接近 220 字/分的一次
python3 scripts/tts_pipeline.py --script episodes/ep02/script_zh.txt \
    --out audio/ep02 --samples 3 --target-cpm 220
```

## 快速开始

```bash
# 1) 起一个本地 TTS 服务（OpenAI 兼容 /v1/audio/speech，WAV 输出）
./start.sh tts && curl -s localhost:5091/health   # {"ready":true}

# 2) 稿子 → 音频（切句 / 合成 / 裁剪静音 / 拼接 / 响度 / m4a）
python3 scripts/tts_pipeline.py \
    --script episodes/ep01/script_zh.txt \
    --out audio/ep01

# 3) 改完停顿或裁剪参数后，不重新合成、只重新拼接
python3 scripts/tts_pipeline.py --script episodes/ep01/script_zh.txt \
    --out audio/ep01 --reassemble      # 复用 audio/ep01_segs/

# 4) 封面（用真实波形）+ 播客 RSS
python3 scripts/make_cover.py audio/ep01.wav cover.jpg
python3 scripts/make_feed.py --base https://<user>.github.io/<repo> \
    --out site/feed.xml --episodes episodes/ep01/ep01.m4a \
    --titles "一台 Mac 做中文播客：本地语音合成的实测账本"
```

稿子格式：纯文本，`[正文]` 之后为朗读内容；`#` 开头的行会被忽略。
数字与英文缩写建议在稿子里改写成中文读法（`2.5×` → `二点七倍`）。

## 目录

```
scripts/tts_pipeline.py   # 切句 → 合成 → 裁剪 → 拼接 → 响度 → m4a
scripts/make_feed.py      # 生成 iTunes 规范的 feed.xml
scripts/make_cover.py     # 用真实波形生成 1400×1400 封面
scripts/build_site.py     # 文章 Markdown → 单页站点
scripts/make_chapters.py  # 由逐段耗时反推章节时间轴
scripts/experiment_pacing.py  # 语速抖动实验（24 次合成）
scripts/tts_clone.py      # 克隆模式批量合成（参考音频钉死音色 + 逐段响度归一）
scripts/check_timbre.py   # VoiceDesign vs Clone 音色一致性 A/B
scripts/diagnose_episode.py  # 成片逐段诊断：说话人相似度、基频、最差段定位
experiment/pacing.json    # 实验原始记录
episodes/ep01/            # 朗读稿、成品音频、逐段实测数据
article/                  # 长文（本站首页）
```

## 已知边界（四个必须自己缝的坑）

1. **单次输入上限 500 字符** → 必须切句，而切句位置直接决定听感。
2. **长段落韵律漂移** → 超过 4–5 句音调会后仰，需切短并重复音色描述。
3. **专有名词必翻车** → 数字、缩写、人名要在稿子里改写成中文读法。
4. **拼接后响度不统一** → 必须做一次峰值归一/限幅。
5. **合成不确定**：同一段文字在不同批次生成长度可能相差 20%–40%（实测同一句 45 字：10.2 s vs 14.1 s）。所以 RTF 稳 ≠ 语速稳。

## 生成声明

第 01 期的文稿、音频、封面、站点均由**同一套本地流水线**生成；音频为合成语音，非真人录音。
本项目在节目开场与文章中都明确披露这一点。

## License

MIT © 2026 happydl
