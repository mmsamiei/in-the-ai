import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect import connect, save
from process import initialize, process_one


class EventFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.temp.name) / 'test.sqlite3')
        initialize(self.db)
        self.evidence = patch('process.evidence', return_value={
            'text': 'A model was released with downloadable weights. ' * 20,
            'kind': 'article_body', 'retrieval_error': None})
        self.evidence.start()

    def tearDown(self):
        self.evidence.stop()
        self.db.close()
        self.temp.cleanup()

    def row(self, suffix):
        save(self.db, 'test', [dict(url='https://example.com/' + suffix, title='Model', content='text')], False)
        return self.db.execute('''SELECT v.id,a.source,v.data FROM versions v JOIN articles a ON a.id=v.article_id
                                 ORDER BY v.id DESC LIMIT 1''').fetchone()

    def decision(self, action='new', event_id=None):
        return dict(action=action, event_id=event_id, event_title='Model release', reason='Important release',
                    facts=['Weights available'], draft='مدل تازه منتشر شده.\n\nوزن‌هاش در دسترسه.\n\nمی‌شه بررسیش کرد.'
                    if action in ('new', 'update') else '')

    def model(self, decision, supported=True):
        def run(prompt, schema):
            if 'supported' in schema['properties']:
                return dict(supported=supported, issues=[] if supported else ['Unsupported number'])
            return decision
        return run


class EventTests(EventFixture, unittest.TestCase):
    def test_update_replies_to_original_and_duplicate_makes_no_draft(self):
        process_one(self.db, self.row('first'), self.model(self.decision()))
        process_one(self.db, self.row('update'), self.model(self.decision('update', 1)))
        process_one(self.db, self.row('duplicate'), self.model(self.decision('duplicate', 1)))
        self.assertEqual(self.db.execute('SELECT parent_draft_id FROM drafts ORDER BY id').fetchall(),
                         [(None,), (1,)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0], 1)

    def test_failed_fact_check_creates_no_event_or_draft(self):
        result = process_one(self.db, self.row('bad'), self.model(self.decision(), supported=False))
        self.assertEqual(result['action'], 'hold')
        self.assertEqual(self.db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0], 0)

    def test_unknown_event_id_rejected(self):
        with self.assertRaises(ValueError):
            process_one(self.db, self.row('unknown'), self.model(self.decision('update', 999)))
        self.assertEqual(self.db.execute('SELECT count(*) FROM decisions').fetchone()[0], 0)

    def test_hold_can_be_rechecked_without_duplicate_decision(self):
        row = self.row('retry')
        process_one(self.db, row, self.model(self.decision(), supported=False))
        process_one(self.db, row, self.model(self.decision()))
        self.assertEqual(self.db.execute('SELECT count(*) FROM decisions').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM drafts').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
