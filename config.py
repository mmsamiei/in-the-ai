"""Load literal .env values without executing shell code or exporting secrets."""
import os
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parent


def load_env(path=None):
    path = Path(path) if path else ROOT / '.env'
    values = {}
    if not path.exists():
        return values
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            raise ValueError(f'Invalid .env syntax on line {number}')
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise ValueError(f'Invalid .env value on line {number}') from None
        if len(parts) > 1:
            raise ValueError(f'Quote values containing spaces in .env on line {number}')
        values[key] = parts[0] if parts else ''
    return values


def setting(key, default=None):
    if key in os.environ:
        return os.environ[key]
    return load_env().get(key, default)


def database_path():
    path = Path(setting('AI_NEWS_DATABASE_PATH') or 'news.sqlite3').expanduser()
    return path if path.is_absolute() else ROOT / path
