"""Capture tokenization must preserve Windows path suffixes and errors."""
import unittest
from pathlib import PureWindowsPath

from capture_wt_core_b07_paths import tokenize


class Tokens(unittest.TestCase):
    def test_windows_root_tokens_keep_path_suffix(self):
        root = PureWindowsPath(r'C:\synthetic\case')
        self.assertEqual(tokenize(str(root / '.mir' / 'memory.db'), root),
                         r'{ROOT}\.mir\memory.db')
        self.assertEqual(tokenize(r'D:\elsewhere\file', root), r'D:\elsewhere\file')
        self.assertEqual(tokenize(r'C:\elsewhere\file', root), r'{DRIVE}\elsewhere\file')

    def test_json_escaped_root_without_separator_rewrite(self):
        root = PureWindowsPath(r'C:\synthetic\case')
        self.assertEqual(tokenize(r'C:\\synthetic\\case\\.mir\\memory.db', root),
                         r'{ROOT}\\.mir\\memory.db')
        self.assertEqual(tokenize('memory database is unavailable', root),
                         'memory database is unavailable')
