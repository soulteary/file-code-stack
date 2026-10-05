#!/usr/bin/env bash
set -euo pipefail
cd /app/file-code-stack
docker compose ps
docker compose ps -q | while read -r cid; do
  docker inspect --format '{{.Name}} user={{.Config.User}} privileged={{.HostConfig.Privileged}} readonly={{.HostConfig.ReadonlyRootfs}} caps={{json .HostConfig.CapDrop}} security={{json .HostConfig.SecurityOpt}} ports={{json .HostConfig.PortBindings}} apparmor={{.AppArmorProfile}}' "$cid"
  docker inspect --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' "$cid"
done
docker stats --no-stream
ss -lntp
