# Aliyun DNS-01 凭据与授权准备

如果域名的权威 DNS 使用阿里云云解析，可以通过 AliDNS 完成 DNS-01 验证。Traefik 会调用阿里云 API 创建临时 TXT 记录，完成域名验证后清理记录。这个过程不依赖公网 HTTP 验证入口，图片和下载域名已经接入 CDN 时也可以使用。

这里看的是域名的权威 DNS，而不是注册商或服务器所在的云平台。域名在阿里云注册，但 DNS 已经迁移到 Cloudflare 时，应使用 [Cloudflare 方案](cloudflare.md)。

在阿里云 RAM 控制台创建独立用户，为它创建 AccessKey，不使用云账号主密钥。创建自定义权限策略，将下面的 `阿里云账号ID` 和 `example.com` 换成实际值，再将策略授权给这个用户：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "alidns:DescribeDomains"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "alidns:DescribeDomainRecords",
        "alidns:AddDomainRecord",
        "alidns:DeleteDomainRecord"
      ],
      "Resource": [
        "acs:alidns:*:阿里云账号ID:domain/example.com"
      ]
    }
  ]
}
```

`DescribeDomains` 用于查询域名列表，需要全局资源授权；解析记录的操作限定到实际使用的 DNS 域。四个服务域名都属于 `example.com` 时，授权这个 DNS 域即可，不分别填写 `img.example.com`、`s3.example.com` 等主机名。使用多个 DNS 域时，在 `Resource` 中逐个添加对应资源。独立托管的子域按实际 DNS 域填写，具体规则可以参考[阿里云自定义权限策略说明](https://help.aliyun.com/zh/dns/alibaba-cloud-dns-custom-permission-policy-reference-dns)。

先按[部署与运维实践](deployment.md#挂载检查与初始化)完成初始化，创建 root 私有的 `secrets` 目录。下面以 root 权限打开 Vim，分别保存 AccessKey ID 和 AccessKey Secret，同时关闭交换文件、编辑历史和备份文件，减少额外副本：

```bash
cd /app/file-code-stack

sudo env EDITOR=vim VISUAL=vim vim -n -i NONE \
  -c 'set nobackup nowritebackup' secrets/alidns_access_key

sudo env EDITOR=vim VISUAL=vim vim -n -i NONE \
  -c 'set nobackup nowritebackup' secrets/alidns_secret_key
```

`alidns_access_key` 只写 AccessKey ID，`alidns_secret_key` 只写对应的 AccessKey Secret；不写变量名、引号或 `export`。分别保存退出后，设置归属和权限：

```bash
(
set -euo pipefail
cd /app/file-code-stack

sudo chown 20003:20003 \
  secrets/alidns_access_key secrets/alidns_secret_key
sudo chmod 0400 \
  secrets/alidns_access_key secrets/alidns_secret_key
sudo stat -c '%u:%g %a %n' \
  secrets/alidns_access_key secrets/alidns_secret_key
)
```

两个文件的检查结果都应为 `20003:20003`、400。不在终端打印密钥，也不提交 Git。

凭据准备完成后，按[配置说明](configuration.md#生成与应用)设置 `TLS_MODE=alidns`、生成、预检查并应用配置。生成器通过 `ALICLOUD_ACCESS_KEY_FILE`、`ALICLOUD_SECRET_KEY_FILE` 读取两个 secrets；不手动改生成文件。变量说明见 [lego AliDNS provider](https://go-acme.github.io/lego/dns/alidns/)。

首次部署时，S3 和 Git 域名先直接解析到服务器，便于验证来源 IP 限制。图片及下载域名可以在服务验证完成后接入 CDN；DNS-01 不要求将业务域名临时改回源站，但服务访问仍需要正确的 DNS 和回源配置。

两个密钥文件需要持续保留，供 Traefik 自动续期使用。证书和 ACME 账号保存在 `/data/traefik/acme/acme.json`，切换验证方式时不删除这个文件。DNS-01 不需要开放公网 HTTP 验证入口，但本项目仍保留 TCP 80，用于将普通 HTTP 请求跳转到 HTTPS。

申请失败时，先查看 Traefik 日志。权限错误检查 RAM 策略和资源范围；找不到 DNS 域时检查权威 DNS、所属账号及域名列表查询权限；TXT 验证超时则检查记录是否写入正确的 DNS 域，以及公网解析是否已生效，不通过关闭验证绕过问题。
