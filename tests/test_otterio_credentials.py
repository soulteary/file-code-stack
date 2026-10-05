"""Verify Compose points the reviewed image entrypoint at modern secrets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_render_config import ROOT, render, inputs


@unittest.skipUnless(shutil.which('docker'), 'Compose CLI unavailable')
class CredentialsTests(unittest.TestCase):
    def test_official_entrypoint_and_absolute_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(ROOT / 'traefik/templates', root / 'traefik/templates')
            shutil.copy2(ROOT / 'compose.yaml', root / 'compose.yaml')
            values = inputs()
            (root / '.env').write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
            render.render(root)
            env = {k:v for k,v in os.environ.items() if k not in values and not k.startswith('COMPOSE_')}
            config = json.loads(subprocess.check_output(['docker','compose','config','--format','json'],cwd=root,env=env))
            service = config['services']['otterio']
            self.assertIsNone(service.get('entrypoint'))
            self.assertEqual(service['command'],['server','--address',':9000','--console-address',':9001','/data'])
            for key,name in [('ROOT_USER','root_user'),('ROOT_PASSWORD','root_password')]:
                self.assertEqual(service['environment'][f'OTTERIO_{key}_FILE'],f'/run/secrets/{name}')
            for key in ['ACCESS_KEY','SECRET_KEY']:
                self.assertEqual(service['environment'][f'OTTERIO_{key}_FILE'],'')
            self.assertNotIn('OTTERIO_ROOT_PASSWORD',service['environment'])
