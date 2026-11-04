"""Append-only local activity history, stored outside the repository."""
from datetime import datetime
from pathlib import Path
import os

LOG_PATH = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'WinToolKit' / 'activity.log'


def record(message):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as stream:
        stream.write(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n')


def read_recent(limit=400):
    if not LOG_PATH.exists():
        return 'No activity recorded yet.'
    with LOG_PATH.open('r', encoding='utf-8', errors='replace') as stream:
        lines = stream.readlines()
    return ''.join(lines[-limit:]) or 'No activity recorded yet.'
