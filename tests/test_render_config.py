import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('render', ROOT / 'scripts/render-config.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def inputs():
    return dict(TRAEFIK_IMAGE='traefik@sha256:'+'a'*64,
                OTTERIO_IMAGE='ghcr.io/soulteary/otterio@sha256:'+'b'*64,
                GITEA_IMAGE='gitea/gitea@sha256:'+'c'*64,
                IMAGE_DOMAIN='img.test.net', DOWNLOAD_DOMAIN='files.test.net',
                S3_DOMAIN='s3.test.net', GIT_DOMAIN='git.test.net',
                ACME_EMAIL='admin@test.net', TLS_MODE='http',
                UPLOAD_CIDRS='198.18.0.1/32,198.18.0.2/32', ADMIN_CIDRS='198.18.0.3/32',
                GIT_BOOTSTRAP='true', COMPOSE_FILE=render.COMPOSE_FILES)


class ConfigTests(unittest.TestCase):
    def test_wildcard_dns_modes_and_exact_routes(self):
        for provider in ['alidns', 'cloudflare']:
            with self.subTest(provider=provider):
                files = render.build(inputs() | {'TLS_MODE': provider,
                    'TLS_CERT_MODE': 'wildcard', 'WILDCARD_DOMAIN': '*.test.net'})
                tls = files[Path('traefik.yaml')]['entryPoints']['websecure']['http']['tls']
                self.assertEqual(tls, {'certResolver': 'le',
                    'domains': [{'main': 'test.net', 'sans': ['*.test.net']}]})
                acme = files[Path('traefik.yaml')]['certificatesResolvers']['le']['acme']
                self.assertEqual(acme['dnsChallenge']['provider'], provider)
                self.assertNotIn('httpChallenge', acme)
                routers = files[Path('dynamic/routes.yaml')]['http']['routers']
                self.assertEqual(routers['s3']['rule'], 'Host(`s3.test.net`)')
                for router in routers.values():
                    self.assertNotIn('tls', router)
                    self.assertNotIn('*', router['rule'])

    def test_wildcard_accepts_apex_but_not_nested_or_unrelated_domains(self):
        values = inputs() | {'TLS_MODE': 'cloudflare', 'TLS_CERT_MODE': 'wildcard',
                             'WILDCARD_DOMAIN': '*.test.net'}
        render.build(values | {'GIT_DOMAIN': 'test.net'})
        for domain in ['git.other.net', 'git.sub.test.net']:
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                render.build(values | {'GIT_DOMAIN': domain})

    def test_reject_invalid_certificate_selections(self):
        values = inputs() | {'TLS_MODE': 'alidns', 'TLS_CERT_MODE': 'wildcard',
                             'WILDCARD_DOMAIN': '*.test.net'}
        invalid = [{'TLS_MODE': 'http'}, {'TLS_CERT_MODE': 'invalid'},
                   {'TLS_CERT_MODE': 'hosts'}, {'WILDCARD_DOMAIN': ''},
                   {'WILDCARD_DOMAIN': '*.*.test.net'}, {'WILDCARD_DOMAIN': '*.Test.net'},
                   {'WILDCARD_DOMAIN': '*.example.com'}, {'WILDCARD_DOMAIN': 'test.net'},
                   {'WILDCARD_DOMAIN': '*.test.net`) || Host(`evil.net'}]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                render.build(values | change)
        self.assertNotIn('domains', render.build(inputs())[Path('traefik.yaml')]
                         ['entryPoints']['websecure']['http']['tls'])

    def test_http_and_security_boundaries(self):
        files = render.build(inputs())
        static = files[Path('traefik.yaml')]
        acme = static['certificatesResolvers']['le']['acme']
        self.assertEqual(acme['httpChallenge'], {'entryPoint': 'web'})
        self.assertNotIn('dnsChallenge', acme)
        self.assertEqual(static['entryPoints']['health']['address'], '127.0.0.1:8082')
        self.assertEqual(set(static['providers']), {'file'})
        self.assertEqual(static['entryPoints']['websecure']['http']['tls']['certResolver'], 'le')
        routes = files[Path('dynamic/routes.yaml')]['http']
        self.assertEqual(routes['routers']['s3']['rule'], 'Host(`s3.test.net`)')
        for router in routes['routers'].values():
            self.assertNotIn('tls', router)  # Even an empty section overrides entryPoint TLS defaults.
        for name, bucket in [('images', 'images'), ('downloads', 'downloads')]:
            rule = routes['routers'][name]['rule']
            self.assertIn(f'PathPrefix(`/{bucket}/`)', rule)
            self.assertIn('Method(`GET`) || Method(`HEAD`)', rule)
        self.assertTrue(routes['services']['otterio']['loadBalancer']['passHostHeader'])
        self.assertEqual(routes['routers']['git']['middlewares'], ['git-bootstrap-ips'])
        self.assertEqual(routes['middlewares']['uploader-ips']['ipAllowList']['sourceRange'], ['198.18.0.1/32','198.18.0.2/32'])
        self.assertEqual(files[Path('compose.yaml')], {'services': {}})

    def test_alidns_and_bootstrap_release(self):
        files = render.build(inputs() | {'TLS_MODE': 'alidns', 'GIT_BOOTSTRAP': 'false'})
        acme = files[Path('traefik.yaml')]['certificatesResolvers']['le']['acme']
        self.assertNotIn('httpChallenge', acme)
        self.assertEqual(acme['dnsChallenge']['provider'], 'alidns')
        service = files[Path('compose.yaml')]['services']['traefik']
        self.assertNotIn('command', service)
        self.assertEqual(service['environment']['ALICLOUD_ACCESS_KEY_FILE'], '/run/secrets/alidns_access_key')
        self.assertNotIn('middlewares', files[Path('dynamic/routes.yaml')]['http']['routers']['git'])

    def test_digit_in_variable_name(self):
        self.assertEqual(render.substitute('${S3_DOMAIN}', {'S3_DOMAIN': 's3.test.net'}), 's3.test.net')
        self.assertEqual(render.substitute('Host(`${S3_DOMAIN}`)', {'S3_DOMAIN': 's3.test.net'}), 'Host(`s3.test.net`)')

    def test_unresolved_placeholder_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'traefik/templates').mkdir(parents=True)
            for source in (ROOT / 'traefik/templates').glob('*.json'):
                (root / 'traefik/templates' / source.name).write_text(source.read_text())
            (root / '.env').write_text('\n'.join(f'{k}={v}' for k,v in inputs().items()))
            render.render(root)
            output = root / 'traefik/generated/dynamic/routes.yaml'
            before = output.read_bytes()
            template = root / 'traefik/templates/routes.json'
            template.write_text(template.read_text().replace('${S3_DOMAIN}', '${s3_domain}'))
            for check in [False, True]:
                with self.assertRaisesRegex(ValueError, 'Unresolved template placeholder'):
                    render.render(root, check=check)
            self.assertEqual(output.read_bytes(), before)

    def test_cloudflare_token_file(self):
        files = render.build(inputs() | {'TLS_MODE': 'cloudflare'})
        acme = files[Path('traefik.yaml')]['certificatesResolvers']['le']['acme']
        self.assertEqual(acme['dnsChallenge'], {'provider': 'cloudflare'})
        self.assertNotIn('httpChallenge', acme)
        service = files[Path('compose.yaml')]['services']['traefik']
        self.assertEqual(service['environment'], {'CF_DNS_API_TOKEN_FILE': '/run/secrets/cloudflare_dns_api_token'})
        self.assertEqual(service['secrets'], ['cloudflare_dns_api_token'])
        self.assertNotIn('command', service)

    def test_reject_unsafe_or_inconsistent_inputs(self):
        for key, value in [('GIT_DOMAIN', 'git.test.net`) || Host(`evil.net'),
                           ('S3_DOMAIN', 'git.test.net'), ('IMAGE_DOMAIN', 'img.example.com'),
                           ('TLS_MODE', 'dns'), ('UPLOAD_CIDRS', '0.0.0.0/0'),
                           ('UPLOAD_CIDRS', '203.0.113.10/32'), ('ADMIN_CIDRS', '::/0'),
                           ('ADMIN_CIDRS', '2001:db8::/32'), ('GIT_BOOTSTRAP', 'yes'),
                           ('COMPOSE_FILE', 'compose.yaml:compose.alidns.yaml'),
                           ('TRAEFIK_IMAGE', 'traefik:latest')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                render.build(inputs() | {key: value})

    def test_staleness_and_invalid_input_preserve_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'traefik/templates').mkdir(parents=True)
            for source in (ROOT / 'traefik/templates').glob('*.json'):
                (root / 'traefik/templates' / source.name).write_text(source.read_text())
            env = root / '.env'
            env.write_text('\n'.join(f'{k}={v}' for k,v in inputs().items()))
            render.render(root)
            render.render(root, check=True)
            before = (root / 'traefik/generated/traefik.yaml').read_bytes()
            env.write_text(env.read_text().replace('TLS_MODE=http','TLS_MODE=bad'))
            with self.assertRaises(ValueError): render.render(root)
            self.assertEqual(before, (root / 'traefik/generated/traefik.yaml').read_bytes())
            env.write_text('\n'.join(f'{k}={v}' for k,v in (inputs() | {'TLS_MODE':'alidns'}).items()))
            with self.assertRaises(ValueError): render.render(root, check=True)
            render.render(root)
            render.render(root, check=True)

    def test_switching_modes_removes_previous_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'traefik/templates').mkdir(parents=True)
            for source in (ROOT / 'traefik/templates').glob('*.json'):
                (root / 'traefik/templates' / source.name).write_text(source.read_text())
            for mode in ['cloudflare', 'alidns', 'http', 'cloudflare']:
                values = inputs() | {'TLS_MODE': mode}
                (root / '.env').write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
                render.render(root)
                render.render(root, check=True)
                import json
                actual = json.loads((root / 'traefik/generated/compose.yaml').read_text())
                self.assertEqual(actual, render.build(values)[Path('compose.yaml')])

    def test_literal_env_parser(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('# comment\nGIT_DOMAIN="git.test.net"\n')
            self.assertEqual(render.read_env(path)['GIT_DOMAIN'], 'git.test.net')
            for text in ['GIT_DOMAIN=a\nGIT_DOMAIN=b', 'A=${OTHER}', 'A=`command`', 'A="broken']:
                path.write_text(text)
                with self.assertRaises(ValueError): render.read_env(path)


if __name__ == '__main__':
    unittest.main()
