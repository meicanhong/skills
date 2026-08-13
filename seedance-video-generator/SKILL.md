---
name: seedance-video-generator
description: 仅使用 Seedance 2.0 Mini 模型，通过火山方舟 Seedance 视频生成 API 把自然语言指令、首尾帧图片或多模态参考素材生成视频，并在每次付费任务提交前强制展示完整入参、等待人类明确确认，再使用一次性批准单提交；支持查询、等待、下载视频和尾帧。用户提到 Seedance、豆包视频生成、文生视频、图生视频、首尾帧生视频、参考图/音频/视频生成，或要求查询 Seedance 任务时使用。
---

# Seedance 视频生成

使用 `scripts/seedance.py` 调用火山方舟正式 API。密钥只从 Skill 根目录 `.env` 或进程环境变量读取，绝不在命令参数、日志或回复中展示。

## 执行流程

1. 解析用户指令，先写好最终发送给模型的 `model_text`，再整理模型、素材、画幅、分辨率、时长、音频和水印等参数。把 `model_text` 写成简洁、自然、可直接发送给模型的文本；通常写清主体、动作和场景即可，只在本次视频确有需要时补充素材用途、镜头、声音、风格或约束，不擅自扩写剧情。
2. 根据场景选择素材参数：
   - 文生视频：只传 `--prompt`。
   - 首帧生视频：传 `--first-frame`。
   - 首尾帧生视频：同时传 `--first-frame` 与 `--last-frame`。
   - 多模态参考：传一个或多个 `--reference-image`、`--reference-video`、`--reference-audio`。
   - 首尾帧场景与多模态参考场景互斥，不可混用。
3. 始终使用且仅使用模型 `doubao-seedance-2-0-mini-260615`。不得改用其他模型；命令行、环境变量、`.env` 或历史批准单指定其他模型时必须在 API 调用前停止。涉及高级参数时先读 `references/api.md`。
4. 将写好的最终 `model_text` 通过 `--model-text` 传给 `prepare`。禁止把用户的原始短句未经整理直接提交，禁止在 `prepare` 之后再改写；此步骤只保存待提交参数并返回 `approval_id`，绝不调用 Seedance API。
5. 将 `prepare` 返回的 `request` 原样展示给人类，首先完整展示 `model_text`，再展示模型、全部素材、分辨率、画幅、时长、有声/水印等参数，并明确说明提交会计费。随后停止当前执行，询问“确认按以上 model_text 和参数提交吗？”。
6. 只有人类在后续消息中明确回复“确认提交”“同意”“批准”等肯定表达，才运行 `approve APPROVAL_ID`，然后运行 `submit APPROVAL_ID`。最初的生成指令不算确认；含糊回复、沉默或代理自行判断均不算确认。
7. 若确认前任何入参变化、批准单过期或已使用，重新运行 `prepare` 并再次请求人类确认。禁止复用批准单，禁止绕过 `prepare → approve → submit`。
8. `submit` 前若 `.env` 中 `ARK_API_KEY` 为空，停止并请用户填写；不要代填、猜测或回显密钥。
9. 报告任务 ID、最终状态、实际输出路径；失败时报告 API 错误码和可执行的修正建议，不泄露完整响应、密钥或签名下载 URL。

## 人工确认边界

- 确认仅约束会创建计费任务的 `POST /contents/generations/tasks`。
- `models`、`status`、`wait` 等只读操作无需确认。
- `prepare` 生成的批准单 30 分钟过期，只能提交一次。
- `submit` 在发起 POST 前先消费批准单。网络超时或 API 失败后也不得复用，避免不确定状态下重复计费；必须重新准备并确认。
- 不得在同一轮中连续执行 `prepare`、`approve`、`submit`。必须真实等待人类后续回复。

## 常用命令

查看支持模型：

```bash
python3 scripts/seedance.py models
```

第一阶段：准备参数，不调用 API：

```bash
python3 scripts/seedance.py prepare \
  --model-text '雨后东京街头，湿润路面反射霓虹灯光。一名撑透明雨伞的行人从画面左侧缓慢走向右侧，电影感写实风格，低饱和蓝紫色调，镜头平稳缓慢前推，环境雨声自然。' \
  --resolution 720p --ratio 16:9 --duration 5
```

将返回的 `request` 展示给人类并等待后续明确确认。确认后再执行：

```bash
python3 scripts/seedance.py approve APPROVAL_ID
python3 scripts/seedance.py submit APPROVAL_ID --output ./seedance.mp4
```

多模态参考的准备示例：

```bash
python3 scripts/seedance.py prepare \
  --model-text '保持参考图角色的外观、服装和色彩一致。角色跟随参考音乐节奏自然跳舞，动作连贯，主体始终清晰居中。' \
  --reference-image https://example.com/character.png \
  --reference-audio /absolute/path/music.mp3 \
  --model doubao-seedance-2-0-mini-260615
```

查询或等待已有任务：

```bash
python3 scripts/seedance.py status TASK_ID
python3 scripts/seedance.py wait TASK_ID --output ./result.mp4
```

## 参数原则

- 优先使用 body 强校验参数，不把 `--rs`、`--dur` 等拼入提示词。
- 遇到多素材引用、复杂运镜、视频延长/编辑、卡点、广告、短剧或科普等复杂提示词时，按需读取 `references/seedance2-prompt-guide-upstream.md`。该文件是即梦 Seedance 2.0 的上游参考快照，只借鉴提示词结构和示例；不得照搬与本 Skill 的 Mini 模型、火山方舟 API 或安全规则冲突的内容，也不强制使用其中的 `@` 语法。
- Seedance 2.0 Mini 不支持 `camera_fixed` 请求参数。用户要求固定镜头时，把“固定机位、镜头保持静止、无推拉摇移、画面构图不变”等准确要求写入 `model_text` 并提示效果不作硬保证；不得传 `camera_fixed`。
- `prepare` 必须包含非空 `model_text`，其内容会原样写入 API 的 `content[].text`。确认前任何文字改动都必须重新 `prepare`。
- 只支持 Seedance 2.0 Mini，不得使用或建议改用其他模型：

| 模型 | Model ID | 主要能力 |
|---|---|---|
| Seedance 2.0 Mini（唯一允许） | `doubao-seedance-2-0-mini-260615` | 成本更低，最高 720p |

- 用户未指定模型时不要追问，直接使用 Mini。用户指定任何其他模型时，在创建任务前停止并说明本 Skill 仅允许 Mini；不得为了完成请求绕过脚本校验。
- 视频参考素材只接受公网 URL 或 `asset://` ID；图片和音频允许本地文件。
- 本地 Base64 素材会增大请求体。接近平台限制时要求用户改用公网 URL/素材 ID。
- 生成会计费。用户没有明确要求批量时只创建一个任务；重试只针对临时网络错误和 429/5xx，不重复提交创建请求。
- 生成结果 URL 有时效，任务成功后及时下载。

## 文件

- `scripts/seedance.py`：无第三方依赖的 CLI 客户端。
- `references/api.md`：接口、状态、主要限制与官方文档链接。
- `references/seedance2-prompt-guide-upstream.md`：第三方 Seedance 2.0 中文提示词 Skill 的固定版本参考，包含来源、适用边界和 MIT 许可。
- `.env`：本地密钥和默认模型配置；必须保持私密，不提交版本库。
