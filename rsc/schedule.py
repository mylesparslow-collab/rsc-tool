"""The week at a glance: which job each person is planned on, day by day.

Typed the way Nick would say it: "Mon-Wed Delano Mike Dave; Thu Hartwell Mike". Names are matched against the crew list and the
job by last name or address, in code (no model needed), and anything that can't be read is reported back instead of guessed.
A person planned on two jobs the same day is flagged. Hours actually logged show up next to the plan.
"""
import re
import sqlite3
from datetime import date, timedelta

from . import books, crew

DAY = crew.DAYWORD
RANGE = re.compile(rf"\b({DAY})\s*(?:-|–|to|through|thru)\s*({DAY})\b", re.I)
SINGLE = re.compile(rf"\b({DAY})\b", re.I)
STOP = {"and", "on", "at", "the", "with", "&", "in", "is", "are", "will", "be", "working", "work", "crew", "plus", "for", "to"}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _idx(word: str) -> int:
    return [i for i, w in enumerate(crew.WEEKDAYS) if word.lower().startswith(w)][0]


def parse_days(text: str, start: date) -> tuple[list[date], str]:
    """The dates named in a phrase (inside the week beginning at `start`) and the text with them removed."""
    days: list[int] = []
    m = RANGE.search(text)
    if m:
        a, b = _idx(m.group(1)), _idx(m.group(2))
        days += list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        text = text[:m.start()] + " " + text[m.end():]
    for m in SINGLE.finditer(text):
        days.append(_idx(m.group(1)))
    text = SINGLE.sub(" ", text)
    return [start + timedelta(days=i) for i in sorted(set(days))], text


def add(conn: sqlite3.Connection, text: str, start: date) -> dict:
    """Apply typed plans. Returns {"saved": n, "problems": [...]}."""
    saved, problems = 0, []
    for seg in [s.strip() for s in re.split(r"[;\n]+", text or "") if s.strip()]:
        days, rest = parse_days(seg, start)
        if not days:
            problems.append(f"No day in “{seg}”. Say which day, like Mon-Wed.")
            continue
        people, left, amb = [], [], False
        for tok in [t for t in re.split(r"[\s,]+|\band\b|&", rest) if t]:
            if tok.lower() in STOP:
                continue
            try:
                p = crew.find_person(conn, tok)
            except crew.AmbiguousName:
                problems.append(f"“{tok}” matches more than one person in “{seg}”. Use the full name.")
                amb = True
                continue
            (people if p else left).append(p if p else tok)
        if amb:
            continue
        job = crew.resolve_job(conn, " ".join(left)) if left else None
        if not job:
            problems.append(f"Couldn't tell which job in “{seg}”." if left else f"No job named in “{seg}”.")
            continue
        for d in days:
            for p in (people or [None]):
                cur = conn.execute("INSERT OR IGNORE INTO schedule (job_number, crew_id, day) VALUES (?, ?, ?)",
                                   (job["number"], p["id"] if p else None, d.isoformat()))
                saved += cur.rowcount
        if people and conn.execute("SELECT 1 WHERE 0").fetchone():  # pragma: no cover
            pass
    conn.commit()
    return {"saved": saved, "problems": problems}


def remove(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM schedule WHERE id = ?", (entry_id,))
    conn.commit()


def clear_job_day(conn: sqlite3.Connection, job_number: int, day: str) -> None:
    conn.execute("DELETE FROM schedule WHERE job_number = ? AND day = ?", (job_number, day))
    conn.commit()


def week(conn: sqlite3.Connection, start: date) -> dict:
    days = [start + timedelta(days=i) for i in range(7)]
    lo, hi = days[0].isoformat(), days[-1].isoformat()
    rows = conn.execute(
        "SELECT s.id, s.job_number, s.day, s.crew_id, c.name FROM schedule s LEFT JOIN crew c ON c.id = s.crew_id "
        "WHERE s.day BETWEEN ? AND ? ORDER BY c.name", (lo, hi)).fetchall()
    logged = {(r[0], r[1]): r[2] for r in conn.execute(
        "SELECT job_number, work_date, SUM(hours) FROM crew_hours WHERE work_date BETWEEN ? AND ? GROUP BY 1, 2", (lo, hi))}
    jobs: dict[int, dict] = {}
    for r in rows:
        j = jobs.setdefault(r["job_number"], {"job": books.get_job(conn, r["job_number"]), "cells": {d.isoformat(): [] for d in days}})
        j["cells"][r["day"]].append({"id": r["id"], "name": r["name"] or "Crew", "crew_id": r["crew_id"]})
    # Jobs with hours logged but no plan still appear, so the week shows what really happened too.
    for (jn, d), _h in logged.items():
        if jn not in jobs and books.get_job(conn, jn):
            jobs[jn] = {"job": books.get_job(conn, jn), "cells": {x.isoformat(): [] for x in days}}
    for jn, j in jobs.items():
        j["hours"] = {d.isoformat(): logged.get((jn, d.isoformat())) for d in days}
    per_person: dict[tuple, set] = {}
    for r in rows:
        if r["crew_id"]:
            per_person.setdefault((r["crew_id"], r["day"]), set()).add(r["job_number"])
    conflicts = sorted({(crew_name, d) for (cid, d), js in per_person.items() if len(js) > 1
                        for crew_name in [conn.execute("SELECT name FROM crew WHERE id = ?", (cid,)).fetchone()[0]]},
                       key=lambda x: (x[1], x[0]))
    return {"days": days, "jobs": sorted(jobs.values(), key=lambda j: j["job"]["number"]), "conflicts": conflicts,
            "start": start, "prev": start - timedelta(days=7), "next": start + timedelta(days=7)}
