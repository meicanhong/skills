# 风格锁定卡

## 主 Prompt

```text
Chinese skincare e-commerce science comic for a short video, clean low-complexity flat 2D animation, warm ivory or light gray background, stable thick dark-brown or black outlines, rounded simplified characters, exaggerated facial expressions, flat muted cream, blush pink, brown, ochre, pale blue and pale green color blocks, almost no shading, mixed black-and-white line-art panels, colored daily-life scenes, skin cross-section diagrams, anthropomorphic cells and particles, ingredient cards, evidence/report cards, split-screen before-and-after comparison, clear knowledge-card composition, one causal action per frame, large black bold Chinese keyword as a graphic element, not premium beauty advertising and not realistic medical rendering.
```

## 与原视频最关键的视觉语法

目标不是“温暖手绘插画”，而是“中国护肤电商知识漫画素材”。生成时优先模拟一组可剪辑的知识卡，而不是一张完整海报：

- 画面可以有黑色粗边框、上下分栏、左右对照、局部剖面、放大圆和突兀的大字卡。
- 一帧只完成一个小动作，必须允许构图不对称、主体偏左或偏右、留白和信息密度变化；不要连续生成相同的居中卡片。
- 连续镜头的版式要主动变化：黑框分栏 → 偏置单主体 → 局部放大圆 → 左右对照或大字卡；相邻两帧不得复用同一种版式。
- 局部特写要高频出现：每 3–4 个镜头至少安排 1 个局部特写，优先特写皮肤剖面、毛孔/细胞、自由基、成分符号、屏障裂缝或箭头碰撞，不要所有镜头都展示完整人物或完整皮肤。
- 黑白和彩色必须交替：每 2–3 个镜头至少出现一次黑白线稿/灰阶问题卡，再切回低饱和彩色机制卡；黑白卡也保留相同粗线稿和纸张底，不得变成另一种画风。
- 人物和细胞要像干净扁平的动画素材：五官简化、稳定粗描边、表情夸张，避免精致绘本、水彩质感和潦草抖动线。
- 彩色人物卡只保留大轮廓、平涂色块和 2–3 个表情线索；人物比例可略夸张，手部、衣服和背景不要展开细节。
- 彩色人物卡优先半身、侧脸、局部脸部或被画面边缘裁切的构图，不要正面全身站立和完整室内场景。
- 禁止彩色人物卡出现细腻皮肤渐变、发丝级细节、柔光、精致五官、复杂植物/家具、商业插画式完整背景；使用有限色块和稳定粗线。
- 让人物像“动画中停住的一帧”：轮廓稳定、平涂干净，表情用粗眉、眼袋、汗滴、皱线或嘴型快速传达。
- 机制图优先使用小型拟人颗粒、箭头、虚线、爆炸线、裂纹、火焰、汗滴和简单前后状态，不要用大型发光光环替代因果关系。
- 皮肤剖面要是平面分层的粉色/米色条带，细胞是重复的简化块状结构，不追求真实组织纹理。
- 画面内文字是剪辑节奏的一部分：大字卡、短标签、气泡和产品/报告小卡交替出现；不要每一帧都放顶部居中标题。
- 同一视频允许在黑白线稿、彩色漫画、剖面图、产品卡和报告卡之间跳切，但必须共享相同的粗线稿、纸张底色和色彩语义。

## 负面 Prompt

```text
photorealistic, realistic skin texture, 3D medical render, cinematic lighting, luxury beauty ad, glossy product commercial, complex anatomy, watercolor texture, sketchy trembling lines, rough paper grain, hair-strand detail, soft skin gradient, anime, children's picture book, neon colors, high saturation, crowded background, tiny illegible text, random Chinese characters, long generated captions, watermark, logo, invented brand claims
```

## 固定符号

- 成分：金色三球分子；同一项目不可改变形状和颜色。
- 氧化刺激：红橙色带刺颗粒。
- 中和后：平静的浅黄色圆粒。
- 皮肤屏障：分层粉色剖面。
- 细胞：圆角粉色边界；蛋白质：米色折叠团；DNA：玫瑰色简化双螺旋；保护：浅绿/奶油盾牌。
- 箭头、爆炸、裂纹、火焰、汗滴、速度线可作为手绘动作符号。

## 参考资产选择

读取 [asset-catalog.md](asset-catalog.md) 和 [apimart-image-workflow.md](apimart-image-workflow.md)。接触表只用于浏览选型，不得传给生图模型。每次生图从 `assets/reference-frames/` 选择 1 张主参考单帧，必要时增加 1 张辅参考单帧，并把每个绝对路径作为 APIMart CLI 的 `--image` 参数真实上传；只把文件名写进 Prompt 不算引用。

原视频资产负责锁定线稿、人物比例、平涂色块、知识卡构图和信息密度；主题 Prompt 只负责替换内容。不要连续只引用上一张生成图。

## 生成规则

1. 一张图只讲一个动作或因果关系，按“可剪辑素材卡”设计，而非完整海报。
2. 同一视频固定角色发型、脸型、服装、线宽和符号；至少一张原视频独立参考帧始终保留在参考输入中。
3. 画面内只让模型生成 2–4 个字的大关键词；长句、字幕、产品标签后期排版。
4. Fun-ASR 真实时间轴生成后，选择其中一个真实镜头做一张风格测试图；测试图必须至少包含以下任意三项：分栏/黑框、局部剖面、拟人化颗粒、粗箭头或虚线、短关键词、非对称构图。通过后再批量生成。
5. 每轮只修正漂移项：线稿、角色、色彩、构图、符号、文字中的一个或两个，不要整套提示词无目标重写。
6. 风格测试图和正式分镜图只使用 APIMart 非官方 `gpt-image-2`，并固定 `official_fallback=false`；每个任务固定 `n=1`，画幅跟随已确认的成片/Seedance 画幅，默认 `1k`。只有用户明确要求更高分辨率时才改为 `2k` 或 `4k`。

## 节奏验收

- 8 镜头脚本至少包含 2 张黑白或灰阶线稿卡、2 张局部特写卡、2 种以上非对称版式。
- 连续两张分镜不得同时满足“完整人物居中、顶部标题、单一米白背景、无分栏”。
- 若批量图片出现 3 张以上相同居中构图，必须重做版式，不得只改颜色或关键词。
