# Gitea 初始化与代码发布

先完成[配置与启动](configuration.md)，安装期间保持管理 IP 限制。

## 初始化 Gitea 并发布代码

本文使用的 [Gitea 28.1.0](https://github.com/go-gitea/gitea/releases/tag/v28.1.0)修复了特殊字符分支名处理、并发 repack 时的 go-git 存储读取、新建访问令牌的复制，以及部分 API 和 Web 处理函数缺少检查的问题。它也修复了提交状态查询触发 SQLite 表达式深度限制的情况，与本文使用的 SQLite 部署相关。

该版本还包含 Actions、npm 软件包及其他数据库的修复；本文仍保持 Actions、LFS 和软件包仓库关闭，数据库继续使用 SQLite，不因版本更新额外启用功能。首次部署后继续验证 Token 认证、push、clone 和公开、私有仓库的访问权限。

Gitea rootless 镜像使用 `/var/lib/gitea` 和 `/etc/gitea` 保存数据与配置，默认 UID/GID 为 `1000:1000`。本项目通过 Compose 的 `user` 指定 `20001:20001`，挂载目录也使用相同归属。它与普通镜像的目录布局不同，不能只替换镜像名称就切换，具体可以参考 [Gitea rootless 安装说明](https://docs.gitea.com/installation/install-with-docker-rootless/)。

安装期间保留 `GIT_BOOTSTRAP=true`，让 Git 域名只允许配置中的管理出口访问。推荐直接打开已经启用 HTTPS 的 Git 域名完成安装。

需要通过隧道访问后端时，可以在自己的电脑上执行：

```bash
SERVER_IP=203.0.113.10
ADMIN_KEY="$HOME/.ssh/file-code-stack_ed25519"

ssh -N \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -i "$ADMIN_KEY" \
  -L 127.0.0.1:13000:127.0.0.1:13000 \
  "deploy@$SERVER_IP"
```

然后打开 `http://127.0.0.1:13000`。如果浏览器跳转到配置中的 `ROOT_URL`，继续使用受管理 IP 限制的 HTTPS Git 域名。

安装页面中核对数据库类型为 SQLite，数据库路径为 `/var/lib/gitea/data/gitea.db`，公共 URL 为 `https://git.实际域名/`。创建管理员账号并设置强密码。

安装完成后，在 `/data/gitea/config/app.ini` 中确认 `INSTALL_LOCK=true`，检查公开注册已关闭、安装页面不能再次进入。查看配置时注意其中包含内部密钥，不将整份文件贴到日志、聊天或工单中。

管理员启用 2FA 或 Passkey，恢复码单独保存。不要在整个 Git 域名前再增加一层 BasicAuth，以免影响匿名 clone 和 Gitea 自身的认证。

初始化完成后，按[配置说明](configuration.md#gitea-安装完成后)解除 Git 初始化限制，再验证匿名访问和推送。

模板关闭了 push 自动建仓，不能仅靠第一次 `git push` 创建远端仓库。

新仓库先保持私有，检查完整 Git 历史、附件、凭据和许可证后，再改为公开。检查历史时不能只看当前工作目录，已经删除的敏感文件也可能保留在旧提交中。

项目代码先在本机审查，再通过 HTTPS 推送，初期不使用服务器端的在线仓库导入功能。推送使用权限范围受限的访问 Token，保存到系统凭据管理器，不写入远端 URL。

模板关闭的是使用账号密码的 HTTP Basic 认证，Token 认证仍然可用，不影响网页密码登录；具体行为见 [Gitea 认证配置说明](https://docs.gitea.com/administration/config-cheat-sheet/#service-service)。

在已有本地仓库中，添加远端并推送已经检查过的分支和标签：

```bash
git remote add code https://git.实际域名/你的账号/示例仓库.git

git push code main

# 将标签名替换为实际需要发布的标签。
git push code v1.0.0
```

不要将 Token 拼进 URL。客户端需要认证时，通过凭据管理器提供。

公开后，在没有 `.netrc`、URL 改写、认证请求头和已存凭据的独立环境中验证匿名 clone。换一个目录不会清除全局凭据配置。下面的命令关闭凭据管理器和交互式认证；不要在仍设置了其他认证方式的环境中把结果当成匿名验收：

```bash
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false \
  git -c credential.helper= clone \
  https://git.实际域名/你的账号/示例仓库.git
```

在同样的无凭据环境中访问私有仓库，应失败。

只推送需要发布的分支和标签，不使用 `--mirror` 上传未经检查的全部 refs。以后需要配置 GitHub 拉取镜像时，再设置迁移域名和地址限制，并按选定版本验证对私网、回环地址和云元数据地址的防护。Gitea 容器不保存云账号凭据。

Gitea 的浏览、clone 和 push 直接走 HTTPS。登录、API、私有仓库，以及 `info/refs`、`git-upload-pack`、`git-receive-pack` 不使用公共 CDN 缓存。固定版本的大文件可以放到 OtterIO 下载桶，确认公开后再接入 CDN。
