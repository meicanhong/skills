# Seedance API 摘要

## 官方入口

- 创建任务：<https://docs.volcengine.com/docs/82379/1520757>
- 查询任务：<https://docs.volcengine.com/docs/82379/1520758>
- 视频生成 API 导航：<https://docs.volcengine.com/docs/82379/1520756>
- 模型列表与 Model ID：<https://docs.volcengine.com/docs/82379/1330310>
- API Key 管理：<https://console.volcengine.com/ark/region:cn-beijing/apiKey>

本摘要依据用户提供的“创建视频生成任务 API”文档（最近更新时间 2026-06-25）整理。模型能力、价格与配额会变化，调用前以官方文档和当前账户控制台为准。

## Skill 支持模型

| 模型 | Model ID | 主要能力 |
|---|---|---|
| Seedance 2.0 Mini（唯一允许） | `doubao-seedance-2-0-mini-260615` | 成本更低，最高 720p |

唯一允许的 Model ID 为 `doubao-seedance-2-0-mini-260615`。本 Skill 不接受任何其他 Model ID 或 Endpoint ID；命令行、环境变量、统一配置和批准单都会在 API 调用前校验。

## 人工确认协议

创建生成任务会计费，必须使用以下三阶段协议：

1. `prepare`：构造并持久化精确 API payload，向人类完整展示将原样发送给模型的 `model_text`，以及不含密钥和 Base64 正文的其他参数摘要。
2. `approve`：仅在人类后续明确确认后，将待确认参数标记为已批准。
3. `submit`：一次性消费批准单，再调用创建任务 API。

批准单保存于 Skill 根目录 `.approvals/`，权限为仅当前用户可读写，30 分钟过期且不可重复使用。参数变化必须重新准备和确认。查询任务不会产生新的生成任务，不需要批准单。

## 接口

```text
POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks
GET  https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}
Authorization: Bearer <ARK_API_KEY>
Content-Type: application/json
```

创建接口是异步接口，响应核心字段为 `id`。查询状态包括 `queued`、`running`、`succeeded`、`failed`、`expired`，部分接口还可能返回 `cancelled`。成功结果位于 `content.video_url`，请求尾帧时可读取 `content.last_frame_url`。任务只保存有限时间，成功后及时下载。

## content 结构

```json
[
  {"type": "text", "text": "提示词"},
  {"type": "image_url", "image_url": {"url": "..."}, "role": "first_frame"},
  {"type": "image_url", "image_url": {"url": "..."}, "role": "last_frame"},
  {"type": "image_url", "image_url": {"url": "..."}, "role": "reference_image"},
  {"type": "video_url", "video_url": {"url": "..."}, "role": "reference_video"},
  {"type": "audio_url", "audio_url": {"url": "..."}, "role": "reference_audio"}
]
```

- 图片支持公网 URL、Base64 data URL、`asset://` 素材 ID。
- 视频支持公网 URL、`asset://` 素材 ID，不支持本地 Base64。
- 音频支持公网 URL、Base64 data URL、`asset://` 素材 ID。
- 首帧/首尾帧场景与多模态参考场景互斥。
- Seedance 2.0 Mini 对真人脸素材可能有额外授权和可信素材限制。

## 主要参数

- `model`：必填，且必须是 `doubao-seedance-2-0-mini-260615`。
- `content[].text`：本 Skill 必填。先写成最终 `model_text`，由 `prepare` 原样展示并等待人类确认。
- `resolution`：`480p`、`720p`、`1080p`、`4k`，各模型支持范围不同。
- `ratio`：`16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`。
- `duration`：4–15 秒整数，最短 4 秒；不得传 3 秒。需要更短成片时先生成至少 4 秒，再在本地裁切。
- `generate_audio`：支持模型可生成有声或无声视频。
- `watermark`：是否显示“AI 生成”水印。
- `return_last_frame`：是否返回尾帧。
- `execution_expires_after`：3600–259200 秒。
- `priority`：0–9，仅部分模型与在线模式支持。
- `service_tier`：`default` 或 `flex`；是否可用以 Seedance 2.0 Mini 当前模型规则为准。
- `camera_fixed`：Seedance 2.0 Mini 不支持，本 Skill 禁止传入。固定机位只能通过 `model_text` 表达，实际遵循效果不作硬保证。

不要仅靠本摘要预判参数兼容性；API body 强校验返回错误后，依据错误码和 Seedance 2.0 Mini 官方模型规则修正，不要静默删除用户明确要求的参数，也不要切换模型规避错误。
