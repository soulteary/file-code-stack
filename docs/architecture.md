# 服务架构与权限边界

## 先确定服务入口

公网请求统一交给 Traefik，服务器只开放 TCP `80`、`443`，以及限制来源 IP 的 SSH 端口。OtterIO 的 S3、管理 API 和 Gitea 的后端端口只绑定宿主机 `127.0.0.1`，需要直接访问时，通过 SSH 隧道连接。Gitea 的日常浏览和 HTTPS clone 仍走 Traefik。

管理界面使用 [OC](oc.md)，在管理电脑本机运行，通过 SSH 隧道连接两个 OtterIO API。OtterIO 自带浏览器关闭；OC 界面不经 Traefik 发布。

Traefik 同时加入 `s3_proxy` 和 `git_proxy` 两个网络，分别连接 OtterIO 和 Gitea。两个后端不共享网络，减少直接互访。这里的网络划分主要用于隔离服务；普通 Docker 桥接网络仍可能访问公网和部分宿主机地址，如需限制出站访问，还要单独配置规则。

| 服务                | 容器 UID/GID    | 宿主机端口映射                                           | 可写持久化目录                                 |
| ----------------- | ------------- | ------------------------------------------------- | --------------------------------------- |
| Traefik           | `20003:20003` | `80 → 8080`、`443 → 8443`                          | `/data/traefik/acme`                    |
| OtterIO           | `20002:20002` | `127.0.0.1:19000 → 9000`、`127.0.0.1:19001 → 9001` | `/data/otterio`                         |
| Gitea rootless 镜像 | `20001:20001` | `127.0.0.1:13000 → 3000`                          | `/data/gitea/data`、`/data/gitea/config` |

这些 UID/GID 用于容器进程及挂载文件的归属，不需要创建同号的宿主机登录账号。宿主机已有的 `ubuntu`、`lighthouse` 等账号保持原编号，后面的初始化脚本会检查服务预留编号是否被占用。

Traefik 在容器内监听 `8080` 和 `8443`，由 Docker 映射到宿主机的 `80` 和 `443`。这样应用进程无需绑定容器内的低位端口，也就不需要为此保留额外的 capability。

三个容器都以非 root 用户运行，移除全部 capabilities，设置 `no-new-privileges`，并限制内存和进程数。保留 Docker 默认的 seccomp 配置；宿主机启用 AppArmor 时，也保留默认容器配置。

Traefik 和 OtterIO 使用只读根文件系统，需要的临时写入通过单独的临时目录提供。Gitea 暂时保留可写根层，待选定镜像完成初始化、确认实际写入位置后再收紧。数据库、仓库、对象和证书等持久化内容，都写入表中对应的挂载目录。

Traefik 使用[文件配置](https://doc.traefik.io/traefik/reference/install-configuration/providers/others/file/)声明路由，无需挂载 Docker socket。其他容器也不挂载宿主机根目录、`/proc`、SSH 私钥或云账户管理员凭据，不启用 `privileged`、host network 或 host PID。关于默认隔离机制，可以参考 Docker 的 [seccomp](https://docs.docker.com/engine/security/seccomp/) 和 [AppArmor](https://docs.docker.com/engine/security/apparmor/) 文档。

这里使用的是由 root 运行的 Docker daemon，应用进程则使用各自的非 root UID。[Gitea rootless 镜像](https://docs.gitea.com/installation/install-with-docker-rootless/)描述的是容器内部的运行方式，不代表 Docker daemon 也以非 root 用户运行。如果后续需要进一步隔离 daemon 权限，可以评估 [rootless Docker](https://docs.docker.com/engine/security/rootless/)，同时重新验证端口映射、挂载目录权限和资源限制。

## 准备域名和部署参数

配置服务前，先确认服务器的 CPU、内存、架构、公网 IPv4/IPv6，以及计划用于 `/data` 的存储容量和挂载方式。管理电脑和上传程序的公网出口 IP 也要记录下来，后面会用于 SSH、初始化页面和 S3 入口的访问限制。

这套服务使用四个域名，分别提供图片访问、文件下载、S3 API 和代码托管。如果接入 CDN，还要确定回源地址、回源 Host 和 HTTPS 配置。

| 参数        | 示例                            | 使用位置               |
| --------- | ----------------------------- | ------------------ |
| 图片域名      | `img.example.com`             | `.env`、CDN         |
| 文件下载域名    | `files.example.com`           | `.env`、下载链接、可选 CDN |
| S3 API 域名 | `s3.example.com`              | `.env`、上传及应用客户端    |
| Git 域名    | `git.example.com`             | `.env`             |
| ACME 邮箱   | `admin@example.com`           | `.env`             |
| 管理来源      | 实际公网 IPv4 `/32` 或 IPv6 `/128` | 云防火墙、Gitea 初始化路由   |
| S3 客户端来源  | 上传程序或应用的公网出口 IP/CIDR          | S3 路由              |
| 镜像引用      | `repository@sha256:…`         | `.env`             |

表中的域名、邮箱和镜像引用都是占位值，部署前需要替换。填写访问来源时，应使用请求实际到达服务器时的出口地址。

对象总量在几个 GB 到几十 GB、访问量较小时，可以从 2 vCPU、4 GB 内存起步，再按实际负载调整。代码托管还需要考虑完整 Git 历史、附件容量，以及多人同时 clone 时的 CPU、内存和带宽消耗。存储容量和访问流量分别估算，再决定是否增加服务器资源。

本文配置先关闭 Actions、LFS 和软件包仓库。基本服务运行稳定后，再按需要逐项启用，并调整容量、资源限制和备份范围。
