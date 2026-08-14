# MiniMax 配音与 Fun-ASR 真实时间轴工作流

## 位置与顺序

在旁白、语义分镜和配音参数确认后立即制作配音；不得等待风格测试图或正式分镜图片。调用前完整读取 `${CODEX_HOME:-$HOME/.codex}/skills/minimax-speech/SKILL.md`。默认使用 `speech-2.8-hd`、公司内部获授权的老王棚拍版 `GuangxiLaoWang_Studio_20260814`、`speed=1.0` 和 `language_boost=Chinese`；可用 `MINIMAX_VOICE_ID` 覆盖。脚本阶段按每秒 5.0 个汉字估算时长。

MiniMax 只负责生成最终音频；音频完成后必须调用阿里云 `fun-asr-flash-2026-06-15` 检测真实时间戳。Fun-ASR 时间戳取代估算值和 MiniMax 响应信息，成为画面设计、镜头切换、Seedance 时长和底部字幕的唯一时间真值。

```text
确认完整旁白、语义分镜和配音参数 → MiniMax 生成完整旁白
→ Fun-ASR 检测最终音频 → 生成真实时间轴 → 风格测试图
→ 正式分镜图片 → Seedance 分镜视频 → 精确裁切拼接 → 字幕合成
```

## 第 2 次确认：MiniMax 配音与 Fun-ASR

语音合成和 Fun-ASR 都会计费，必须合并为一次确认。展示：

- 完整旁白；
- MiniMax 模型 `speech-2.8-hd`；
- 完整 `voice_id`；
- `speed`、`language_boost`、音频格式、采样率和码率；
- 是否显式设置 `emotion`，以及文本中是否包含语气标签或 `<#x#>` 精确停顿；
- TTS 输出路径和非敏感元数据路径；
- Fun-ASR 固定模型、音频输入、完整旁白上下文和 ASR 输出路径。

用户一次确认授权 1 次 MiniMax TTS 和紧随其后的 1 次 Fun-ASR。不得展示 API Key。失败后不自动重试计费请求；先报告错误，再由用户决定是否重试。

## 文本与表演控制

整条视频一次生成完整旁白，保持音色和情绪连续；不要逐镜头分别合成。每个镜头旁白独占一个段落，段落顺序必须与分镜一致。不要在文本中加入镜头编号或导演备注。

默认不设置 `emotion`，不自动插入 `(breath)`、`(laughs)` 等语气标签，也不自动插入 `<#x#>` 精确停顿；让模型依据已确认文本和标点自然表达。只有用户在第 1 或第 2 次确认中明确要求时，才提交这些控制。避免同时叠加标点停顿、精确停顿和换气标签，以免语气做作或节奏拖慢。

默认不做后期变速。若成片目标时长与默认估算冲突，优先改写旁白或拆分镜头；只有用户确认后才调整 `speed`，合理范围优先控制在 `0.9–1.15`。

## MiniMax 配音命令

先做无计费检查：

```bash
python3 scripts/minimax_tts.py check
```

第 2 次确认后生成：

```bash
python3 scripts/minimax_tts.py synthesize \
  --text-file /absolute/project/audio/narration.txt \
  --output /absolute/project/audio/narration.mp3 \
  --metadata /absolute/project/audio/narration.meta.json
```

适配器复用 `${CODEX_HOME:-$HOME/.codex}/skills/minimax-speech/scripts/minimax_speech.py`；密钥从统一配置或系统环境读取，默认音色内置为公司内部获授权的老王棚拍版。使用其他已授权音色或显式表演控制时才增加：

```bash
--voice-id OtherAuthorizedVoice01 --speed 1.05 --emotion calm
```

输出元数据必须包含 `provider=minimax`、`model`、`voice_id`、`duration_s`、`trace_id` 和 `narration_sha256`，不得包含 API Key、完整请求体或音频内容。

## 强制 Fun-ASR 检测

先运行不计费配置检查：

```bash
python3 scripts/aliyun_fun_asr.py check
```

真实调用会计费，但已包含在第 2 次确认中。TTS 成功后直接运行，不再单独询问：

```bash
python3 scripts/aliyun_fun_asr.py transcribe \
  --audio /absolute/project/audio/narration.mp3 \
  --context-file /absolute/project/audio/narration.txt \
  --output /absolute/project/audio/narration.fun-asr.json
```

客户端将本地 MP3 编码为 Base64 Data URI，通过同步 HTTP 提交；仅记录请求 ID、模型、字词数和音频时长，不记录密钥或完整云端响应。必须确认 `ok=true`、`word_count>0` 且输出 JSON 非空。MiniMax 的响应信息只允许保留作供应商诊断，禁止作为分镜、字幕、裁切或成片同步的输入。

`--context-file` 必须传入送给 MiniMax 的完整旁白。客户端不得按固定字符数静默截断上下文；若阿里云返回上下文长度错误，应停止并报告，不得删掉后半段旁白继续提交。

统一配置必须包含 `DASHSCOPE_API_KEY`。可选 `DASHSCOPE_BASE_URL`；未配置时使用阿里云兼容公共域名。模型固定为 `fun-asr-flash-2026-06-15`，不得通过环境变量静默替换。

Fun-ASR 失败时停止并报告，不得调用本地 Whisper、MLX 或其他 ASR 继续生产，也不得把 MiniMax 响应信息当作替代品。修复配置或服务问题后，新的付费重试需针对变化部分重新确认。

## 自动时间轴回写

不要让 agent 手工猜测或复制时间。准备一个 UTF-8 JSON 分镜文件；顶层可以是镜头数组，也可以是包含 `scenes` 数组的对象。每个镜头必须含有与送入 MiniMax 的段落完全一致的 `narration`：

```json
{
  "scenes": [
    {"scene": 1, "narration": "脸色暗沉，不一定只是没睡好。", "visual": "人物照镜子"},
    {"scene": 2, "narration": "藏在皮肤里的氧化压力，才是幕后推手。", "visual": "氧化颗粒进入剖面"}
  ]
}
```

运行确定性工具：

```bash
python3 scripts/build_timeline.py \
  --storyboard /absolute/project/storyboard.json \
  --narration-file /absolute/project/audio/narration.txt \
  --tts-metadata /absolute/project/audio/narration.meta.json \
  --asr-json /absolute/project/audio/narration.fun-asr.json \
  --audio /absolute/project/audio/narration.mp3 \
  --timeline /absolute/project/storyboard.timed.json \
  --srt /absolute/project/subtitles.srt \
  --ass /absolute/project/subtitles.ass \
  --aspect-ratio 9:16
```

工具会：

- 只接受 `timestamp_source=aliyun_fun_asr_flash` 的规范化 JSON，拒绝本地 ASR 或来源不明的数据。
- 校验 TTS 元数据中的 `narration_sha256`、原旁白文件和分镜 `narration` 三者一致；任一不一致立即失败。
- 以已确认旁白为准确文字，以 Fun-ASR 为真实时间；通过字符级序列对齐容忍少量同音错字。
- 写入每镜头 `start_s`、`end_s`、`duration_s` 和 `seedance_duration_s=max(4, ceil(duration_s))`；Seedance 2.0 Mini 仅接受 4–15 秒整数，绝不能写入 3。
- 直接生成每条 8–15 字的 SRT 和抖音竖屏 ASS。
- 在 ASR 文本编辑率超过 5% 时输出质量警告；超过 10%、时间戳倒退、音频时长异常或单镜头超过 8 秒时失败，不输出看似可用的错误时间轴。

以 Fun-ASR 驱动的 `storyboard.timed.json` 作为 Seedance 和最终剪辑的唯一时间轴。Seedance 使用 `seedance_duration_s` 生成，再按 `duration_s` 精确裁切；不拉伸人声。最终剪辑将每个语义起点统一映射到全局帧号 `floor(start_s*fps)`，禁止分别对每段时长向上取整后累加；导出后必须读回实际切点验证“不晚于发声”。

## 字幕

底部字幕由 `build_timeline.py` 使用已确认旁白文字与 Fun-ASR 时间生成。SRT 用于通用剪辑；`--aspect-ratio` 默认 `9:16`，ASS 使用 1080×1920 竖屏画布。只有用户明确指定横屏时传 `16:9`，ASS 才改为 1920×1080。图片内 2–4 字关键词仍属于画面设计，不与底部字幕合并。
