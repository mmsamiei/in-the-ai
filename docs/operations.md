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

No scheduler is currently active through this project. Preferred cadence is
every ten minutes using native scheduling. Use scheduled-task-prompt.txt and
set its working directory to the actual checkout. Verify the first scheduled
run independently. A prepared file or installed CLI does not prove scheduling
exists. Do not install cron/systemd as an implicit substitute. Keep existing locks.

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
