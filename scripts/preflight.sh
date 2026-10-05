#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
mountpoint -q /data || { echo '/data is not mounted'; exit 1; }
cd /app/file-code-stack
# shellcheck source=/dev/null
source scripts/service-identities.sh
check_service_identities
python3 scripts/render-config.py --check
python3 - <<'PY'
import importlib.util
import pathlib
import subprocess
import json
import sys
spec = importlib.util.spec_from_file_location('render', 'scripts/render-config.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)
values = render.validated(render.read_env(pathlib.Path('.env')))
secrets = {'root_user': 20002, 'root_password': 20002}
if values['TLS_MODE'] == 'alidns':
    secrets.update({'alidns_access_key': 20003, 'alidns_secret_key': 20003})
if values['TLS_MODE'] == 'cloudflare':
    secrets['cloudflare_dns_api_token'] = 20003
for name, uid in secrets.items():
    p = pathlib.Path('secrets') / name
    if not p.is_file() or not p.stat().st_size:
        sys.exit('Missing secret: '+name)
    st = p.stat()
    if st.st_uid != uid or st.st_gid != uid or st.st_mode & 0o077 or not st.st_mode & 0o400:
        sys.exit('Secret must be owner-readable, private and owned by UID '+str(uid)+': '+name)
if pathlib.Path('.env').stat().st_mode & 0o077:
    sys.exit('.env must not be group/world accessible')
config = json.loads(subprocess.check_output(['docker','compose','config','--format','json']))
for service, key in [('traefik','TRAEFIK_IMAGE'), ('otterio','OTTERIO_IMAGE'), ('gitea','GITEA_IMAGE')]:
    if config['services'][service]['image'] != values[key]:
        sys.exit('Compose image differs from .env; clear environment overrides: '+key)
for service, uid in [('gitea',20001), ('otterio',20002), ('traefik',20003)]:
    if config['services'][service]['user'] != f'{uid}:{uid}':
        sys.exit('Service identity differs from the reserved UID/GID: '+service)
for directory, uid in [('/data/gitea/data',20001), ('/data/gitea/config',20001),
                       ('/data/otterio',20002), ('/data/traefik/acme',20003)]:
    path = pathlib.Path(directory)
    if not path.is_dir() or path.stat().st_uid != uid or path.stat().st_gid != uid:
        sys.exit('Data directory ownership differs from reserved UID/GID: '+directory)
if config['services']['gitea']['environment']['GITEA__server__DOMAIN'] != values['GIT_DOMAIN']:
    sys.exit('Compose Git domain differs from .env; clear environment overrides')
if config['services']['traefik'].get('command'):
    sys.exit('Traefik must load static configuration exclusively from its file')
expected = ['alidns_access_key', 'alidns_secret_key'] if values['TLS_MODE'] == 'alidns' else []
if values['TLS_MODE'] == 'cloudflare':
    expected = ['cloudflare_dns_api_token']
if sorted(s['source'] for s in config['services']['traefik'].get('secrets', [])) != expected:
    sys.exit('Compose secrets do not match TLS_MODE; check COMPOSE_FILE')
if values['TLS_MODE'] == 'cloudflare':
    environment = config['services']['traefik'].get('environment', {})
    if environment.get('CF_DNS_API_TOKEN_FILE') != '/run/secrets/cloudflare_dns_api_token':
        sys.exit('Cloudflare token path differs from generated configuration')
print('Required inputs and merged Compose configuration verified')
PY
docker info --format '{{json .SecurityOptions}}'
df -h /data /app/file-code-stack /var/lib/docker
echo 'Review AppArmor/seccomp, DNS, cloud firewall and off-site backup before public launch.'
