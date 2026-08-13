# APIMart GPT-Image-2 API 参考

来源（2026-08-13 核对）：

- 生成：https://docs.apimart.ai/cn/api-reference/images/gpt-image-2/generation
- 任务：https://docs.apimart.ai/cn/api-reference/tasks/status
- 上传：https://docs.apimart.ai/cn/api-reference/uploads/images

## 接口

| 用途 | 方法与路径 | 请求 | 关键响应 |
|---|---|---|---|
| 上传本地图片 | `POST /v1/uploads/images` | `multipart/form-data`，字段 `file` | `url`, `filename`, `content_type`, `bytes`, `created_at` |
| 提交生成 | `POST /v1/images/generations` | JSON | `data[0].status`, `data[0].task_id` |
| 查询任务 | `GET /v1/tasks/{task_id}?language=zh` | 路径参数、可选语言 | `data.status`, `data.progress`, `data.result`, `data.error` |

Base URL 为 `https://api.apimart.ai`。所有请求使用 `Authorization: Bearer $APIMART_API_KEY`。

## 生成参数

- `model`：必填，固定非官方渠道 `gpt-image-2`；不使用兼容别名 `gpt-image-2-ext`。
- `prompt`：必填，支持中英文，提交前经过平台安全审核。
- `size`：默认 `1:1`。支持 `auto`、`1:1`、`3:2`、`2:3`、`4:3`、`3:4`、`5:4`、`4:5`、`16:9`、`9:16`、`2:1`、`1:2`、`3:1`、`1:3`、`21:9`、`9:21`，也支持 `宽x高` 像素串。
- `resolution`：`1k`（默认）、`2k`、`4k`。
- `n`：客户端固定为整数 `1`。文档参数说明限定为 1，虽另有多张示例，为避免未确认计费差异不放宽。
- `image_urls`：参考图数组，最多 16 张；单张最大 20MB，总体最大 256MB。接口支持公网 URL 与 base64 data URI 混填；本客户端对本地图片使用上传接口取得 URL。
- `official_fallback`：固定 `false`，禁止非官方上游不可用时切换到高价官方渠道。

非官方接口未文档化 `quality`、`background`、`moderation`、`output_format`、`output_compression` 和 `mask_url`，客户端不发送这些字段。`response_format` 与 `style` 会被服务端忽略，也不发送。

## 上传限制

支持 JPEG、PNG、WebP、GIF，单文件最大 20MB。上传后的 URL 仅保存 72 小时。非官方生成接口也支持 base64 data URI，但客户端继续使用上传 URL，避免增大请求体并保持统一链路。

## 尺寸映射

| 比例 | 1k | 2k | 4k |
|---|---:|---:|---:|
| 1:1 | 1024x1024 或 1254x1254 | 2048x2048 | 2880x2880 |
| 3:2 | 1536x1024 | 2048x1360 | 3520x2336 |
| 2:3 | 1024x1536 | 1360x2048 | 2336x3520 |
| 4:3 | 1024x768 | 2048x1536 | 3312x2480 |
| 3:4 | 768x1024 | 1536x2048 | 2480x3312 |
| 5:4 | 1280x1024 或 1448x1086 | 2560x2048 | 3216x2576 |
| 4:5 | 1024x1280 或 1122x1402 | 2048x2560 | 2576x3216 |
| 16:9 | 1536x864 或 1672x941 | 2048x1152 | 3840x2160 |
| 9:16 | 864x1536 或 941x1672 | 1152x2048 | 2160x3840 |
| 2:1 | 2048x1024 或 1774x887 | 2688x1344 | 3840x1920 |
| 1:2 | 1024x2048 或 887x1774 | 1344x2688 | 1920x3840 |
| 3:1 | 1881x836 或 1536x512 | 3072x1024 | 3840x1280 |
| 1:3 | 887x1774 或 512x1536 | 1024x3072 | 1280x3840 |
| 21:9 | 2016x864 或 1915x821 | 2688x1152 | 3840x1648 |
| 9:21 | 864x2016 或 821x1915 | 1152x2688 | 1648x3840 |

## 状态与错误

任务终态为 `completed`、`failed`、`cancelled`。文档不同页面对处理中状态使用两套命名，客户端兼容 `submitted`、`pending`、`in_progress`、`processing`。

- `400`：参数或任务 ID 错误，不重试。
- `401`：认证失败，不重试。
- `402`：余额不足，不重试。
- `403`：无权限，不重试。
- `429`：频率限制。只读查询可退避重试；生成和上传不自动重试。
- `500`、`502`、`503`：服务、网关或上游暂不可用。只读查询可退避重试；生成和上传不自动重试，且不会官方兜底。
- 上传另有 `413`：文件过大，不重试。
