---
name: apimart-gpt-image-2
description: 通过 APIMart 的非官方 gpt-image-2 API 生成或编辑图片，支持文生图、图生图、多参考图、本地图片上传、异步任务轮询和结果下载，并强制关闭官方渠道兜底。用户明确要求使用 APIMart、GPT-Image-2 低成本渠道，或要求通过 APIMart API 生成/修改图片时使用；不要替代或修改本地 imagegen、Imagen 或其他图片 Skill。
---

# APIMart GPT-Image-2

使用独立脚本调用 APIMart，不修改或复用其他图片 Skill。API 调用会消耗 APIMart 额度。

## 安全边界

- 仅在用户明确要求生成、编辑或重绘图片时提交生成任务。
- 优先从本 Skill 根目录的 `.env` 读取密钥；未配置时才读取系统环境变量 `APIMART_API_KEY`。不得输出密钥或拼入命令行参数。
- 固定使用非官方模型 `gpt-image-2`，并在每个请求中强制发送 `official_fallback=false`；不得接受用户覆盖模型名或开启官方渠道兜底。
- 不自动重试生成、上传等 `POST` 请求，避免重复任务或重复计费。
- 只对 `GET` 任务轮询中的 `429`、`500`、`502` 和网络瞬时错误做有限退避重试。
- 不触碰 `~/.codex/skills/.system/imagegen`、任何 Imagen Skill 或它们的配置。
- 没有密钥时停止并指出 `.env` 路径；不要索要用户在聊天中粘贴密钥。

## 配置

把 API Key 写入本 Skill 根目录的 `.env`：

```dotenv
APIMART_API_KEY=你的密钥
```

`.env` 权限必须保持为 `600`，且已由 `.gitignore` 排除。不要在命令、聊天或日志中显示文件内容。

## 工作流

1. 根据用户意图确定文生图、图生图或局部重绘。
2. 对不明确的参数使用低成本默认值：`size=1:1`、`resolution=1k`、`n=1`。
3. 生成前运行 `--dry-run`，验证请求字段和约束；dry-run 不需要密钥、不会联网或计费。
4. 用户提供本地参考图时使用 `--image PATH`；脚本先上传并取得 72 小时有效 URL。已有公网 URL 时使用 `--image-url URL`。
5. 当前非官方接口不支持 mask 局部重绘；需要局部修改时用参考图加文字描述表达，不得静默切换官方模型。
6. 使用 `--wait --output-dir DIR` 提交、轮询并下载结果。高分辨率可能耗时较长，按需求提高 `--timeout`。
7. 向用户返回任务 ID、最终状态、图片文件路径、远端 URL、到期时间和可用的计费字段；失败时返回 API 错误类型与消息。
8. 下载成功后必须在当前 Codex 任务中用本地绝对路径的 Markdown 图片语法直接展示每张结果，例如 `![生成结果 1](/absolute/path/result.png)`；不得只给路径、普通链接、远端 URL 或任务 ID。批量结果按顺序逐张展示全部原图，接触表只能作为附加总览，不能替代原图。

## 命令

脚本路径：`scripts/apimart_gpt_image_2.py`

先验证请求：

```bash
python3 scripts/apimart_gpt_image_2.py generate \
  --prompt "星空下的古老城堡" \
  --size 16:9 --resolution 1k \
  --dry-run
```

生成并下载：

```bash
python3 scripts/apimart_gpt_image_2.py generate \
  --prompt "星空下的古老城堡" \
  --size 16:9 --resolution 1k \
  --wait --output-dir ./outputs
```

使用本地参考图：

```bash
python3 scripts/apimart_gpt_image_2.py generate \
  --prompt "保留主体轮廓，改成手绘海报" \
  --image /absolute/path/reference.png \
  --wait --output-dir ./outputs
```

查询已有任务：

```bash
python3 scripts/apimart_gpt_image_2.py status TASK_ID --language zh
```

所有命令输出机器可读 JSON。完整字段、尺寸映射和错误语义见 [API 参考](references/api-reference.md)。

## 结果判定

- 提交响应：读取 `data[0].task_id`，不得把 `submitted` 当作完成。
- 轮询状态兼容 `submitted`、`pending`、`in_progress`、`processing`。
- 仅当状态为 `completed` 时读取 `data.result.images[*].url[*]`。
- `failed` 或 `cancelled` 为终态；保留 `data.error` 供诊断。
- 下载链接会过期，应在完成后立即下载到用户指定目录。
- 只有本地文件已下载、实际检查并在聊天中直接渲染后，才算完成面向用户的图片交付。
