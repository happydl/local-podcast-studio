# local-podcast-studio

> 用一台 Mac、一个 1.7B 的本地语音模型，把中文稿子做成可以订阅的播客。
> 全离线 · 零边际成本 · 约 200 行 Python。

**[收听第 01 期](https://happydl.github.io/local-podcast-studio/)** · **[RSS](https://happydl.github.io/local-podcast-studio/feed.xml)**

---

## 实测数据（M1 Max / 64 GB，2026-11-10）

| 指标 | 数值 |
|---|---|
| 文稿 | 2128 字（50 段合成单元） |
| 音频时长 | 9 分 29 秒（568.9 s） |
| 合成耗时 | 3 分 46 秒（226.4 s） |
| 等效速度 | **2.51× 实时** |
| 实时率 RTF（逐段） | 平均 0.404，区间 0.385 – 0.433 |
| 语速 | 224 字/分钟音频 |
| 电费 | **< ¥0.01**（40 W × 226 s ≈ 2.5 Wh） |
| 云端调用 | 0 次 |

模型：`Qwen3-TTS-12Hz-1.7B-VoiceDesign`（8-bit），MLX 推理，24 kHz 单声道。

## 成本对比（同样 2128 字）

| 方案 | 成本 |
|---|---|
| 火山引擎（豆包 TTS，按量 3–5 元/万字） | ¥0.64 – ¥1.06 |
| ElevenLabs Flash（$0.04–0.05/千字符） | ≈ ¥0.75 |
| 本地（本机） | < ¥0.01 |

**结论：省钱不是理由（差额只有一块钱），改稿自由才是。**
商用按字符计费会改变你的写作习惯；本地重跑一百遍也不要钱。

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
