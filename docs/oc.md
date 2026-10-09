# 使用 OC 管理 OtterIO

S3 和管理 API 继续由 OtterIO 提供，操作界面改为 OC。Compose 关闭 OtterIO 自带浏览器，但保留 9001 管理 API（宿主机 `127.0.0.1:19001`）。公开图片、下载、S3 和 Git 路由不代理管理界面。

固定使用 [OC RELEASE.2026-10-09T14-38-15Z](https://github.com/soulteary/oc/releases/tag/RELEASE.2026-10-09T14-38-15Z)，源码提交 `c62be561ef03f9b7749c53a2e71b3886efa76db4`。[上游控制台说明](https://github.com/soulteary/oc/blob/RELEASE.2026-10-09T14-38-15Z/docs/console.md)规定 `oc-console` 是单操作者、本机界面，监听 loopback；发布的 CLI 归档和容器不包含它。不要将 OC 界面放到 Traefik 或共享隧道后面。

## 在管理电脑构建

准备 Git 和 Go 1.27.2，在本仓库目录执行。脚本下载固定源码、核对提交，并同时生成 CLI 和控制台；输出目录必须不存在，不覆盖已有工具。

```bash
scripts/build-oc.sh "$HOME/file-code-oc"
"$HOME/file-code-oc/oc" --version
"$HOME/file-code-oc/oc-console" --version
```

`SOURCE` 记录版本和源码提交。构建需要联网下载 Go 模块。只需要命令行时，也可下载上游对应平台归档并验证 `checksums.txt`；Web 管理界面仍需上述构建。

## 连接存储和管理 API

先建立[存储页中的 SSH 隧道](storage.md#创建存储桶和上传账号)，让管理电脑的 19000、19001 分别连接服务器的 S3 和管理 API。隧道转发的是 OtterIO API；OC 界面在管理电脑本机启动。

在管理电脑的安全终端执行，输入已保存的账号凭据（输入不显示，不写进命令历史）：

```bash
(
set -euo pipefail
umask 077
read -r -p 'Access key: ' -s oc_access
printf '\n'
read -r -p 'Secret key: ' -s oc_secret
printf '\n'
"$HOME/file-code-oc/oc" alias set store http://127.0.0.1:19000 \
  "$oc_access" "$oc_secret" --api S3v4 --path on \
  --admin-url http://127.0.0.1:19001
unset oc_access oc_secret
)
"$HOME/file-code-oc/oc-console" --alias store
```

OC 将凭据存到管理电脑的 `~/.oc/config.json`；保护这个目录。初始化命令执行时凭据短暂存在进程参数中，应在可信的单用户管理电脑执行。浏览器打开控制台打印的本机 URL，输入本次启动的 login code。不要打开 19001 作为管理页面。登录会话有效期为 30 分钟，login code 在进程停止前有效；停止程序后再更换 alias 凭据。

默认只读。创建桶、上传、管理账号和修改设置时，停止只读进程，再明确启用写入：

```bash
"$HOME/file-code-oc/oc-console" --alias store --allow-writes
```

权限来自 alias 的身份。先在测试桶检查列举、下载、创建桶和上传，确认协议与权限后再操作正式数据。界面支持对象、桶、IAM 和配置管理；不支持的操作使用同版本 OC CLI。配置写入、版本读取等能力需要匹配服务端协议，页面拒绝时先检查服务端能力，不能通过界面开关绕过。当前 `/data` 单目录是 FS 部署，不能据此启用需要纠删码的版本或分层功能。

分享链接需要单独启用 `--allow-sharing --share-url https://实际S3域名`；本项目 S3 入口有来源 IP 限制，接收者仍必须满足该限制。默认不启用分享。
