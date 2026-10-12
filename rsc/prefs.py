"""Small settings Nick can change from the Setup page. Stored in the database next to everything else."""
import re
import sqlite3

DEFAULTS = {"report_to": "", "daily_to": "", "review_url": "", "visit_when": "weekdays at 4pm", "owner_name": "Nick"}


def get(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else DEFAULTS.get(key, "")


def put(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value.strip()))
    conn.commit()


def report_recipients(conn: sqlite3.Connection) -> list[str]:
    return [a for a in re.split(r"[,;\s]+", get(conn, "report_to")) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", a)]


def daily_recipients(conn: sqlite3.Connection) -> list[str]:
    """Anyone listed on the Setup page plus every active crew member who has an email."""
    out = [a for a in re.split(r"[,;\s]+", get(conn, "daily_to")) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", a)]
    out += [r[0] for r in conn.execute("SELECT email FROM crew WHERE active = 1 AND email != ''")]
    seen, uniq = set(), []
    for a in out:
        if a.lower() not in seen:
            seen.add(a.lower())
            uniq.append(a)
    return uniq
