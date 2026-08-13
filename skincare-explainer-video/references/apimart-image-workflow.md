# APIMart 分镜生图工作流

## 边界

- 唯一生图提供方：`$apimart-gpt-image-2`。
- 唯一模型：非官方 `gpt-image-2`。
- 每个请求必须包含 `official_fallback=false`，禁止因上游不可用切到高价官方渠道。
- 唯一客户端：同一 Skills 根目录下的 `apimart-gpt-image-2/scripts/apimart_gpt_image_2.py`。
- 密钥只由 APIMart Skill 根目录的 `.env` 提供；不得复制到本 Skill 的 `.env`，不得显示或记录。
- 不调用系统 `imagegen`、Imagen、subagent 生图或其他图片模型作为 fallback。

每次开始风格测试或正式分镜生图前，完整读取 [`../../apimart-gpt-image-2/SKILL.md`](../../apimart-gpt-image-2/SKILL.md)，以其当前 API 参数、安全边界、轮询和下载规则为准。执行命令前，将该依赖 Skill 的实际根目录解析为绝对路径 `APIMART_SKILL_ROOT`；不得假设用户名或固定的 `~/.codex` 路径。

## 前置条件

只有同时满足以下条件才准备生图：

1. 旁白与语义分镜已确认。
2. 整条豆包配音已生成，并已用 `fun-asr-flash-2026-06-15` 检测最终音频的真实词句时间戳。
3. `storyboard.timed.json` 已生成且镜头均不超过 8 秒。
4. 当前镜头的构图、色彩状态、2–4 字关键词、唯一动作和参考帧已补全。
5. 已记录输出画幅；抖音项目默认统一为 `9:16`，只有用户明确指定横屏时才使用 `16:9`。APIMart、Seedance、字幕和最终成片必须使用同一画幅。

## Prompt 组装

按以下顺序组成单个 Prompt：

1. `style-guide.md` 的主 Prompt。
2. 当前镜头的唯一动作、主体位置、构图、黑白/彩色状态和 2–4 字关键词。
3. 参考图职责，例如“图 1 只锁定粗线稿、人物比例和平涂色块；图 2 只锁定皮肤剖面与局部放大构图”。
4. 固定符号、色彩语义和相邻镜头版式差异。
5. `style-guide.md` 的负面 Prompt，以 `Avoid:` 段落并入正文；APIMart 接口没有独立 `negative_prompt` 字段。
6. 明确“不复制参考图中的品牌、产品、字幕或功效结论；不生成底部字幕、Logo 和水印”。

## 计费确认门

APIMart 生成会计费。风格测试和正式批次是两个独立确认门。

提交前向用户展示：

- 镜头 ID 和用途（风格测试/正式分镜）。
- 完整 Prompt。
- 每个主辅参考帧的绝对路径和锁定职责。
- `size`、`resolution`、`n`、`official_fallback=false`。
- 每个镜头的独立输出目录。
- 本批次将创建的任务数量。
- 正式分镜批次的并发数，默认 `5`。

未获得当前阶段明确确认时停止。旧阶段确认、风格测试确认或 Seedance 确认不能代替正式分镜批次确认。

## 无计费预检

先确认参考帧是独立图片而非接触表，并检查文件存在、格式和尺寸。然后运行不带本地 `--image` 的 dry-run 验证生成参数；本地参考图会在真实提交时由 `--image` 上传，dry-run 不上传文件。

```bash
python3 "$APIMART_SKILL_ROOT/scripts/apimart_gpt_image_2.py" \
  generate \
  --prompt "$FULL_PROMPT" \
  --size 9:16 \
  --resolution 1k \
  --n 1 \
  --dry-run
```

如果用户明确确认横屏，把 `--size 9:16` 改成 `--size 16:9`；不得让单个阶段自行改变画幅。

## 风格测试提交

用户批准后，只生成 1 张真实镜头测试图。每张参考帧各写一个 `--image`：

```bash
python3 "$APIMART_SKILL_ROOT/scripts/apimart_gpt_image_2.py" \
  --verbose generate \
  --prompt "$FULL_PROMPT" \
  --image "/absolute/path/to/main-reference.png" \
  --image "/absolute/path/to/optional-secondary-reference.png" \
  --size 9:16 \
  --resolution 1k \
  --n 1 \
  --wait \
  --output-dir "/absolute/project/path/images/style-test"
```

没有辅参考时删除第二个 `--image`，不要传空值。完成后实际打开图片，按 `style-guide.md` 和 `SKILL.md` 验收；不能只看 `completed`。随后必须在当前任务回复中用本地绝对路径直接展示图片，例如：

```markdown
![风格测试镜头 07](/absolute/project/path/images/style-test/shot-07.png)
```

普通文件链接、远端 URL、任务 ID 或“已生成”的文字不能代替图片展示。展示后等待用户确认风格，不得直接开始正式批次。

## 正式分镜批次

风格测试图得到用户确认后，为每个镜头准备一条完整命令和独立目录，例如 `images/shot-01/`。展示完整批次并再次等待用户确认，然后才可并发执行。默认并发数为 `5`：任一时刻最多运行 5 个 APIMart 正式分镜任务；任务完成或明确失败后再补入下一个，直到批次结束。镜头少于 5 个时按实际数量执行；用户可在批次确认时明确降低或提高并发数。

- 每个镜头固定 `n=1`，避免一条任务产生未审核变体。
- 每个镜头始终至少带 1 张原视频独立参考帧。已确认风格测试图可作为附加参考，但不能替代原视频帧。
- 并发任务必须使用不同输出目录并逐个记录 `task_id`；单个失败不得重提整批。
- 风格测试图始终单任务执行，不计入正式分镜批次的默认并发数。
- 每张完成图都要实际打开检查，并记录镜头 ID、任务 ID、本地路径、远端 URL 到期时间、费用和 token 用量。

## 批次展示与确认门

正式批次全部完成或明确失败后，先汇总成功、失败和隔离状态，再按镜头编号逐张在当前 Codex 任务中展示所有成功的本地原图：

```markdown
![镜头 01](/absolute/project/path/images/shot-01/result.png)

![镜头 02](/absolute/project/path/images/shot-02/result.png)
```

- 必须使用 `![说明](本地绝对路径)` 图片语法，使 Codex 客户端直接渲染图片；不得只给可点击路径。
- 必须展示每张成功原图，不能只展示拼图、接触表或任意抽样；可额外提供接触表帮助总览，但不能替代原图。
- 每张图的说明至少包含镜头编号；失败或被隔离的镜头在相应位置明确标注原因，不伪造占位图。
- 展示完成后明确请求用户审核这一批分镜。用户确认前不得运行 Seedance `prepare`，更不得提交视频生成。

## 失败处理

- POST 没有返回明确结果时，不自动重试；先根据已有 `task_id` 查询，缺少 `task_id` 时报告状态不确定。
- 已有 `task_id` 时使用 `status TASK_ID --language zh` 查询原任务，不创建重复任务。
- 下载失败但任务已完成时，从原任务响应中的 URL 再下载，不重新生成。
- 只有任务明确为 `failed` 才可准备新任务；先缩短 Prompt、减少主体或移除长文字，展示新请求并重新获得计费确认。
- `401/402/403` 直接停止并报告认证、余额或权限问题；`429/500/502/503` 不自动重发生成 POST，且不得开启官方兜底。
