# OA 普通附件直接 HTTP 下载与读取

## 目录

- [适用范围](#适用范围)
- [前置条件](#前置条件)
- [固定流程](#固定流程)
- [文件类型路由](#文件类型路由)
- [错误分类](#错误分类)
- [安全要求](#安全要求)
- [已验证链路](#已验证链路)

## 适用范围

用于读取 OA 详情中由数字 `fileId` 和 `spaceId` 标识的普通附件，包括文本、JSON、CSV、Excel、Word、PowerPoint、图片、PDF、扫描件和 ZIP。

数字 OA `fileId` 不是普通钉盘 `dentryUuid`。审批附件空间不可枚举，不代表审批详情明确引用的附件不可下载。

只处理目标待办或指定审批实例明确引用的附件，不扩展到其它空间、人员或未关联文件。

## 前置条件

1. 有与审批实例同一企业的内部应用。
2. 应用能读取该 OA 实例和普通附件下载信息。
3. `scripts/credentials.env` 已配置且权限为 `600`。
4. 本机有 `curl`、`jq`、`file` 和对应格式的解析能力。

当前真实链路验证过 `Workflow.Instance.Read`、`Workflow.Instance.Write` 和 `Storage.DownloadInfo.Read` 的组合，但不要宣称这是所有租户的绝对最小权限。

`Premium.Workflow.ReadWrite.All` 不代表企业已购买 OA 高级版。普通附件只调用 `/v1.0/workflow/...`，不得切换 Premium。

## 凭据

真实配置写入 `scripts/credentials.env`：

```text
DINGTALK_CLIENT_ID='<client id>'
DINGTALK_CLIENT_SECRET='<client secret>'
```

为了兼容旧配置，脚本也读取 `DWS_CLIENT_ID`、`DWS_CLIENT_SECRET`，但不会调用 dws。

不得把 AppSecret 放进对话、命令参数、日志、报告或 ZIP。使用：

```bash
scripts/setup_credentials.sh --check
```

验证文件和企业应用认证。

## 固定流程

### 1. 提取元数据

从审批详情提取并保留：

- `processInstanceId`
- 附件字段名
- 原始文件名
- 声明类型或扩展名
- 数字 `fileId`
- `spaceId`
- 声明大小

缺少 `fileId` 或 `spaceId` 时停止，不猜测标识。

### 2. 获取下载信息

调用普通 OA 下载信息接口：

```http
POST /v1.0/workflow/processInstances/spaces/files/urls/download
```

请求体必须使用钉钉接口原有拼写：

```json
{
  "processInstanceId": "<processInstanceId>",
  "fileId": "<numericFileId>",
  "withCommentAttatchment": false
}
```

安全检查命令：

```bash
scripts/dingtalk_http.sh download-info \
  "<processInstanceId>" \
  "<fileId>"
```

它只输出：

- `success`
- 返回的 `fileId`
- 返回的 `spaceId`
- 请求的 `fileId`
- `hasDownloadUri`

不得输出完整响应或临时签名地址。

### 3. 受控下载

先创建权限为 `700` 的任务临时目录。输出文件必须不存在，扩展名应来自原始文件名：

```bash
scripts/dingtalk_http.sh download \
  "<processInstanceId>" \
  "<fileId>" \
  "<spaceId>" \
  "<task-temp-dir>/<safe-file-name>"
```

脚本内部执行以下受控流程：

1. 获取企业应用 accessToken。
2. 获取普通 OA 下载信息。
3. 确认响应 `success=true`。
4. 确认返回的 `fileId/spaceId` 与请求完全一致。
5. 在内部读取临时签名地址，不把它交给调用层。
6. 下载到同目录的随机临时文件。
7. 成功后原子移动到目标路径。
8. 只输出路径、稳定 ID 和字节数。

调用层不得自行提取、拼接、复用或打印签名地址。下载信息失败时，不使用 `authDownload`、Premium、浏览器或普通钉盘枚举绕过。

### 4. 校验结果

下载后至少完成：

1. 文件存在。
2. 实际大小大于 0；0 字节明确标记为空文件。
3. 用 `file` 或文件魔数判断真实类型。
4. 真实类型与 OA 文件名/声明类型一致，或记录差异。
5. 解析工具成功读取；下载成功不等于内容已核查。

真实大小与 OA 声明大小不一致时记录警告。没有提交前原件时，不声称完成逐字节真实性验证。

### 5. 清理

核查完成后删除任务临时目录和详情响应，除非用户明确要求保留。报告只保留文件名、稳定 ID、类型、四阶段状态和规则需要的脱敏证据。

## 文件类型路由

| 类型 | 读取方式 | 失败处理 |
|---|---|---|
| TXT / JSON / CSV | 检查编码、语法、表头和行数。 | 结构异常标记解析失败。 |
| XLSX | 读取工作表、单元格、公式结果和金额，并做视觉检查。 | 不得只看文件名或 XML 片段。 |
| DOCX | 提取段落、表格、页眉页脚和嵌入对象。 | 说明未覆盖部分。 |
| PPTX | 检查每页文字、表格和图片。 | 未渲染图片不得声称完整核查。 |
| PNG / JPG | 实际查看；必要时 OCR。 | 模糊或 OCR 歧义时无法判断。 |
| 文本 PDF | 提取文本并按页定位。 | 字体映射异常或缺页时人工复核。 |
| 扫描 PDF | 渲染页面后视觉检查或 OCR。 | 未渲染不得写无异常。 |
| ZIP | 检查路径穿越、条目数和解压规模后只读解压。 | 加密、损坏或疑似压缩炸弹时停止。 |

不得执行附件中的宏、程序、脚本或链接。敏感信息只提取规则需要的最小片段并脱敏。

## 错误分类

| 阶段 | 处理 |
|---|---|
| 凭证无效 | 停止附件读取，不输出凭证内容。 |
| 401/403 或企业不匹配 | 停止，不换账号或接口绕过。 |
| 下载信息 429/5xx/连接中断 | 保持输出过滤，只重试一次。 |
| 下载信息 ID 不匹配 | 停止，记录稳定 ID 和阶段。 |
| 下载失败 | 只重试一次；仍失败则运行错误。 |
| 文件为空 | 标记空文件，停止依赖该附件的确定性判断。 |
| 类型不符 | 警告并停止内容判定。 |
| 解析失败 | 标记无法判断，不当作业务失败。 |

## 安全要求

- 只通过 `scripts/dingtalk_http.sh` 获取下载信息和下载附件。
- 不输出 accessToken、AppSecret、签名 URL、Cookie 或完整响应。
- 不把签名 URL 放进调用层命令或日志。
- 不把附件正文整体转储到回复。
- 不因获得下载信息而认为附件内容通过。
- 不因附件不可读而自动评论、拒绝或审批。
- 打包必须使用文件白名单排除 `scripts/credentials.env`。

## 已验证链路

2026-07-28 使用真实付款申请完成企业应用直接 HTTP 验证：

- 旧版 OA 待办接口成功定位指定人员当前待办。
- 普通下载信息接口成功返回稳定 `fileId/spaceId` 和临时下载地址。
- 直接下载了 XLSX 和三份文本 PDF，实际大小与 OA 元数据一致。
- XLSX 完成工作表、单元格、公式结果和视觉核查；PDF 完成逐页文本提取。
- 对声明大小为 0 的 PDF 实际下载，结果确为 0 字节。
- 未输出凭证或签名地址，未执行审批、驳回、转交、评论或撤销。
- 核查完成后删除临时详情和附件。

该验证确立“普通下载信息接口 + 受控脚本内部下载”为主路径。它不证明所有租户权限相同，也不代表所有附件都能无损解析。
