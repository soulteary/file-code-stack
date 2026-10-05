from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IdentityTests(unittest.TestCase):
    def check(self, database, occupied):
        command = '''source "$1"
getent() { [[ "$1" = "$TEST_DATABASE" && "$2" = "$OCCUPIED_ID" ]]; }
check_service_identities
'''
        # Function references explicit environment values, never a real host database.
        return subprocess.run(['bash','-c',command,'test',str(ROOT/'scripts/service-identities.sh')],
                              env=os.environ|{'TEST_DATABASE':database,'OCCUPIED_ID':str(occupied)},capture_output=True)

    def test_cloud_account_ids_are_not_reserved(self):
        for database in ['passwd','group']:
            for uid in [1000,1001,1002]:
                self.assertEqual(self.check(database,uid).returncode,0)

    def test_every_reserved_user_or_group_is_rejected(self):
        for database in ['passwd','group']:
            for uid in [20001,20002,20003]:
                self.assertNotEqual(self.check(database,uid).returncode,0)

    def test_initializer_checks_before_changing_ownership(self):
        code=(ROOT/'scripts/init-state.sh').read_text()
        self.assertLess(code.index('check_service_identities'),code.index('install -d'))
