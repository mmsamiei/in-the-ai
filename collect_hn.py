"""Run Hacker News discovery; never publishes."""
import argparse
import json
from pathlib import Path
from collect import connect
from config import database_path
from hacker_news import collect
from process import lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=database_path())
    args = parser.parse_args()
    with lock(str(args.database.resolve()) + '.lock'):
        db = connect(args.database)
        result = collect(db)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1 if result['failed_items'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
