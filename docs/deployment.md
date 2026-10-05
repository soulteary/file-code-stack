# Ubuntu 主机准备与首次初始化

先阅读[服务架构](architecture.md)，准备四个域名、管理来源和存储容量。本文命令用于新 Ubuntu 26.04 云服务器，不在管理电脑上执行服务初始化。

## 创建运维账号并配置 SSH

修改账号和 SSH 配置前，先确认云控制台的救援登录可用，并保留当前 SSH 连接。后面另开终端验证新账号的登录和 sudo 权限，确认成功后再关闭旧会话。

### 检查系统并准备工具

先在服务器的初始账号会话中检查系统状态：

```bash
cat /etc/os-release
uname -m
free -h
df -hT
lsblk -f
timedatectl status
```

阿里云和腾讯云以及其他不同云服务供应商的镜像可能提供不同的初始账号，实际入口以镜像说明和云控制台提示为准。

| 初始账号                  | 取得管理权限       | 后续运维方式                   |
| --------------------- | ------------ | ------------------------ |
| 阿里云 `root`            | 登录后已是 root   | `deploy` + SSH 密钥 + sudo |
| 阿里云 `ecs-user`        | 执行 `sudo -i` | `deploy` + SSH 密钥 + sudo |
| 腾讯云 `ubuntu`          | 执行 `sudo -i` | `deploy` + SSH 密钥 + sudo |
| 腾讯云轻量服务器 `lighthouse` | 执行 `sudo -i` | `deploy` + SSH 密钥 + sudo |

当前是 `root` 时直接继续，其他账号先执行：

```bash
sudo -i
```

下面的初始化命令在 root shell 中执行，确认是 `root` 身份后，更新系统并安装工具：

```bash
if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' '请先执行 sudo -i，进入 root shell。'
  exit 1
fi

apt update
apt upgrade
apt install sudo openssh-server ca-certificates curl openssl \
  ufw unattended-upgrades apparmor-utils restic python3 vim rsync
```

软件包升级可能出现确认提示，根据实际情况，完成变更检查后继续，如果有弹出提示，不要强制覆盖已有配置。

即使我们安装了“无人值守更新” `unattended-upgrades` 也不代表完成了自动更新策略，后面还需要检查它的配置。

更新结束，如果系统提示需要重启，先重启、重新登录并恢复 root shell，再继续部署。这里尤其需要确认时间同步正常，避免时钟偏差影响 S3 签名校验。至于服务器上预安装的云厂商初始化组件和厂商监控服务先保留，后续根据实际需求再决定是否调整。

### 准备并上传管理公钥

我们在自己的电脑或者管理服务器上准备一把专用的 Ed25519（`ssh-ed25519`）密钥，并将公钥上传到这台需要完成部署的服务器上，上传前后注意核对公钥内容和指纹。

如果已有符合要求的密钥，可以直接使用。下面的命令仅在私钥和公钥文件都不存在时生成新密钥：

```bash
# 在自己的电脑上执行。
mkdir -p "$HOME/.ssh"
chmod 0700 "$HOME/.ssh"

ADMIN_KEY="$HOME/.ssh/file-code-stack_ed25519"

if [ ! -e "$ADMIN_KEY" ] && [ ! -e "$ADMIN_KEY.pub" ]; then
  ssh-keygen -t ed25519 \
    -f "$ADMIN_KEY" \
    -C file-code-stack-admin
else
  printf '%s\n' '密钥文件已存在，请确认后使用，不要覆盖。'
fi
```

生成时建议为私钥设置一个口令。当使用其他已有密钥时，可以将上面的 `ADMIN_KEY` 改为对应的私钥路径。

公钥和私钥通常成对出现，如果缺失了某一个文件，建议先停下来检查原因。先使用命令确认公钥文件存在，查看内容和指纹：

```bash
test -f "$ADMIN_KEY.pub"
cat "$ADMIN_KEY.pub"
ssh-keygen -lf "$ADMIN_KEY.pub"
```

公钥文件应只包含自己的那一条公钥。记录下指纹，稍后在服务器上再次核对。

接下来，在自己的电脑上下载配套配置。从[仓库提交记录](https://github.com/soulteary/file-code-stack/commits/main/)选择包含所需模板和文档的已审核提交，将下面的 `YOUR_REVIEWED_COMMIT` 替换为完整 40 位提交摘要，并保存在部署记录中。不要直接把变化中的 `main` 当成固定版本。需要 `curl` 和 `tar`；在一个新的工作目录中执行，不覆盖已有配置：

```bash
(
set -euo pipefail

STACK_REF=YOUR_REVIEWED_COMMIT
[[ "$STACK_REF" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' '请先填写已审核的完整提交摘要。'
  exit 1
}
STACK_DIR="$(mktemp -d "$PWD/file-code-stack-source.XXXXXX")"

curl -fL "https://codeload.github.com/soulteary/file-code-stack/tar.gz/$STACK_REF" \
  -o "$STACK_DIR/source.tar.gz"
mkdir "$STACK_DIR/file-code-stack"
tar -xzf "$STACK_DIR/source.tar.gz" \
  --strip-components=1 -C "$STACK_DIR/file-code-stack"

test -f "$STACK_DIR/file-code-stack/compose.yaml"
test -f "$STACK_DIR/file-code-stack/scripts/render-config.py"
printf '配置目录：%s\n' "$STACK_DIR/file-code-stack"
)
```

下载完成后，进入输出的配置目录的上一级，再上传公钥和整个 `file-code-stack` 目录。下面的 `INITIAL_USER` 和 `SERVER_IP` 需要按实际环境填写：

```bash
# 在自己的电脑上执行。
INITIAL_USER=ubuntu
SERVER_IP=203.0.113.10

scp "$ADMIN_KEY.pub" \
  "$INITIAL_USER@$SERVER_IP:~/deploy-admin.pub"

# 在解压后的 file-code-stack 目录所在位置执行。
# 远端 staging 目录应尚不存在，避免重复上传形成嵌套目录。
scp -r file-code-stack \
  "$INITIAL_USER@$SERVER_IP:~/file-code-stack-staging"
```

`203.0.113.10` 是示例地址，执行前需要替换。初始账号可能是阿里云的 `root`、`ecs-user`，或腾讯云的 `ubuntu` 或其他服务商的各种用户名，以实际登录账号为准。

首次连接时，通过云控制台等可信渠道核对服务器的 SSH 主机密钥指纹，不关闭主机密钥校验。这里核对的服务器主机密钥，与前面生成的管理员登录密钥是两种不同的密钥。

### 创建用户并分配权限

回到服务器的 root shell，通过初始账号定位上传的公钥。下面的 `INITIAL_USER` 必须与上传时使用的账号一致：

```bash
INITIAL_USER=ubuntu
INITIAL_HOME=$(getent passwd "$INITIAL_USER" | cut -d: -f6)
PUBLIC_KEY="$INITIAL_HOME/deploy-admin.pub"

test -n "$INITIAL_HOME"
test -f "$PUBLIC_KEY"

cat "$PUBLIC_KEY"
ssh-keygen -lf "$PUBLIC_KEY"
```

将这里显示的内容和指纹与自己电脑上的结果比较。确认文件只包含自己的公钥，且指纹一致后，再执行下面的创建命令。

下面按首次部署创建新账号；若已经存在 `deploy` 用户或组，命令会停止，不覆盖原账号：

```bash
(
set -euo pipefail

[ "$(id -u)" -eq 0 ] || {
  printf '%s\n' '请在 root shell 中执行。'
  exit 1
}

INITIAL_USER=ubuntu
INITIAL_HOME=$(getent passwd "$INITIAL_USER" | cut -d: -f6)
test -n "$INITIAL_HOME"
PUBLIC_KEY="$INITIAL_HOME/deploy-admin.pub"
test -f "$PUBLIC_KEY"

if getent passwd deploy >/dev/null || getent group deploy >/dev/null; then
  printf '%s\n' 'deploy 用户或组已存在，请先核对，不继续创建。'
  exit 1
fi

DEPLOY_ID=1001
while getent passwd "$DEPLOY_ID" >/dev/null ||
      getent group "$DEPLOY_ID" >/dev/null ||
      [ "$DEPLOY_ID" -eq 20001 ] ||
      [ "$DEPLOY_ID" -eq 20002 ] ||
      [ "$DEPLOY_ID" -eq 20003 ]; do
  DEPLOY_ID=$((DEPLOY_ID + 1))
done

groupadd --gid "$DEPLOY_ID" deploy
useradd --uid "$DEPLOY_ID" --gid deploy \
  --create-home --shell /bin/bash deploy
passwd --lock deploy
chmod 0750 /home/deploy

install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
install -m 0600 -o deploy -g deploy \
  "$PUBLIC_KEY" /home/deploy/.ssh/authorized_keys

id deploy
)
```

新创建的账号将从 1001 起选择未占用的 UID/GID，并跳过服务预留的 20001、20002、20003。例如，宿主机已有 `ubuntu=1000`、`lighthouse=1001` 时，新建的 `deploy` 会使用 1002，不需要修改默认账号编号。

创建的账号会锁定本地密码，只允许通过 SSH 密钥登录。

这里有个细节，容器服务使用的 UID/GID 与登录账号分开，后面也不要将服务预留编号用于其他登录账号。

如果创建账号过程中会话中断或某条命令失败，账号可能只完成了部分配置。再次执行时，如果提示 `deploy 用户或组已存在`，先在原来的 root 会话查看账号和用户组，不直接删除账号：

```bash
getent passwd deploy || true
getent group deploy || true
```

下面的命令会备份并删除 `/home/deploy`，必须在 root shell 中执行，不要从部分创建就绪的 deploy 账号的 SSH 会话切换到 root 后执行：

```bash
(
set -euo pipefail

[ "$(id -u)" -eq 0 ] || {
  printf '%s\n' '请从初始管理员会话进入 root shell 后执行。'
  exit 1
}

if id deploy >/dev/null 2>&1; then
  if [ "$(getent passwd deploy | cut -d: -f6)" != /home/deploy ]; then
    printf '%s\n' 'deploy 家目录不是 /home/deploy，请先人工核对。'
    exit 1
  fi

  if [ -d /home/deploy ]; then
    tar -czpf "/root/deploy-home-$(date +%Y%m%d-%H%M%S).tar.gz" \
      -C /home deploy
  fi

  loginctl terminate-user deploy 2>/dev/null || true
  pkill -TERM -u deploy 2>/dev/null || true
  sleep 2
  pkill -KILL -u deploy 2>/dev/null || true
  userdel --remove deploy
fi

if getent group deploy >/dev/null; then
  groupdel deploy
fi

getent passwd deploy || true
getent group deploy || true
)
```

最后两条查询都没有输出后，再执行创建命令。

账号删除不会清理 `/app`、`/data` 和 sudoers 规则。如果之前已经创建配置目录，重建账号后还要核对这些目录的用户组归属。这里的清理仅用于首次部署的误操作；已有业务数据时，按实际状态修复，不通过重置服务器处理。

完成账号创建之后，我们将 `deploy` 作为受信任的管理员，配置免密码 sudo，便于后面的运维脚本运行。有这个账号 SSH 登录权限的人可以进一步取得 root 权限，因此这个账号要注意保管，以及不要配置给 CI 使用。

下面的命令仍在 root shell 中执行。使用命令生成固定授权的文件，先创建临时文件，然后再安装到 sudoers 目录：

```bash
(
set -euo pipefail

[ "$(id -u)" -eq 0 ] || {
  printf '%s\n' '请在 root shell 中执行。'
  exit 1
}

id deploy

if [ -e /etc/sudoers.d/deploy ] || [ -L /etc/sudoers.d/deploy ]; then
  printf '%s\n' '/etc/sudoers.d/deploy 已存在，请先核对原授权。'
  exit 1
fi

SUDOERS_TMP=$(mktemp)
trap 'rm -f "$SUDOERS_TMP"' EXIT

cat > "$SUDOERS_TMP" <<'EOF'
deploy ALL=(ALL:ALL) NOPASSWD: ALL
EOF

chmod 0440 "$SUDOERS_TMP"
visudo -cf "$SUDOERS_TMP"
install -o root -g root -m 0440 \
  "$SUDOERS_TMP" /etc/sudoers.d/deploy
visudo -c

# 从 root 会话验证 deploy 的免密码 sudo。
su - deploy -c 'sudo -n true && sudo -n id -u && sudo -n -l'
)
```

如果系统中已有 `/etc/sudoers.d/deploy` 配置，上面的配置命令会自动停止。我们可以先在 root 会话查看原授权的详细情况：

```bash
cat /etc/sudoers.d/deploy
grep -RnsE '(^|[[:space:]])%?deploy([[:space:]]|$)' \
  /etc/sudoers /etc/sudoers.d
```

如果只包含我们配置的账号内容，可以直接删除，再次执行命令进行生成。如果还包含其他账号，不要直接删除。可以使用 Vim 修改规则文件内容，并检查规则语法是否正确：

```bash
EDITOR=vim VISUAL=vim visudo -f /etc/sudoers.d/deploy
visudo -c
```

修改其他配置文件里的授权信息，调整实际路径即可。

如果 deploy 可以登录，但 `sudo -n true` 提示 `user deploy may not run sudo`，说明账号可以登录，sudo 授权尚未生效。我们回到原来的 root 会话检查授权文件、权限和 `visudo -c` 的结果，不必重新创建用户。

本文不倾向将 deploy 加入 docker 组，Docker 操作统一使用 sudo docker。

因为 deploy 已有免密码 sudo 权限，执行 sudo docker 就能管理容器，再加入 docker 组没有必要。同时，docker 组也不是普通的应用权限：成员可以启动容器并挂载宿主机目录，实际能够取得接近 root 的控制能力。

这里统一使用 sudo docker，主要是让需要管理员权限的操作在命令中明确体现，并减少一处重复授权。它不会限制 deploy 的权限，因为这个账号本来就能通过 sudo 执行任意管理命令。

### 验证新账号

保留 SSH 连接状态，在自己的电脑上另开一个终端会话，使用上文提到的专用密钥建立全新连接。新终端需要重新设置 `SERVER_IP` 和 `ADMIN_KEY` 变量；如果前面使用了其他密钥，这里的路径也要保持一致：

```bash
SERVER_IP=203.0.113.10
ADMIN_KEY="$HOME/.ssh/file-code-stack_ed25519"

ssh \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o ControlMaster=no \
  -o ControlPath=none \
  -i "$ADMIN_KEY" \
  "deploy@$SERVER_IP"
```

上面的命令里，明确使用公钥进行认证，并通过 `IdentitiesOnly=yes` 选择指定身份，避免 SSH agent 中的其他密钥造成额外认证尝试。我们关闭了连接复用，确保进行的是一次新的登录验证。

如果刚刚的私钥设置了口令，连接时可能需要输入私钥口令。这与服务器账号的登录密码不同。

登录后，在新的 `deploy` 会话中检查身份和 sudo 权限：

```bash
id
sudo -n true
sudo -n id -u
sudo -n -l
```

`id` 应显示当前用户为 `deploy`；`sudo -n true` 应成功退出且没有输出；`sudo -n id -u` 应输出 `0`；`sudo -n -l` 应包含为 deploy 配置的 `NOPASSWD: ALL` 授权。

确认新登录和 sudo 都成功后，再继续收紧 SSH 配置。如果登录或 sudo 检查失败，继续使用保留的原会话排查，先不修改 SSH 策略。

### 验证登录后，收紧 SSH

新账号验证成功后，我们调整 SSH 配置，只允许 `deploy` 账号登录；多人管理的机器，需要先将其他授权账号也加入 `AllowUsers`。继续保留原 SSH 连接，并确认云控制台救援入口可用。

在新的 `deploy` 会话中创建配置文件：

```bash
sudo install -d -o root -g root -m 0755 /etc/ssh/sshd_config.d

# 只创建新文件；如果目标已存在，命令会失败。
# 此时先检查文件来源并备份，不直接覆盖。
sudo bash -c '
set -eu
target=/etc/ssh/sshd_config.d/00-service-hardening.conf
umask 022
set -C
cat > "$target"
' <<'EOF'
PermitRootLogin no
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
AllowUsers deploy
X11Forwarding no
AllowAgentForwarding no
MaxAuthTries 3
AllowTcpForwarding local
EOF
```

上面的命令中，`AuthenticationMethods publickey` 要求使用 SSH 密钥登录，`AllowTcpForwarding local` 允许我们通过 `ssh -L`，从自己的电脑访问服务器上的管理控制台；不允许通过 `ssh -R` 在服务器一侧建立转发入口。

不过，拥有 shell 和 sudo 权限的管理员仍然可以运行其他程序进行转发，因此这项配置不能用于限制管理员权限。

执行完毕命令后，先检查配置语法是否正确：

```bash
sudo /usr/sbin/sshd -t
```

成功时通常没有输出。如果检查失败，不重新加载服务，先修正配置或删除本次新建的文件。

接着按当前连接的实际来源检查最终配置。以下命令在 `deploy` 的 SSH 会话中执行：

```bash
# SSH_CONNECTION 的顺序为：
# 客户端地址、客户端端口、服务器本地地址、服务器端口。
test -n "$SSH_CONNECTION"
read -r CLIENT_IP CLIENT_PORT SERVER_LOCAL_IP SSH_PORT <<< "$SSH_CONNECTION"

CLIENT_HOST="$CLIENT_IP"

sudo /usr/sbin/sshd -T \
  -C "user=deploy,host=$CLIENT_HOST,addr=$CLIENT_IP,laddr=$SERVER_LOCAL_IP,lport=$SSH_PORT" \
  | grep -E '^(permitrootlogin|pubkeyauthentication|authenticationmethods|passwordauthentication|kbdinteractiveauthentication|permitemptypasswords|allowusers|denyusers|allowgroups|denygroups|x11forwarding|allowagentforwarding|maxauthtries|allowtcpforwarding|disableforwarding|permitopen) '
```

服务器地址取自当前连接的 `SSH_CONNECTION`。云服务器的公网 IP 经过 NAT 映射时，sshd 实际接收连接的地址可能是私网 IP，检查配置时应使用这个地址。如果已有配置包含 `Match Host`，还需要将 `CLIENT_HOST` 设置为 sshd 实际识别的客户端主机名。

检查输出是否符合预期：

| 参数                             | 预期值                       |
| ------------------------------ | ------------------------- |
| `permitrootlogin`              | `no`                      |
| `pubkeyauthentication`         | `yes`                     |
| `authenticationmethods`        | `publickey`               |
| `passwordauthentication`       | `no`                      |
| `kbdinteractiveauthentication` | `no`                      |
| `permitemptypasswords`         | `no`                      |
| `allowusers`                   | 只有 `deploy`，或事先确定的授权账号    |
| `x11forwarding`                | `no`                      |
| `allowagentforwarding`         | `no`                      |
| `maxauthtries`                 | `3`                       |
| `allowtcpforwarding`           | `local`                   |
| `disableforwarding`            | `no`                      |
| `permitopen`                   | `any`，或明确允许后面隧道所需的目标地址与端口 |

如果最终配置中出现 `DisableForwarding yes`，即使设置了 `AllowTcpForwarding local`，本地隧道也无法使用。`PermitOpen` 和 `authorized_keys` 中的公钥选项还可能限制转发目标，因此后面需要通过 SSH 隧道实际访问控制台，确认配置生效。

同时检查 `DenyUsers`、`AllowGroups` 和 `DenyGroups`，确认这些规则不会阻止 `deploy` 登录。然后将检查命令中的 `user=deploy` 分别替换为 `root` 和实际初始账号名，查看这些账号是否有单独的 `Match` 规则。

OpenSSH 的多数参数采用先读到的值，但也有例外，例如多条 `AllowUsers` 会累加允许登录的账号。因此，将文件命名为 `00-service-hardening.conf` 并不意味着能覆盖所有已有配置，仍需检查最终结果。具体规则可以参考 [OpenSSH 配置手册](https://man.openbsd.org/sshd_config)。

输出不一致时，检查主配置和片段文件：

```bash
sudo grep -RInE \
  '^[[:space:]]*(Include|Match|AllowUsers|DenyUsers|AllowGroups|DenyGroups|PermitRootLogin|AuthenticationMethods|PasswordAuthentication|KbdInteractiveAuthentication|PubkeyAuthentication|AllowTcpForwarding|DisableForwarding|PermitOpen)[[:space:]]' \
  /etc/ssh/sshd_config /etc/ssh/sshd_config.d
```

如果 `Include` 引用了其他目录中的配置文件，也要一并检查。修改前先备份，再使用 Vim 调整；完成后重新检查语法和最终生效的配置，确认结果符合预期。Ubuntu 上的具体配置方法可以参考 [OpenSSH 服务配置说明](https://ubuntu.com/server/docs/how-to/security/openssh-server/)。

确认检查通过后，重新加载服务：

```bash
sudo /usr/sbin/sshd -t && sudo systemctl reload ssh.service
```

然后在自己的电脑上再开一个终端，重新设置 `SERVER_IP` 和 `ADMIN_KEY`，使用[验证新账号](#验证新账号)中的 SSH 命令建立第三个全新 deploy 会话，再执行：

```bash
id
sudo -n true
sudo -n id -u
```

确认新的 deploy 会话可以登录并正常使用 sudo 后，再用初始账号建立一次全新的 SSH 连接，确认它已无法登录。测试时同样关闭连接复用，避免复用仍然有效的旧连接。两项验证都完成后，再关闭旧会话。

这里不修改 SSH 端口、监听地址或 socket activation 配置。未列入最终 `AllowUsers` 的账号将无法通过 SSH 登录，但账号和云初始化配置仍然保留。先确认云厂商的救援功能是否依赖这些账号，再决定是否锁定或删除。

如果语法检查失败，或重新加载后无法建立新的 deploy 连接，在保留的旧会话中删除本次新建的配置文件，再检查语法并重新加载服务：

```bash
sudo rm -- /etc/ssh/sshd_config.d/00-service-hardening.conf
sudo /usr/sbin/sshd -t && sudo systemctl reload ssh.service
```

上面的命令只撤销本次新增的配置文件。如果还改动了其他配置，也需要恢复对应的备份，再检查语法并重新加载服务。

### 用命令生成配置，编辑时使用 Vim

固定配置尽量通过命令生成，再用 `install` 设置文件归属和权限。前面用到的 `<<'EOF'` 会保留内容中的变量和特殊字符，不让当前 shell 提前展开。需要手动修改配置或排查问题时，统一使用 Vim。

前面已经安装了 `vim`，接下来将它设为系统默认编辑器，并为后续登录会话设置编辑器变量：

```bash
sudo update-alternatives --set editor /usr/bin/vim.basic

sudo tee /etc/profile.d/10-service-editor.sh >/dev/null <<'EOF'
export EDITOR=vim
export VISUAL=vim
export SUDO_EDITOR=vim
EOF

sudo chown root:root /etc/profile.d/10-service-editor.sh
sudo chmod 0644 /etc/profile.d/10-service-editor.sh

# 让当前会话立即生效。
export EDITOR=vim
export VISUAL=vim
export SUDO_EDITOR=vim
```

编辑普通系统配置文件时，可以使用 `sudoedit`，将下面的示例路径替换为实际路径：

```bash
SUDO_EDITOR=vim sudoedit /etc/某配置文件
```

编辑 sudoers 文件时使用 `visudo`，它会在保存时检查语法。修改独立配置文件后，再检查整套 sudo 配置：

```bash
sudo env EDITOR=vim VISUAL=vim SUDO_EDITOR=vim \
  visudo -f /etc/sudoers.d/deploy

sudo visudo -c
```

不要用 `sudo echo ... > /etc/文件` 写入系统配置：`sudo` 只作用于 `echo`，重定向仍由当前用户的 shell 执行，可能因权限不足而失败。可以改用 `sudo tee`，或者先生成临时文件，再用 `sudo install` 保存。

修改服务配置后，先检查语法，再重新加载对应服务。密码和私钥不放进命令参数、shell 历史或 Git。

## 云防火墙和 UFW

先在云安全组或轻量服务器防火墙中限制入站访问：TCP 22 只允许管理电脑的公网出口地址，TCP 80、443 用于 Web 访问。如果实际 SSH 端口不是 22，下面的规则也要相应调整。

OtterIO、Gitea 的后端端口，以及 Docker API 和 Traefik 内部端口，都不向公网开放。IPv6 的防火墙规则也要单独检查；暂不发布 AAAA 记录并不能阻止别人通过服务器的 IPv6 地址访问。

接下来配置服务器上的 UFW。将下面的 `ADMIN_CIDR` 换成实际管理出口，单个 IPv4 地址使用 `/32`，单个 IPv6 地址使用 `/128`。如果出口地址经常变化，先准备稳定的管理入口，并保留云控制台救援方式。

```bash
# 替换为实际管理出口地址。
ADMIN_CIDR='203.0.113.10/32'
SSH_PORT=22

# 先检查是否已有规则。
sudo ufw status numbered

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from "$ADMIN_CIDR" to any port "$SSH_PORT" proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 确认管理地址和 SSH 端口填写正确后启用。
sudo ufw enable
sudo ufw status verbose
```

设置默认拒绝入站不会删除已有的允许规则。如果之前存在面向所有来源的 SSH 放行规则，需要核对并删除，才能将 SSH 访问限制到管理出口。

启用后保留当前连接，在自己的电脑上使用前面的 SSH 命令建立一次全新连接，确认 deploy 登录和 sudo 仍然正常，再关闭旧会话。

Docker 发布端口时会配置自己的转发规则，容器流量可能绕过 UFW 的常规入站规则。因此，除了配置 UFW，还要限制云防火墙、减少端口发布，并将后台端口绑定到 `127.0.0.1`。服务启动后，从另一台机器检查实际暴露的端口。不要通过设置 `iptables=false` 解决这个问题，它可能破坏容器网络，具体原因可以参考 [Docker 防火墙说明](https://docs.docker.com/engine/network/packet-filtering-firewalls/)。

以后需要限制容器出站或增加转发过滤时，先确认 Docker 使用的防火墙后端。`DOCKER-USER` 的配置方法适用于 iptables 后端，不能直接照搬到 Docker 原生 nftables 后端；系统使用 `iptables-nft` 也不等于 Docker 已启用原生 nftables。相关区别可以参考 [Docker nftables 配置说明](https://docs.docker.com/engine/network/firewall-nftables/)。修改规则前保留备份和救援会话。

## 安装 Docker Engine

按 [Docker 安装说明](docker-install.md)安装 Engine、Buildx 和 Compose，并检查服务、安全选项和资源限制。已经安装的机器只执行安装后的检查，不重复移除运行时或添加 APT 源。

## 放置配置并挂载数据盘

### root 持有配置，deploy 可进入运维目录

接下来，我们把之前上传的配置复制到 `/app/file-code-stack`。

下面在 `deploy` 会话中执行，`STAGING_DIR` 按 3.2 章节初始账号的实际目录填写。例如，如之前使用 `lighthouse` 上传，路径为 `/home/lighthouse/file-code-stack-staging`；使用 root 上传时，通常为 `/root/file-code-stack-staging`。

复制和权限设置放在同一个命令块中，任何一步失败都会停止。下面只用于首次放置配置，目标目录已经存在时，先检查内容，不要直接覆盖。

```bash
STAGING_DIR=/home/ubuntu/file-code-stack-staging

sudo bash -s -- "$STAGING_DIR" <<'EOF'
set -euo pipefail

source_dir=$1
target=/app/file-code-stack

test -d "$source_dir"
test -f "$source_dir/compose.yaml"
test -f "$source_dir/.env.example"
test -f "$source_dir/scripts/init-state.sh"

if [ -e "$target" ] || [ -L "$target" ]; then
  printf '%s\n' '/app/file-code-stack 已存在，请先检查，不直接覆盖。'
  exit 1
fi

# 首次部署使用尚未初始化的配置目录。
if [ -e "$source_dir/.env" ] || [ -e "$source_dir/secrets" ]; then
  printf '%s\n' '上传目录包含 .env 或 secrets，请先核对，不执行批量权限调整。'
  exit 1
fi

install -d -m 0750 -o root -g deploy "$target"
cp -a "$source_dir/." "$target/"

chown -R root:root "$target"
find "$target" -mindepth 1 -type d -exec chmod 0755 {} +
find "$target" -type f -exec chmod 0644 {} +
chmod 0755 "$target"/scripts/*.sh "$target/scripts/render-config.py"

chown root:deploy "$target"
chmod 0750 "$target"
EOF
```

命令成功后进入配置目录：

```bash
cd /app/file-code-stack

# 继续完成下文 /data 挂载步骤，此处暂不运行初始化。
```

顶层目录设置为 `root:deploy`、0750 后，deploy 可以进入并读取普通配置，修改仍需要 sudo。Traefik 读取的配置子目录保留 0755，供容器内 UID 20003 访问。

**初始化后还要核对一次下面的权限。不要重新执行前面的批量权限调整，它会放宽 `.env` 和秘密文件的访问权限。**

| 对象                                          | 所有者             | 权限 / 用途                      |
| ------------------------------------------- | --------------- | ---------------------------- |
| `/home/deploy`                              | `deploy:deploy` | 0750                         |
| `/home/deploy/.ssh`                         | `deploy:deploy` | 0700                         |
| `/home/deploy/.ssh/authorized_keys`         | `deploy:deploy` | 0600                         |
| `/app/file-code-stack`                      | `root:deploy`   | 0750，deploy 可进入              |
| Compose、普通配置、脚本                             | `root:root`     | 文件 0644；可执行脚本 0755；仅 root 可写 |
| `.env`                                      | `root:root`     | 0600，由 sudo 执行的 Compose 读取   |
| `secrets` 目录                                | `root:root`     | 0700                         |
| `secrets/root_user`、`secrets/root_password` | `20002:20002`   | 0400；只读挂入容器                  |
| `/data/otterio`                             | `20002:20002`   | 0750                         |
| `/data/gitea/data`、`/data/gitea/config`     | `20001:20001`   | 0750                         |
| `/data/traefik/acme`                        | `20003:20003`   | 0750                         |
| `/data/traefik/acme/acme.json`              | `20003:20003`   | 0600                         |
| 后续创建的备份配置和口令文件                              | `root:root`     | 0600                         |

这里没有启用用户命名空间重映射，容器进程的 UID/GID 与宿主机文件权限使用相同的数字。本项目为 Gitea、OtterIO、Traefik 分别预留 20001、20002、20003，不需要创建对应的宿主机登录账号，也不与 ubuntu、lighthouse 等账号共用。

初始化和预检查会确认这些 UID/GID 没有被宿主机用户或用户组占用，发现冲突就停止。选择较大的编号是为了避开常见登录账号，本身不提供额外隔离。如果后续启用用户命名空间重映射或 rootless Docker，需要重新核对挂载目录的权限。

初始化脚本不会覆盖已有用户名和密码文件。`secrets` 目录归 root，权限为 0700；两个凭据文件归 `20002:20002`，权限为 0400，OtterIO 使用相同身份读取挂入容器的文件。这里的 Compose secrets 是文件挂载，不是加密存储，宿主机 root 和 Docker 管理员仍能读取。

服务数据统一放在 `/data`：OtterIO 使用 `/data/otterio`，Gitea 使用 `/data/gitea/data` 和 `/data/gitea/config`，证书保存在 `/data/traefik/acme`。配置和秘密文件仍留在 `/app/file-code-stack`。前面的递归归属和权限调整只用于新复制的配置，不对 `/data` 执行。

这里不迁移 Docker 的 `data-root`。即使服务数据使用独立数据盘，镜像、容器可写层和日志仍可能占用系统盘。使用 containerd image store 时，还要检查 containerd 的独立存储目录，通常为 `/var/lib/containerd`；修改 Docker 的 `data-root` 不会自动迁移这部分内容，具体可以参考 [Docker 存储目录说明](https://docs.docker.com/engine/storage/containerd/)。

### 选择 /data 的挂载方式

先查看磁盘和挂载情况：

```bash
sudo mkdir -p /data

lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,UUID
findmnt --target /data
mountpoint /data
```

`findmnt --target /data` 显示的是承载这个目录的文件系统。如果挂载目标显示为 `/`，说明 `/data` 当前位于根文件系统中，尚未单独挂载。

下面根据是否有独立数据盘选择一种方式，完成后再初始化。已经正确挂载 `/data` 的机器，可以直接进入[挂载检查与初始化](deployment.md#挂载检查与初始化)。

当我们使用独立数据盘时，先根据 `lsblk` 核对数据分区、UUID 和文件系统。下面按分区已经有文件系统的情况配置，已有数据的分区不执行 `mkfs`。如果磁盘尚未分区或格式化，先完成磁盘准备，再继续。

挂载前检查 `/data`：

```bash
mountpoint /data
sudo ls -la /data
```

如果已经挂载，先核对来源；如果目录里有文件，先处理这些文件，不直接挂载覆盖。挂载不会删除原文件，但会让挂载点下的原内容暂时不可见。

编辑挂载配置前保留备份：

```bash
sudo cp -a /etc/fstab "/etc/fstab.backup-$(date +%Y%m%d-%H%M%S)"
SUDO_EDITOR=vim sudoedit /etc/fstab
```

如果已经有 `/data` 的配置，先核对原记录，不重复添加。ext4 数据分区可以使用下面的格式，实际 UUID 从 `lsblk` 输出中获取：

```text
UUID=实际UUID /data ext4 defaults 0 2
```

使用 XFS 等文件系统时，按实际类型填写，最后的文件系统检查项也要相应调整，不能直接照抄 ext4。

保存后挂载并检查：

```bash
(
set -euo pipefail

sudo systemctl daemon-reload
sudo mount /data

mountpoint /data
findmnt --mountpoint /data
df -h /data
)
```

确认挂载来源、文件系统和容量符合预期。挂载失败时先处理，不继续初始化或启动应用。使用独立数据盘的读者，到这里可以进入[挂载检查与初始化](deployment.md#挂载检查与初始化)。

而当我们只使用系统盘的时候，部分轻量云服务器只有一块系统盘。如果暂时使用系统盘保存服务数据，我们在 `/srv/file-code-stack-data` 创建专用目录，再将它绑定挂载到 `/data`。

这里的 `/srv/file-code-stack-data` 是数据存放位置，`/data` 是提供给 Compose 和运维脚本的统一入口。挂载后，两条路径访问的是同一份文件，不会额外复制数据。

这种方式满足项目的挂载检查，但数据、镜像和系统仍然共享同一块磁盘的空间与故障风险，不等于增加了一块独立数据盘。

下面用于首次部署，要求 `/data` 尚未挂载且为空。如果 fstab 已有 `/data` 配置，命令会停止，先检查原配置：

```bash
(
set -euo pipefail

sudo mkdir -p /data

if mountpoint -q /data; then
  printf '%s\n' '/data 已挂载，请核对现有挂载，不重复配置。'
  exit 1
fi

if [ -n "$(sudo find /data -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  printf '%s\n' '/data 非空，请先检查其中内容。'
  exit 1
fi

if grep -qE '^[^#[:space:]]+[[:space:]]+/data[[:space:]]' /etc/fstab; then
  printf '%s\n' 'fstab 已包含 /data 配置，请先核对。'
  exit 1
fi

sudo install -d -o root -g root -m 0755 /srv/file-code-stack-data

sudo cp -a /etc/fstab "/etc/fstab.backup-$(date +%Y%m%d-%H%M%S)"
printf '%s\n' '/srv/file-code-stack-data /data none bind 0 0' |
  sudo tee -a /etc/fstab >/dev/null

sudo systemctl daemon-reload
sudo mount /data

mountpoint /data
findmnt --mountpoint /data
df -h /data
)
```

如果挂载失败，先检查错误和刚写入的 fstab 记录，不反复追加配置。

服务启动后，数据会通过 `/data` 写入，实际保存在 `/srv/file-code-stack-data` 中。服务运行期间不卸载挂载点，也不直接清理这个源目录。

### 挂载检查与初始化

确认 `/data` 的挂载来源无误后，安装仓库附带的 Docker 启动保护：

```bash
sudo install -d -o root -g root -m 0755 \
  /etc/systemd/system/docker.service.d

sudo install -o root -g root -m 0644 \
  /app/file-code-stack/scripts/docker-data.conf \
  /etc/systemd/system/docker.service.d/20-service-data.conf

sudo systemctl daemon-reload
sudo systemctl cat docker
```

这份配置让 Docker 服务启动时依赖 `/data`，并在启动前检查它是否为挂载点。它作用于整个 Docker daemon，因此也会影响同一台机器上的其他容器。

`daemon-reload` 只让 systemd 重新读取配置，不会重启正在运行的 Docker。这里在首次启动应用前安装，后续需要重启 Docker 时再安排维护窗口。

挂载检查只能确认 `/data` 是挂载点，不能保证挂载了正确的设备或目录，仍然需要核对 `findmnt` 的结果。如果 fstab 配置错误导致启动失败，通过云控制台救援入口恢复。

接下来初始化数据目录、凭据和 ACME 文件。初始化与检查放在同一个命令块中，初始化失败后就停止，不继续检查尚未创建的文件：

```bash
(
set -euo pipefail

cd /app/file-code-stack
sudo scripts/init-state.sh

sudo stat -c '%U:%G %a %n' \
  /app/file-code-stack \
  /app/file-code-stack/.env \
  /app/file-code-stack/secrets

sudo stat -c '%u:%g %a %n' \
  /data/otterio \
  /data/gitea/data \
  /data/gitea/config \
  /data/traefik/acme

sudo stat -c '%u:%g %a %n' \
  secrets/root_user \
  secrets/root_password \
  /data/traefik/acme/acme.json
)
```

对照[目录权限说明](deployment.md#root-持有配置deploy-可进入运维目录)的权限表检查结果。OtterIO 凭据应为 `20002:20002`、0400，ACME 文件应为 `20003:20003`、0600。

初始化脚本会创建 `.env`、生成尚不存在的管理员凭据，并准备数据目录和证书文件，不会启动容器。已有凭据不会被覆盖，后面继续填写部署参数和核对镜像摘要。

如果脚本提示 `/data must be a mounted filesystem`，说明它已在写入前停止。此时 `.env`、`secrets` 或数据目录尚未创建属于预期结果。回到上一节完成挂载，再执行初始化，不跳过检查。

初始化、预检查和备份脚本都会在 `/data` 未挂载时停止。后续重启服务器前先备份，重启后再检查挂载和容器状态。权限不匹配时，按[目录权限说明](deployment.md#root-持有配置deploy-可进入运维目录)核对对应文件和目录，不用 `chmod 777` 解决，也不要随意复用服务预留的 UID/GID。

初始化成功后，按[配置说明](configuration.md)固定镜像、准备证书凭据并启动，再配置[对象存储](storage.md)和 [Gitea](gitea.md)。
