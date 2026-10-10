# 配置字段与仓库结构

## 仓库目录

```text
compose.yaml              基础服务、网络、挂载和资源限制
.env.example              参数示例，不含有效凭据
traefik/templates/        静态配置与路由源模板
traefik/generated/        本机生成结果，不提交 Git
traefik/custom/           管理员可选动态配置源，不提交 Git
policies/                 匿名读取及上传账号策略
examples/                 可选扩展，默认不加载
scripts/                  初始化、生成、预检查、审计、备份和 systemd 文件
docs/                    部署与维护文档
tests/                   临时环境测试
.github/                  CI、问题模板和 PR 模板
```

`compose.yaml`、模板和脚本是部署接口，保留路径以便博客和服务器命令继续使用。文档集中到 `docs/`。运行时 `.env`、secrets、数据和生成结果不属于源码；不要将其作为示例提交。

## .env 字段

既有字段全部必填；新增证书字段省略时兼容原来的单域名模式；完整语法与应用步骤见[配置说明](configuration.md)。

- `TRAEFIK_IMAGE`、`OTTERIO_IMAGE`、`GITEA_IMAGE`：经过核对的 `repository@sha256:` 加 64 位小写十六进制摘要。镜像标签仅用于选择版本和核对来源。
- `IMAGE_DOMAIN`、`DOWNLOAD_DOMAIN`、`S3_DOMAIN`、`GIT_DOMAIN`：四个不同的小写 DNS 主机名，不带协议、路径或端口。分别对应公开图片、下载、受限 S3 API 和 Git。
- `ACME_EMAIL`：ACME 账号邮箱。
- `TLS_MODE`：`http`、`alidns` 或 `cloudflare`。
- `TLS_CERT_MODE`：`hosts`（默认）、`wildcard`（兼容单泛域名配置）或 `custom`（显式域名列表）。
- `TLS_DOMAINS`：custom 模式必填，用英文逗号分隔普通域名和／或泛域名；包含泛域名时必须使用 DNS-01；已被泛域名覆盖的普通域名不再单独申请证书。其他模式留空。
- `WILDCARD_DOMAIN`：hosts 和 custom 模式留空；wildcard 模式填写 `*.实际根域`，必须使用 DNS-01，所有服务域名须被覆盖。
- `UPLOAD_CIDRS`：访问 S3 入口的客户端出口网段，逗号分隔，单 IPv4 用 `/32`，单 IPv6 用 `/128`。
- `ADMIN_CIDRS`：Git 初始化期间允许的管理来源，格式同上；不控制宿主机 SSH。
- `GIT_BOOTSTRAP`：首次安装用 `true`；安装锁和管理员验证完成后用 `false` 开放 Git 入口。
- `COMPOSE_FILE`：固定为 `compose.yaml:traefik/generated/compose.yaml`，避免遗漏证书模式覆盖文件。

`.env` 不接受变量展开或命令。示例域名、文档 IP 和 `/0` 来源会被拒绝。生成器不会判断镜像是否真实存在，也不会证明发布者身份；必须先核对镜像并记录来源。

## 文件和脚本职责

- `scripts/init-state.sh`：root 在服务器执行；要求 `/data` 已挂载、服务 UID/GID 空闲，准备目录、缺失的凭据、`.env` 与 ACME 文件。不启动容器，不覆盖已有凭据。
- `scripts/render-config.py`：从 `.env` 和模板生成三个文件；`--check` 只检查，不写入。Python 仅使用标准库。
- `scripts/preflight.sh`：检查挂载、运行身份、凭据和生成结果，校验合并后的 Compose；必须在应用配置前运行。
- `scripts/build-oc.sh`：管理电脑构建固定版本的 OC CLI 和本机 Web 界面，见 [OC 管理](oc.md)。
- `scripts/audit.sh`：检查运行中的容器权限、挂载、监听和资源，用 `sudo` 在服务器运行。
- `scripts/backup.sh`：停两个后端进行 restic 一致性备份；`--recover` 用于未完成恢复标记。详见[备份说明](backup.md)。
- `scripts/docker-data.conf`：整个 Docker daemon 的 `/data` 挂载依赖与启动检查。
- `scripts/file-code-stack-backup.service`、`.timer`：备份任务与调度，首次成功备份后再安装。

Traefik 生成输出为 `traefik.yaml`、`dynamic/routes.yaml`、`compose.yaml`。每个文件单独原子替换，整个配置集合不是一次事务，也不自动备份旧配置。生成器不清理额外动态文件，预检查不校验这些文件；自定义文件由管理员单独备份、审阅和验证。

## 策略文件

- `policies/public-images.json`、`public-downloads.json`：对应桶的匿名 `GetObject`，不授予列桶、写入或删除。
- `policies/uploader.json`、`download-uploader.json`：对应上传账号的对象读写，不是匿名桶策略。

实际桶名变更时同时调整策略 Resource、Traefik 路由与客户端；不能只改域名。分片上传需要按客户端实际 API 额外授权和验证。
