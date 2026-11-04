"""Conservative temporary-file cleanup: regular files older than 24 hours only."""
import os
import stat
import tempfile
import time
from pathlib import Path

MIN_AGE_SECONDS = 24 * 3600


def locations():
    user = Path(tempfile.gettempdir()).resolve()
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
    result = {"User temporary files": user}
    if os.path.normcase(str(user)) != os.path.normcase(str(system)):
        result["Windows temporary files"] = system
    return result


def candidates(folder, now=None):
    """Yield only old, non-link regular files within the specified temp folder."""
    now = time.time() if now is None else now
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        return
    for root, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in files:
            path = Path(root) / name
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_mtime > now - MIN_AGE_SECONDS:
                    continue
                yield path, info.st_size
            except OSError:
                continue


def scan(selected):
    summary = {}
    for name, folder in locations().items():
        if name in selected:
            count = 0
            size = 0
            for _, n in candidates(folder):
                count += 1
                size += n
            summary[name] = (count, size)
    return summary


def clean(selected, dry_run=True):
    """Rescan at execution time. Never follow symlinks or remove directories."""
    results = {}
    for name, folder in locations().items():
        if name not in selected:
            continue
        count = bytes_total = skipped = 0
        for path, size in candidates(folder):
            if dry_run:
                count += 1
                bytes_total += size
                continue
            try:
                # Recheck the entry immediately before deletion.
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_mtime > time.time() - MIN_AGE_SECONDS:
                    skipped += 1
                    continue
                path.unlink()
                count += 1
                bytes_total += info.st_size
            except OSError:
                skipped += 1
        results[name] = (count, bytes_total, skipped)
    return results
