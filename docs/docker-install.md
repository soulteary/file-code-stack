# Ubuntu 26.04 Docker 安装

先按 [原文](https://soulteary.com/2026/10/06/install-docker-on-ubuntu-26-04-with-aliyun-and-tencent-cloud-mirrors-and-basic-security.html) 检查已有容器、冲突包和重复软件源。已有业务的机器先备份并安排维护窗口。以下在 Bash 中运行，选择一家源，不修改 Ubuntu 系统源、不替换发行版代号。

```bash
sudo apt-get -o APT::Update::Error-Mode=any update
sudo apt-get install ca-certificates curl gnupg
(
  set -eu
  . /etc/os-release
  [ "$ID" = ubuntu ]
  CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  [ -n "$CODENAME" ]
  ARCH="$(dpkg --print-architecture)"
  MIRROR=https://mirrors.aliyun.com/docker-ce
  # 腾讯云可改为 https://mirrors.cloud.tencent.com/docker-ce
  # 官方源可改为 https://download.docker.com（不带 /docker-ce）
  [ ! -e /etc/apt/sources.list.d/docker.sources ] || {
    echo 'docker.sources 已存在，先检查和备份'; exit 1;
  }
  TASK_TMP="$(mktemp -d)"
  trap 'rm -rf "$TASK_TMP"' EXIT
  curl -fsSL --connect-timeout 10 --max-time 60 \
    "$MIRROR/linux/ubuntu/dists/$CODENAME/Release" -o "$TASK_TMP/Release"
  grep -Fq "stable/binary-$ARCH/Packages" "$TASK_TMP/Release"
  curl -fsSL --connect-timeout 10 --max-time 60 \
    "$MIRROR/linux/ubuntu/gpg" -o "$TASK_TMP/docker.asc"
  gpg --batch --show-keys "$TASK_TMP/docker.asc"
  # 通过 Docker 官方渠道独立核对公钥指纹后再保存。
  sudo install -d -m 0755 /etc/apt/keyrings
  sudo install -m 0644 "$TASK_TMP/docker.asc" /etc/apt/keyrings/docker.asc
  sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<APT
Types: deb
URIs: $MIRROR/linux/ubuntu
Suites: $CODENAME
Components: stable
Architectures: $ARCH
Signed-By: /etc/apt/keyrings/docker.asc
APT
)
sudo apt-get -o APT::Update::Error-Mode=any update
apt-cache policy docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# 确认 Candidate 与来源后执行：
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
sudo docker buildx version
sudo docker info
sudo aa-status
```

Ubuntu 26.04 使用 `resolute`；镜像暂未同步时检查官方源或其他镜像，不能改成 `noble`。APT 更新仍须验证签名及实际软件包是否可用。

APT 源只加速软件包下载，不加速 `docker pull`。镜像超时应检查 GHCR/Docker Hub 的网络与 daemon 代理。不要配置未知公共 registry mirror。使用 `deploy` + `sudo docker`，Docker 组等价于授予高权限。

本仓库每个服务已配置 json-file 日志轮转。已有 `/etc/docker/daemon.json` 时合并配置，不能覆盖现有配置；更改 daemon 设置会影响整台服务器，重启须安排维护窗口。保留默认 seccomp、AppArmor，不使用 `iptables=false`。Docker 发布端口不能仅依靠 UFW，另配置云安全组并从外部验证。

检查 `docker info` 的 SecurityOptions 包含 seccomp、apparmor，确认 cgroup 和内存限制可用。失败时查看内核/AppArmor 日志，不用 unconfined 绕过。`aa-status` 需要主机已安装 apparmor-utils。

系统安全更新使用发行版的 unattended-upgrades，配置后核对实际更新来源。Docker 和应用镜像升级安排维护窗口，避免无人值守更换大版本；无需为本负载调整内核缓冲或关闭 AppArmor。
