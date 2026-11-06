# Operations and handoff

## Configuration

For a new install, copy example.env to .env, fill it locally and chmod 600 .env.
Do not overwrite the existing deployment's configured file. SQLite path is
relative to the repository unless absolute; parent directories must exist.
Explicit --database overrides it for collect/process/publish. A normal cycle
uses the same AI_NEWS_DATABASE_PATH setting for every stage.

Environment variables override .env. Values are literal, without shell execution
or expansion. Secrets are not exported to every child process. The old
.secrets/telegram-token and telegram.json formats remain backward-compatible
fallbacks; current configuration uses .env as primary.

## Commands

From the repository root:

```sh
python3 -m unittest -v
python3 collect.py --pending
python3 cycle.py --limit 5
python3 publish.py                   # preview, no Telegram network call
python3 publish.py --check           # permission check, no post
python3 cycle.py --publish --limit 5  # real publication
```

First successful source collection is a baseline. Later new/changed entries
become pending. Source failure does not block other sources and reports partial
failure nonzero. Held items are reconsidered after six hours; --retry-holds asks
for an earlier check. Model/format errors are recorded in processing_errors.

process.py --demo copies state to an independent demo database. Never publish
it without an explicit request. Output files and demo state are not Git files.

## Scheduling

The user approved `ai-news.timer` on this server, with calendar runs every fifteen
minutes (:00, :15, :30, :45). The oneshot service runs cycle.py with
publication enabled. If still active, systemd does not start a second copy;
application locks provide an additional overlap guard. Persistent=true requests
one catch-up activation after downtime, rather than replaying every missed tick.

The server-specific templates are in deploy/. They use the existing root account,
checkout /root/ai-news-mvp, /usr/bin/python3 and Codex in /root/.local/bin. Adjust
these paths/account on another host. Secrets are read by the application from
.env, not loaded as an EnvironmentFile for the entire service process tree.
The service kills its process group after a 45-minute limit; interrupted sends
remain sending/uncertain and must be reconciled before retry.

Install/update and inspect:

```sh
install -m 644 deploy/ai-news.service /etc/systemd/system/ai-news.service
install -m 644 deploy/ai-news.timer /etc/systemd/system/ai-news.timer
systemctl daemon-reload
systemctl enable --now ai-news.timer
systemctl status ai-news.timer
systemctl show ai-news.service -p Result -p ExecMainStatus
journalctl -u ai-news.service -n 50 --no-pager
```

To trigger a real cycle now, use `systemctl start ai-news.service`. To pause
future runs use `systemctl stop ai-news.timer`; an already running cycle keeps
running. `systemctl disable --now ai-news.timer` also prevents boot activation.

Do not create parallel native or cron jobs. scheduled-task-prompt.txt is retained
only for a future migration; disable the system timer before using another
scheduler. Inference is pinned to gpt-6.1-terra with reasoning_effort=low in
inference.json, regardless of the model selected in a desktop chat.

## Delivery issues

- failed: explicit rejection. Resolve its cause before a deliberate retry.
- retry: rate limit; the next run respects retry_at without blocking sleep.
- sending/uncertain: may already have posted. Check the channel before changing
  state. No automatic reconciliation command exists.
- Updates require a confirmed original message ID. Do not silently remove replies.
- A database binds to one channel. Use separate state or a deliberate migration
  when changing channel; message IDs are channel-specific.

Inspect drafts, deliveries, decisions, fetches and processing_errors. Do not
delete history just to clear an error: that can lose replies or duplicate posts.

## Backup and migration

Git stores code/instructions, not runtime memory. Use SQLite backup rather than
copying a potentially busy file:

```sh
python3 - <<'PY'
from pathlib import Path
import sqlite3
from config import database_path
Path('backups').mkdir(exist_ok=True)
with sqlite3.connect(database_path()) as source, sqlite3.connect('backups/news.sqlite3') as target:
    source.backup(target)
PY
```

For cutover, disable the old scheduler and let runs finish. Clone the repo,
transfer the final backup and .env securely, adjust paths and authenticate the
selected inference backend. Run tests, publish.py --check and a local draft cycle.
Preserve message IDs/channel binding. Enable exactly one scheduler on the new host.
Keep credentials, databases and backups outside Git.

## Persisting a user preference

1. Record the accepted decision in docs/product.md.
2. Update the prompt/configuration actually used by the application.
3. For deterministic requirements, update validation and meaningful tests.
4. Update scheduled-task-prompt.txt if run instructions changed.
5. Review the diff, run appropriate checks, and commit.

Prompt-only wording changes can be checked with a local sample. Do not publish
arbitrary diagnostics or demos; public samples require the user's request.
