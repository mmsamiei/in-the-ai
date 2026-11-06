import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from codex_runner import generate


class CodexCommandTests(unittest.TestCase):
    def test_model_effort_and_secret_filtering_reach_cli(self):
        def fake_run(command, **kwargs):
            self.assertEqual(command[command.index('--model') + 1], 'gpt-6.1-terra')
            self.assertIn('model_reasoning_effort="low"', command)
            self.assertNotIn('TELEGRAM_BOT_TOKEN', kwargs['env'])
            Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps({'ok': True}))
            return SimpleNamespace(returncode=0, stderr='')
        with patch('codex_runner.subprocess.run', side_effect=fake_run):
            self.assertEqual(generate('x', {}, model='gpt-6.1-terra', reasoning_effort='low'), {'ok': True})

    def test_light_label_is_not_sent_as_an_invalid_cli_value(self):
        with self.assertRaises(ValueError):
            generate('x', {}, model='gpt-6.1-terra', reasoning_effort='light')
