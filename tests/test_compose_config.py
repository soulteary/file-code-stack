"""Check merged deployment boundaries without connecting to Docker daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_render_config import ROOT, render, inputs


@unittest.skipUnless(shutil.which('docker'), 'Docker Compose CLI is not installed')
class ComposeTests(unittest.TestCase):
    def test_all_certificate_modes(self):
        for mode in ['http', 'alidns', 'cloudflare']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                shutil.copytree(ROOT / 'traefik/templates', root / 'traefik/templates')
                shutil.copy2(ROOT / 'compose.yaml', root / 'compose.yaml')
                values = inputs() | {'TLS_MODE': mode}
                (root / '.env').write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
                render.render(root)
                env = {k:v for k,v in os.environ.items() if k not in values and not k.startswith('COMPOSE_')}
                config = json.loads(subprocess.check_output(
                    ['docker','compose','config','--format','json'], cwd=root, env=env))
                services = config['services']
                self.assertEqual(set(services), {'traefik','gitea','otterio'})
                self.assertFalse(services['traefik'].get('command'))
                for service, uid in [('gitea',20001),('otterio',20002),('traefik',20003)]:
                    self.assertEqual(services[service]['user'], f'{uid}:{uid}')
                for service, uid in [('gitea',20001),('otterio',20002)]:
                    self.assertIn(f'uid={uid},gid={uid}', services[service]['tmpfs'][0])
                self.assertEqual(services['traefik']['healthcheck']['test'][1:3], ['traefik','healthcheck'])
                self.assertEqual(set(services['traefik']['networks']), {'s3_proxy','git_proxy'})
                self.assertEqual(set(services['gitea']['networks']), {'git_proxy'})
                self.assertEqual(set(services['otterio']['networks']), {'s3_proxy'})
                for name in ['gitea','otterio']:
                    for port in services[name]['ports']:
                        self.assertEqual(port['host_ip'], '127.0.0.1')
                self.assertEqual({str(p['published']) for p in services['traefik']['ports']}, {'80','443'})
                self.assertNotIn('docker.sock', json.dumps(config))
                self.assertEqual(services['gitea']['environment']['GITEA__server__DOMAIN'], values['GIT_DOMAIN'])
                expected = {'alidns_access_key','alidns_secret_key'} if mode == 'alidns' else set()
                if mode == 'cloudflare':
                    expected = {'cloudflare_dns_api_token'}
                    self.assertEqual(services['traefik']['environment']['CF_DNS_API_TOKEN_FILE'], '/run/secrets/cloudflare_dns_api_token')
                self.assertEqual({s['source'] for s in services['traefik'].get('secrets', [])}, expected)
                for secret in expected:
                    self.assertEqual(Path(config['secrets'][secret]['file']).resolve(), (root / 'secrets' / secret).resolve())


if __name__ == '__main__':
    unittest.main()
