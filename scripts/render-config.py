#!/usr/bin/env python3
"""Render Traefik and Compose inputs from literal .env values; stdlib only."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = 'compose.yaml:traefik/generated/compose.yaml'


def read_env(path):
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(.*)', line)
        if not match:
            raise ValueError(f'Invalid .env assignment at line {number}')
        key, value = match.groups()
        value = value.strip()
        if key in values:
            raise ValueError(f'Duplicate .env key: {key}')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'Unclosed quote: {key}')
            value = value[1:-1]
        if any(c in value for c in ['$','`','\\','\n','\r']):
            raise ValueError(f'Only literal values are supported: {key}')
        values[key] = value
    return values


def validated(values):
    values = dict(values)
    required = ['TRAEFIK_IMAGE', 'OTTERIO_IMAGE', 'GITEA_IMAGE', 'IMAGE_DOMAIN',
                'DOWNLOAD_DOMAIN', 'S3_DOMAIN', 'GIT_DOMAIN', 'ACME_EMAIL',
                'TLS_MODE', 'UPLOAD_CIDRS', 'ADMIN_CIDRS', 'GIT_BOOTSTRAP', 'COMPOSE_FILE']
    for key in required:
        if not values.get(key):
            raise ValueError(f'Missing value: {key}')
    for key in required[:3]:
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[0-9a-f]{64}', values[key]):
            raise ValueError(f'Expected a pinned image digest: {key}')
    values.setdefault('TLS_CERT_MODE', 'hosts')
    values.setdefault('WILDCARD_DOMAIN', '')
    domains = []
    for key in ['IMAGE_DOMAIN', 'DOWNLOAD_DOMAIN', 'S3_DOMAIN', 'GIT_DOMAIN']:
        domain = values[key].lower()
        if len(domain) > 253 or '.' not in domain or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
            for label in domain.split('.')
        ) or domain == 'example.com' or domain.endswith('.example.com'):
            raise ValueError(f'Expected a real DNS hostname: {key}')
        # Compose also reads GIT_DOMAIN; require the same canonical spelling.
        if domain != values[key]:
            raise ValueError(f'Use a lowercase hostname: {key}')
        domains.append(domain)
    if len(set(domains)) != len(domains):
        raise ValueError('The four service domains must be distinct')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values['ACME_EMAIL']) or values['ACME_EMAIL'].endswith('@example.com'):
        raise ValueError('Expected a real ACME_EMAIL')
    if values['TLS_MODE'] not in ['http', 'alidns', 'cloudflare']:
        raise ValueError('TLS_MODE must be http, alidns or cloudflare')
    if values['TLS_CERT_MODE'] not in ['hosts', 'wildcard']:
        raise ValueError('TLS_CERT_MODE must be hosts or wildcard')
    wildcard = values['WILDCARD_DOMAIN']
    if values['TLS_CERT_MODE'] == 'wildcard':
        if values['TLS_MODE'] == 'http':
            raise ValueError('Wildcard certificates require DNS-01: alidns or cloudflare')
        if not wildcard.startswith('*.'):
            raise ValueError('WILDCARD_DOMAIN must start with *.')
        base = wildcard[2:]
        if len(wildcard) > 253 or '.' not in base or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
            for label in base.split('.')
        ) or base == 'example.com' or base.endswith('.example.com'):
            raise ValueError('Expected a real lowercase wildcard DNS domain')
        if any(domain != base and domain.split('.', 1)[1] != base for domain in domains):
            raise ValueError('All service domains must be covered by WILDCARD_DOMAIN (apex or one subdomain level)')
    elif wildcard:
        raise ValueError('WILDCARD_DOMAIN must be empty in hosts mode')
    if values['GIT_BOOTSTRAP'] not in ['true', 'false']:
        raise ValueError('GIT_BOOTSTRAP must be true or false')
    if values['COMPOSE_FILE'] != COMPOSE_FILES:
        raise ValueError(f'COMPOSE_FILE must be {COMPOSE_FILES}')
    for key in ['UPLOAD_CIDRS', 'ADMIN_CIDRS']:
        networks = []
        for item in values[key].split(','):
            network = ipaddress.ip_network(item.strip(), strict=True)
            if network.prefixlen == 0:
                raise ValueError(f'Use a restricted real source network: {key}')
            if network.version == 4 and any(network.overlaps(ipaddress.ip_network(n)) for n in ['192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24']):
                raise ValueError(f'Replace documentation addresses: {key}')
            if network.version == 6 and network.overlaps(ipaddress.ip_network('2001:db8::/32')):
                raise ValueError(f'Replace documentation addresses: {key}')
            networks.append(str(network))
        values[key] = networks
    return values


def substitute(node, values):
    if isinstance(node, dict):
        return {k: substitute(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [substitute(v, values) for v in node]
    if not isinstance(node, str):
        return node
    exact = re.fullmatch(r'\$\{([A-Z][A-Z0-9_]*)\}', node)
    if exact:
        return values[exact[1]]
    return re.sub(r'\$\{([A-Z][A-Z0-9_]*)\}', lambda m: values[m[1]], node)


def build(values, root=ROOT):
    values = validated(values)
    static, routes = [substitute(json.loads((root / f'traefik/templates/{name}.json').read_text()), values)
                      for name in ['static', 'routes']]
    if values['TLS_CERT_MODE'] == 'wildcard':
        static['entryPoints']['websecure']['http']['tls']['domains'] = [
            {'main': values['WILDCARD_DOMAIN'][2:], 'sans': [values['WILDCARD_DOMAIN']]}]
    acme = static['certificatesResolvers']['le']['acme']
    override = {'services': {}}
    if values['TLS_MODE'] == 'http':
        acme['httpChallenge'] = {'entryPoint': 'web'}
    elif values['TLS_MODE'] == 'alidns':
        acme['dnsChallenge'] = {'provider': 'alidns'}
        override = {
            'services': {'traefik': {
                'environment': {'ALICLOUD_ACCESS_KEY_FILE': '/run/secrets/alidns_access_key',
                                'ALICLOUD_SECRET_KEY_FILE': '/run/secrets/alidns_secret_key'},
                'secrets': ['alidns_access_key', 'alidns_secret_key']}},
            'secrets': {key: {'file': f'./secrets/{key}'} for key in ['alidns_access_key', 'alidns_secret_key']}}
    else:
        acme['dnsChallenge'] = {'provider': 'cloudflare'}
        override = {
            'services': {'traefik': {
                'environment': {'CF_DNS_API_TOKEN_FILE': '/run/secrets/cloudflare_dns_api_token'},
                'secrets': ['cloudflare_dns_api_token']}},
            'secrets': {'cloudflare_dns_api_token': {'file': './secrets/cloudflare_dns_api_token'}}}
    if values['GIT_BOOTSTRAP'] == 'false':
        routes['http']['routers']['git'].pop('middlewares')
    # JSON is valid YAML; no third-party parser is required on the server.
    return {Path('traefik.yaml'): static, Path('dynamic/routes.yaml'): routes,
            Path('compose.yaml'): override}


def render(root=ROOT, check=False):
    files = build(read_env(root / '.env'), root)
    target = root / 'traefik/generated'
    encoded = {p: json.dumps(data, ensure_ascii=False, indent=2) + '\n' for p, data in files.items()}
    for path, content in encoded.items():
        if '${' in content:
            raise ValueError(f'Unresolved template placeholder in {path}; check templates')
    if check:
        for path, content in encoded.items():
            if not (target / path).is_file() or (target / path).read_text() != content:
                raise ValueError(f'Generated config is missing or stale: {path}; run render-config.py')
        return
    # Validate all inputs before writing. Replace each file atomically on the same filesystem.
    for path, content in encoded.items():
        output = target / path
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        temp = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=output.parent, delete=False) as handle:
                temp = Path(handle.name)
                handle.write(content)
            temp.chmod(0o644)
            os.replace(temp, output)
        finally:
            if temp and temp.exists():
                temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Reject missing or stale generated files')
    args = parser.parse_args()
    try:
        render(check=args.check)
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
    print('Generated configuration is current' if args.check else 'Configuration generated; restart Traefik for static changes')


if __name__ == '__main__':
    main()
