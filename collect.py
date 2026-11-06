"""Fetch feeds into a versioned inbox; never publishes or calls a model."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import urllib.request
import xml.etree.ElementTree as ET
from config import database_path

ROOT = Path(__file__).resolve().parent
ATOM = '{http://www.w3.org/2005/Atom}'


def parse_feed(body):
    root = ET.fromstring(body)
    rows = root.findall('./channel/item') or root.findall(ATOM + 'entry')
    result = []
    for row in rows:
        def value(*names):
            for name in names:
                node = row.find(name)
                if node is not None:
                    text = ''.join(node.itertext()).strip()
                    if text:
                        return text
            return ''
        link = value('link')
        if not link:
            for node in row.findall(ATOM + 'link'):
                if node.get('rel', 'alternate') == 'alternate':
                    link = node.get('href', '')
                    break
        if not link.startswith(('https://', 'http://')):
            continue
        result.append(dict(
            url=link, title=value('title', ATOM + 'title'),
            published=value('pubDate', ATOM + 'published', ATOM + 'updated'),
            updated=value(ATOM + 'updated'),
            content=value('{http://purl.org/rss/1.0/modules/content/}encoded',
                          ATOM + 'content', 'description', ATOM + 'summary')))
    if not rows:
        raise ValueError('No RSS/Atom entries found')
    return result


def fetch(source):
    request = urllib.request.Request(source['url'], headers={'User-Agent': 'AINewsMVP/0.1'})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(8_000_001)
    if len(body) > 8_000_000:
        raise ValueError('Feed exceeds size limit')
    return parse_feed(body)


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, url TEXT NOT NULL,
        UNIQUE(source,url));
      CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id),
        digest TEXT NOT NULL, data TEXT NOT NULL, fetched_at TEXT NOT NULL,
        status TEXT NOT NULL, UNIQUE(article_id,digest));
      CREATE TABLE IF NOT EXISTS fetches (
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
        count INTEGER, error TEXT);
    ''')
    return db


def save(db, source, items, baseline):
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        db.execute('INSERT OR IGNORE INTO articles(source,url) VALUES (?,?)', (source, item['url']))
        article_id = db.execute('SELECT id FROM articles WHERE source=? AND url=?',
                                (source, item['url'])).fetchone()[0]
        data = json.dumps(item, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(data.encode()).hexdigest()
        cursor = db.execute('''INSERT OR IGNORE INTO versions
          (article_id,digest,data,fetched_at,status) VALUES (?,?,?,?,?)''',
          (article_id, digest, data, now, 'baseline' if baseline else 'pending'))
        inserted += cursor.rowcount
    return inserted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true', help='Store current items without queuing them')
    parser.add_argument('--database', type=Path, default=database_path())
    parser.add_argument('--pending', action='store_true', help='Export pending feed entries as JSON')
    args = parser.parse_args()
    db = connect(args.database)
    if args.pending:
        rows = db.execute('''SELECT v.id,a.source,v.data FROM versions v
            JOIN articles a ON a.id=v.article_id WHERE v.status='pending' ORDER BY v.id''')
        print(json.dumps([dict(version_id=i, source=s, **json.loads(d)) for i,s,d in rows], ensure_ascii=False, indent=2))
        return
    sources = json.loads((ROOT / 'sources.json').read_text())
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [(source, pool.submit(fetch, source)) for source in sources]
        for source, future in jobs:
            try:
                items = future.result()
                # First successful fetch of a source is always a baseline.
                first_fetch = not db.execute('SELECT 1 FROM fetches WHERE source=? AND error IS NULL',
                                             (source['id'],)).fetchone()
                with db:
                    added = save(db, source['id'], items, args.baseline or first_fetch)
                    db.execute('INSERT INTO fetches(source,fetched_at,count) VALUES (?,?,?)',
                               (source['id'], datetime.now(timezone.utc).isoformat(), len(items)))
                print(json.dumps(dict(source=source['id'], received=len(items), new_versions=added)))
            except Exception as exc:
                failures += 1
                with db:
                    db.execute('INSERT INTO fetches(source,fetched_at,error) VALUES (?,?,?)',
                               (source['id'], datetime.now(timezone.utc).isoformat(), str(exc)))
                print(json.dumps(dict(source=source['id'], error=str(exc))))
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
