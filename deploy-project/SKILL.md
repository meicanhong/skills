---
name: deploy-project
description: 部署当前项目上线：先构建 linux/amd64 镜像推送到阿里云 ACR，再按项目自带的部署方式发布。凡是发版、上线、部署、发布、更新线上服务、构建镜像、推镜像、要镜像地址、回滚版本时都使用本技能。
---

# 构建并发布镜像到 ACR

本技能只负责**把镜像做出来、推进 ACR**。推送完成后，按该项目实际部署方式发布，本技能不规定部署方式。

使用前请将本目录的 `.env.example` 复制为 `.env`（权限设为 `600`，不要提交）并填入实际的 ACR 域名、命名空间与凭证。

## 一、两个域名（先分清）

| 用途 | 域名 |
|---|---|
| 本地构建打 tag、推送 | `<ACR_REGISTRY>`（例如 `your-registry.cn-region.cr.aliyuncs.com`） |
| 阿里云内网拉取 | `<ACR_REGISTRY_VPC>`（例如 `your-registry-vpc.cn-region.cr.aliyuncs.com`） |

同一个镜像，两个地址前缀不同，仓库路径和 tag 完全一致：

```
推送  <ACR_REGISTRY>/<ACR_NAMESPACE>/<项目>:<env>-<YYYYMMDD>-<短sha>
拉取  <ACR_REGISTRY_VPC>/<ACR_NAMESPACE>/<项目>:<env>-<YYYYMMDD>-<短sha>
```

## 二、构建

```bash
docker build --platform linux/amd64 \
  -t <ACR_REGISTRY>/<ACR_NAMESPACE>/<项目>:<env>-<YYYYMMDD>-<短sha> .
```

构建默认使用 Docker 缓存，不要加 `--no-cache`。未变化的层直接复用，从第一个变化的层开始重新构建。

- **项目名**：git remote 仓库名转小写（例如 `MyApp` → `myapp`，`my-service` 不变）
- **tag 格式**：`<env>-<YYYYMMDD>-<短sha>`，例如 `prod-20261124-a1b2c3d`
  - 看得出属于哪个环境
  - 按时间排序天然就是发布顺序，回滚和清理可直接用
- **必须带 `--platform linux/amd64`**：开发机是 arm64，不带这个参数打出来的镜像在服务器上会 `exec format error`

## 三、推送

```bash
docker login <ACR_REGISTRY>   # 未登录时才需要
docker push <ACR_REGISTRY>/<ACR_NAMESPACE>/<项目>:<env>-<YYYYMMDD>-<短sha>
```

推送也是**增量**的：ACR 已有的层会显示 `Layer already exists`，只上传新层和新的镜像清单。

## 四、推送之后

镜像已经在 ACR 里了。接下来怎么部署，按该项目自己的方式处理，但要注意两点：

1. **用刚推送的这个 tag**，不要用 `latest` 之类的浮动 tag
2. **能内网就内网**：机器在上述 VPC 内就用 `-registry-vpc.` 域名，否则用公网域名

部署后确认容器健康状态；如果新版本启动失败，回退到上一个 tag 再拉起。

## 五、服务器拉取失败

服务器拉镜像报 `unauthorized` 时，读取本技能目录的 `.env`，登录拉取所用的 ACR 域名后重试。

```bash
source <DEPLOY_PROJECT_SKILL_DIR>/.env
printf '%s' "$ACR_PASSWORD" | ssh <服务器> \
  "sudo docker login --username '$ACR_USERNAME' --password-stdin $ACR_REGISTRY_VPC"
```

`.env`（参考 `.env.example`）：

```dotenv
ACR_REGISTRY=<公网 ACR 域名>
ACR_REGISTRY_VPC=<内网 VPC ACR 域名>
ACR_NAMESPACE=<ACR 命名空间>
ACR_USERNAME=<ACR 登录用户名>
ACR_PASSWORD=<ACR 登录密码>
```

`docker login` 和 `docker pull` 使用相同账号。`.env` 权限设为 `600`，不要提交。

## 六、四个坑

1. **漏 `--platform linux/amd64`** → 服务器报 `exec format error`
2. **忘记 `docker login`** → push 报 `unauthorized`
3. **拿脏工作区构建** → 镜像内容和 commit 对不上；构建前先确认代码已提交
4. **用 ACR 云端构建** → 它的构建环境连不上 Docker Hub（已实测），不要用
