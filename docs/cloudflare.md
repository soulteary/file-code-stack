# Cloudflare DNS-01 凭据准备

域名的权威 DNS 使用 Cloudflare 时，创建 API Token，授权 Zone / DNS / Edit 和 Zone / Zone / Read，并将 Zone Resources 限定到实际域名。不要使用 Global API Key。参见 [lego Cloudflare provider](https://go-acme.github.io/lego/dns/cloudflare/)。

Token 同时包含两项权限时，只需一个秘密文件。secrets 目录为 root 私有，使用 root 权限启动 Vim：

```bash
cd /app/file-code-stack
sudo env EDITOR=vim VISUAL=vim vim -n -i NONE \
  -c 'set nobackup nowritebackup' secrets/cloudflare_dns_api_token
sudo chown 20003:20003 secrets/cloudflare_dns_api_token
sudo chmod 0400 secrets/cloudflare_dns_api_token
```

文件只存 Token 内容，不写变量名、引号或 export，不提交 Git。修改 .env 为 TLS_MODE=cloudflare，按 [配置说明](configuration.md#生成与应用) 重新生成、预检查、up -d 并重启 Traefik。生成器设置 provider=cloudflare 和 CF_DNS_API_TOKEN_FILE，不需要手动编辑生成文件。

DNS-01 不要求开启 Cloudflare 代理。初次部署 S3/Git 使用 DNS only，避免代理影响来源 IP 限制和协议请求。证书及 ACME 账号仍保存在 /data/traefik/acme/acme.json。
