"""One complete news cycle, callable by native Codex scheduling."""
import argparse
import subprocess
import sys

from collect import ROOT
from process import lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--publish', action='store_true', help='Also send ready drafts to configured Telegram channel')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    with lock(ROOT / 'cycle.lock'):
        collected = subprocess.run([sys.executable, str(ROOT / 'collect.py')], cwd=ROOT)
        discovered = subprocess.run([sys.executable, str(ROOT / 'collect_hn.py')], cwd=ROOT)
        # One unavailable source must not block processing the other sources.
        processed = subprocess.run([sys.executable, str(ROOT / 'process.py'), '--limit', str(args.limit)], cwd=ROOT)
        published = None
        if args.publish:
            published = subprocess.run([sys.executable, str(ROOT / 'publish.py'), '--send', '--limit', str(args.limit)], cwd=ROOT)
        return 1 if collected.returncode or discovered.returncode or processed.returncode or (published and published.returncode) else 0


if __name__ == '__main__':
    raise SystemExit(main())
