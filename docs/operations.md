# 日常运维与资源检查

以下命令在部署服务器执行；项目目录为 `/app/file-code-stack`。

## 观察资源占用再调优

当前 Compose 为 Traefik、OtterIO、Gitea 分别设置 `256m`、`768m`、`1280m` 的内存上限，合计约 2.25 GiB，为 4 GB 主机留出系统和缓存空间。这是起步配置，2 GB 主机不能直接照用。

CPU 配额的合计可以超过物理核数，但不代表机器具备这些算力。并发 clone、上传和下载时，仍要观察实际资源竞争和响应时间。

Gitea 的 `/tmp` 暂时保留执行权限，避免影响 Git 和初始化。其他应用也先确认临时目录的用途，再决定是否设置 `noexec`。`pids_limit` 限制进程和线程任务数量，不等于网络连接或请求并发限制。

Compose 的日志轮转将每个容器的日志保留量控制在约 60 MiB，还要检查 journald、服务数据目录，以及 Docker/containerd 的镜像和快照占用。

```bash
sudo /app/file-code-stack/scripts/audit.sh
sudo docker system df

df -h /data /app/file-code-stack /var/lib/docker
df -i /data /app/file-code-stack

# 使用默认 containerd 存储目录时，另外检查它所在的文件系统。
if [ -d /var/lib/containerd ]; then
  df -h /var/lib/containerd
fi
```

`audit.sh` 用于查看容器运行身份、权限、挂载、端口和当前资源占用，不是完整的性能测试。

先监控磁盘用量、inode、OOMKilled 和容器重启次数。磁盘使用率可以从 70% 提醒、85% 告警起步，再根据增长速度调整，同时监测外部下载、Git clone、证书有效期和最近成功备份时间。

调优时结合 P95 延迟、CPU、内存和网络峰值观察。套餐标注的 200 Mbps 峰值带宽不等于持续保底带宽，不能只根据这个数值估算长期服务能力。

图片转换优先离线进行，并发先从 1–2 开始。Git clone 测试先从 2–4 个并发开始，再按结果调整，不直接提高所有服务的并发。

清理镜像和卷前先确认用途，不自动执行 `image prune -a`、`volume prune`，也不让 Watchtower 未经检查更新镜像。长期内存不足时，先检查实际负载和服务配额，再考虑增加主机内存；确实需要 swap 缓解短时峰值时，再评估性能和数据保护要求。
