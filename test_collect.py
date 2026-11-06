import tempfile
import unittest
from pathlib import Path
from collect import connect, parse_feed, save


class IntakeTests(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = b'<rss><channel><item><title>A</title><link>https://example.com/a</link><description>Body</description></item></channel></rss>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title><link href="https://example.com/a"/><content>Body</content></entry></feed>'
        for body in (rss, atom):
            self.assertEqual(parse_feed(body)[0]['content'], 'Body')

    def test_baseline_repeat_and_changed_content(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'test.sqlite3')
            item = dict(url='https://example.com/a', title='A', content='old')
            self.assertEqual(save(db, 'test', [item], True), 1)
            self.assertEqual(save(db, 'test', [item], False), 0)
            self.assertEqual(save(db, 'test', [dict(item, content='new')], False), 1)
            self.assertEqual(db.execute('SELECT status FROM versions ORDER BY id').fetchall(),
                             [('baseline',), ('pending',)])


if __name__ == '__main__':
    unittest.main()
