# MiniMax Speech 2.8 HD API 摘要

## 端点

| 操作 | 方法与路径 |
|---|---|
| 上传复刻/示例音频 | `POST /v1/files/upload`，multipart |
| 快速复刻 | `POST /v1/voice_clone`，JSON |
| 查询音色 | `POST /v1/get_voice`，JSON |
| 同步合成 | `POST /v1/t2a_v2`，JSON |

API Base：`https://api.minimaxi.com`；同步合成备用地址：`https://api-bj.minimaxi.com/v1/t2a_v2`。

## 核心约束

- 所有请求使用 `Authorization: Bearer $MINIMAX_API_KEY`。
- 复刻原音频：MP3/M4A/WAV，10 秒–5 分钟，最大 20 MB，上传 `purpose=voice_clone`。
- 可选示例音频：MP3/M4A/WAV，小于 8 秒，最大 20 MB，上传 `purpose=prompt_audio`；提交 `clone_prompt` 时 `prompt_audio` 与 `prompt_text` 必须同时提供。
- `voice_id`：8–256 位；英文字母开头；只含字母、数字、连字符、下划线；末位不能是连字符或下划线；账号内唯一。
- `text_validation` 最大 200 字符；配合 `accuracy`（0–1，默认 0.7）校验音频逐字稿，失败码为 1043。
- 克隆接口中的 `text` 是收费试听文本，最大 1000 字符；不传则 `demo_audio` 为空。
- 同步合成文本小于 10,000 字符；超过 3,000 字符时官方建议流式输出。本 Skill 为可靠落盘采用非流式，超长任务应改用官方异步接口。
- 快速克隆音色需成功进行一次正式合成后才会出现在 `/v1/get_voice` 的 `voice_cloning` 中。

## Speech 2.8 HD 特性

- 支持 `(laughs)`、`(breath)`、`(sighs)`、`(crying)` 等行内语气词标签。
- 支持 `language_boost`，中文普通话用 `Chinese`，粤语用 `Chinese,Yue`，也可用 `auto`。
- 支持 `speed`、`vol`、`pitch`、`emotion`、采样率、码率和输出格式。
- 字幕粒度支持 `sentence`、`word`、流式时的 `word_streaming`。
- 非流式 `output_format` 可选 `hex` 或 24 小时有效的 `url`。脚本固定使用 `hex` 并立即写入本地，避免临时 URL 失效。

## 官方文档

- [同步语音合成](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)
- [上传复刻音频](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadcloneaudio)
- [上传示例音频](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadprompt)
- [音色快速复刻](https://platform.minimaxi.com/docs/api-reference/voice-cloning-clone)
- [查询可用音色](https://platform.minimaxi.com/docs/api-reference/voice-management-get)

