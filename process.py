"""Classify events and generate verified local drafts. No Telegram publishing."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import sqlite3

from collect import ROOT, connect
from content import evidence
from inference import generate
from text_rules import validate_post
from config import database_path


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


STRING = {'type': 'string'}
STRINGS = {'type': 'array', 'items': STRING}
DECISION_SCHEMA = object_schema(dict(
    action={'type': 'string', 'enum': ['new', 'update', 'duplicate', 'skip', 'hold']},
    event_id={'type': ['integer', 'null']}, event_title=STRING, reason=STRING,
    facts=STRINGS, draft=STRING))
CHECK_SCHEMA = object_schema(dict(supported={'type': 'boolean'}, issues=STRINGS))


def initialize(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, facts TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS decisions (
        version_id INTEGER PRIMARY KEY REFERENCES versions(id), event_id INTEGER REFERENCES events(id),
        action TEXT NOT NULL, reason TEXT NOT NULL, evidence TEXT NOT NULL,
        model_output TEXT NOT NULL, checked_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL UNIQUE REFERENCES versions(id),
        event_id INTEGER NOT NULL REFERENCES events(id), parent_draft_id INTEGER REFERENCES drafts(id),
        body TEXT NOT NULL, facts TEXT NOT NULL, source_url TEXT NOT NULL,
        created_at TEXT NOT NULL, verification TEXT NOT NULL,
        telegram_message_id INTEGER, status TEXT NOT NULL DEFAULT 'ready');
      CREATE TABLE IF NOT EXISTS processing_errors (
        id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, created_at TEXT NOT NULL, error TEXT NOT NULL);
    ''')


@contextmanager
def lock(path):
    with open(path, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another processing run is active')
        yield


def event_context(db):
    result = []
    for event_id, title, facts in db.execute('SELECT id,title,facts FROM events ORDER BY updated_at DESC LIMIT 200'):
        drafts = db.execute('SELECT id,body,facts,telegram_message_id FROM drafts WHERE event_id=? ORDER BY id',
                            (event_id,)).fetchall()
        result.append(dict(id=event_id, title=title, known_facts=json.loads(facts),
                           drafts=[dict(id=i, text=b, facts=json.loads(f), published=m is not None)
                                   for i,b,f,m in drafts]))
    return result


def prompt_for(item, source_text, events):
    instructions = (ROOT / 'prompts' / 'selection.txt').read_text() + '\nWriting instruction:\n'
    return instructions + (ROOT / 'writing-prompt.txt').read_text() + '\nINPUT_JSON:\n' + json.dumps(
        dict(article=item, evidence=source_text, existing_events=events), ensure_ascii=False)


def validate(decision, events):
    if set(decision) != set(DECISION_SCHEMA['properties']):
        raise ValueError('Unexpected decision fields')
    if decision['action'] not in ('new', 'update', 'duplicate', 'skip', 'hold'):
        raise ValueError('Unknown action')
    for key in ('event_title', 'reason', 'draft'):
        if not isinstance(decision[key], str):
            raise ValueError(f'Invalid {key}')
    if not isinstance(decision['facts'], list) or not all(isinstance(f, str) for f in decision['facts']):
        raise ValueError('Invalid facts')
    event_id = decision['event_id']
    if event_id is not None and (type(event_id) is not int or event_id not in {e['id'] for e in events}):
        raise ValueError('Unknown event id')
    if decision['action'] == 'update' and (event_id is None or
        not next(e for e in events if e['id'] == event_id)['drafts']):
        raise ValueError('Update requires a previous draft')
    if decision['action'] == 'duplicate' and event_id is None:
        raise ValueError('Duplicate requires a matching event')
    if decision['action'] == 'new' and event_id is not None:
        if next(e for e in events if e['id'] == event_id)['drafts']:
            raise ValueError('Existing drafted event requires update or duplicate')
    if decision['action'] in ('new', 'update'):
        body = decision['draft'].strip()
        if not body or not decision['facts'] or not decision['event_title'].strip():
            raise ValueError('Draft requires facts, title and text')
        validate_post(body)


def record(db, version_id, item, source_text, decision, verification):
    now = datetime.now(timezone.utc).isoformat()
    action = decision['action']
    event_id = decision['event_id']
    with db:
        if action in ('new', 'update') or (decision['facts'] and action == 'duplicate'):
            if event_id is None:
                event_id = db.execute('INSERT INTO events(title,facts,created_at,updated_at) VALUES (?,?,?,?)',
                    (decision['event_title'], json.dumps(decision['facts'], ensure_ascii=False), now, now)).lastrowid
            else:
                old = json.loads(db.execute('SELECT facts FROM events WHERE id=?', (event_id,)).fetchone()[0])
                merged = list(dict.fromkeys(old + decision['facts']))
                db.execute('UPDATE events SET facts=?,updated_at=? WHERE id=?',
                           (json.dumps(merged, ensure_ascii=False), now, event_id))
        if action in ('new', 'update'):
            parent = db.execute('SELECT id FROM drafts WHERE event_id=? ORDER BY id LIMIT 1', (event_id,)).fetchone()
            db.execute('''INSERT INTO drafts(version_id,event_id,parent_draft_id,body,facts,source_url,created_at,verification)
                          VALUES (?,?,?,?,?,?,?,?)''',
                       (version_id, event_id, parent[0] if parent else None, decision['draft'].strip(),
                        json.dumps(decision['facts'], ensure_ascii=False), item['url'], now,
                        json.dumps(verification, ensure_ascii=False)))
        db.execute('''INSERT INTO decisions VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(version_id) DO UPDATE SET event_id=excluded.event_id,
                   action=excluded.action,reason=excluded.reason,evidence=excluded.evidence,
                   model_output=excluded.model_output,checked_at=excluded.checked_at''',
                   (version_id, event_id, action, decision['reason'], json.dumps(source_text, ensure_ascii=False),
                    json.dumps(decision, ensure_ascii=False), now))
        db.execute('UPDATE versions SET status=? WHERE id=?', (action, version_id))


def process_one(db, row, model=generate):
    version_id, source, raw = row
    item = dict(json.loads(raw), source=source)
    source_text = evidence(item)
    events = event_context(db)
    if len(source_text['text']) < 200:
        decision = dict(action='hold', event_id=None, event_title=item['title'],
                        reason='Insufficient source text', facts=[], draft='')
    else:
        decision = model(prompt_for(item, source_text, events), DECISION_SCHEMA)
        validate(decision, events)
    verification = None
    if decision['action'] in ('new', 'update'):
        verification = model((ROOT / 'prompts' / 'verification.txt').read_text() + '\nINPUT_JSON:\n' + json.dumps(dict(
            article=item, evidence=source_text, draft=decision['draft'], facts=decision['facts']), ensure_ascii=False), CHECK_SCHEMA)
        if (set(verification) != {'supported', 'issues'} or type(verification['supported']) is not bool
            or not isinstance(verification['issues'], list)
            or not all(isinstance(issue, str) for issue in verification['issues'])):
            raise ValueError('Invalid verification response')
        if not verification['supported'] or verification['issues']:
            decision = dict(decision, action='hold', reason='Fact check: ' + '; '.join(verification['issues']))
    record(db, version_id, item, source_text, decision, verification)
    return dict(version_id=version_id, source=source, action=decision['action'], reason=decision['reason'])


def export(db, directory):
    directory.mkdir(parents=True, exist_ok=True)
    rows = db.execute('SELECT id,event_id,parent_draft_id,body,source_url,created_at FROM drafts ORDER BY id')
    result = [dict(id=i,event_id=e,reply_to_draft=p,text=b,source_url=u,created_at=t) for i,e,p,b,u,t in rows]
    (directory / 'drafts.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (directory / 'drafts.txt').write_text('\n\n'.join(
        f"[{x['id']}] reply_to={x['reply_to_draft']}\n{x['text']}\n{x['source_url']}" for x in result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=database_path())
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--demo', action='store_true', help='Copy database and sample baseline articles; no live queue changes')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--retry-holds', action='store_true', help='Also recheck held items (normally after six hours)')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    database = args.database.resolve()
    if args.demo:
        database = ROOT / 'demo.sqlite3'
    with lock(str(database) + '.lock'):
        if args.demo and not database.exists():
            with sqlite3.connect(args.database) as source, sqlite3.connect(database) as target:
                source.backup(target)
            with connect(database) as db:
                # One newest feed entry per source. Baselines are for demonstration only.
                db.execute('''UPDATE versions SET status='pending' WHERE id IN
                   (SELECT MIN(v.id) FROM versions v JOIN articles a ON a.id=v.article_id GROUP BY a.source)''')
        db = connect(database)
        initialize(db)
        failures = 0
        if not args.export_only:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
            rows = db.execute('''SELECT v.id,a.source,v.data FROM versions v JOIN articles a ON a.id=v.article_id
                                 LEFT JOIN decisions d ON d.version_id=v.id
                                 WHERE v.status='pending' OR (v.status='hold' AND (d.checked_at<? OR ?))
                                 ORDER BY v.id LIMIT ?''', (cutoff, args.retry_holds, args.limit)).fetchall()
            for row in rows:
                try:
                    print(json.dumps(process_one(db, row), ensure_ascii=False), flush=True)
                except Exception as exc:
                    failures += 1
                    with db:
                        db.execute('INSERT INTO processing_errors(version_id,created_at,error) VALUES (?,?,?)',
                                   (row[0], datetime.now(timezone.utc).isoformat(), str(exc)))
                    print(json.dumps(dict(version_id=row[0], error=str(exc)), ensure_ascii=False), flush=True)
        export(db, ROOT / ('demo-output' if args.demo else 'output'))
        return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
