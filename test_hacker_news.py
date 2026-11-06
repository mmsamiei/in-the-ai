import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect import connect
from content import require_public_url
from hacker_news import collect


class HNTests(unittest.TestCase):
    def test_top_stories_classified_once_even_when_scores_change(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'db.sqlite3')
            stories = {1: {'id': 1, 'type': 'story', 'title': 'A model', 'url': 'https://example.com/model', 'time': 100, 'score': 4},
                       2: {'id': 2, 'type': 'story', 'title': 'Gardening', 'time': 101, 'score': 9},
                       3: {'id': 3, 'type': 'story', 'title': 'Ask HN: AI?', 'text': 'Question', 'time': 102}}
            def get(path):
                return [1, 2, 3] if path == 'topstories.json' else stories[int(path.split('/')[1].split('.')[0])]
            calls = []
            def model(prompt, schema):
                calls.append(prompt)
                return {'results': [{'id': i, 'relevant': i != 2} for i in (1, 2, 3)]}
            first = collect(db, get, model)
            stories[1]['score'] = 200
            second = collect(db, get, model)
            self.assertEqual((first['relevant'], second['classified'], len(calls)), (2, 0, 1))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM versions WHERE status='pending'").fetchone()[0], 2)
            urls = [x[0] for x in db.execute('SELECT url FROM articles ORDER BY id')]
            self.assertEqual(urls, ['https://example.com/model', 'https://news.ycombinator.com/item?id=3'])

    def test_bad_classifier_response_does_not_mark_seen(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'db.sqlite3')
            def get(path):
                return [1] if path == 'topstories.json' else {'id': 1, 'type': 'story', 'title': 'AI', 'time': 100}
            with self.assertRaises(ValueError):
                collect(db, get, lambda prompt, schema: {'results': []})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM hn_seen').fetchone()[0], 0)

    def test_private_addresses_rejected(self):
        with patch('content.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError):
                require_public_url('http://example.com/')
