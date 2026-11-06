"""Launch one self-directed Codex news cycle with a cross-version lock."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile

from config import ROOT, database_path, setting


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('timeout must be positive')
    if args.dry_run and setting('TELEGRAM_BOT_TOKEN'):
        raise SystemExit('Dry run requires an isolated workspace without a Telegram token.')
    with open(ROOT / 'cycle.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another news cycle is active; this run was skipped.')
            return 0
        db = database_path().resolve()
        if not db.is_file():
            raise SystemExit('Configured SQLite database does not exist; initialize it before running.')
        # The database must live in this checkout so workspace-write can update it.
        if not db.is_relative_to(ROOT.resolve()):
            raise SystemExit('SQLite path must be inside the workspace for this sandbox.')
        mode = 'DRY RUN: do not send any Telegram messages, even test messages.' if args.dry_run else 'LIVE: publication is authorized under the repository instructions.'
        task = (f'Perform one complete AI news cycle. Mode: {mode}\n'
                f'The SQLite database is {db}. Read AGENTS.md and instructions/agent-workflow.md.\n'
                'Use your tools to do the work. Do not modify application code or print secrets. '
                'Return a short factual run report.')
        command = ['codex', '--no-daemon', '--search', '-a', 'never', 'exec',
                   '--ignore-user-config', '--ephemeral', '--sandbox', 'workspace-write',
                   '--cd', str(ROOT), '--model', 'gpt-6-luna',
                   '-c', 'model_reasoning_effort="low"',
                   '-c', 'sandbox_workspace_write.network_access=true',
                   '--disable', 'apps', '--disable', 'plugins', '--disable', 'hooks',
                   '--disable', 'computer_use', '--disable', 'browser_use', '-']
        token = setting('TELEGRAM_BOT_TOKEN') or ''
        environment = {key: value for key, value in os.environ.items() if key in (
            'PATH', 'HOME', 'CODEX_HOME', 'LANG', 'LC_ALL', 'TMPDIR',
            'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY')}
        start = datetime.now(timezone.utc)
        try:
            completed = subprocess.run(command, input=task, text=True, capture_output=True,
                                       timeout=args.timeout, cwd=ROOT, env=environment)
            status, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            status = 124
            stdout = (exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            stderr = (exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
        if token:
            stdout, stderr = stdout.replace(token, '[REDACTED]'), stderr.replace(token, '[REDACTED]')
        out = ROOT / 'output'
        out.mkdir(mode=0o700, exist_ok=True)
        report = out / ('agent-' + start.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        payload = {'started_at': start.isoformat(), 'finished_at': datetime.now(timezone.utc).isoformat(),
                   'mode': 'dry-run' if args.dry_run else 'live', 'exit_code': status,
                   'stdout': stdout[-200000:], 'stderr': stderr[-200000:]}
        fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(payload, file, ensure_ascii=False)
        print(json.dumps({'exit_code': status, 'mode': payload['mode'], 'report': str(report)}, ensure_ascii=False))
        return status


if __name__ == '__main__':
    raise SystemExit(main())
