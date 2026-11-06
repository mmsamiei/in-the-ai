import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from inference import generate
from process import prompt_for, ROOT


class InferenceTests(unittest.TestCase):
    def config(self, folder, data):
        path = Path(folder) / 'inference.json'
        path.write_text(json.dumps(data))
        return path

    def test_existing_codex_backend_remains_default(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self.config(folder, {'backend': 'codex', 'timeout_seconds': 90})
            with patch('inference.codex_generate', return_value={'ok': True}) as backend:
                self.assertEqual(generate('prompt', {'type': 'object'}, config), {'ok': True})
                backend.assert_called_once_with('prompt', {'type': 'object'}, timeout=90,
                                                model=None, reasoning_effort=None)

    def test_pinned_terra_and_light_are_forwarded(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self.config(folder, {'backend': 'codex', 'model': 'gpt-6.1-terra',
                                          'reasoning_effort': 'low'})
            with patch('inference.codex_generate', return_value={'ok': True}) as backend:
                generate('prompt', {}, config)
                backend.assert_called_once_with('prompt', {}, timeout=240,
                                                model='gpt-6.1-terra', reasoning_effort='low')

    def test_command_backend_protocol_and_environment(self):
        code = '''import json,os,sys
r=json.load(sys.stdin)
print(json.dumps(dict(version=r['protocol_version'],prompt=r['prompt'],schema=r['schema'],
  explicit=os.getenv('EXPLICIT_TEST_KEY'),token=os.getenv('TELEGRAM_BOT_TOKEN'))))'''
        with tempfile.TemporaryDirectory() as folder:
            config = self.config(folder, dict(backend='command', command=[sys.executable, '-c', code],
                                             pass_env=['EXPLICIT_TEST_KEY']))
            with patch.dict(os.environ, {'EXPLICIT_TEST_KEY': 'allowed', 'TELEGRAM_BOT_TOKEN': 'not-allowed'}):
                result = generate('متن فارسی', {'type': 'object'}, config)
            self.assertEqual(result, dict(version=1, prompt='متن فارسی', schema={'type': 'object'},
                                          explicit='allowed', token=None))

    def test_failure_does_not_leak_adapter_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self.config(folder, dict(backend='command', command=[sys.executable, '-c',
                'import sys;sys.stderr.write("private-key-value");sys.exit(3)']))
            with self.assertRaises(RuntimeError) as error:
                generate('x', {}, config)
            self.assertNotIn('private-key-value', str(error.exception))

    def test_shell_string_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = self.config(folder, dict(backend='command', command='echo unsafe'))
            with self.assertRaises(ValueError):
                generate('x', {}, config)

    def test_prompt_uses_repository_instruction_files(self):
        prompt = prompt_for({'title': 'A'}, {'text': 'B'}, [])
        self.assertIn((ROOT / 'prompts' / 'selection.txt').read_text(), prompt)
        self.assertIn((ROOT / 'writing-prompt.txt').read_text(), prompt)
        self.assertIn('INPUT_JSON:', prompt)
