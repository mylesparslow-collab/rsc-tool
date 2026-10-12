"""After a job is marked Complete: ask for a review a few days later, check in a year later.

The tool drafts each message; Nick sends it from his own email (a button opens it already written) and marks it done.
"""
import sqlite3
from datetime import date, timedelta

from . import brand, prefs

KINDS = {"review": ("Ask for a review", 3), "checkin": ("One-year check-in", 365)}
SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
PROMPT = {
    "review": """Write a short, warm email from a remodeling contractor, {owner}, to a client whose job just finished.
3 to 4 sentences. Thank them, say it was a pleasure, and ask if they'd leave an honest review. Include this link on its
own line exactly as given: {link}. If there is no link, ask them to reply with a few words about how it went.
Plain text, no subject line. Sign it "{owner}, {biz}".""",
    "checkin": """Write a short, friendly email from a remodeling contractor, {owner}, checking in a year after finishing a job.
3 to 4 sentences. Ask how the work is holding up and whether anything needs a look, mention they can reply or call {phone}
for a free quick visit, and that referrals are always appreciated. Plain text, no subject line.
Sign it "{owner}, {biz}".""",
}
SUBJECT = {"review": "Thank you from {biz}", "checkin": "Checking in on your {what}"}


def schedule(conn: sqlite3.Connection, job_number: int, today: date | None = None) -> None:
    """Called when a job becomes Complete. Safe to call twice; each kind is scheduled once per job."""
    today = today or date.today()
    for kind, (_, days) in KINDS.items():
        conn.execute("INSERT OR IGNORE INTO followups (job_number, kind, due_date) VALUES (?, ?, ?)",
                     (job_number, kind, (today + timedelta(days=days)).isoformat()))
    conn.commit()


def cancel(conn: sqlite3.Connection, job_number: int) -> None:
    """If a job is reopened, the follow-ups that haven't gone out are dropped."""
    conn.execute("DELETE FROM followups WHERE job_number = ? AND status = 'pending'", (job_number,))
    conn.commit()


def due(conn: sqlite3.Connection, today: date | None = None, ahead_days: int = 0) -> list[dict]:
    limit = ((today or date.today()) + timedelta(days=ahead_days)).isoformat()
    rows = conn.execute(
        "SELECT f.*, j.last_name, j.first_name, j.email, j.job_type, j.number || '-' || j.code AS job_id FROM followups f "
        "JOIN jobs j ON j.number = f.job_number WHERE f.status = 'pending' AND f.due_date <= ? ORDER BY f.due_date",
        (limit,)).fetchall()
    return [_row(r) for r in rows]


def upcoming(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT f.*, j.last_name, j.first_name, j.email, j.job_type, j.number || '-' || j.code AS job_id FROM followups f "
        "JOIN jobs j ON j.number = f.job_number WHERE f.status = 'pending' ORDER BY f.due_date LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def _row(r) -> dict:
    d = dict(r)
    d["title"] = KINDS[d["kind"]][0]
    d["subject"] = SUBJECT[d["kind"]].format(biz=brand.current()["name"], what=(d.get("job_type") or "project").lower())
    return d


def draft(model, conn: sqlite3.Connection, followup_id: int, phone: str) -> str:
    """Write (or return the already-written) message for one follow-up."""
    f = conn.execute("SELECT f.*, j.first_name, j.last_name, j.job_type, j.notes FROM followups f "
                     "JOIN jobs j ON j.number = f.job_number WHERE f.id = ?", (followup_id,)).fetchone()
    if f["draft"]:
        return f["draft"]
    owner = prefs.get(conn, "owner_name") or "Nick"
    link = prefs.get(conn, "review_url")
    first = f["first_name"] or f["last_name"]
    try:
        text = model.extract(PROMPT[f["kind"]].format(biz=brand.current()["name"], owner=owner, link=link or "(none)", phone=phone),
                             f"Client: {first}. Project: {f['job_type'] or 'remodel'}. Notes: {f['notes'][:300]}", SCHEMA)
        text = (text.get("message") or "").strip()
    except Exception:
        text = ""
    if len(text) < 40 or (f["kind"] == "review" and link and link not in text):
        text = _template(f["kind"], first, link, owner, phone)
    conn.execute("UPDATE followups SET draft = ? WHERE id = ?", (text, followup_id))
    conn.commit()
    return text


def _template(kind: str, first: str, link: str, owner: str, phone: str) -> str:
    biz = brand.current()["name"]
    if kind == "review":
        ask = f"If you have a minute, an honest review would mean a lot to a small business like ours:\n{link}" if link \
            else "If you have a minute, a few words back about how it went would mean a lot to a small business like ours."
        return f"Hi {first},\n\nThank you again. It was a pleasure working on your home. {ask}\n\n{owner}\n{biz}"
    return (f"Hi {first},\n\nIt's been a year since we finished your project, so I wanted to check in. How is everything holding up? "
            f"If anything needs a look, reply here or call {phone} and I'll stop by for a free quick visit. And if friends or "
            f"neighbors are planning work, I'd appreciate the introduction.\n\n{owner}\n{biz}")


def mark(conn: sqlite3.Connection, followup_id: int, status: str) -> None:
    if status not in ("sent", "skipped"):
        raise ValueError(status)
    conn.execute("UPDATE followups SET status = ?, done_at = datetime('now') WHERE id = ?", (status, followup_id))
    conn.commit()
