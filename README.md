# file-code-stack

用 Docker Compose 在 Ubuntu 云服务器部署文件存储、公开下载与代码托管：Traefik 提供 HTTPS，OtterIO 提供 S3 兼容存储，Gitea 提供 Git 服务。

默认公开 80/443，后台端口绑定本机；应用使用非 root UID，Traefik 使用文件路由，不挂载 Docker socket。配置放在 `/app/file-code-stack`，数据放在 `/data` 挂载点，支持 HTTP-01、AliDNS 和 Cloudflare DNS-01。

## 首次部署

1. 阅读[架构与边界](docs/architecture.md)，按[主机准备](docs/deployment.md)配置账号、SSH、防火墙、Docker 和数据挂载。
2. 按[配置与启动](docs/configuration.md)固定镜像摘要、填写域名与来源 IP、准备证书凭据，生成并预检查后启动。
3. 配置[存储策略](docs/storage.md)和 [Gitea](docs/gitea.md)，完成[异地备份](docs/backup.md)、[恢复演练](docs/upgrade.md)及[上线验收](docs/validation.md)。

从未初始化的配置开始。目标目录已有文件时先核对，不覆盖 `.env`、secrets 或数据。不要在管理电脑执行服务器初始化与备份命令。

## 文档与维护

完整导航见[文档目录](docs/README.md)。日常操作见[运维](docs/operations.md)，异常处理见[排错](docs/troubleshooting.md)，开发与检查见[贡献指南](CONTRIBUTING.md)。

这是单机部署模板，不提供高可用或自动故障切换。测试使用临时配置；真实镜像启动、证书签发与恢复能力需要在目标环境验证。[版本记录](CHANGELOG.md)记录模板变化，组件各自遵循其上游许可证；本仓库采用 [Apache-2.0](LICENSE)。
