"""Catch navigation regressions without network or deployment operations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_docs', ROOT / 'scripts/check-docs.py')
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocumentationTests(unittest.TestCase):
    def test_repository_navigation(self):
        _, errors = docs.check(ROOT)
        self.assertEqual(errors, [])

    def test_missing_file_and_anchor_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('[file](missing.md)\n[anchor](guide.md#absent)\n')
            (root / 'guide.md').write_text('# Present\n')
            _, errors = docs.check(root)
            self.assertEqual(len(errors), 2)

    def test_encoded_paths_and_duplicate_chinese_headings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('[中文](%E6%96%87%E6%A1%A3.md#配置-1)\n')
            (root / '文档.md').write_text('# 配置\n\n## 配置\n')
            self.assertEqual(docs.check(root)[1], [])

    def test_invalid_bash_is_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('```bash\nif true; then\n```\n')
            self.assertEqual(len(docs.check(root)[1]), 1)
            (root / 'README.md').write_text('```bash\ntouch should-not-exist\n```\n')
            self.assertEqual(docs.check(root)[1], [])
            self.assertFalse((root / 'should-not-exist').exists())

    def test_fenced_examples_are_not_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'README.md'
            path.write_text('~~~text\n[example](not-a-file.md)\n~~~\n')
            self.assertEqual(docs.check(root)[1], [])
            path.write_text('```bash\necho unfinished\n')
            self.assertEqual(len(docs.check(root)[1]), 1)


if __name__ == '__main__':
    unittest.main()
