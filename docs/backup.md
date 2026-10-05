# 异地加密备份与中断恢复

备份使用 restic，目标选择另一账户的 COS/S3 或异地仓库，不把本机 OtterIO 的桶作为唯一副本。备份账号与源站管理员分开，只授权备份仓库所需的范围。

如果源主机保存着可以删除备份的凭据，主机被攻破后，远端备份也可能被删除。因此，还需要在目标端安排版本保留、经过验证的不可变策略，或独立离线副本。具体方案要与 restic 的写入、锁文件和清理操作兼容。

## 1 准备备份凭据

将备份配置保存到 `/etc/file-code-stack-backup.env`，归 root 所有，权限为 0600。实际密钥在受控位置准备，再安装到服务器，不写进公开文章和仓库：

```bash
sudo install -o root -g root -m 0600 \
  /受控临时路径/backup.env \
  /etc/file-code-stack-backup.env

# 确认安装成功后，删除临时明文副本。
```

配置内容如下，替换为实际端点、桶、访问键和 region：

```bash
RESTIC_REPOSITORY='s3:https://独立对象存储端点/备份桶/file-code-stack'
RESTIC_PASSWORD_FILE='/etc/file-code-stack-restic-password'
AWS_ACCESS_KEY_ID='备份专用访问键'
AWS_SECRET_ACCESS_KEY='备份专用秘密键'
AWS_DEFAULT_REGION='目标region'
```

这个文件会被 root shell 通过 `source` 加载，属于可执行的 shell 配置，与按字面量读取的项目 `.env` 不同。它必须由 root 持有，普通账号不能修改，只包含自己确认过的变量赋值。

首次创建备份密码时执行下面的命令。文件已经存在时停止，不覆盖原密码：

```bash
sudo bash <<'EOF'
set -euo pipefail
umask 077

password_file=/etc/file-code-stack-restic-password

if [ -e "$password_file" ] || [ -L "$password_file" ]; then
  printf '%s\n' '备份密码文件已存在，请核对，不重新生成。'
  exit 1
fi

openssl rand -hex 32 > "$password_file"
chown root:root "$password_file"
chmod 0600 "$password_file"
EOF
```

将备份密码另存到安全的密码管理器或离线介质。恢复备份需要这个密码，只有对象存储访问键还不够。不要把唯一一份密码留在源主机上。

## 2 初始化仓库并执行首次备份

下面只用于尚未初始化的新 restic 仓库：

```bash
sudo bash <<'EOF'
set -euo pipefail

set -a
source /etc/file-code-stack-backup.env
set +a

restic init
restic snapshots
EOF
```

已有仓库不再执行 `restic init`，先用对应凭据运行 `restic snapshots`，确认能够访问。

接下来执行项目的备份脚本：

```bash
sudo /app/file-code-stack/scripts/backup.sh
```

脚本会检查 `/data` 挂载、远端仓库访问，以及三个服务的运行状态。检查通过后，停止 OtterIO 和 Gitea，直接使用 restic 备份：

- `/app/file-code-stack`：配置、脚本和秘密文件。
- `/data/otterio`：对象及相关数据。
- `/data/gitea`：数据库、仓库和 Gitea 配置。

restic 完成后，脚本启动两个后端并检查三个容器是否处于运行状态。备份失败时，退出处理也会尝试恢复后端；备份命令仍返回失败，不会把服务恢复成功当成备份成功。容器运行不等于业务可用，仍需检查 Git 和 S3 请求：

```bash
cd /app/file-code-stack
sudo docker compose ps
sudo docker compose logs --tail 100 otterio gitea
```

脚本在停服前写入 `/var/lib/file-code-stack/backup-backends-stopped`，后端恢复并通过运行状态检查后删除。这个标记不保存密钥，用于发现未完成的恢复；标记存在时，下一次普通备份会停止，避免直接掩盖中断状态。

退出处理无法应对断电、`SIGKILL` 或宿主机故障。两个后端使用 `unless-stopped`，备份时主动停止后，不能依赖机器重启自动恢复。出现中断标记时，先查看日志、核对 `/data` 的挂载来源和配置，再运行：

```bash
sudo /app/file-code-stack/scripts/backup.sh --recover

cd /app/file-code-stack
sudo docker compose ps
sudo docker compose logs --tail 100 otterio gitea
```

恢复模式会取得与备份相同的锁，执行预检查，启动后端并检查运行状态；失败时保留标记。它不重试备份，也不能证明上次备份成功。恢复后验证实际请求，检查远端快照，再重新安排备份。没有标记但服务仍不可用时，继续按日志排查，不以标记是否存在代替服务监控。

停服是为了避免备份期间继续写入 SQLite、Git 仓库和对象目录。停服时间包含 restic 扫描和上传所需的时间，没有先复制到本地暂存目录。

Traefik 继续运行，但未命中 CDN 缓存的请求可能出现后端不可用错误，所以应选择低峰时间。数据量增大、停服时间无法接受时，再改用经过验证的一致性快照方案。

## 3 单独备份证书状态

当前备份脚本不包含 `/data/traefik/acme`，因为运行中的 Traefik 可能更新 ACME 文件。

需要保留证书状态时，在维护窗口短暂停止 Traefik，将 `acme.json` 复制到 root 私有目录，然后恢复 Traefik，再对这份副本执行加密备份。复制和重启过程也需要安排失败处理，确保入口服务恢复。

`acme.json` 包含 ACME 账号和证书私钥，副本保持 root 所有、0600，不放进公开仓库。恢复到正式服务目录时，再按项目要求设置为 `20003:20003`、0600。

没有这份备份时，可以重新申请证书，但可能遇到 CA 速率限制。Cloudflare 或 AliDNS 的续期凭据位于项目的 `secrets` 目录，会随项目配置备份；恢复后仍要确认这些凭据有效。

## 4 配置定时任务

首次备份成功后，再安装定时任务：

```bash
(
set -euo pipefail

sudo install -o root -g root -m 0644 \
  /app/file-code-stack/scripts/file-code-stack-backup.service \
  /etc/systemd/system/file-code-stack-backup.service

sudo install -o root -g root -m 0644 \
  /app/file-code-stack/scripts/file-code-stack-backup.timer \
  /etc/systemd/system/file-code-stack-backup.timer

sudo systemctl daemon-reload
sudo systemctl enable --now file-code-stack-backup.timer

sudo systemctl list-timers file-code-stack-backup.timer
sudo journalctl -u file-code-stack-backup.service --no-pager
)
```

定时器按北京时间每天 04:10 调度，并增加最多 10 分钟的随机延迟。它设置了 `Persistent=true`，机器关机期间错过的任务可能在下次启动后补执行，需要考虑这次停服对业务的影响。

失败会记录到 journal，不会自动发送通知。接入自己的监控，检查任务执行结果、后端恢复状态和最近一次成功快照，不能只确认 timer 处于启用状态。

保留策略可以先采用最近 7 个日备份、4 个周备份、6 个备份月份。脚本不自动执行 `forget` 或 `prune`，完成恢复演练后，再单独安排清理。

定期运行 `restic check`，并安排完整或分批的数据读取检查。读取量、时间和对象存储费用按仓库大小评估。检查命令同样需要先加载备份环境，restic 的完整说明可以参考其[官方文档](https://restic.readthedocs.io/)。

恢复和升级步骤见[部署与运维实践](upgrade.md)。
