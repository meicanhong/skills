# 原视频参考资产目录

## 使用合同

- `assets/original-video-4s-contact-sheets/`：8 张原视频接触表，仅用于浏览、比较和定位画面，不得作为生图输入。
- `assets/reference-frames/`：从接触表裁出的 24 张 1280×720 独立原视频帧，是实际传入生图模型的参考资产。

每次生图必须：

1. 按镜头类型从下表选择 1 张主参考单帧；确需兼顾另一种视觉类型时再选 1 张辅参考单帧。
2. 将每张具体单帧的绝对路径作为 APIMart CLI 的独立 `--image /绝对路径/单帧.png` 参数；主辅参考共传两个 `--image`。
3. 不得使用 subagent 的 `local_image`、系统 `imagegen`、Imagen 或其他工具代替 APIMart；不得发送接触表，也不能仅凭目录文字要求工具自行读取。
4. 在 Prompt 中说明每张参考图负责锁定什么，例如“图 1 锁定粗糙人物比例，图 2 锁定皮肤剖面与局部构图”。
5. 不复制原帧中的品牌、产品、字幕或功效结论，只参考线稿、色块、人物比例、机制符号和版式。

## 独立参考帧

### 人物 `character/`

| 文件 | 优先用途 |
|---|---|
| `character-freckles-front-color.png` | 正面面部、雀斑、简化五官 |
| `character-aging-face-park-color.png` | 衰老状态、面部疲惫、户外人物 |
| `character-acne-mirror-color.png` | 照镜子、痘痘痛点、人物对照 |
| `character-redness-distress-cropped-color.png` | 泛红敏感、焦虑表情、裁切人物 |
| `character-dullness-dust-color.png` | 暗黄、灰尘油脂、夸张痛点 |
| `character-night-phone-fatigue-color.png` | 熬夜、手机、生活场景 |
| `character-scalp-washing-color.png` | 洗头、头皮护理、局部动作 |
| `character-oily-dull-face-color.png` | 出油暗沉、面部状态、黄色颗粒 |

### 机制 `mechanism/`

| 文件 | 优先用途 |
|---|---|
| `mechanism-melanin-particles-closeup-color.png` | 黑色素颗粒、聚集、拟人化细胞 |
| `mechanism-sebum-microbes-closeup-color.png` | 油脂团、微生物、毛囊环境 |
| `mechanism-inflammation-fire-closeup-color.png` | 炎症、火焰、屏障受损 |
| `mechanism-sebum-release-closeup-color.png` | 皮脂腺、油脂释放、黄色颗粒 |
| `mechanism-cell-oxidative-stress-color.png` | 氧化压力、细胞受扰、夜间机制 |
| `mechanism-scalp-night-cells-color.png` | 头皮细胞、夜间活跃、拟人颗粒 |
| `mechanism-pollution-particles-closeup-color.png` | 污染吸附、灰尘颗粒、局部机制 |

### 皮肤与头皮剖面 `skin-cross-section/`

| 文件 | 优先用途 |
|---|---|
| `skin-collagen-fibers-cutaway-color.png` | 胶原、弹性纤维、皮肤层次 |
| `skin-sebum-factory-cutaway-color.png` | 皮肤下油脂工厂、拟人剖面 |
| `skin-barrier-repair-cutaway-color.png` | 屏障修护、脂质与纤维蛋白 |
| `skin-barrier-layer-closeup-color.png` | 平整屏障、皮肤分层、保护状态 |
| `scalp-follicle-magnifier-color.png` | 毛囊放大圆、头皮堵塞、局部特写 |
| `skin-dullness-layer-cutaway-color.png` | 暗沉皮肤层、黄色沉积、皮肤剖面 |

### 证据与版式 `evidence-layout/`

| 文件 | 优先用途 |
|---|---|
| `evidence-report-expert-split-color.png` | 报告＋专家、左右分栏、证据卡 |
| `layout-skin-before-after-color.png` | 皮肤前后对比、粗箭头、切面变化 |
| `layout-oxidation-glycation-split-color.png` | 氧化/糖化双栏、标签卡、机制比较 |

## 快速选择

- 人物生活痛点：从 `character/` 选 1 张。
- 氧化、自由基、麦角硫因：主选 `mechanism-cell-oxidative-stress-color.png`，需要皮肤结构时辅选 `skin-barrier-layer-closeup-color.png`。
- 屏障、泛红、炎症：主选 `mechanism-inflammation-fire-closeup-color.png` 或 `skin-barrier-repair-cutaway-color.png`。
- 毛囊、油脂、头皮：主选 `scalp-follicle-magnifier-color.png` 或 `mechanism-sebum-microbes-closeup-color.png`。
- 专家、报告和证据：主选 `evidence-report-expert-split-color.png`。
- 前后对比或双机制：选择 `layout-skin-before-after-color.png` 或 `layout-oxidation-glycation-split-color.png`。

同一批分镜可复用一张独立参考帧保持风格，但相邻镜头应切换人物、机制、剖面或版式类型，避免重复构图。不得把生成结果作为唯一参考；至少保留一张原视频独立参考帧。
