"""Black-box renderer acceptance tests: real CLI, isolated files, independent expectations.

Run directly: python3 tests/test_render_cli.py
No network, Docker daemon, real .env or production data is used.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/render'
OUTPUTS = ('traefik.yaml', 'dynamic/routes.yaml', 'compose.yaml')
BASE = dict(
    TRAEFIK_IMAGE='traefik@sha256:' + 'a' * 64,
    OTTERIO_IMAGE='ghcr.io/soulteary/otterio@sha256:' + 'b' * 64,
    GITEA_IMAGE='gitea/gitea@sha256:' + 'c' * 64,
    IMAGE_DOMAIN='img.test.net', DOWNLOAD_DOMAIN='files.test.net',
    S3_DOMAIN='s3.test.net', GIT_DOMAIN='git.test.net', ACME_EMAIL='admin@test.net',
    TLS_MODE='http', UPLOAD_CIDRS='198.18.0.1/32,198.18.0.2/32',
    ADMIN_CIDRS='198.18.0.3/32', GIT_BOOTSTRAP='true',
    COMPOSE_FILE='compose.yaml:traefik/generated/compose.yaml')
PROVIDER_SECRETS = {
    'alidns': {'ALICLOUD_ACCESS_KEY_FILE': 'alidns_access_key',
               'ALICLOUD_SECRET_KEY_FILE': 'alidns_secret_key'},
    'cloudflare': {'CF_DNS_API_TOKEN_FILE': 'cloudflare_dns_api_token'}}


def expected_override(provider):
    if provider == 'http':
        return {'services': {}}
    secrets = PROVIDER_SECRETS[provider]
    return {'services': {'traefik': {
        'environment': {key: '/run/secrets/' + name for key, name in secrets.items()},
        'secrets': list(secrets.values())}},
        'secrets': {name: {'file': './secrets/' + name} for name in secrets.values()}}


class RenderCLITests(unittest.TestCase):
    selected_provider = None
    selected_case = None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'stack'
        (self.root / 'scripts').mkdir(parents=True)
        shutil.copy2(ROOT / 'scripts/render-config.py', self.root / 'scripts/render-config.py')
        shutil.copytree(ROOT / 'traefik/templates', self.root / 'traefik/templates')
        self.generated = self.root / 'traefik/generated'
        self.static = json.loads((FIXTURES / 'http-static.json').read_text())
        self.routes = json.loads((FIXTURES / 'routes.json').read_text())
        self.write_env(BASE)

    def write_env(self, values):
        (self.root / '.env').write_text('\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')

    def run_cli(self, *args, success=True):
        # Run outside the stack directory and supply hostile environment overrides:
        # the renderer must use its own literal .env, not cwd or exported settings.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TLS_MODE='bad',
                   TLS_DOMAINS='*.evil.net', S3_DOMAIN='evil.net')
        result = subprocess.run([sys.executable, str(self.root / 'scripts/render-config.py'), *args],
                                cwd=self.temp.name, env=env, text=True,
                                capture_output=True, timeout=15)
        message = f'{result.stdout}\n{result.stderr}'
        if success:
            self.assertEqual(result.returncode, 0, message)
            self.assertEqual(result.stderr, '')
        else:
            self.assertNotEqual(result.returncode, 0, message)
            self.assertNotIn('Traceback', message)
        return result

    def snapshot(self):
        return {name: ((self.generated / name).read_bytes(),
                       (self.generated / name).stat().st_mtime_ns,
                       (self.generated / name).stat().st_mode & 0o777)
                for name in OUTPUTS}

    def assert_outputs(self, static, routes, override):
        self.assertEqual({p.relative_to(self.generated).as_posix()
                          for p in self.generated.rglob('*') if p.is_file()}, set(OUTPUTS))
        for name, expected in zip(OUTPUTS, [static, routes, override]):
            with self.subTest(file=name):
                path = self.generated / name
                self.assertEqual(json.loads(path.read_text()), expected)
                self.assertNotIn('${', path.read_text())
                self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_baseline_complete_outputs_and_read_only_check(self):
        result = self.run_cli()
        self.assertIn('Configuration generated', result.stdout)
        self.assert_outputs(self.static, self.routes, {'services': {}})
        before = self.snapshot()
        result = self.run_cli('--check')
        self.assertIn('Generated configuration is current', result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.run_cli()
        self.assertEqual({k: v[0] for k, v in self.snapshot().items()},
                         {k: v[0] for k, v in before.items()})

    def test_certificate_and_bootstrap_matrix(self):
        single = [{'main': 'test.net', 'sans': ['*.test.net']}]
        multiple = single + [{'main': 'console.test.net', 'sans': ['*.console.test.net']}]
        hosts = [{'main': name} for name in ['img.test.net', 'files.test.net', 's3.test.net', 'git.test.net']]
        cases = [
            ('hosts', {}, None, ('http', 'alidns', 'cloudflare')),
            ('legacy', {'TLS_CERT_MODE': 'wildcard', 'WILDCARD_DOMAIN': '*.test.net'}, single, ('alidns', 'cloudflare')),
            ('explicit-hosts', {'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': ','.join(g['main'] for g in hosts)}, hosts, ('http', 'alidns', 'cloudflare')),
            ('multiple-wildcards', {'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': '*.test.net,*.console.test.net'}, multiple, ('alidns', 'cloudflare')),
            ('mixed-covered', {'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': 'img.test.net,*.test.net,git.console.test.net,*.console.test.net,files.other.net',
                               'GIT_DOMAIN': 'git.console.test.net', 'DOWNLOAD_DOMAIN': 'files.other.net'},
             multiple + [{'main': 'files.other.net'}], ('alidns', 'cloudflare'))]
        combinations = 0
        for label, changes, domains, providers in cases:
            if self.selected_case and label != self.selected_case:
                continue
            for provider in providers:
                if self.selected_provider and provider != self.selected_provider:
                    continue
                for bootstrap in ('true', 'false'):
                    combinations += 1
                    with self.subTest(case=label, provider=provider, bootstrap=bootstrap):
                        self.write_env(BASE | changes | {'TLS_MODE': provider, 'GIT_BOOTSTRAP': bootstrap})
                        self.run_cli()
                        static, routes = copy.deepcopy(self.static), copy.deepcopy(self.routes)
                        acme = static['certificatesResolvers']['le']['acme']
                        if provider != 'http':
                            del acme['httpChallenge']
                            acme['dnsChallenge'] = {'provider': provider}
                        if domains is not None:
                            static['entryPoints']['websecure']['http']['tls']['domains'] = domains
                        routers = routes['http']['routers']
                        if label == 'mixed-covered':
                            routers['git']['rule'] = 'Host(`git.console.test.net`)'
                            routers['downloads']['rule'] = 'Host(`files.other.net`) && PathPrefix(`/downloads/`) && (Method(`GET`) || Method(`HEAD`))'
                        if bootstrap == 'false':
                            del routers['git']['middlewares']
                        self.assert_outputs(static, routes, expected_override(provider))
                        before = self.snapshot()
                        self.run_cli('--check')
                        self.assertEqual(self.snapshot(), before)

        self.assertGreater(combinations, 0, 'No valid configuration combinations selected')
        if self.selected_case or self.selected_provider:
            print(f'Validated {combinations} combinations: '
                  f'case={self.selected_case or "all"}, provider={self.selected_provider or "all"}')

    def test_invalid_inputs_preserve_all_existing_outputs(self):
        self.run_cli()
        before = self.snapshot()
        cases = [
            {'TLS_MODE': 'bad'}, {'TLS_CERT_MODE': 'bad'},
            {'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': '*.test.net'},
            {'TLS_MODE': 'cloudflare', 'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': '*.other.net'},
            {'TLS_MODE': 'cloudflare', 'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': '*.test.net,'},
            {'TLS_MODE': 'cloudflare', 'TLS_CERT_MODE': 'custom', 'TLS_DOMAINS': '*.test.net,*.test.net'},
            {'UPLOAD_CIDRS': '0.0.0.0/0'}, {'ADMIN_CIDRS': '::/0'},
            {'S3_DOMAIN': 'git.test.net'}, {'TRAEFIK_IMAGE': 'traefik:latest'},
            {'COMPOSE_FILE': 'compose.yaml'}, {'GIT_BOOTSTRAP': 'yes'}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_env(BASE | changes)
                for args in [(), ('--check',)]:
                    self.run_cli(*args, success=False)
                    self.assertEqual(self.snapshot(), before)

    def test_check_rejects_stale_missing_and_tampered_outputs_without_writing(self):
        self.run_cli()
        self.write_env(BASE | {'TLS_MODE': 'cloudflare'})
        before = self.snapshot()
        self.run_cli('--check', success=False)
        self.assertEqual(self.snapshot(), before)
        self.run_cli()
        for name in OUTPUTS:
            with self.subTest(file=name):
                path = self.generated / name
                original = path.read_bytes()
                path.write_text('{}\n')
                before = self.snapshot()
                self.run_cli('--check', success=False)
                self.assertEqual(self.snapshot(), before)
                path.unlink()
                self.run_cli('--check', success=False)
                self.assertFalse(path.exists())
                path.write_bytes(original)
        self.run_cli('--check')

    def test_parser_template_and_cli_errors_have_no_partial_writes(self):
        self.run_cli()
        before = self.snapshot()
        for text in ['TLS_MODE=http\nTLS_MODE=alidns\n', 'S3_DOMAIN=${OTHER}\n', 'S3_DOMAIN="broken\n']:
            (self.root / '.env').write_text(text)
            self.run_cli(success=False)
            self.assertEqual(self.snapshot(), before)
        self.write_env(BASE)
        template = self.root / 'traefik/templates/routes.json'
        original = template.read_text()
        for placeholder in ('${s3_domain}', '${MISSING_VALUE}'):
            template.write_text(original.replace('${S3_DOMAIN}', placeholder))
            self.run_cli(success=False)
            self.assertEqual(self.snapshot(), before)
        template.write_text(original)
        self.run_cli('--unknown-option', success=False)
        self.assertEqual(self.snapshot(), before)
        (self.root / '.env').unlink()
        self.run_cli(success=False)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_first_run_and_check_do_not_create_outputs(self):
        self.run_cli('--check', success=False)
        self.assertFalse(self.generated.exists())
        self.write_env(BASE | {'TLS_MODE': 'bad'})
        self.run_cli(success=False)
        self.assertFalse(self.generated.exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['http', 'alidns', 'cloudflare'])
    parser.add_argument('--certificate-case', choices=[
        'hosts', 'legacy', 'explicit-hosts', 'multiple-wildcards', 'mixed-covered'])
    args = parser.parse_args()
    if args.provider == 'http' and args.certificate_case in ['legacy', 'multiple-wildcards', 'mixed-covered']:
        parser.error('The selected wildcard case requires a DNS-01 provider')
    RenderCLITests.selected_provider = args.provider
    RenderCLITests.selected_case = args.certificate_case
    selected = bool(args.provider or args.certificate_case)
    unittest.main(argv=[sys.argv[0]], verbosity=2,
                  defaultTest='RenderCLITests.test_certificate_and_bootstrap_matrix' if selected else None)

