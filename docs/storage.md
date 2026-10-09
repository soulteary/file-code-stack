# 对象存储初始化与访问策略

先完成[主机初始化](deployment.md)和[配置与启动](configuration.md)。

### 从秘密文件加载凭据

[主机初始化](deployment.md#挂载检查与初始化)中的 `init-state.sh` 已经创建两个凭据文件：

- `secrets/root_user`：默认管理员名为 `file-code-root`。
- `secrets/root_password`：使用 `openssl rand -hex 32` 生成随机密码。

重复执行初始化不会覆盖已有凭据。先检查文件和数据目录的归属、权限：

```bash
cd /app/file-code-stack

sudo stat -c '%u:%g %a %n' \
  secrets/root_user \
  secrets/root_password \
  /data/otterio
```

两个凭据文件都应为 `20002:20002`、0400，数据目录应为 `20002:20002`、0750。

默认管理员名可以直接使用。如果希望更换，在首次启动前执行下面的命令，将示例名称替换为自己的名称：

```bash
(
set -euo pipefail

printf '%s\n' 'your-admin-name' |
  sudo tee /app/file-code-stack/secrets/root_user >/dev/null

sudo chown 20002:20002 /app/file-code-stack/secrets/root_user
sudo chmod 0400 /app/file-code-stack/secrets/root_user
)
```

在安全终端查看凭据，并保存到密码管理器：

```bash
sudo cat /app/file-code-stack/secrets/root_user
sudo cat /app/file-code-stack/secrets/root_password
```

秘密文件不提交 Git，也不复制到聊天、日志或工单。服务启动后遇到问题，先检查日志、配置和文件权限，不通过重新生成密码尝试修复。需要修改管理员凭据时，单独安排变更，并更新使用该凭据的客户端。

仓库通过 `.env` 中的 `OTTERIO_IMAGE` 固定镜像，通过 `/data/otterio` 保存数据，通过 Compose secrets 挂载凭据，无需在 shell 中 export 管理员密码。

OtterIO 使用镜像自带的入口脚本加载用户名和密码。下面是仓库中已有的配置片段，用于说明读取方式，不需要另外创建一份 Compose 文件：

```yaml
command: [server, --address, ':9000', --console-address, ':9001', /data]
environment:
  HOME: /tmp
  OTTERIO_BROWSER: "off"
  OTTERIO_REGION_NAME: us-east-1
  OTTERIO_ROOT_USER_FILE: /run/secrets/root_user
  OTTERIO_ROOT_PASSWORD_FILE: /run/secrets/root_password
  OTTERIO_ACCESS_KEY_FILE: ''
  OTTERIO_SECRET_KEY_FILE: ''
secrets: [root_user, root_password]
```

两个 `_FILE` 变量指向容器内的绝对路径，Compose 将宿主机上的凭据文件挂载到对应位置。保留镜像原有的 `entrypoint`，不绕过它的凭据检查。

这个版本要求显式配置非默认凭据。这里统一使用文件方式，不再为同一个设置提供非空环境变量，也不混用新旧两组凭据变量。文件必须可读、非空且为普通文件；镜像不会自动调整数据目录归属，启动前需要核对权限，具体要求见[版本发布说明](https://github.com/soulteary/otterio/releases/tag/RELEASE.2026-10-09T15-22-07Z)。

## 创建存储桶和上传账号

先在自己的电脑上建立 SSH 隧道。服务器地址和密钥路径按实际情况填写：

```bash
SERVER_IP=203.0.113.10
ADMIN_KEY="$HOME/.ssh/file-code-stack_ed25519"

ssh -N \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -i "$ADMIN_KEY" \
  -L 127.0.0.1:19001:127.0.0.1:19001 \
  -L 127.0.0.1:19000:127.0.0.1:19000 \
  "deploy@$SERVER_IP"
```

命令运行期间保留这个终端。19001 用于 OC 连接管理 API，19000 用于连接 S3 API；本地监听地址明确绑定为 `127.0.0.1`，不向管理电脑所在网络开放。

按 [OC 管理界面](oc.md)在管理电脑构建固定版本的 OC，设置 S3 与独立管理地址，启动 `oc-console --alias store --allow-writes`，浏览器打开它打印的本机 URL 并输入 login code。19001 只提供管理 API，OtterIO 自带界面已关闭。

在控制台完成下面几步：

1. 创建 `images` 桶，保持默认私有状态。
2. 创建图片上传专用账号，将[图片上传策略](../policies/uploader.json) 的完整 JSON 保存为它的权限策略；上传客户端只使用这个账号的访问键。
3. 确认桶内只有允许公开的图片，再将[图片公开策略](../policies/public-images.json) 的完整 JSON 保存为该桶的匿名读取策略。
4. 使用专用账号上传一个测试对象，再分别验证匿名读取成功、匿名写入和列桶失败，以及该账号不能访问其他桶。

策略文件随前面的配置目录一并下载。操作时区分用户或账号的权限策略与桶的匿名策略，不把两个 JSON 填到同一处。控制台的菜单和管理能力随版本变化；如果所选版本缺少创建账号或设置策略的入口，先补齐经过该版本验证的管理工具，再继续开放服务。

账号策略和桶策略用途不同：前者限制上传账号可以执行的操作，后者决定匿名访问是否允许。其他桶按用途单独配置，不一起公开。

仓库的公开策略只允许 `GetObject`，不允许匿名列桶、上传或删除。对象也可以通过 S3 域名读取，但这个入口仍受来源 IP 限制。

如果控制台不能导入所需策略，先确认所选管理工具与当前 OtterIO 版本兼容。S3 兼容并不代表管理 API 也兼容，不直接套用其他项目的账号管理命令。

程序连接时，endpoint 设置为 `https://s3.实际域名`，region 使用 `us-east-1`，启用 path-style。每个应用使用自己的账号，不把管理员密钥交给插件、网页或其他应用。

图片上传策略只授权 `images` 桶内的 `GetObject` 和 `PutObject`，不开放删除或列桶。需要分片上传时，再根据客户端调用的 API 补充权限，并在测试桶验证。

图片入口只允许 `/images/` 下的 GET、HEAD。例如，桶中的对象 key 为 `demo/example.png`，公开地址就是：

```text
https://图片域名/images/demo/example.png
```

先使用便于检查的文件名和目录结构完成上传、读取验证，再测试特殊字符、URL 编码及条件请求。不要通过改写上传请求路径来调整公开链接，以免影响 S3 签名。

### 提供公开文件下载

下载文件使用 `downloads` 桶，将[下载公开策略](../policies/public-downloads.json) 应用为桶策略，上传账号使用[下载上传策略](../policies/download-uploader.json)。

下载上传账号与图片上传账号分开，只授权各自桶内的对象读写，不开放删除或列桶。需要分片上传时，同样先在测试桶验证所需权限。

例如，一个发布包的公开地址是：

```text
https://files.实际域名/downloads/releases/demo/v1.0.0/demo-linux-amd64.tar.gz
```

下载路由只允许 `/downloads/` 下的 GET、HEAD，上传仍通过 S3 域名并使用签名认证。对象是否允许匿名读取，最终还取决于桶策略。

发布包按版本目录或内容哈希保存，不覆盖已经发布的对象。上传策略中的 `PutObject` 本身允许覆盖已有 key，因此这里还需要由发布流程保证文件名不重复。

每次发布同时提供 SHA-256 校验文件，重要软件再提供签名。校验和用于检查内容是否一致，不能单独证明发布者身份。私有文件不要临时放进公开桶。

上传时设置正确的 `Content-Type`。需要下载保存的压缩包和二进制文件，可以设置 `Content-Disposition: attachment`；图片保持正常展示，不给所有对象统一追加下载头。元数据通过 SDK 或兼容工具设置，上传后检查实际响应。

下载入口需要验证 GET、HEAD、Range 和 ETag 条件请求，并确认写请求被拒绝。下面使用一个大于 1,024 字节的测试文件，检查响应头并读取前 1,024 字节：

```bash
FILE_URL='https://files.实际域名/downloads/releases/demo/v1.0.0/demo-linux-amd64.tar.gz'

curl -fsSI "$FILE_URL"

curl -fsS \
  -D /tmp/file-range.headers \
  -H 'Range: bytes=0-1023' \
  "$FILE_URL" \
  -o /tmp/file-range.bin

cat /tmp/file-range.headers
wc -c /tmp/file-range.bin
```

Range 请求应返回 `206 Partial Content`，`Content-Range` 中的范围应为 `bytes 0-1023/文件总长度`，保存的内容应为 1,024 字节。只看到 curl 成功退出不够，还要核对这些结果。

再复制响应中的完整 ETag 值，包括双引号，测试条件请求：

```bash
ETAG='"替换为实际ETag值"'

curl -sS -D - -o /dev/null \
  -H "If-None-Match: $ETAG" \
  "$FILE_URL"
```

对象未变化时应返回 `304 Not Modified`。不要把 ETag 一律当成文件的 MD5 校验值，文件完整性仍使用发布时提供的 SHA-256 校验文件检查。

接入 CDN 后，再通过 CDN 域名重复这些测试，确认范围请求、条件请求和响应元数据仍然符合预期。

### 给程序接入私有存储

程序数据使用独立桶或明确的前缀，并创建独立账号。默认不设置匿名访问策略，读、写、删除权限按业务需要分别授权，不共用图片上传账号。

私有文件可以通过签名 S3 请求下载，也可以由应用检查用户权限后生成短期预签名链接。

不过，预签名链接不会绕过 Traefik 的来源 IP 限制。当前 S3 入口只允许配置中的客户端来源，因此普通读者不能直接使用这个入口的预签名链接。如果需要向读者提供私有下载，另行设计下载入口，并检查授权和缓存行为，避免私有响应被公开缓存。

## 通过 S3 API 应用匿名策略

桶策略可通过标准 S3 `PutBucketPolicy` 应用，不要求控制台具有导入菜单。下面是已安装 AWS CLI 时的可选操作，在部署服务器执行；`images` 桶应已创建，桶内内容已确认可以公开。

应用操作会替换现有 Bucket Policy，有需要保留的规则时先导出并合并。账号 IAM 策略仍使用与所选 OtterIO 版本兼容的管理接口，不能用 Bucket Policy 代替上传账号的权限配置。

```bash
sudo bash <<'S3POLICY'
set -euo pipefail
cd /app/file-code-stack
command -v aws >/dev/null
export AWS_ACCESS_KEY_ID="$(cat secrets/root_user)"
export AWS_SECRET_ACCESS_KEY="$(cat secrets/root_password)"
export AWS_DEFAULT_REGION=us-east-1
export AWS_EC2_METADATA_DISABLED=true
unset AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE

aws --endpoint-url http://127.0.0.1:19000 s3api put-bucket-policy \
  --bucket images --policy file://policies/public-images.json
aws --endpoint-url http://127.0.0.1:19000 s3api get-bucket-policy \
  --bucket images
S3POLICY
```

凭据只在这个子进程中加载，不写入命令参数或 Git；不要启用 shell tracing。下载桶使用 `downloads` 与 `policies/public-downloads.json`。完成后不带凭据请求已存在的测试对象，应返回 200；匿名列桶应拒绝。实际工具兼容性和业务请求仍需验证。

## 可选图片短地址

默认 URL 保留 `/images/`。需要 `https://图片域名/2023/05/20/example.jpg` 时，可以使用[可选动态路由示例](../examples/traefik/image-short-url.yaml.example)，内部给日期路径加上 `/images`；浏览器地址保持原样。

先复制示例到自己的受控配置位置，将 `img.example.com` 改为 `.env` 的实际图片域名，保留只允许 GET/HEAD 的条件；再安装到 file provider 监听目录。下面在服务器执行，要求已有配置生成结果：

```bash
(
set -euo pipefail
cd /app/file-code-stack
sudo install -d -o root -g root -m 0750 traefik/custom
sudo test ! -e traefik/custom/image-short-url.yaml
sudo install -o root -g root -m 0644 \
  examples/traefik/image-short-url.yaml.example \
  traefik/custom/image-short-url.yaml
sudo env EDITOR=vim VISUAL=vim vim -n -i NONE \
  -c 'set nobackup nowritebackup' traefik/custom/image-short-url.yaml
sudo install -o root -g root -m 0644 \
  traefik/custom/image-short-url.yaml \
  traefik/generated/dynamic/image-short-url.yaml
sudo docker compose logs --since 5m traefik
)
```

首次安装才执行复制示例的命令；后续编辑 `traefik/custom/image-short-url.yaml` 并重新安装，不覆盖已定制的内容。额外动态文件不由生成器或 preflight 验证；部署后检查日志和真实请求。受控源文件 `traefik/custom/image-short-url.yaml` 不提交 Git，会随 `/app/file-code-stack` 一起备份。

对象仍保存在 `images` 桶，对象键不带 `images/`。签名上传走原始 S3 路径；不要改写上传请求。CDN 若已添加桶前缀，只在一处处理，避免双重前缀。此示例仅匹配日期目录，原有 `/images/` 地址仍可访问。
