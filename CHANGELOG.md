# 变更记录

记录部署模板、脚本和文档的变化，不复制各组件完整发布日志。项目正在准备首次发布，以下为未发布内容。

## Unreleased

- OtterIO 更新到 `RELEASE.2026-10-09T15-22-07Z`；管理使用 `RELEASE.2026-10-09T14-38-15Z` 的 OC CLI 和源码构建的本机界面，关闭旧浏览器。
- 新增固定源码构建脚本、OC 管理步骤，以及可选择的 DNS-01 泛域名证书，校验服务域名覆盖范围。

- 文档按主机、配置、存储、Git、CDN、运维、备份、升级与验收拆分，重复命令集中到各任务页面。
- 新增字段与脚本参考、贡献指南、安全说明、Issue/PR 模板和自动检查。
- OtterIO 示例使用 `RELEASE.2026-10-09T15-22-07Z`，Gitea 使用 `28.1.0-rootless`，部署继续要求完整镜像摘要。
- 支持 HTTP-01、AliDNS、Cloudflare DNS-01 的生成和预检查，使用 file provider，不挂载 Docker socket。
- 服务预留 UID/GID：Gitea 20001、OtterIO 20002、Traefik 20003；初始化检查宿主机编号冲突。
- 备份采用停止后端的 restic 一致性备份，记录中断标记并提供显式恢复。

文档入口从根目录的长篇 `实践文档.md` 调整为 [docs/README.md](docs/README.md)。Compose、模板、策略及运维脚本路径保持不变；这项文档调整不要求迁移服务数据。
