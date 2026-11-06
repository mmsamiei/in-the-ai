import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config import load_env, setting, database_path, ROOT


class ConfigTests(unittest.TestCase):
    def test_literals_are_not_executed_or_expanded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('# comment\nEMPTY=\nA="hello world"\nB=literal$HOME\nC="$(false)"\n')
            self.assertEqual(load_env(path), dict(EMPTY='', A='hello world', B='literal$HOME', C='$(false)'))

    def test_environment_overrides_file(self):
        with patch('config.load_env', return_value={'EXAMPLE_SETTING': 'file'}):
            with patch.dict(os.environ, {'EXAMPLE_SETTING': 'environment'}):
                self.assertEqual(setting('EXAMPLE_SETTING'), 'environment')

    def test_database_paths_are_relative_to_repository(self):
        with patch('config.setting', return_value='custom.sqlite3'):
            self.assertEqual(database_path(), ROOT / 'custom.sqlite3')
        with patch('config.setting', return_value='/tmp/custom.sqlite3'):
            self.assertEqual(database_path(), Path('/tmp/custom.sqlite3'))

    def test_parse_error_does_not_echo_secret_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('TOKEN="private-value')
            with self.assertRaises(ValueError) as error:
                load_env(path)
            self.assertNotIn('private-value', str(error.exception))
