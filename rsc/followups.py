"""After a job is marked Complete: ask for a review a few days later, check in a year later.

The tool drafts each message; Nick sends it from his own email or phone (a button opens it already written) and marks
it done. When the review request is marked sent, the same follow-up comes back a week later as a gentle reminder
(round 2), unless Nick marks that the client already left one.
"""
import sqlite3
from datetime import date, timedelta

from . import brand, prefs

KINDS = {"review": ("Ask for a review", 3), "checkin": ("One-year check-in", 365)}
REMINDER_DAYS = 7  # after the review request goes out, one gentle reminder
SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
PROMPT = {
    "review": """Write a short, warm email from a remodeling contractor, {owner}, to a client whose job just finished.
3 to 4 sentences. Thank them, say it was a pleasure, and ask if they'd leave an honest review. Include this link on its
own line exactly as given: {link}. If there is no link, ask them to reply with a few words about how it went.
Plain text, no subject line. Sign it "{owner}, {biz}".""",
    "review2": """Write a very short, friendly note from a remodeling contractor, {owner}, to a client who was asked for a review a week ago.
2 sentences. Say no pressure at all and that it only takes a minute, and include this link on its own line exactly as
given: {link}. If there is no link, ask them to reply with a few words about how it went. Never guilt or push.
Plain text, no subject line. Sign it "{owner}, {biz}".""",
    "checkin": """Write a short, friendly email from a remodeling contractor, {owner}, checking in a year after finishing a job.
3 to 4 sentences. Ask how the work is holding up and whether anything needs a look, mention they can reply or call {phone}
for a free quick visit, and that referrals are always appreciated. Plain text, no subject line.
Sign it "{owner}, {biz}".""",
}
SUBJECT = {"review": "Thank you from {biz}", "review2": "A quick favor from {biz}", "checkin": "Checking in on your {what}"}


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
        "SELECT f.*, j.last_name, j.first_name, j.email, j.phone, j.job_type, j.number || '-' || j.code AS job_id FROM followups f "
        "JOIN jobs j ON j.number = f.job_number WHERE f.status = 'pending' AND f.due_date <= ? ORDER BY f.due_date",
        (limit,)).fetchall()
    return [_row(r) for r in rows]


def upcoming(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT f.*, j.last_name, j.first_name, j.email, j.phone, j.job_type, j.number || '-' || j.code AS job_id FROM followups f "
        "JOIN jobs j ON j.number = f.job_number WHERE f.status = 'pending' ORDER BY f.due_date LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def _key(f) -> str:
    """Which message this follow-up is now: the review request, its reminder, or the check-in."""
    return "review2" if f["kind"] == "review" and f["round"] > 1 else f["kind"]


def _row(r) -> dict:
    d = dict(r)
    d["title"] = "Review reminder" if _key(d) == "review2" else KINDS[d["kind"]][0]
    d["sms"] = "".join(ch for ch in d.get("phone") or "" if ch.isdigit() or ch == "+")
    d["subject"] = SUBJECT[_key(d)].format(biz=brand.current()["name"], what=(d.get("job_type") or "project").lower())
    return d


def draft(model, conn: sqlite3.Connection, followup_id: int, phone: str) -> str:
    """Write (or return the already-written) message for one follow-up."""
    f = conn.execute("SELECT f.*, j.first_name, j.last_name, j.job_type, j.notes FROM followups f "
                     "JOIN jobs j ON j.number = f.job_number WHERE f.id = ?", (followup_id,)).fetchone()
    link = prefs.get(conn, "review_url")
    if f["draft"] and not (f["kind"] == "review" and link and link not in f["draft"]):
        return f["draft"]  # kept, unless the review link was added (or changed) after it was written
    owner = prefs.get(conn, "owner_name") or "Nick"
    key = _key(f)
    first = f["first_name"] or f["last_name"]
    try:
        text = model.extract(PROMPT[key].format(biz=brand.current()["name"], owner=owner, link=link or "(none)", phone=phone),
                             f"Client: {first}. Project: {f['job_type'] or 'remodel'}. Notes: {f['notes'][:300]}", SCHEMA)
        text = (text.get("message") or "").strip()
    except Exception:
        text = ""
    if len(text) < 40 or (f["kind"] == "review" and link and link not in text):
        text = _template(key, first, link, owner, phone)
    conn.execute("UPDATE followups SET draft = ? WHERE id = ?", (text, followup_id))
    conn.commit()
    return text


def _template(kind: str, first: str, link: str, owner: str, phone: str) -> str:
    biz = brand.current()["name"]
    if kind == "review":
        ask = f"If you have a minute, an honest review would mean a lot to a small business like ours:\n{link}" if link \
            else "If you have a minute, a few words back about how it went would mean a lot to a small business like ours."
        return f"Hi {first},\n\nThank you again. It was a pleasure working on your home. {ask}\n\n{owner}\n{biz}"
    if kind == "review2":
        ask = f"If you get a minute, here's the link again:\n{link}" if link else "If you get a minute, a few words back about how it went would be great."
        return f"Hi {first},\n\nNo pressure at all, just a quick reminder. {ask}\n\nThanks again,\n{owner}\n{biz}"
    return (f"Hi {first},\n\nIt's been a year since we finished your project, so I wanted to check in. How is everything holding up? "
            f"If anything needs a look, reply here or call {phone} and I'll stop by for a free quick visit. And if friends or "
            f"neighbors are planning work, I'd appreciate the introduction.\n\n{owner}\n{biz}")


def mark(conn: sqlite3.Connection, followup_id: int, status: str, today: date | None = None) -> None:
    """sent, skipped, or reviewed (the client already left one: no reminder)."""
    if status not in ("sent", "skipped", "reviewed"):
        raise ValueError(status)
    f = conn.execute("SELECT kind, round FROM followups WHERE id = ?", (followup_id,)).fetchone()
    if status == "sent" and f and f["kind"] == "review" and f["round"] == 1:
        due_date = ((today or date.today()) + timedelta(days=REMINDER_DAYS)).isoformat()
        conn.execute("UPDATE followups SET round = 2, due_date = ?, draft = '' WHERE id = ?", (due_date, followup_id))
        conn.commit()
        return
    status = "sent" if status == "reviewed" else status
    conn.execute("UPDATE followups SET status = ?, done_at = datetime('now') WHERE id = ?", (status, followup_id))
    conn.commit()
