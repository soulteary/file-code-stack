# 故障排查

从实际响应和日志定位问题。分享输出前移除凭据、Token、签名 URL 和私钥。

## 遇到问题先看日志

先查看容器和系统日志：

```bash
cd /app/file-code-stack

sudo docker compose ps
sudo docker compose logs --tail 100
sudo journalctl -u docker --since '30 minutes ago' --no-pager
sudo journalctl -k --since '30 minutes ago' --no-pager
```

按具体错误继续排查：

| 问题                    | 优先检查                                    |
| --------------------- | --------------------------------------- |
| 403                   | 路由 IP 白名单、上传账号策略、签名 Host/时钟             |
| SignatureDoesNotMatch | 公共域名签名、路径/查询是否被改写、SDK path-style        |
| 502                   | 后端是否启动、网络名、服务 URL、内存 OOM                |
| HTTP-01 证书失败 | A/AAAA、80 入站、CDN 验证路径转发、ACME 文件权限 |
| Cloudflare DNS-01 失败 | 权威 DNS、Token 的 Zone 范围和 DNS/Edit、Zone/Read 权限、秘密文件读取、TXT 传播、API 日志 |
| AliDNS DNS-01 失败 | 权威 DNS、RAM 授权、秘密文件读取、TXT 传播、API 日志 |
| Permission denied     | 对应 UID、secret 0400、目录可写位置、AppArmor 日志   |
| Gitea 启动失败            | 是否 rootless 变体、20001 UID、config/data 布局 |
| Git push 认证失败         | 使用权限正确的 token，非账号密码；仓库已创建               |
| 公网后端端口意外可达            | Docker 实际 PortBindings、云防火墙 IPv4/IPv6   |

替换配置时保留原有归属和权限，避免文件已经存在，容器却无法读取。

需要查看 `docker inspect` 时，只输出排查所需的字段，避免将完整环境和秘密信息复制到日志或工单。先根据具体错误处理，不把 `privileged`、`unconfined` 或 `chmod 777` 当作通用修复。

## DNS-01 账号有效，但没有证书

`acme.json` 中 ACME Account 的 `status=valid` 表示账号注册成功，不代表域名验证或证书签发成功。账号 PrivateKey 与 Certificates 内的证书私钥用途不同。不要删除 ACME 文件重新注册，也不要将其内容贴到 Issue。

先看 Traefik 日志中的域名、provider、API 操作和错误码，确认配置模式、域名和秘密文件与当前参数一致。`Certificates` 缺失或为空时继续检查签发错误；文件存在不等于签发成功。

Cloudflare 的 `403 / 10000 Authentication error` 优先检查 Token 内容、有效期、Zone 范围、DNS/Edit 和 Zone/Read，以及 Token 来源 IP 条件是否允许服务器实际出口。AliDNS 的 `Forbidden.RAM` 或 `ImplicitDeny` 检查实际 AccessKey 对应用户、策略默认版本、域名所属账号与资源组授权范围；等待 TXT 传播不能修复 API 权限拒绝。创建 TXT 失败后的清理报错通常是后续结果，先处理首次失败。

TXT 创建成功后才排查权威 DNS、委派、记录名称、传播及验证超时。配置方式与权限准备见 [AliDNS](alidns.md)、[Cloudflare](cloudflare.md)及[证书模式](configuration.md#证书验证方式)。

## 更新秘密文件后仍使用旧凭据

编辑器可能通过替换文件更新内容，现有文件挂载仍指向旧 inode。更新凭据后安排入口维护窗口，按[配置说明](configuration.md#生成与应用)重新生成和预检查，再重建 Traefik：

```bash
(
set -euo pipefail
cd /app/file-code-stack
sudo python3 scripts/render-config.py
sudo scripts/preflight.sh
sudo docker compose up -d --force-recreate traefik
sudo docker compose logs --since 5m traefik
)
```

不要删除 `acme.json`。普通静态配置重载与秘密文件挂载更新不同，单纯 restart 不能作为文件替换后更新挂载的保证。

## 图片跳转或匿名访问失败

默认图片 URL 为 `/images/对象键`。短地址需要内部改写，不能用 301/302 跳转代替；见[可选短地址](storage.md#可选图片短地址)。先用不带 `-L` 的请求查看第一次响应：

```bash
curl -sS -D - -o /dev/null 'https://图片域名/images/实际对象键'
```

直连服务器上 `http://127.0.0.1:19000/images/实际对象键` 对比。后端返回图片而公网跳转时，检查 CDN 或入口代理规则和已缓存的跳转；后端返回 403 时检查桶策略、对象位置和签名。不要仅删除 Location 头，它不会将跳转响应变成图片。
