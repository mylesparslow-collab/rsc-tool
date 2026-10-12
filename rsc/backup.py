"""A copy of the database every day, so a bad disk or a bad click never costs Nick his books."""
import sqlite3
from datetime import date
from pathlib import Path

KEEP = 30


def folder(home: Path) -> Path:
    return Path(home) / "backups"


def run(db_path: Path, home: Path, today: date | None = None) -> Path | None:
    """Copy the database into backups/ once per day. Returns the new file, or None if today's already exists."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    dest_dir = folder(home)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"rsc-{(today or date.today()).isoformat()}.db"
    if dest.exists():
        return None
    tmp = dest.with_suffix(".tmp")
    src = sqlite3.connect(str(db_path))
    try:
        out = sqlite3.connect(str(tmp))
        try:
            src.backup(out)  # safe while the app is running
        finally:
            out.close()
    finally:
        src.close()
    tmp.rename(dest)
    for old in sorted(dest_dir.glob("rsc-????-??-??.db"))[:-KEEP]:
        old.unlink()
    return dest


def latest(home: Path) -> tuple[Path, int] | None:
    """The newest backup and how many days old it is."""
    files = sorted(folder(home).glob("rsc-????-??-??.db"))
    if not files:
        return None
    try:
        d = date.fromisoformat(files[-1].stem[4:])
    except ValueError:
        return None
    return files[-1], (date.today() - d).days
