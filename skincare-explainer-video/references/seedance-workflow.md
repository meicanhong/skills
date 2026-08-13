# Seedance 2.0 Mini 工作流

每次准备任务前完整读取 `/Users/danny/.codex/skills/seedance-video-generator/SKILL.md`，以它当前的模型、参数、批准单和失败处理为准。仅使用模型 `doubao-seedance-2-0-mini-260615`。每个已确认分镜单独生成视频片段，API 的整数时长严格使用分镜表中的 `seedance_duration_s`；下载后按 `duration_s` 和全局帧切点精确裁切。缺少这两个字段时停止，不得自行默认 5 秒或 15 秒。默认 720p、9:16、无声、无水印；只有用户明确指定横屏时才改为 16:9。

用于画风或主体一致性的多张图片走 `reference-image`；有明确首帧和尾帧的连续变化才使用首尾帧模式。两种模式不可混用。多张 reference-image 不代表连续分镜，必须在 `model_text` 中说明每张图的用途，不能让模型自行猜测顺序。

不得用一个 Seedance 任务生成整条 45–60 秒科普视频，也不得为了凑时长让一张分镜持续 15 秒。逐镜头准备任务，最终在后期按时间轴拼接。

必须使用 `/Users/danny/.codex/skills/seedance-video-generator/scripts/seedance.py` 先运行 `prepare`，展示每个镜头的完整 `model_text`、模型、参考图、画幅、分辨率、`seedance_duration_s`、音频、水印和输出格式。生成会计费，必须等用户后续明确确认才运行 `approve` 与 `submit`。批量镜头必须逐项列明，但只有用户明确批准的任务才可提交。网络超时、下载错误或状态不确定时查询原 task id，不重复创建任务。成功后验证 MP4、H.264、实际时长和分辨率；不得拉伸人声或用累计取整时长决定切点。禁止回显 API key、Cookie、签名 URL 或环境变量内容。
