# 文档目录

## 首次部署顺序

1. [服务架构与权限边界](architecture.md)：域名、端口、网络、运行身份与存储规划。
2. [Ubuntu 主机准备](deployment.md)：运维账号、SSH、防火墙、上传配置、数据挂载和初始化。
3. [Docker 安装](docker-install.md)：官方、阿里云、腾讯云软件源与检查。
4. [配置与启动](configuration.md)：镜像、参数、证书模式、生成、预检查和 Git 初始化开关。
5. [对象存储](storage.md)：凭据、桶、匿名策略、上传账号、下载与私有存储。
6. [Gitea](gitea.md)：首次安装、Token、代码发布与访问验证。
7. [备份](backup.md)、[恢复与升级](upgrade.md)、[上线验收](validation.md)。

主机准备文档会在安装 Docker 时引导到对应页面，安装后返回主机文档继续数据挂载。每页顶部说明前置条件，命令块注明执行位置；所有服务命令均在服务器的项目目录运行。

## 按任务查找

- 管理 S3 存储：[OC 本机管理界面](oc.md)。
- 申请 DNS-01 证书：[AliDNS](alidns.md)、[Cloudflare](cloudflare.md)。配置应用步骤统一见[配置说明](configuration.md#生成与应用)。
- 接入 CDN 或检查缓存：[CDN](cdn.md)。
- 检查资源、日志和容器权限：[运维](operations.md)。
- 处理证书失败、403、502、权限或 Git 认证问题：[故障排查](troubleshooting.md)。
- 查找参数或脚本职责：[配置字段与仓库结构](reference.md)。
- 修改模板、添加测试或提 PR：[贡献指南](../CONTRIBUTING.md)。

## 维护约定

仓库文档是操作说明，博客是完整讲解；不在仓库保留另一份完整博客副本。配置操作只维护在 `configuration.md`，DNS 凭据分别维护在 provider 页面，备份步骤只维护在 `backup.md`。新增内容优先补到已有任务页。

结构参考 [Diátaxis](https://diataxis.fr/) 对教程、操作、参考和解释的区分；简短 README、贡献入口与文档目录参考 [Traefik](https://github.com/traefik/traefik)，部署示例与测试说明参考 [Awesome Compose](https://github.com/docker/awesome-compose)。参数集中方式参考 [traefik-v3-example](https://github.com/soulteary/traefik-v3-example)，保留本项目的文件路由与安全默认值。

历史文章：[Docker 安装](https://soulteary.com/2026/10/06/install-docker-on-ubuntu-26-04-with-aliyun-and-tencent-cloud-mirrors-and-basic-security.html)、[OtterIO 维护](https://soulteary.com/2026/10/05/continuing-minio-otterio-early-october-maintenance-notes.html)、[Traefik 入门](https://soulteary.com/2024/08/04/best-practices-for-traefik-3-in-docker-getting-started-quickly.html)、[Gitea 部署](https://soulteary.com/2025/03/26/gitea-git-server-with-docker-and-traefik-v3.html)。部署时以仓库选定提交的模板和组件固定版本为准。
