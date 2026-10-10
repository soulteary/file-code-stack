# 部署参数、HTTPS 与服务启动

本页是部署参数、生成、预检查、启动和 Git 初始化开关的统一操作入口。需要 Python 3（仅标准库）和 Docker Compose，不安装额外模板工具。

字段格式和目录职责见[配置参考](reference.md)。

## 配置来源

- `.env`：镜像 digest、四个域名、邮箱、证书模式、IP 白名单和 Git 初始化开关。
- `traefik/templates/static.json`：入口、日志、TLS 默认值及健康检查。
- `traefik/templates/routes.json`：应用路由、后端与访问限制。
- `secrets/`：对象存储和可选 DNS provider 凭据，不写入 `.env`。

`.env` 支持空行、整行注释与可选单/双引号。值必须为字面量，不使用变量展开、转义、行尾注释或 shell 命令。域名使用小写，四个域名不同；CIDR 用逗号分隔，单 IP 使用 `/32` 或 `/128`。生成器拒绝示例域名、文档 IP、全网 IP 白名单与未固定镜像。

`TLS_MODE=http` 生成 HTTP-01，`TLS_MODE=alidns` 生成 DNS-01（先完成 [AliDNS 凭据准备](alidns.md)），`TLS_MODE=cloudflare` 使用 Cloudflare DNS-01（先完成 [Cloudflare 凭据准备](cloudflare.md)）；保持以下固定值，使所有运维命令使用同一组合：

```text
COMPOSE_FILE=compose.yaml:traefik/generated/compose.yaml
```

生成的 Compose 覆盖文件仅负责所选 DNS provider 的环境变量与 secrets 挂载。根据 [Traefik 配置方式说明](https://doc.traefik.io/traefik/reference/install-configuration/boot-environment/)，静态配置应只采用一种加载方式。本项目 Traefik 的静态配置全部来自生成的 `/etc/traefik/traefik.yaml`，没有 CLI 或 TRAEFIK_* 参数覆盖。不要另加这些参数，也不要通过 shell 环境覆盖 `.env`。

HTTPS 入口统一设置默认 resolver，路由不重复声明 `tls`；即便空 `tls: {}` 也会覆盖入口默认值，详见 [入口 TLS 配置](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/)。自定义路由若明确指定 TLS，需同时明确所需 resolver。

## 单域名与泛域名证书

默认 `TLS_CERT_MODE=hosts`、`WILDCARD_DOMAIN=`，Traefik 按四条 `Host()` 路由申请域名证书。HTTP-01 和两种 DNS-01 均可使用。

申请 `*.example.ltd` 形式的泛域名证书时，替换为自己控制的域名，并设置：

```text
TLS_MODE=cloudflare
TLS_CERT_MODE=wildcard
WILDCARD_DOMAIN=*.example.ltd
IMAGE_DOMAIN=img.example.ltd
DOWNLOAD_DOMAIN=files.example.ltd
S3_DOMAIN=s3.example.ltd
GIT_DOMAIN=git.example.ltd
```

也可使用 `TLS_MODE=alidns`。泛域名只支持 DNS-01，生成器拒绝 HTTP-01、非法域名和不受证书覆盖的服务域名。证书同时包含根域和 `*.根域`，仅覆盖一级子域，不覆盖 `a.b.example.ltd`。四个服务仍必须使用不同的准确域名。

生成器设置入口 `http.tls.domains` 的 `main` 和 `sans`，保留 `certResolver=le`；所有路由继承此 TLS 设置。匹配规则仍是准确的 `Host()`，不会把任意子域送往 S3 或 Git，也不使用 ``Host(`*.example.ltd`)``。证书覆盖范围与业务路由是两个设置。详见 [Traefik ACME 泛域名说明](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/#wildcard-domains)。

变更后按下方生成、预检查、应用并重启 Traefik。DNS 凭据需允许操作根域 `_acme-challenge` TXT；验收四个域名的实际证书 SAN、续期和路由，未知子域不应匹配业务路由。

### 多个普通域名、多个泛域名与混合配置

使用 `TLS_CERT_MODE=custom`，将需要申请证书的名字放进 `TLS_DOMAINS`，用英文逗号分隔。单个普通域名、多个普通域名、多个泛域名和混合列表使用同一个字段：

```text
TLS_MODE=cloudflare
TLS_CERT_MODE=custom
WILDCARD_DOMAIN=
TLS_DOMAINS=*.example.ltd,*.console.example.ltd,files.other.ltd
IMAGE_DOMAIN=img.example.ltd
DOWNLOAD_DOMAIN=files.other.ltd
S3_DOMAIN=s3.example.ltd
GIT_DOMAIN=git.console.example.ltd
```

这是示例，替换为实际域名。只申请普通域名时，例如：

```text
TLS_MODE=http
TLS_CERT_MODE=custom
WILDCARD_DOMAIN=
TLS_DOMAINS=img.example.ltd,files.example.ltd,s3.example.ltd,git.example.ltd
```

只申请多个泛域名时，例如：

```text
TLS_MODE=alidns
TLS_CERT_MODE=custom
WILDCARD_DOMAIN=
TLS_DOMAINS=*.example.ltd,*.console.example.ltd
```

普通域名可使用任一种验证方式；列表中包含任何泛域名，就必须使用 DNS-01。`custom` 模式不再填写旧字段 `WILDCARD_DOMAIN`。原来的 `hosts` 和 `wildcard` 模式保持兼容，省略新增字段时沿用原行为。

生成器先省略已被列表中泛域名覆盖的普通域名，再将剩余普通域名写成独立的 `http.tls.domains` 条目；每个泛域名使用根域作为 `main`、泛域名作为 `sans`。例如上面的混合列表会生成：

```yaml
http:
  tls:
    certResolver: le
    domains:
      - main: example.ltd
        sans: ["*.example.ltd"]
      - main: console.example.ltd
        sans: ["*.console.example.ltd"]
      - main: files.other.ltd
```

这是 `entryPoints.websecure` 下的配置片段，实际文件由生成器写入，不手动另加。每个条目分别申请证书；如果普通域名与某个泛域名的根域相同，它们合并到一个条目。例如 `*.example.ltd,img.example.ltd,*.console.example.ltd,git.console.example.ltd` 只生成两个泛域名证书条目，不再单独申请 `img.example.ltd` 或 `git.console.example.ltd`，与列表顺序无关。根域仍作为泛域名证书的 `main` 保留；更深层的普通域名若没有对应泛域名覆盖，则继续单独申请。重复名字、空列表项、非法域名和未覆盖的服务域名会被拒绝。

`*.example.ltd` 覆盖 `console.example.ltd`，但不覆盖 `git.console.example.ltd`；后者需要 `*.console.example.ltd` 或准确域名。生成的每个泛域名证书还包括自己的根域。配置额外的证书域名不会创建新的业务路由，也不会创建 DNS A/AAAA 记录；新增服务仍需单独配置准确的路由。

当前配置只选择一个 DNS provider。多个根域需要由所选 provider 和凭据实际管理：Cloudflare Token 覆盖对应 Zone，AliDNS RAM 策略覆盖对应 DNS 域。如果域名分属不同 DNS provider，需要另行配置多个 resolver 和对应的路由 TLS 设置，不能只在列表中追加名字。

修改后执行生成、预检查、应用配置并重启 Traefik。检查每个域名的实际证书和后端路由；配置校验不验证 DNS 管理权限，也不保证 CA 已签发证书。

## 服务 UID/GID

本项目固定 Gitea=20001:20001、OtterIO=20002:20002、Traefik=20003:20003。这些数字用于容器和挂载目录，不创建同号宿主机账号。宿主机 ubuntu=1000、lighthouse=1001 和 deploy=1002 可以保持不变。init-state 和 preflight 在写入前检查这些 UID/GID 是否被宿主机账号占用；不要把预留范围用于新登录账号。

Gitea rootless 支持 [自定义用户](https://docs.gitea.com/installation/install-with-docker-rootless/#custom-user)，Compose 的 user、数据目录及 tmpfs 采用相同数字。实际部署仍需用选定的镜像 digest 验证启动和 Git 读写。

## 镜像固定

OtterIO 示例固定为 `ghcr.io/soulteary/otterio:RELEASE.2026-10-09T15-22-07Z`，标签采用 UTC，对应北京时间十月九日 23:22:07。先拉取并记录 RepoDigests：

```bash
sudo docker pull ghcr.io/soulteary/otterio:RELEASE.2026-10-09T15-22-07Z
sudo docker image inspect ghcr.io/soulteary/otterio:RELEASE.2026-10-09T15-22-07Z --format '{{json .RepoDigests}}'
```

从 [OtterIO Release 页面](https://github.com/soulteary/otterio/releases/tag/RELEASE.2026-10-09T15-22-07Z)下载 `release-manifest.json`，核对版本、仓库和摘要。`RepoDigests` 与 IMAGE ID 不同，多平台索引与平台镜像摘要也不同；比较前确认对应对象，并记录实际运行架构。清单记录镜像身份，本身不等于签名或可复现构建证明。

Traefik 选择受支持、经过验证的 v3 正式版，Gitea 使用官方 `ghcr.io/go-gitea/gitea:28.1.0-rootless` 正式版，用同样方式记录摘要；不要把普通 Gitea 镜像的挂载布局用于 rootless 镜像。模板未预填 Traefik/Gitea 的生产镜像，也不声称任意版本均已验收。保存实际版本标签、架构、完整 RepoDigest 和检查日期；不要只记录 `v3` 或 `latest`。

Gitea 同样先拉取固定版本，再记录摘要：

```bash
sudo docker pull ghcr.io/go-gitea/gitea:28.1.0-rootless
sudo docker image inspect ghcr.io/go-gitea/gitea:28.1.0-rootless --format '{{json .RepoDigests}}'
```

OtterIO 的凭据和存储检查继续适用，新版本修复及升级验证范围见[升级说明](upgrade.md#存储检查与后续升级)；Gitea 的相关修复见[初始化说明](gitea.md)。

三份镜像在 `.env` 中都使用 `repository@sha256:完整64位摘要`，不使用 latest。

digest 只固定内容，不单独证明可信。保留来源、版本、digest 和变更摘要；发布者提供签名或证明材料时，按其公开方法验证。升级前保留旧摘要并完成一致性备份。

## 证书验证方式

`TLS_MODE=http` 使用 HTTP-01：四个域名应解析到服务器，TCP 80 可达；CDN 若未正确转发 ACME 校验路径，改用 DNS-01。`TLS_MODE=alidns` 或 `cloudflare` 使用域名权威 DNS 对应的 provider，不根据服务器厂商或域名注册商选择。业务流量始终使用 HTTPS。

DNS-01 先按 [AliDNS](alidns.md)或 [Cloudflare](cloudflare.md)准备秘密文件，再填写 `TLS_MODE`。凭据要保留供续期使用。S3/Git 初次部署直接解析到源站；接入代理前验证实际来源 IP 和信任链。

## 生成与应用

```bash
(
set -euo pipefail
cd /app/file-code-stack
SUDO_EDITOR=vim sudoedit .env
sudo python3 scripts/render-config.py
sudo scripts/preflight.sh
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
)
```

生成器先校验全部输入，并确认没有残留 ${...} 占位符，再对每个输出文件原子替换。S3_DOMAIN 等包含数字的变量名也会完整替换。输出采用 JSON 格式（合法 YAML），目录位于 `traefik/generated/`，不提交 Git。不要手动编辑生成结果；修改路由结构时编辑模板，部署参数修改 `.env`。

动态路由由 file provider 监听，生成后可以热更新。静态配置、邮箱和证书模式变化需要重启 Traefik；`docker compose up -d` 不一定因挂载文件内容变化而重建容器，执行：

```bash
sudo docker compose restart traefik
```

切换 `TLS_MODE` 时先准备对应秘密文件，再生成、预检查和 `up -d`，使 secrets 挂载变化生效，然后重启入口。证书模式切换不删除既有 `acme.json`；变更应安排维护窗口。

`sudo python3 scripts/render-config.py --check` 只验证当前输出是否与参数和模板一致，不写文件。preflight 会调用它，再检查密码文件 UID/权限、合并后镜像/域名/证书挂载；配置缺失或过期时停止。

## Gitea 安装完成后

确认 `INSTALL_LOCK=true`、注册关闭、管理员账户和恢复码就绪后，将 `.env` 中 `GIT_BOOTSTRAP=false`，重新生成并预检查：

```bash
(
set -euo pipefail
cd /app/file-code-stack
SUDO_EDITOR=vim sudoedit .env
sudo python3 scripts/render-config.py
sudo scripts/preflight.sh
)
```

动态路由会自动加载；检查 Git 域名的匿名浏览与 clone 后再结束维护。此开关仅去掉 Git 路由的初始化 IP middleware，上传 IP 限制和公共桶路由不变；可随时改回 true 收紧入口。

模板关闭 push 自动建仓；先在 Gitea 创建同名私有仓库，再推送本地历史。已有本地仓库时，不初始化远端 README、许可证或 `.gitignore`。匿名 clone 要在无凭据环境验收，换目录不会清除全局凭据。

## 健康检查与验证

Traefik 使用自带 `healthcheck` 命令，ping 仅监听容器内 `127.0.0.1:8082`，不公开端口、不启用 Dashboard。它检查进程存活，不代表后端、域名或证书正常；unhealthy 不会自行触发 `unless-stopped` 重启。

服务启动后继续[对象存储初始化](storage.md)、[Gitea 初始化](gitea.md)与[上线验收](validation.md)。开发检查统一见[贡献指南](../CONTRIBUTING.md)，脚本测试不能代替业务验证。
