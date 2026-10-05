# 安全问题与部署边界

本仓库维护单机部署模板。应用和 Docker Engine 的漏洞以各上游公告为准；镜像使用固定摘要，管理员负责核对和安排升级。仓库尚未声明多个长期支持分支，修复优先针对 `main`，请记录部署提交。

## 报告问题

如果 GitHub 的 Security 页面提供 “Report a vulnerability”，使用私密报告；否则先创建不包含漏洞利用细节或秘密的 Issue，请求私密联系渠道。不要公开上传 `.env`、secrets、ACME JSON、备份环境、访问 Token 或未脱敏日志。项目没有承诺响应时限。

普通配置或功能问题使用 Issue，并提供系统、架构、部署提交、镜像版本、失败步骤和脱敏输出。已泄露的凭据先在对应服务撤销或轮换，删除 Git 文件不会清除历史。

## 权限与限制

`deploy` 的免密 sudo 和 Docker daemon 管理权限可取得 root 控制能力。非 root 容器、capability 移除和分离网络降低误用范围，不提供管理员之间的隔离。root 和 Docker 管理员可读取文件 secrets；Compose secrets 不是加密保管服务。

默认仅开放 Web 端口，管理端口绑定本机，S3 入口限制来源，Git 初始化限制管理 IP。云防火墙、IPv6、Docker 转发规则与实际端口仍需外部验收。IP 白名单不能代替 S3 签名和账号策略。

数据盘绑定挂载仍共享系统盘故障风险。单机没有冗余或自动故障切换，备份需要独立存储与实际恢复演练。Gitea 保留可写根层；检查和限制范围见[架构说明](docs/architecture.md)、[上线验收](docs/validation.md)和[恢复操作](docs/upgrade.md)。
