"""The daily work sheet: what the crew should work on today, job by job.

Built from the scope of work and which steps are already checked off, so it needs no extra typing. Each job in progress
shows the rest of the current phase (up to 8 steps), who has been working on it, what to call in for inspection, and a
note from Nick for the day. It goes out by email on weekday mornings (`rsc daily-sheet --send`) and is on the Today page.
"""
import smtplib
import sqlite3
from datetime import date, timedelta
from email.message import EmailMessage

from . import books, brand, crew, estimates, prefs, report

MAX_STEPS = 8


def done_steps(conn: sqlite3.Connection, job_number: int) -> set[int]:
    return {r[0] for r in conn.execute("SELECT step_no FROM step_done WHERE job_number = ?", (job_number,))}


def set_steps(conn: sqlite3.Connection, job_number: int, shown: list[int], done: list[int], today: date | None = None) -> None:
    """Of the steps that were on screen, the ticked ones are done and the rest are not."""
    when = (today or date.today()).isoformat()
    est = estimates.get(conn, job_number)
    total = sum(len(p["steps"]) for p in est["phases"]) if est else 0
    for n in shown:
        if not 1 <= n <= total:
            continue
        if n in done:
            conn.execute("INSERT OR IGNORE INTO step_done (job_number, step_no, done_on) VALUES (?, ?, ?)", (job_number, n, when))
        else:
            conn.execute("DELETE FROM step_done WHERE job_number = ? AND step_no = ?", (job_number, n))
    conn.commit()


def set_note(conn: sqlite3.Connection, job_number: int, day: str, note: str) -> None:
    note = (note or "").strip()[:600]
    if note:
        conn.execute("INSERT INTO daily_notes (job_number, day, note) VALUES (?, ?, ?) ON CONFLICT(job_number, day) DO UPDATE SET note = excluded.note",
                     (job_number, day, note))
    else:
        conn.execute("DELETE FROM daily_notes WHERE job_number = ? AND day = ?", (job_number, day))
    conn.commit()


def _plan_for(conn: sqlite3.Connection, job: dict, today: date) -> dict | None:
    est = estimates.get(conn, job["number"])
    if not est or not est["phases"]:
        return None
    done = done_steps(conn, job["number"])
    flat, n = [], 0
    for pi, p in enumerate(est["phases"]):
        for text in p["steps"]:
            n += 1
            flat.append({"n": n, "text": text, "phase": pi, "done": n in done})
    remaining = [s for s in flat if not s["done"]]
    since = (today - timedelta(days=7)).isoformat()
    people = [r[0] for r in conn.execute(
        "SELECT DISTINCT c.name FROM crew_hours h JOIN crew c ON c.id = h.crew_id WHERE h.job_number = ? AND h.work_date >= ? ORDER BY c.name",
        (job["number"], since))]
    planned = [r[0] or "Crew" for r in conn.execute(
        "SELECT c.name FROM schedule s LEFT JOIN crew c ON c.id = s.crew_id WHERE s.job_number = ? AND s.day = ? ORDER BY c.name",
        (job["number"], today.isoformat()))]
    people = planned + [p for p in people if p not in planned]      # who Nick planned for today, then who was there lately
    note = conn.execute("SELECT note FROM daily_notes WHERE job_number = ? AND day = ?", (job["number"], today.isoformat())).fetchone()
    out = {"job": job, "steps": [], "phase": "", "inspection": "", "people": people, "note": note[0] if note else "",
           "done": len(done & {s["n"] for s in flat}), "total": len(flat), "finished": not remaining,
           "materials": [], "duration": est.get("duration", ""), "crew": est.get("crew", "")}
    if remaining:
        cur = remaining[0]["phase"]
        in_phase = [s for s in remaining if s["phase"] == cur]
        out["steps"] = in_phase[:MAX_STEPS]
        out["phase"] = est["phases"][cur]["title"]
        if len(in_phase) <= MAX_STEPS and est["phases"][cur].get("inspection"):
            out["inspection"] = est["phases"][cur]["inspection"]
        out["more"] = max(0, len(in_phase) - MAX_STEPS)
        if not done:  # nothing started yet: remind what has to be on site
            out["materials"] = [x.strip() for x in (est.get("materials_list") or "").splitlines() if x.strip()][:10]
    return out


def build(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    jobs = []
    coming = []
    for j in books.list_jobs(conn, active_only=True):
        if j["status"] == "In Progress":
            plan = _plan_for(conn, j, today)
            if plan:
                jobs.append(plan)
        elif j["status"] == "Signed":
            plan = _plan_for(conn, j, today)
            if plan and plan["steps"]:
                coming.append({"job": j, "phase": plan["phase"], "note": plan["note"]})
    return {"date": today, "jobs": jobs, "coming": coming}


def subject(d: dict) -> str:
    n = len(d["jobs"])
    return f"Today's work, {d['date'].strftime('%a %b')} {d['date'].day}: {n} job{'s' if n != 1 else ''}"


def render_text(d: dict) -> str:
    L = [f"{brand.current()['name']}: work for {d['date'].strftime('%A, %B')} {d['date'].day}", ""]
    if not d["jobs"]:
        L += ["No jobs are in progress today."]
    for p in d["jobs"]:
        j = p["job"]
        L.append(f"{j['job_id']} {j['last_name']}".upper())
        L.append(f"  {j['address'] or 'address not on file'}" + (f"  |  Client phone: {j['phone']}" if j.get("phone") else ""))
        if p["people"]:
            L.append("  On this job: " + ", ".join(p["people"]))
        if p["note"]:
            L.append(f"  FROM NICK: {p['note']}")
        if p["finished"]:
            L.append("  Every step is checked off. Walk the job with the client and tell Nick it's ready to close out.")
        else:
            L.append(f"  Today: {p['phase']} ({p['done']} of {p['total']} steps done)")
            L += [f"    [ ] {s['n']}. {s['text']}" for s in p["steps"]]
            if p.get("more"):
                L.append(f"    ...and {p['more']} more steps in this phase")
            if p["inspection"]:
                L.append(f"  When this phase is done, call in: {p['inspection']}")
            if p["materials"]:
                L.append("  Before you start, make sure these are on site:")
                L += [f"    - {m}" for m in p["materials"]]
        L.append("")
    if d["coming"]:
        L.append("COMING UP")
        L += [f"  {c['job']['job_id']} {c['job']['last_name']}: starts with {c['phase']}" for c in d["coming"]]
        L.append("")
    L += ["Please log hours today (who worked, how many) and send photos of any receipts.", "Anything the client asks for that isn't in the steps is a change order: tell Nick first."]
    return "\n".join(L) + "\n"


def recipients(conn: sqlite3.Connection) -> list[str]:
    return prefs.daily_recipients(conn)


def send(conn: sqlite3.Connection, address: str, password: str, d: dict, host: str = "smtp.gmail.com") -> list[str]:
    to = recipients(conn)
    if not to:
        raise ValueError("Add who should get the daily sheet on the Setup page, or an email on the Crew page.")
    text = render_text(d)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = address, ", ".join(to), subject(d)
    msg.set_content(text)
    msg.add_alternative(report.render_html(text), subtype="html")
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(address, password)
        s.send_message(msg)
    return to
