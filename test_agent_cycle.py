import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import agent_cycle


class AgentCycleTests(unittest.TestCase):
    def test_launches_one_tool_enabled_agent_and_redacts_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'news.sqlite3'
            db.touch()
            def run(command, **kwargs):
                self.assertIn('--search', command)
                self.assertIn('workspace-write', command)
                self.assertIn('sandbox_workspace_write.network_access=true', command)
                self.assertNotIn('shell_tool', command)
                self.assertIn('gpt-6-luna', command)
                self.assertIn('LIVE', kwargs['input'])
                self.assertIn('Before EVERY publication', kwargs['input'])
                self.assertIn('instructions/deduplication.md', kwargs['input'])
                self.assertIn('publication_checks', kwargs['input'])
                self.assertNotIn('TELEGRAM_BOT_TOKEN', kwargs['env'])
                return SimpleNamespace(returncode=0, stdout='test-token', stderr='error test-token')
            with patch.object(agent_cycle, 'ROOT', root), patch.object(agent_cycle, 'database_path', return_value=db), \
                 patch.object(agent_cycle, 'setting', return_value='test-token'), \
                 patch('agent_cycle.subprocess.run', side_effect=run), \
                 patch('sys.argv', ['agent_cycle.py']):
                self.assertEqual(agent_cycle.main(), 0)
            report = json.loads(next((root / 'output').glob('*.json')).read_text())
            self.assertNotIn('test-token', json.dumps(report))
            self.assertIn('[REDACTED]', report['stdout'])

    def test_dry_run_refuses_workspace_with_token(self):
        with patch.object(agent_cycle, 'setting', return_value='token'), \
             patch('sys.argv', ['agent_cycle.py', '--dry-run']):
            with self.assertRaises(SystemExit):
                agent_cycle.main()

    def test_database_outside_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            db = Path(b) / 'news.sqlite3'
            db.touch()
            with patch.object(agent_cycle, 'ROOT', Path(a)), patch.object(agent_cycle, 'database_path', return_value=db), \
                 patch('sys.argv', ['agent_cycle.py', '--dry-run']):
                with self.assertRaises(SystemExit):
                    agent_cycle.main()
