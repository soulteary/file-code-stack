#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
mountpoint -q /data || { echo "/data must be a mounted filesystem"; exit 1; }
cd /app/file-code-stack
# shellcheck source=/dev/null
source scripts/service-identities.sh
check_service_identities
umask 077
install -d -m 0700 secrets
install -d -m 0750 -o 20002 -g 20002 /data/otterio
install -d -m 0750 -o 20003 -g 20003 /data/traefik/acme
install -d -m 0750 -o 20001 -g 20001 /data/gitea/data /data/gitea/config
[[ -e secrets/root_user ]] || printf 'file-code-root\n' > secrets/root_user
[[ -e secrets/root_password ]] || openssl rand -hex 32 > secrets/root_password
chown 20002:20002 secrets/root_user secrets/root_password
chmod 0400 secrets/root_user secrets/root_password
[[ -e /data/traefik/acme/acme.json ]] || printf '{}' > /data/traefik/acme/acme.json
chown 20003:20003 /data/traefik/acme/acme.json
chmod 0600 /data/traefik/acme/acme.json
[[ -e .env ]] || cp .env.example .env
chmod 0600 .env
echo 'State prepared; existing credentials preserved. Configure .env, then run scripts/render-config.py before start.'
