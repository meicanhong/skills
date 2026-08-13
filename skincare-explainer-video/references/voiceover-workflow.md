# 豆包复刻配音与 Fun-ASR 真实时间轴工作流

## 位置与顺序

在旁白、语义分镜和配音参数确认后立即制作配音；不得等待风格测试图或正式分镜图片。默认使用当前复刻音色、`seed-tts-2.0-expressive` 和 `speech_rate=0`；脚本阶段按实测每秒 5.0 个汉字估算时长。豆包只负责生成最终音频；音频完成后必须调用阿里云 `fun-asr-flash-2026-06-15` 检测真实时间戳。Fun-ASR 时间戳取代估算值和豆包时间戳，成为画面设计、镜头切换、Seedance 时长和底部字幕的唯一时间真值。

```text
确认完整旁白、语义分镜和配音参数 → 豆包生成完整旁白
→ Fun-ASR 检测最终音频 → 生成真实时间轴 → 风格测试图
→ 正式分镜图片 → Seedance 分镜视频 → 精确裁切拼接 → 字幕合成
```

## 计费确认

语音合成会计费。调用前展示：完整旁白、Speaker 配置是否存在、Resource ID、模型、语速、表演指令和输出路径；不得展示 API Key 或完整 Speaker ID。等待用户明确确认后才运行 `synthesize`。用户在同一条消息中明确要求生成或测试某段配音，可视为该次调用授权。

## 文本组织

整条视频一次生成完整旁白，保持音色、气口和情绪连续；不要逐镜头分别合成。每个镜头旁白独占一个段落，段落顺序必须与分镜一致。不要在文本中加入镜头编号、导演备注或括号情绪标签。

默认表演指令：

```text
用年轻自然的中文护肤博主语气表达。前三秒有悬念和冲击力；揭晓机制时清晰、有节奏；成分登场时提高能量；结尾坚定、有记忆点。不要播音腔，不要喊叫。
```

## 命令

先做无计费检查：

```bash
python3 scripts/doubao_tts.py check
```

确认后生成：

```bash
python3 scripts/doubao_tts.py synthesize \
  --text-file /absolute/project/audio/narration.txt \
  --output /absolute/project/audio/narration.mp3 \
  --words /absolute/project/audio/narration.words.json \
  --metadata /absolute/project/audio/narration.meta.json \
  --instruction '用年轻自然的中文护肤博主语气表达。前三秒有悬念和冲击力；揭晓机制时清晰、有节奏；成分登场时提高能量；结尾坚定、有记忆点。不要播音腔，不要喊叫。'
```

脚本固定从 Skill 根目录 `.env` 读取配置，不得把密钥写进命令行、日志、Prompt 或项目产物。失败后不自动重试计费请求；先报告错误，再由用户决定是否重试。

## 强制 Fun-ASR 检测

先运行不计费配置检查：

```bash
python3 scripts/aliyun_fun_asr.py check
```

真实调用会计费。提交前展示固定模型 `fun-asr-flash-2026-06-15`、最终音频绝对路径、已确认旁白上下文、规范化 JSON 输出路径，并等待用户明确确认。确认后运行：

```bash
python3 scripts/aliyun_fun_asr.py transcribe \
  --audio /absolute/project/audio/narration.mp3 \
  --context-file /absolute/project/audio/narration.txt \
  --output /absolute/project/audio/narration.fun-asr.json
```

客户端将本地 MP3 编码为 Base64 Data URI，通过同步 HTTP 提交；仅记录请求 ID、模型、字词数和音频时长，不记录密钥或完整云端响应。必须确认 `ok=true`、`word_count>0` 且输出 JSON 非空。豆包 `words.json` 只允许保留作供应商诊断，禁止作为分镜、字幕、裁切或成片同步的输入。

`--context-file` 必须传入送给豆包的完整旁白。客户端不得按固定字符数静默截断上下文；若阿里云返回上下文长度错误，应停止并报告，不得删掉后半段旁白继续提交。

Skill `.env` 必须配置 `DASHSCOPE_API_KEY`。可选 `DASHSCOPE_BASE_URL`；未配置时使用阿里云兼容公共域名。模型固定为 `fun-asr-flash-2026-06-15`，不得通过环境变量静默替换。

Fun-ASR 失败时停止并报告，不得调用本地 Whisper、MLX 或其他 ASR 继续生产，也不得把豆包供应商时间戳当作替代品。修复配置或服务问题后，重新展示计费参数并取得确认，再重试 Fun-ASR。

## 自动时间轴回写

不要让 agent 手工猜测或复制时间。准备一个 UTF-8 JSON 分镜文件；顶层可以是镜头数组，也可以是包含 `scenes` 数组的对象。每个镜头必须含有与送入豆包的段落完全一致的 `narration`：

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
- 校验豆包元数据中的 `narration_sha256`、原旁白文件和分镜 `narration` 三者一致；任一不一致立即失败。
- 以已确认旁白为准确文字，以 Fun-ASR 为真实时间；通过字符级序列对齐容忍少量同音错字。
- 写入每镜头 `start_s`、`end_s`、`duration_s` 和向上取整的 `seedance_duration_s`。
- 直接生成每条 8–15 字的 SRT 和抖音竖屏 ASS。
- 在 ASR 文本编辑率超过 5% 时输出质量警告；超过 10%、时间戳倒退、音频时长异常或单镜头超过 8 秒时失败，不输出看似可用的错误时间轴。

以 Fun-ASR 驱动的 `storyboard.timed.json` 作为 Seedance 和最终剪辑的唯一时间轴。Seedance 使用 `seedance_duration_s` 生成，再按 `duration_s` 精确裁切；不拉伸人声。最终剪辑将每个语义起点统一映射到全局帧号 `floor(start_s*fps)`，禁止分别对每段时长向上取整后累加；导出后必须读回实际切点验证“不晚于发声”。

## 字幕

底部字幕由 `build_timeline.py` 使用已确认旁白文字与 Fun-ASR 时间生成。SRT 用于通用剪辑；`--aspect-ratio` 默认 `9:16`，ASS 使用 1080×1920 竖屏画布。只有用户明确指定横屏时传 `16:9`，ASS 才改为 1920×1080。图片内 2–4 字关键词仍属于画面设计，不与底部字幕合并。
