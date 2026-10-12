"""Who worked on what, and whether the people working for Nick are properly insured.

Hours are typed (or spoken) in plain words: "Tue Mike 8, Dave 6 on Delano". The local model reads them; the code checks
every name, job, date and number before anything is saved, and a plain pattern reader takes over if the model is off.
Insurance certificates are photographed; the vision model reads the insurer, policy number and expiry date.
"""
import math
import re
import sqlite3
from datetime import date, timedelta

from . import books

ROLES = ("employee", "helper", "sub")
ROLE_LABEL = {"employee": "Employee (on payroll)", "helper": "Helper (paid by hand)", "sub": "Subcontractor"}
CERT_KINDS = ["General liability", "Workers comp", "Disability / PFL", "Auto", "Other"]
DEFAULT_BURDEN = {"employee": 18.0, "helper": 0.0, "sub": 0.0}   # payroll taxes + workers comp when on payroll
EXPIRY_WARN_DAYS = 30
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYWORD = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
FILLER_WORDS = r"(?:worked|put in|did|logged|had|was there|for)"


class AmbiguousName(ValueError):
    pass


class CrewError(ValueError):
    pass


# ---------------------------------------------------------------- people
def clean_email(text: str) -> str:
    t = (text or "").strip()
    return t if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t) else ""



def add_person(conn: sqlite3.Connection, name: str, role: str = "helper", wage: float = 0, burden_pct: float | None = None, email: str = "") -> int:
    name = (name or "").strip()
    if not name:
        raise CrewError("Add a name.")
    if role not in ROLES:
        raise CrewError("Pick employee, helper or subcontractor.")
    if not math.isfinite(wage) or wage < 0 or wage > 500:
        raise CrewError("That hourly rate doesn't look right.")
    if burden_pct is None:
        burden_pct = DEFAULT_BURDEN[role]
    cur = conn.execute("INSERT INTO crew (name, role, wage, burden_pct, email) VALUES (?, ?, ?, ?, ?)",
                       (name, role, wage, burden_pct, clean_email(email)))
    conn.commit()
    return cur.lastrowid


def update_person(conn: sqlite3.Connection, crew_id: int, name: str, role: str, wage: float, active: bool, email: str = "") -> None:
    if role not in ROLES:
        raise CrewError("Pick employee, helper or subcontractor.")
    if not (name or "").strip():
        raise CrewError("Add a name.")
    if not math.isfinite(wage) or wage < 0 or wage > 500:
        raise CrewError("That hourly rate doesn't look right.")
    old = conn.execute("SELECT role, burden_pct FROM crew WHERE id = ?", (crew_id,)).fetchone()
    if not old:
        raise CrewError("No such person.")
    burden = old["burden_pct"] if old["role"] == role else DEFAULT_BURDEN[role]
    conn.execute("UPDATE crew SET name = ?, role = ?, wage = ?, burden_pct = ?, active = ?, email = ? WHERE id = ?",
                 (name.strip(), role, wage, burden, 1 if active else 0, clean_email(email), crew_id))
    conn.commit()


def people(conn: sqlite3.Connection, active_only: bool = False) -> list[dict]:
    sql = ("SELECT c.*, COALESCE((SELECT SUM(hours) FROM crew_hours h WHERE h.crew_id = c.id), 0) AS total_hours, "
           "COALESCE((SELECT SUM(hours) FROM crew_hours h WHERE h.crew_id = c.id AND h.work_date >= ?), 0) AS recent_hours "
           "FROM crew c" + (" WHERE c.active = 1" if active_only else "") + " ORDER BY c.active DESC, c.name COLLATE NOCASE")
    since = (date.today() - timedelta(days=30)).isoformat()
    return [dict(r) for r in conn.execute(sql, (since,))]


def find_person(conn: sqlite3.Connection, text: str) -> dict | None:
    """A name as typed ('mike', 'Mike R') -> the one person it means. None when nobody matches.
    Raises AmbiguousName when two people could be meant ('Mike' with a Mike R and a Mike S)."""
    key = re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()
    if not key:
        return None
    rows = [dict(r) for r in conn.execute("SELECT * FROM crew ORDER BY active DESC")]
    norm = lambda r: re.sub(r"[^a-z0-9 ]", "", r["name"].lower()).strip()
    tests = [lambda n: n == key,
             lambda n: bool(n.split()) and n.split()[0] == key.split()[0] and (len(key.split()) == 1 or n == key),
             lambda n: len(key) >= 3 and n.startswith(key)]
    for test in tests:
        hits = [r for r in rows if test(norm(r))]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            actives = [h for h in hits if h["active"]]
            if len(actives) == 1:
                return actives[0]
            raise AmbiguousName(f"Which {text.strip()}? " + ", ".join(h["name"] for h in hits[:4]))
    return None


# ---------------------------------------------------------------- reading typed hours
SCHEMA = {
    "type": "object",
    "properties": {"entries": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "hours": {"type": "number"}, "day": {"type": "string"}, "job_clue": {"type": "string"},
        "note": {"type": "string"}}, "required": ["name", "hours", "day", "job_clue", "note"]}}},
    "required": ["entries"],
}

PROMPT = """A small remodeling contractor types or says who worked how many hours. List one entry per person per day.
name: the person's name as written. hours: the number of hours (half a day = 4, a full day = 8 only if no hours are given).
day: the day as written ("Tue", "yesterday", "10/7") or "" if none. job_clue: the job it was for (a customer's last name,
an address or a job number) or "" if none. note: any other detail, such as "demo" or "framing", or "".
Never invent people or hours that are not in the text."""


def resolve_day(text: str, today: date | None = None) -> date | None:
    """A day as written -> a date, or None when it can't be read (never silently 'today' for something unclear)."""
    today = today or date.today()
    t = (text or "").strip().lower()
    if not t or t == "today":
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    m = re.fullmatch(r"(?:last\s+)?(" + DAYWORD + ")", t)
    if m:
        i = [w for w in WEEKDAYS if m.group(1).startswith(w)][0]
        back = (today.weekday() - WEEKDAYS.index(i)) % 7
        return today - timedelta(days=back or (7 if t.startswith("last") else 0))
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", t)
    if m:
        year = (int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)) if m.group(3) else today.year
        try:
            d = date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        return d if d <= today or m.group(3) else d.replace(year=year - 1)
    return None


def _regex_entries(text: str) -> list[dict]:
    """No model? 'Tue: Mike 8, Dave 6 on Delano' or 'Mike 8 on Delano, Dave 6 on Smith' still works.
    Names must start with a capital letter. A job named later in the text applies to people before it that name none."""
    day_m = re.search(r"\b(today|yesterday|(?:last\s+)?" + DAYWORD + r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", text, re.I)
    day = day_m.group(1) if day_m else ""
    out, last_clue = [], ""
    for seg in re.split(r"[;,\n]+", text):
        clue = ""
        cm = re.search(r"\b(?:on|at|for|job)\s+(?:the\s+)?([A-Za-z0-9][\w\-' ]*)\s*$", seg.strip(), re.I)
        if cm:
            clue = cm.group(1).strip()
            seg = seg[:cm.start()]
        body = re.sub(r"\b(today|yesterday|(?:last\s+)?" + DAYWORD + r")\b[:,]?", " ", seg, flags=re.I)
        found = re.findall(r"\b([A-Z][a-z.'-]+(?: [A-Z][a-z]+)?)(?:\s+" + FILLER_WORDS + r")?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours)?\b", body)
        for name, hrs in found:
            out.append({"name": name, "hours": float(hrs), "day": day, "job_clue": clue, "note": "", "_seg": len(out)})
        if clue:
            last_clue = clue
            for e in out:
                if not e["job_clue"]:
                    e["job_clue"] = clue
    for e in out:
        e["job_clue"] = e["job_clue"] or last_clue
        e["from_pattern"] = True
        e.pop("_seg", None)
    return out


def resolve_job(conn: sqlite3.Connection, clue: str, default: int | None = None) -> dict | None:
    clue_l = (clue or "").lower().strip()
    jobs = books.list_jobs(conn)
    if clue_l:
        digits = re.findall(r"\d{3,}", clue_l)
        for j in jobs:
            if str(j["number"]) in digits or j["job_id"].lower() in clue_l:
                return j
        hits = [j for j in jobs if j["last_name"] and j["last_name"].lower() in clue_l]
        if not hits:
            hits = [j for j in jobs if j["address"] and len(clue_l) > 3 and clue_l in j["address"].lower()]
        if len(hits) > 1:
            live = [j for j in hits if j["status"] in books.ACTIVE]
            hits = live if len(live) == 1 else hits
        return hits[0] if len(hits) == 1 else None   # a job that was named but isn't found is never swapped for the default
    return books.get_job(conn, default) if default else None


def read_entries(model, text: str) -> list[dict]:
    entries = []
    if model is not None:
        try:
            entries = model.extract(PROMPT, text, SCHEMA).get("entries", [])
        except Exception:
            entries = []
    return entries or _regex_entries(text)


def log_hours(conn: sqlite3.Connection, model, text: str, default_job: int | None = None, today: date | None = None) -> dict:
    """Parse, check and save. Returns {'saved': [...], 'problems': [...], 'new_people': [...]}."""
    result = {"saved": [], "problems": [], "new_people": []}
    if not (text or "").strip():
        raise CrewError("Type who worked and for how long, like: Tue Mike 8, Dave 6 on Delano")
    for e in read_entries(model, text):
        name = str(e.get("name", "")).strip()
        try:
            hours = float(e.get("hours") or 0)
        except (TypeError, ValueError):
            hours = 0
        if not name or not 0 < hours <= 16:
            result["problems"].append(f"Skipped '{name or '?'}': hours must be between 0 and 16.")
            continue
        job = resolve_job(conn, e.get("job_clue", ""), default_job)
        if not job:
            result["problems"].append(f"Skipped {name}: which job? Add the customer's name, like 'on Delano'.")
            continue
        d = resolve_day(e.get("day", ""), today)
        if d is None:
            result["problems"].append(f"Skipped {name}: I couldn't read the day '{e.get('day')}'. Try a weekday name or 10/7.")
            continue
        try:
            person = find_person(conn, name)
        except AmbiguousName as exc:
            result["problems"].append(f"Skipped {name}: {exc}")
            continue
        if not person:
            if not re.fullmatch(r"[A-Za-z][A-Za-z.' -]{0,40}", name):
                result["problems"].append(f"Skipped '{name}': that doesn't look like a name.")
                continue
            pid = add_person(conn, name.title(), "helper", 0)
            person = {"id": pid, "name": name.title()}
            result["new_people"].append(person["name"])
        conn.execute("INSERT INTO crew_hours (job_number, crew_id, work_date, hours, note) VALUES (?, ?, ?, ?, ?)",
                     (job["number"], person["id"], d.isoformat(), hours, str(e.get("note", ""))[:200]))
        result["saved"].append({"name": person["name"], "hours": hours, "date": d.isoformat(), "job": job["job_id"]})
    conn.commit()
    return result


def delete_hours(conn: sqlite3.Connection, hours_id: int) -> None:
    conn.execute("DELETE FROM crew_hours WHERE id = ?", (hours_id,))
    conn.commit()


def recent_hours(conn: sqlite3.Connection, limit: int = 30, job_number: int | None = None) -> list[dict]:
    sql = ("SELECT h.*, c.name, c.role, j.last_name, j.number || '-' || j.code AS job_id FROM crew_hours h JOIN crew c ON c.id = h.crew_id "
           "JOIN jobs j ON j.number = h.job_number" + (" WHERE h.job_number = ?" if job_number else "") +
           " ORDER BY h.work_date DESC, h.id DESC LIMIT ?")
    args = (job_number, limit) if job_number else (limit,)
    return [dict(r) for r in conn.execute(sql, args)]


def hours_for_job(conn: sqlite3.Connection, job_number: int) -> float:
    return conn.execute("SELECT COALESCE(SUM(hours), 0) FROM crew_hours WHERE job_number = ?", (job_number,)).fetchone()[0]


def labor_cost_for_job(conn: sqlite3.Connection, job_number: int) -> float:
    """Hours x pay x (1 + payroll burden). Zero for people whose pay hasn't been entered."""
    row = conn.execute("SELECT COALESCE(SUM(h.hours * c.wage * (1 + c.burden_pct / 100.0)), 0) FROM crew_hours h "
                       "JOIN crew c ON c.id = h.crew_id WHERE h.job_number = ?", (job_number,)).fetchone()
    return round(row[0], 2)


# ---------------------------------------------------------------- insurance certificates
CERT_SCHEMA = {
    "type": "object",
    "properties": {"is_certificate": {"type": "boolean"}, "holder": {"type": "string"},
                   "kind": {"type": "string", "enum": CERT_KINDS + [""]}, "insurer": {"type": "string"},
                   "policy_no": {"type": "string"}, "expires": {"type": "string"}},
    "required": ["is_certificate", "holder", "kind", "insurer", "policy_no", "expires"],
}
CERT_PROMPT = """This is a photo of an insurance certificate (ACORD form or similar) for a contractor. Read: holder (the name of the
insured business or person at the top), kind (General liability, Workers comp, Disability / PFL, Auto, or Other),
insurer (the insurance company), policy_no, and expires (the policy expiration date as YYYY-MM-DD; if several policies are
listed, the earliest expiration of the main one). Use "" for anything you cannot read. If it is not an insurance certificate,
set is_certificate to false. Never guess a date."""


def clean_date(text: str) -> str:
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return t
        except ValueError:
            return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        try:
            return date(y, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return ""
    return ""


def read_certificate(model, image: bytes) -> dict:
    raw = model.extract(CERT_PROMPT, "Read this certificate.", CERT_SCHEMA, images=[image])
    if raw.get("is_certificate") is False:
        return {}
    return {"kind": raw.get("kind") or "General liability", "insurer": str(raw.get("insurer", ""))[:80],
            "policy_no": str(raw.get("policy_no", ""))[:60], "expires": clean_date(raw.get("expires", "")),
            "holder": str(raw.get("holder", ""))[:80]}


def add_certificate(conn: sqlite3.Connection, crew_id: int | None, kind: str, insurer: str = "", policy_no: str = "",
                    expires: str = "", mime: str = "", data: bytes | None = None) -> int:
    if kind not in CERT_KINDS:
        kind = "Other"
    if crew_id is not None and not conn.execute("SELECT 1 FROM crew WHERE id = ?", (crew_id,)).fetchone():
        raise CrewError("No such person.")
    cur = conn.execute("INSERT INTO certificates (crew_id, kind, insurer, policy_no, expires, mime, file) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (crew_id, kind, insurer, policy_no, clean_date(expires), mime, data))
    conn.commit()
    return cur.lastrowid


def delete_certificate(conn: sqlite3.Connection, cert_id: int) -> None:
    conn.execute("DELETE FROM certificates WHERE id = ?", (cert_id,))
    conn.commit()


def certificates(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = [dict(r) for r in conn.execute(
        "SELECT ce.id, ce.crew_id, ce.kind, ce.insurer, ce.policy_no, ce.expires, ce.mime, ce.file IS NOT NULL AS has_file, "
        "COALESCE(c.name, 'Our business') AS holder FROM certificates ce LEFT JOIN crew c ON c.id = ce.crew_id "
        "ORDER BY holder, ce.kind")]
    for r in rows:
        r["days_left"], r["state"] = None, "no date"
        if r["expires"]:
            r["days_left"] = (date.fromisoformat(r["expires"]) - today).days
            r["state"] = "expired" if r["days_left"] < 0 else "soon" if r["days_left"] <= EXPIRY_WARN_DAYS else "ok"
    return rows


def certificate_file(conn: sqlite3.Connection, cert_id: int):
    row = conn.execute("SELECT mime, file FROM certificates WHERE id = ? AND file IS NOT NULL", (cert_id,)).fetchone()
    return (row["mime"], bytes(row["file"])) if row else None


def alerts(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """What needs attention about insurance: expired, expiring within 30 days, or a sub working with nothing on file."""
    today = today or date.today()
    out = []
    certs = certificates(conn, today)
    for c in certs:
        if c["state"] == "expired":
            out.append({"level": "bad", "text": f"{c['holder']}'s {c['kind']} certificate expired {-c['days_left']} day(s) ago ({c['expires']})."})
        elif c["state"] == "soon":
            out.append({"level": "warn", "text": f"{c['holder']}'s {c['kind']} certificate expires in {c['days_left']} day(s) ({c['expires']})."})
    for p in people(conn, active_only=True):
        if p["role"] != "sub" or not p["total_hours"]:
            continue
        valid = [c for c in certs if c["crew_id"] == p["id"] and c["state"] in ("ok", "soon")]
        if not valid:
            out.append({"level": "bad", "text": f"{p['name']} (subcontractor) has {p['total_hours']:g} hours logged but no current insurance certificate on file. "
                                                "If a sub without insurance is hurt on a job, the homeowner's claim can land on you."})
    for p in people(conn, active_only=True):
        if p["total_hours"] and not p["wage"]:
            out.append({"level": "warn", "text": f"{p['name']} has {p['total_hours']:g} hours logged but no hourly pay set, so job costs leave them out. Set it on the Crew page."})
    if not any(c["crew_id"] is None for c in certs):
        out.append({"level": "warn", "text": "No certificate for the business's own insurance is on file yet. Add one so it's handy when a client asks."})
    return out


# ---------------------------------------------------------------- what would payroll cost?
def payroll_cost(workers: int, wage: float, hours: float, wc_rate: float = 8.0, dbl_pfl: float = 450.0, service: bool = True) -> dict:
    """Yearly cost of running payroll for `workers` people. Defaults come from the crew and employment research:
    FICA 7.65%, workers comp about $8 per $100 of wages for carpentry, NY unemployment 4.1% of the first $13,000
    (new employer), federal unemployment 0.6% of the first $7,000, disability/paid family leave $300-600 a year,
    and a payroll service ($49 a month plus $6 a person). These are planning numbers, not a quote."""
    gross_each = wage * hours
    gross = gross_each * workers
    items = {
        "Social Security and Medicare (employer half, 7.65%)": gross * 0.0765,
        f"Workers comp (about ${wc_rate:g} per $100 of wages)": gross / 100 * wc_rate,
        "NY unemployment insurance (4.1% of the first $13,000 each)": workers * min(gross_each, 13000) * 0.041,
        "Federal unemployment (0.6% of the first $7,000 each)": workers * min(gross_each, 7000) * 0.006,
        "Disability / paid family leave (business policy)": dbl_pfl if workers else 0,
        "Payroll service": (49 * 12 + 6 * workers * 12) if service and workers else 0,
    }
    total = sum(items.values())
    hours_all = hours * workers
    return {"items": {k: round(v) for k, v in items.items()}, "extra_total": round(total), "wages": round(gross),
            "per_hour": round(total / hours_all, 2) if hours_all else 0,
            "total_with_wages": round(gross + total)}
