#!/usr/bin/env bash
# Requires an initialized, remote restic repository and /etc/file-code-stack-backup.env.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
umask 077
[[ $# -eq 0 || ( $# -eq 1 && $1 == --recover ) ]] || { echo 'Usage: backup.sh [--recover]'; exit 1; }
exec 9>/run/lock/file-code-stack-backup.lock
flock -n 9 || { echo 'Another backup is running'; exit 1; }
mountpoint -q /data || { echo "/data is not mounted"; exit 1; }
cd /app/file-code-stack
install -d -o root -g root -m 0700 /var/lib/file-code-stack
marker=/var/lib/file-code-stack/backup-backends-stopped
backends_running() {
  [[ "$(docker compose ps --status running --services | sort)" == "$(printf 'gitea\notterio\ntraefik\n')" ]]
}
restart_backends() {
  docker compose start otterio gitea && backends_running
}
if [[ ${1:-} == --recover ]]; then
  [[ -f $marker && ! -L $marker ]] || { echo 'No interrupted backup marker; inspect service state manually'; exit 1; }
  scripts/preflight.sh
  restart_backends || { echo 'Backend recovery failed; marker retained'; exit 1; }
  rm -- "$marker"
  echo 'Backends running; verify Git/S3 requests. Recovery does not confirm a successful backup.'
  exit 0
fi
[[ ! -e $marker && ! -L $marker ]] || { echo 'Interrupted backup marker exists; inspect services and run backup.sh --recover'; exit 1; }
[[ -f /etc/file-code-stack-backup.env ]] || { echo 'Missing backup environment'; exit 1; }
set -a
# shellcheck source=/dev/null
source /etc/file-code-stack-backup.env
set +a
: "${RESTIC_REPOSITORY:?}" "${RESTIC_PASSWORD_FILE:?}"
command -v restic >/dev/null
restic snapshots >/dev/null
backends_running || { echo 'Expected all three services running; repair before backup'; exit 1; }
# Persist intent before stopping: EXIT traps cannot recover from SIGKILL or power loss.
(set -C; printf '%s\n' 'Backend recovery may be required after an interrupted backup.' > "$marker")
finish() {
  result=$?
  trap - EXIT INT TERM
  if restart_backends; then
    rm -- "$marker" || result=1
  else
    echo 'Backend recovery failed; marker retained. Inspect services and run backup.sh --recover.' >&2
    result=1
  fi
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker compose stop otterio gitea
# ACME remains writable: exclude it here; separately copy it during an edge maintenance window.
restic backup /app/file-code-stack /data/otterio /data/gitea --tag file-code-stack
restart_backends
rm -- "$marker"
trap - EXIT INT TERM
# List snapshots only after service has been restored.
restic snapshots --latest 1
