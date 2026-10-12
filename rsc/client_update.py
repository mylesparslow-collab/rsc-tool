"""Weekly progress note for the homeowner: what got done this week, what's next, and photos from the site.

The facts come from the checked-off steps (with the date each was finished) and the scope of work. The model only turns them
into a friendly paragraph; if it's unavailable or drops the facts, a plain template is used. Nick reads it, edits it if he
likes, and opens it in Mail. Photos are kept on the job so he can drag them into the message.
"""
import sqlite3
from datetime import date, timedelta

from . import brand, estimates, prefs

SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
PROMPT = """Write a short, warm weekly progress email from {owner} of {biz} to a homeowner whose project is underway.
Use only the facts given. 4 to 7 sentences, plain words, no jargon, no promises about dates or cost that are not in the facts.
Say what was finished this week, what comes next, and invite questions (call {phone}). Mention that photos are attached if
the facts say so. Plain text, no subject line, sign it "{owner}, {biz}"."""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS site_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_number INTEGER NOT NULL REFERENCES jobs(number),
        mime TEXT NOT NULL, data BLOB NOT NULL, taken_on TEXT NOT NULL DEFAULT (date('now')))""")


def add_photo(conn, job_number: int, mime: str, data: bytes) -> int:
    ensure_table(conn)
    cur = conn.execute("INSERT INTO site_photos (job_number, mime, data) VALUES (?, ?, ?)", (job_number, mime, data))
    conn.commit()
    return cur.lastrowid


def photos(conn, job_number: int, since: str | None = None) -> list[dict]:
    ensure_table(conn)
    q, a = "SELECT id, taken_on FROM site_photos WHERE job_number = ?", [job_number]
    if since:
        q, a = q + " AND taken_on >= ?", a + [since]
    return [dict(r) for r in conn.execute(q + " ORDER BY id", a)]


def photo_file(conn, job_number: int, photo_id: int):
    ensure_table(conn)
    r = conn.execute("SELECT mime, data FROM site_photos WHERE id = ? AND job_number = ?", (photo_id, job_number)).fetchone()
    return (r["mime"], bytes(r["data"])) if r else None


def delete_photo(conn, job_number: int, photo_id: int) -> None:
    ensure_table(conn)
    conn.execute("DELETE FROM site_photos WHERE id = ? AND job_number = ?", (photo_id, job_number))
    conn.commit()


def facts(conn: sqlite3.Connection, job_number: int, today: date | None = None) -> dict | None:
    est = estimates.get(conn, job_number)
    if not est or not est["phases"]:
        return None
    today = today or date.today()
    since = (today - timedelta(days=7)).isoformat()
    done = {r[0]: r[1] for r in conn.execute("SELECT step_no, done_on FROM step_done WHERE job_number = ?", (job_number,))}
    flat, n = [], 0
    for p in est["phases"]:
        for text in p["steps"]:
            n += 1
            flat.append((n, text, p["title"]))
    this_week = [t for k, t, _ in flat if done.get(k, "") >= since]
    upcoming = [t for k, t, _ in flat if k not in done][:4]
    phase_now = next((ph for k, _, ph in flat if k not in done), None)
    return {"this_week": this_week[:8], "next": upcoming, "phase": phase_now, "done": len(done), "total": n,
            "percent": round(100 * len(done) / n) if n else 0, "photos": photos(conn, job_number, since)}


def fallback(job: dict, f: dict, owner: str, phone: str) -> str:
    biz = brand.current()["name"]
    first = job.get("first_name") or "there"
    lines = [f"Hi {first},", "", "Here's where your project stands this week."]
    if f["this_week"]:
        lines.append("We finished: " + "; ".join(s.rstrip(".").lower() for s in f["this_week"][:5]) + ".")
    else:
        lines.append("It was a quieter week on site, with no steps finished.")
    if f["next"]:
        lines.append("Coming up next: " + "; ".join(s.rstrip(".").lower() for s in f["next"][:3]) + ".")
    lines.append(f"We're about {f['percent']}% through the planned steps.")
    if f["photos"]:
        lines.append("I've attached a few photos from the site.")
    lines += ["", f"If you have any questions, reply here or call {phone}.", "", "Thank you,", owner, biz]
    return "\n".join(lines)


def draft(model, conn, job: dict, phone: str, today: date | None = None) -> dict | None:
    f = facts(conn, job["number"], today)
    if not f:
        return None
    owner = prefs.get(conn, "owner_name") or brand.current()["owner"]
    text = ""
    if model is not None:
        try:
            user = (f"Homeowner: {job.get('first_name') or 'the client'}. Finished this week: {f['this_week'] or 'nothing'}. "
                    f"Next: {f['next'] or 'wrapping up'}. Percent done: {f['percent']}. Photos attached: {'yes' if f['photos'] else 'no'}.")
            text = (model.extract(PROMPT.format(owner=owner, biz=brand.current()["name"], phone=phone), user, SCHEMA)
                    .get("message") or "").strip()
        except Exception:
            text = ""
    if len(text) < 80:
        text = fallback(job, f, owner, phone)
    return {"text": text, "facts": f, "subject": f"{job.get('last_name', '')} project: this week's update".strip()}
