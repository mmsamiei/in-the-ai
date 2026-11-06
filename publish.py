"""Preview or send verified drafts to the configured Telegram channel."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

from collect import ROOT, connect
from process import initialize, lock
from text_rules import validate_post
from config import database_path, setting


class DeliveryError(Exception):
    def __init__(self, message, uncertain=False, retry_after=None):
        super().__init__(message)
        self.uncertain = uncertain
        self.retry_after = retry_after


class Telegram:
    def __init__(self, token):
        self.token = token.strip()
        if not self.token or ':' not in self.token or any(c.isspace() for c in self.token):
            raise ValueError('Invalid or empty Telegram token file')

    def call(self, method, payload):
        request = urllib.request.Request(
            f'https://api.telegram.org/bot{self.token}/{method}',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read(100000))
            except (ValueError, OSError):
                data = {}
            message = str(data.get('description', f'Telegram HTTP {exc.code}')).replace(self.token, '[redacted]')
            raise DeliveryError(message, uncertain=exc.code >= 500,
                                retry_after=data.get('parameters', {}).get('retry_after')) from None
        except (OSError, TimeoutError):
            # The server may have accepted the message before the connection failed.
            # Do not leak the request URL, which contains the token.
            raise DeliveryError('Telegram connection failed; delivery outcome is unknown', uncertain=True) from None
        try:
            data = json.loads(raw)
            if not data.get('ok'):
                raise DeliveryError(str(data.get('description', 'Telegram rejected request')).replace(self.token, '[redacted]'),
                                    uncertain=int(data.get('error_code', 500)) >= 500,
                                    retry_after=data.get('parameters', {}).get('retry_after'))
            return data['result']
        except (ValueError, KeyError, TypeError):
            raise DeliveryError('Invalid Telegram response; delivery outcome is unknown', uncertain=True) from None


def initialize_delivery(db):
    initialize(db)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS deliveries (
        draft_id INTEGER PRIMARY KEY REFERENCES drafts(id), chat_id TEXT NOT NULL,
        state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        message_id INTEGER, updated_at TEXT NOT NULL, retry_at TEXT, error TEXT);
    ''')


def check_channel(api, configured_chat):
    me = api.call('getMe', {})
    chat = api.call('getChat', {'chat_id': configured_chat})
    if chat.get('type') != 'channel':
        raise ValueError('Configured destination must be a Telegram channel')
    member = api.call('getChatMember', {'chat_id': chat['id'], 'user_id': me['id']})
    if member.get('status') != 'creator' and not (
            member.get('status') == 'administrator' and member.get('can_post_messages')):
        raise ValueError('Bot must be a channel administrator with permission to post')
    return chat


def bind_channel(db, chat_id):
    chat_id = str(chat_id)
    previous = db.execute("SELECT value FROM settings WHERE key='telegram_chat_id'").fetchone()
    if previous and previous[0] != chat_id:
        raise ValueError('Database is already bound to another channel; use a separate database')
    with db:
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('telegram_chat_id',?)", (chat_id,))


def payload_for(db, draft, chat_id, preview=False):
    draft_id, parent_id, body, url, verification = draft
    validate_post(body)
    checked = json.loads(verification)
    if checked.get('supported') is not True or checked.get('issues'):
        raise ValueError(f'Draft {draft_id} has not passed factual verification')
    text = body + '\n\nمنبع: ' + url
    if len(text.encode('utf-16-le')) // 2 > 4096:
        raise ValueError(f'Draft {draft_id} exceeds Telegram message length')
    payload = dict(chat_id=chat_id, text=text, link_preview_options={'is_disabled': True})
    if parent_id is not None:
        parent = db.execute('SELECT telegram_message_id FROM drafts WHERE id=?', (parent_id,)).fetchone()
        if not parent or parent[0] is None:
            if preview:
                return dict(payload, reply_to_draft=parent_id)
            raise ValueError(f'Parent draft {parent_id} has not been published')
        payload['reply_parameters'] = dict(message_id=parent[0], allow_sending_without_reply=False)
    return payload


def publish_one(db, draft, chat_id, api):
    draft_id = draft[0]
    previous = db.execute('SELECT state,retry_at FROM deliveries WHERE draft_id=?', (draft_id,)).fetchone()
    if previous and previous[0] in ('sent', 'sending', 'uncertain', 'failed'):
        return previous[0]
    now = datetime.now(timezone.utc).isoformat()
    if previous and previous[1] and previous[1] > now:
        return 'deferred'
    payload = payload_for(db, draft, chat_id)
    # Commit the sending state before contacting Telegram. A crash after this
    # point requires reconciliation instead of an automatic duplicate send.
    with db:
        db.execute('''INSERT INTO deliveries(draft_id,chat_id,state,attempts,updated_at)
                      VALUES (?,?,'sending',1,?) ON CONFLICT(draft_id) DO UPDATE SET
                      state='sending',attempts=attempts+1,updated_at=excluded.updated_at,retry_at=NULL,error=NULL''',
                   (draft_id, str(chat_id), now))
    try:
        message = api.call('sendMessage', payload)
        message_id = message.get('message_id')
        if type(message_id) is not int or message_id <= 0 or str(message.get('chat', {}).get('id')) != str(chat_id):
            raise DeliveryError('Unexpected Telegram send result', uncertain=True)
    except DeliveryError as exc:
        state = 'uncertain' if exc.uncertain else 'failed'
        retry_at = None
        if not exc.uncertain and type(exc.retry_after) is int and exc.retry_after > 0:
            state = 'retry'
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after)).isoformat()
        with db:
            db.execute('UPDATE deliveries SET state=?,retry_at=?,error=?,updated_at=? WHERE draft_id=?',
                       (state, retry_at, str(exc), now, draft_id))
        raise
    with db:
        db.execute("UPDATE deliveries SET state='sent',message_id=?,updated_at=? WHERE draft_id=?",
                   (message_id, now, draft_id))
        db.execute("UPDATE drafts SET status='published',telegram_message_id=? WHERE id=?",
                   (message_id, draft_id))
    return 'sent'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=database_path())
    parser.add_argument('--token-file', type=Path, default=ROOT / '.secrets' / 'telegram-token')
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--send', action='store_true', help='Send to the configured channel (default: preview only)')
    parser.add_argument('--check', action='store_true', help='Check bot/channel access without sending')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    legacy_config = ROOT / 'telegram.json'
    chat_id = setting('TELEGRAM_CHAT_ID')
    if not chat_id and legacy_config.exists():
        chat_id = json.loads(legacy_config.read_text()).get('chat_id')
    api = None
    if args.send or args.check:
        if not chat_id:
            parser.error('Set TELEGRAM_CHAT_ID in .env first')
        token = setting('TELEGRAM_BOT_TOKEN')
        if not token:
            if not args.token_file.is_file():
                parser.error('Set TELEGRAM_BOT_TOKEN in .env first')
            if args.token_file.stat().st_mode & 0o077:
                parser.error('Token file must be private: chmod 600 TOKEN_FILE')
            token = args.token_file.read_text()
        elif (ROOT / '.env').exists() and (ROOT / '.env').stat().st_mode & 0o077:
            parser.error('.env must be private: chmod 600 .env')
        api = Telegram(token)
        chat = check_channel(api, chat_id)
        chat_id = chat['id']
        if args.check:
            print(json.dumps(dict(channel_id=chat_id, title=chat.get('title'), can_post=True), ensure_ascii=False))
            return 0
    with lock(str(args.database.resolve()) + '.lock'):
        db = connect(args.database)
        initialize_delivery(db)
        if args.send:
            bind_channel(db, chat_id)
        rows = db.execute('''SELECT d.id,d.parent_draft_id,d.body,d.source_url,d.verification FROM drafts d
                             LEFT JOIN deliveries l ON l.draft_id=d.id
                             WHERE d.status='ready' AND (l.state IS NULL OR l.state='retry')
                             ORDER BY d.id LIMIT ?''', (args.limit,)).fetchall()
        failures = 0
        for row in rows:
            try:
                if args.send:
                    print(json.dumps(dict(draft_id=row[0], state=publish_one(db, row, chat_id, api))))
                else:
                    print(json.dumps(dict(draft_id=row[0], payload=payload_for(db, row, chat_id, preview=True)), ensure_ascii=False))
            except (DeliveryError, ValueError) as exc:
                failures += 1
                print(json.dumps(dict(draft_id=row[0], error=str(exc)), ensure_ascii=False))
                # Stop on an API error to respect rate limits and avoid sending a
                # child update after an uncertain parent delivery.
                if isinstance(exc, DeliveryError):
                    break
        return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
