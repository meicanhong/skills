---
name: minimax-speech
description: 通过 MiniMax 中国开放平台的 speech-2.8-hd API 上传授权音频、快速克隆音色、查询可用音色，并使用克隆音色生成 MP3/WAV/FLAC/PCM 音频。用于用户要求接通 MiniMax Speech 2.8 HD、克隆本人或已获授权的声音、管理 voice_id、生成旁白/配音，或排查这些 API 调用时。
---

# MiniMax Speech

使用 `scripts/minimax_speech.py` 完成确定性调用。默认 API 地址为 `https://api.minimaxi.com`，默认模型固定为 `speech-2.8-hd`，公司内部包默认使用已获授权的老王棚拍版 `GuangxiLaoWang_Studio_20260814`；可用统一配置的 `MINIMAX_VOICE_ID` 覆盖。

## 前置条件

1. 仅克隆用户本人或已明确获得授权的声音；不协助冒充、诈骗或绕过同意。
2. 将 MiniMax 密钥填入 `${CODEX_HOME:-$HOME/.codex}/skincare-video-bundle.env`：

```dotenv
MINIMAX_API_KEY=你的密钥
```

脚本会自动读取该文件。同名系统环境变量的优先级更高，适合部署环境。不要在命令、日志或回复中展示密钥。

3. 如需切换兼容网关，在统一配置中设置 `MINIMAX_API_BASE`；否则不要修改。

## 工作流

### 使用已登记音色

未显式传入 `--voice-id` 时，使用公司内部获授权的老王棚拍版音色；统一配置中的 `MINIMAX_VOICE_ID` 可覆盖默认值。只有用户明确要求时才添加情感、语气标签、精确停顿或声音效果器。

### 克隆音色

优先使用一条干净、单人、无背景音乐的 10–30 秒参考音频。`voice_id` 必须为 8–256 位，以英文字母开头，只含字母、数字、`-`、`_`，且不能以 `-` 或 `_` 结尾。

```bash
python3 scripts/minimax_speech.py clone \
  --source-audio /absolute/path/reference.wav \
  --voice-id DannyVoice01 \
  --confirm-rights
```

若用户提供小于 8 秒的示例音频及其逐字文本，可一并提交以增强相似度和稳定性：

```bash
python3 scripts/minimax_speech.py clone \
  --source-audio /absolute/path/reference.wav \
  --voice-id DannyVoice01 \
  --prompt-audio /absolute/path/prompt.wav \
  --prompt-text '示例音频中实际说出的文字' \
  --validation-text '参考音频中实际说出的文字' \
  --confirm-rights
```

只有用户明确要求试听并接受合成计费时，才增加 `--preview-text` 和 `--preview-output`。不要为了验证克隆成功而默认生成收费试听。

### 使用克隆音色合成

文本较长时优先使用 `--text-file`，避免 shell 转义问题：

```bash
python3 scripts/minimax_speech.py synthesize \
  --text-file /absolute/path/narration.txt \
  --output /absolute/path/narration.mp3 \
  --language-boost Chinese
```

省略 `--voice-id` 时使用公司内部获授权的老王棚拍版音色；需要其他音色时显式传入 `--voice-id` 或通过统一配置覆盖默认值。

需要字幕时间戳时增加 `--subtitle-type sentence|word` 和 `--metadata-output /absolute/path/metadata.json`。生成后检查输出文件存在、非空，并向用户报告路径、格式、时长元数据和 API `trace_id`；不要只报告 HTTP 200。

### 查询音色

快速克隆音色只有在成功用于一次正式合成后，才会出现在查询结果中：

```bash
python3 scripts/minimax_speech.py voices --type voice_cloning
```

### 单独上传

只有调试或复用 `file_id` 时使用：

```bash
python3 scripts/minimax_speech.py upload --purpose voice_clone --file /absolute/path/reference.wav
python3 scripts/minimax_speech.py upload --purpose prompt_audio --file /absolute/path/prompt.wav
```

## 行为约束

- 克隆和合成可能计费，脚本不自动重试这些请求。
- 不把完整文本、音频内容、密钥或完整 API 响应写入日志。
- API 返回 HTTP 200 但 `base_resp.status_code != 0` 时仍视为失败。
- 复刻音频必须是 MP3/M4A/WAV、10 秒–5 分钟且不超过 20 MB；示例音频必须小于 8 秒且不超过 20 MB。
- `--text-validation` 校验失败（1043）时，核对逐字稿，不要通过降低阈值掩盖错误，除非用户明确要求。
- 详细字段、计费边界和官方链接见 [references/api.md](references/api.md)。
