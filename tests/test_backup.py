"""Exercise backup failure and recovery with fake commands and temporary paths."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'project'
        (self.project / 'scripts').mkdir(parents=True)
        (self.root / 'bin').mkdir()
        self.marker = self.root / 'state/backup-backends-stopped'
        (self.root / 'backup.env').write_text("RESTIC_REPOSITORY=test\nRESTIC_PASSWORD_FILE=test\n")
        # The production script has fixed root-owned paths. Redirect them only in this
        # disposable copy, and omit the UID check; no test touches a host service.
        source = (ROOT / 'scripts/backup.sh').read_text()
        source = source.replace("[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }\n", '')
        for old, new in [('/app/file-code-stack', self.project),
                         ('/etc/file-code-stack-backup.env', self.root / 'backup.env'),
                         ('/run/lock/file-code-stack-backup.lock', self.root / 'backup.lock'),
                         ('/var/lib/file-code-stack', self.root / 'state'),
                         ('/data', self.root / 'data')]:
            source = source.replace(old, str(new))
        self.script = self.project / 'scripts/backup.sh'
        self.script.write_text(source)
        stub = '''#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import sys
root = Path(os.environ['TEST_ROOT'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / 'calls').open('a') as log:
    log.write(name + ' ' + ' '.join(args) + '\\n')
if name == 'docker':
    if args[1] == 'ps' and not (root / 'stopped').exists():
        print('traefik\\notterio\\ngitea')
    elif args[1] == 'stop':
        (root / 'stopped').touch()
    elif args[1] == 'start':
        if (root / 'fail-start').exists():
            sys.exit(9)
        (root / 'stopped').unlink(missing_ok=True)
elif name == 'restic' and args[0] == 'backup':
    if (root / 'fail-backup').exists():
        sys.exit(42)
    if (root / 'terminate').exists():
        os.kill(os.getppid(), signal.SIGTERM)
    if (root / 'kill').exists():
        os.kill(os.getppid(), signal.SIGKILL)
elif name == 'install':
    Path(args[-1]).mkdir(parents=True, exist_ok=True)
elif name == 'flock' and (root / 'locked').exists():
    sys.exit(1)
elif name == 'preflight.sh' and (root / 'fail-preflight').exists():
    sys.exit(1)
'''
        for name in ['docker', 'restic', 'mountpoint', 'install', 'flock']:
            path = self.root / 'bin' / name
            path.write_text(stub)
            path.chmod(0o755)
        preflight = self.project / 'scripts/preflight.sh'
        preflight.write_text(stub)
        preflight.chmod(0o755)

    def run_backup(self, *args):
        return subprocess.run(['bash', str(self.script), *args],
                              env=os.environ | {'TEST_ROOT': str(self.root),
                                                'PATH': str(self.root / 'bin') + ':' + os.environ['PATH']},
                              capture_output=True, text=True, timeout=10)

    def calls(self):
        return (self.root / 'calls').read_text()

    def test_success_restores_backends_and_clears_marker(self):
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'stopped').exists())
        self.assertLess(self.calls().index('docker compose stop'), self.calls().index('restic backup'))
        self.assertLess(self.calls().index('restic backup'), self.calls().index('docker compose start'))

    def test_backup_failure_is_not_hidden_by_successful_recovery(self):
        (self.root / 'fail-backup').touch()
        self.assertEqual(self.run_backup().returncode, 42)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'stopped').exists())

    def test_failed_start_retains_marker_until_explicit_recovery(self):
        (self.root / 'fail-start').touch()
        self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertTrue(self.marker.exists())
        before = self.calls()
        self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertNotIn('restic', self.calls()[len(before):])
        (self.root / 'fail-start').unlink()
        self.assertEqual(self.run_backup('--recover').returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'stopped').exists())

    def test_sigterm_restores_backends_but_reports_interruption(self):
        (self.root / 'terminate').touch()
        self.assertEqual(self.run_backup().returncode, 143)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'stopped').exists())

    def test_sigkill_leaves_marker_and_can_recover_without_restic_environment(self):
        (self.root / 'kill').touch()
        self.assertEqual(self.run_backup().returncode, -signal.SIGKILL)
        self.assertTrue(self.marker.exists())
        (self.root / 'backup.env').unlink()
        self.assertEqual(self.run_backup('--recover').returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_recovery_obeys_lock_and_preflight_and_requires_marker(self):
        self.assertNotEqual(self.run_backup('--recover').returncode, 0)
        self.marker.write_text('interrupted')
        for failure in ['locked', 'fail-preflight']:
            with self.subTest(failure=failure):
                (self.root / failure).touch()
                before = self.calls()
                self.assertNotEqual(self.run_backup('--recover').returncode, 0)
                self.assertTrue(self.marker.exists())
                self.assertNotIn('docker compose start', self.calls()[len(before):])
                (self.root / failure).unlink()


if __name__ == '__main__':
    unittest.main()
