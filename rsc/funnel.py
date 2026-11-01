"""Leads: a grade for every new lead, whether the crew is booked, and handing overflow to a partner Nick trusts.

Plain code decides everything here (principle 2): the grade comes from words and numbers in the lead, never from the model.
A lead goes to a partner only when the homeowner said yes to that (website box, or Nick recording what they told him),
the partner's insurance is on file and current, and the lead didn't come from Google Local Services (Google forbids
passing those on). The handoff emails open in Mail; nothing is sent for Nick (principle 4).
"""
import re
import sqlite3
from datetime import date, timedelta

from . import books, brand, prefs

# What Nick wants most (the target list: bathrooms, kitchens, porch enclosures, built-ins and restoration), then good work,
# then small jobs. Trades he doesn't do are a poor fit and the natural thing to pass on.
CORE = r"bath(room)?s?|shower|tub|vanit(y|ies)|kitchens?|cabinets?|countertops?|porch enclosure|enclos(e|ed|ing) (the |a |our )?porch|" \
       r"(three|four|3|4)[- ]season|sun ?room|built[- ]?ins?|bookcases?|bookshel(f|ves)|mudroom|restor(e|ation|ing)|remodel"
GOOD = r"decks?|stairs?|staircase|porch(es)?|additions?|basement|floor(s|ing)?|trim|wainscot|doorways?|ramps?|grab bars?|accessib"
SMALL = r"repairs?|fix|handyman|small job|faucet|caulk|paint(ing)?|gutters?|screen door|patch"
OTHER_TRADE = r"roof(ing)? replacement|new roof|re-?roof|hvac|furnace|air condition|electrical (only|panel)|septic|well pump|" \
              r"pav(e|ing)|driveway|asphalt|tree (removal|service)|pool|landscap|fence|siding only|windows only|chimney sweep"

# Towns Nick works in most, then the ones a little farther out. Anything else gets no points (not a minus: he may still go).
NEAR = ("saratoga springs", "saratoga", "wilton", "greenfield", "malta", "ballston spa", "milton", "gansevoort", "porter corners")
FAR = ("clifton park", "halfmoon", "stillwater", "schuylerville", "mechanicville", "round lake", "corinth", "queensbury",
       "glens falls", "south glens falls", "ballston lake", "burnt hills", "galway", "moreau", "victory", "northumberland")

SOON = r"as soon as possible|asap|right away|this (month|week|fall|winter|spring|summer)|next few months|soon|urgent|before (the )?(winter|holidays)"
LATER = r"just (starting to )?plan|someday|no rush|next year|a few years|thinking about|ideas?"

# The website quote form adds this sentence when the homeowner ticks the (optional, unticked) box. Keep it matching
# website/base/index.html.
WEBSITE_CONSENT = re.compile(r"OK to pass my request to one contractor you trust", re.I)
# Lead sources whose leads may never be passed on.
NO_RESALE = re.compile(r"local services|google guaranteed|google screened|\bLSA\b", re.I)

GRADES = ("A", "B", "C", "Pass")


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(rf"\b(?:{pattern})\b", text, re.I))


def amounts(text: str) -> list[float]:
    """Dollar figures a homeowner wrote: '$25k', '20,000', 'about 15-20k' -> [25000.0, 20000.0, 15000.0, 20000.0]."""
    out = []
    for m in re.finditer(r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|K|thousand)?(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(k|K|thousand))?", text):
        whole, k, hi, k2 = m.group(1), m.group(2), m.group(3), m.group(4)
        if not (k or "$" in m.group(0) or "," in whole):
            # '15-20k' marks the first number as thousands too
            if not k2:
                continue
            k = k2
        n = float(whole.replace(",", "")) * (1000 if k else 1)
        if n >= 300:
            out.append(n)
        if hi:
            out.append(float(hi) * (1000 if k2 else 1))
    return out


def town_of(text: str) -> str:
    low = (text or "").lower()
    for t in sorted(NEAR + FAR, key=len, reverse=True):
        if re.search(rf"\b{re.escape(t)}\b", low):
            return t.title()
    return ""


def score(job: dict) -> dict:
    """{'grade', 'points', 'reasons', 'kind', 'town', 'other_trade'} for one lead. Same input, same answer, every time."""
    text = " ".join(str(job.get(k) or "") for k in ("job_type", "notes", "address"))
    pts, why = 0, []
    other = _has(OTHER_TRADE, text)
    if _has(CORE, text):
        pts, kind = pts + 3, "core"
        why.append("the kind of job you want most (+3)")
    elif _has(GOOD, text):
        pts, kind = pts + 2, "good"
        why.append("good fit for the crew (+2)")
    elif _has(SMALL, text):
        kind = "small"
        why.append("small job or repair (+0)")
    else:
        kind = "unclear"
        why.append("job not clear yet (+0)")
    money = amounts(text)
    big = max(money) if money else 0
    if big >= 15000 or _has(r"full remodel|gut(ted)?|whole (house|kitchen|bathroom)|complete remodel", text):
        pts += 2
        why.append("sized like a $15K+ job (+2)")
    elif big >= 5000:
        pts += 1
        why.append("mid-sized budget mentioned (+1)")
    elif big and big < 3000:
        pts -= 1
        why.append("budget under $3,000 (-1)")
    if _has(SOON, text):
        pts += 1
        why.append("wants it soon (+1)")
    elif _has(LATER, text):
        why.append("just planning (+0)")
    town = town_of(text)
    if town.lower() in NEAR:
        pts += 2
        why.append(f"{town} is close by (+2)")
    elif town:
        pts += 1
        why.append(f"{town} is in the wider area (+1)")
    if job.get("phone") and job.get("email"):
        pts += 1
        why.append("left a phone and an email (+1)")
    if other and kind not in ("core", "good"):
        grade = "Pass"
        why.append("a trade the crew doesn't do")
    elif pts >= 7:
        grade = "A"
    elif pts >= 4:
        grade = "B"
    elif pts >= 1:
        grade = "C"
    else:
        grade = "Pass"
    return {"grade": grade, "points": pts, "reasons": why, "kind": kind, "town": town, "other_trade": other}


# ---- crew capacity ----

def crew_slots(conn: sqlite3.Connection) -> int:
    try:
        return max(1, int(prefs.get(conn, "crew_slots") or 2))
    except ValueError:
        return 2


def capacity(conn: sqlite3.Connection) -> dict:
    """How many jobs are running against how many the crew can run at once (Nick's number)."""
    running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('Signed', 'In Progress')").fetchone()[0]
    slots = crew_slots(conn)
    return {"running": running, "slots": slots, "booked": running >= slots, "open": max(0, slots - running)}


# ---- consent ----

def consent(conn: sqlite3.Connection, job: dict) -> dict | None:
    """The homeowner's yes to being passed on: {'how', 'said_on', 'note'}, or None."""
    row = conn.execute("SELECT how, said_on, note FROM lead_consent WHERE job_number = ? ORDER BY id DESC LIMIT 1",
                       (job["number"],)).fetchone()
    if row:
        return dict(row)
    if WEBSITE_CONSENT.search(job.get("notes") or ""):
        return {"how": "Ticked the box on the website form", "said_on": (job.get("created_at") or "")[:10], "note": ""}
    return None


def record_consent(conn: sqlite3.Connection, number: int, how: str, note: str = "", said_on: str = "") -> None:
    how = (how or "").strip()
    if not how:
        raise books.BooksError("Say how they said yes (on the phone, by email, in person).")
    conn.execute("INSERT INTO lead_consent (job_number, how, note, said_on) VALUES (?, ?, ?, ?)",
                 (number, how[:120], (note or "").strip()[:500], said_on or date.today().isoformat()))
    conn.commit()


def no_resale(job: dict) -> bool:
    return bool(NO_RESALE.search(job.get("notes") or ""))


# ---- partners ----

PARTNER_FIELDS = ("name", "company", "email", "phone", "trades", "towns", "license", "insurance_expires", "fee_pct", "notes")


def _date(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def partner_ready(p: dict, today: date | None = None) -> tuple[bool, str]:
    """(ready, why not). Ready = active, has an email, and insurance on file that hasn't expired."""
    today = today or date.today()
    if not p.get("active"):
        return False, "turned off"
    if not p.get("email"):
        return False, "no email address"
    exp = _date(p.get("insurance_expires", ""))
    if not exp:
        return False, "no insurance expiry date on file"
    if exp < today:
        return False, f"insurance expired {exp.isoformat()}"
    return True, ("insurance runs out " + exp.isoformat()) if exp - today <= timedelta(days=30) else ""


def list_partners(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM partners ORDER BY active DESC, name"):
        p = dict(r)
        p["ready"], p["why"] = partner_ready(p, today)
        out.append(p)
    return out


def save_partner(conn: sqlite3.Connection, data: dict, partner_id: int | None = None) -> int:
    vals = {k: (data.get(k) or "").strip() for k in PARTNER_FIELDS}
    if not vals["name"]:
        raise books.BooksError("A partner needs a name.")
    if vals["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", vals["email"]):
        raise books.BooksError("That email address doesn't look right.")
    if vals["insurance_expires"] and not _date(vals["insurance_expires"]):
        raise books.BooksError("Insurance expiry should be a date like 2027-03-31.")
    try:
        vals["fee_pct"] = round(float(vals["fee_pct"].rstrip("%") or 4), 2)
    except ValueError:
        raise books.BooksError("Referral fee should be a percent, like 4.")
    if not 0 <= vals["fee_pct"] <= 25:
        raise books.BooksError("Referral fee should be between 0 and 25 percent.")
    vals["active"] = 0 if data.get("active") == "0" else 1
    if partner_id:
        conn.execute(f"UPDATE partners SET {', '.join(f'{k} = ?' for k in vals)} WHERE id = ?", [*vals.values(), partner_id])
    else:
        cur = conn.execute(f"INSERT INTO partners ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", list(vals.values()))
        partner_id = cur.lastrowid
    conn.commit()
    return partner_id


def matches(partners: list[dict], job: dict, sc: dict) -> list[dict]:
    """Ready partners, best match first: one whose trades share a word with the lead, and who works in its town."""
    text = " ".join(str(job.get(k) or "") for k in ("job_type", "notes")).lower()
    words = set(re.findall(r"[a-z]{4,}", text))

    def fit(p):
        trades = set(re.findall(r"[a-z]{4,}", p["trades"].lower()))
        towns = p["towns"].lower()
        return (len(trades & words) > 0) * 2 + (bool(sc["town"]) and sc["town"].lower() in towns)

    ready = [p for p in partners if p["ready"]]
    return sorted(ready, key=lambda p: (-fit(p), p["name"]))


# ---- the leads list ----

def route(sc: dict, cap: dict, has_consent: bool, blocked: bool) -> dict:
    """What to do with a lead: {'action': 'keep' | 'pass' | 'ask' | 'decline', 'why'}."""
    if sc["grade"] == "A" and not cap["booked"]:
        return {"action": "keep", "why": "A lead and the crew has room."}
    if sc["grade"] == "A":
        return {"action": "keep", "why": "A lead: worth a waiting list even though the crew is booked."}
    if not cap["booked"] and sc["grade"] in ("B", "C") and not sc["other_trade"]:
        return {"action": "keep", "why": "The crew has room."}
    if blocked:
        return {"action": "decline", "why": "Came through Google Local Services, which doesn't allow passing leads on."}
    reason = "a trade the crew doesn't do" if sc["other_trade"] else ("the crew is booked" if cap["booked"] else "a poor fit")
    if has_consent:
        return {"action": "pass", "why": f"Pass to a partner: {reason}, and they said yes to that."}
    return {"action": "ask", "why": f"Worth passing on ({reason}). Ask them first if that's OK."}


def leads(conn: sqlite3.Connection, days: int = 120) -> list[dict]:
    """Open leads (jobs still at Estimate with no estimate sent), newest first, each with its grade and suggested route."""
    cap = capacity(conn)
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute("SELECT * FROM jobs WHERE status = 'Estimate' AND estimate_sent IS NULL AND created_at >= ? "
                        "ORDER BY created_at DESC, number DESC", (since,)).fetchall()
    out = []
    for r in rows:
        job = dict(r)
        job["job_id"] = f"{job['number']}-{job['code']}"
        sc = score(job)
        ok = consent(conn, job)
        blocked = no_resale(job)
        job.update(score=sc, consent=ok, blocked=blocked, route=route(sc, cap, bool(ok), blocked))
        out.append(job)
    order = {g: i for i, g in enumerate(GRADES)}
    return sorted(out, key=lambda j: order[j["score"]["grade"]])


# ---- handoffs and the fee ledger ----

def can_pass(conn: sqlite3.Connection, number: int, partner_id: int) -> tuple[dict, dict, dict]:
    """(job, partner, consent) when a handoff is allowed; raises BooksError with the plain reason when it isn't."""
    job = conn.execute("SELECT * FROM jobs WHERE number = ?", (number,)).fetchone()
    if not job:
        raise books.BooksError("No such job.")
    job = dict(job)
    if no_resale(job):
        raise books.BooksError("This lead came through Google Local Services. Google doesn't allow passing those on.")
    ok = consent(conn, job)
    if not ok:
        raise books.BooksError("They haven't said yes to being passed to another contractor yet. Ask first, then record it.")
    p = conn.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()
    if not p:
        raise books.BooksError("No such partner.")
    p = dict(p)
    ready, why = partner_ready(p)
    if not ready:
        raise books.BooksError(f"{p['name']} can't take leads right now: {why}.")
    return job, p, ok


def handoff_drafts(job: dict, partner: dict, owner: str) -> dict:
    """The two emails Nick sends himself: one introducing the partner to the homeowner, one giving the partner the lead.
    Only what the partner needs to call them: name, contact, town, the project in the homeowner's words."""
    b = brand.current()
    first = job.get("first_name") or "there"
    who = partner["name"] + (f" of {partner['company']}" if partner["company"] else "")
    project = re.sub(r"If you.{1,3}re booked, it.{1,3}s OK to pass my request to one contractor you trust\.?", "", job.get("notes") or "")
    project = re.sub(r"\s+", " ", project or job.get("job_type") or "your project").strip()[:600]
    client = (f"Hi {first},\n\nThank you again for thinking of us. We can't take your project on as soon as you'd like, so as you "
              f"said was OK, I've passed your request to {who}. They do good work and I trust them with a job like yours. "
              f"They should be in touch in the next few days"
              + (f" from {partner['phone']}" if partner["phone"] else "") + ".\n\n"
              f"If it's not a fit, no problem at all, and you're always welcome to call us again.\n\n{owner}\n{b['name']}\n{b['phone']}")
    to_partner = (f"Hi {partner['name'].split()[0]},\n\nHere's a lead I can't take on. The homeowner said it's OK to pass it to you.\n\n"
                  f"Name: {job.get('first_name', '')} {job['last_name']}\n"
                  + (f"Phone: {job['phone']}\n" if job.get("phone") else "")
                  + (f"Email: {job['email']}\n" if job.get("email") else "")
                  + (f"Address or town: {job['address']}\n" if job.get("address") else "")
                  + f"Project: {project}\n\nPlease reach out within two business days, and let me know if you take the job "
                  f"and the contract amount, so I can keep our referral arrangement straight ({partner['fee_pct']:g}% of the contract).\n\n"
                  f"Thanks,\n{owner}\n{b['name']}\n{b['phone']}")
    return {"client": {"to": job.get("email", ""), "subject": f"Your project: introducing {who}", "text": client},
            "partner": {"to": partner["email"], "subject": f"Referral from {b['name']}: {job.get('first_name', '')} {job['last_name']}",
                        "text": to_partner}}


def mark_passed(conn: sqlite3.Connection, number: int, partner_id: int) -> int:
    """Nick sent the emails: log the referral, note it on the job, and move the job to 'Passed on' so it stops nagging."""
    job, partner, ok = can_pass(conn, number, partner_id)
    cur = conn.execute("INSERT INTO partner_referrals (job_number, partner_id, consent, fee_pct) VALUES (?, ?, ?, ?)",
                       (number, partner_id, f"{ok['how']} ({ok['said_on']})", partner["fee_pct"]))
    note = f"Passed to {partner['name']} on {date.today().isoformat()} (partner referral)."
    books.update_job(conn, number, status="Passed on", notes=((job.get("notes") or "") + "\n" + note).strip())
    conn.commit()
    return cur.lastrowid


def referral_outcome(conn: sqlite3.Connection, referral_id: int, status: str, amount: str = "") -> None:
    """Won (with the contract amount, which sets the fee in code), Lost, or fee paid."""
    r = conn.execute("SELECT * FROM partner_referrals WHERE id = ?", (referral_id,)).fetchone()
    if not r:
        raise books.BooksError("No such referral.")
    if status == "Paid":
        if r["status"] != "Won":
            raise books.BooksError("Mark it won first.")
        conn.execute("UPDATE partner_referrals SET fee_paid_on = ? WHERE id = ?", (date.today().isoformat(), referral_id))
    elif status == "Won":
        try:
            total = round(float(re.sub(r"[$,\s]", "", amount or "")), 2)
        except ValueError:
            raise books.BooksError("Put in the partner's contract amount, like 24,500.")
        if total <= 0:
            raise books.BooksError("Put in the partner's contract amount, like 24,500.")
        conn.execute("UPDATE partner_referrals SET status = 'Won', contract_amount = ?, fee_due = ? WHERE id = ?",
                     (total, round(total * r["fee_pct"] / 100, 2), referral_id))
    elif status == "Lost":
        conn.execute("UPDATE partner_referrals SET status = 'Lost', contract_amount = NULL, fee_due = 0 WHERE id = ?", (referral_id,))
    else:
        raise books.BooksError("Unknown outcome.")
    conn.commit()


def ledger(conn: sqlite3.Connection) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT r.*, p.name AS partner, j.first_name, j.last_name, j.number || '-' || j.code AS job_id "
        "FROM partner_referrals r JOIN partners p ON p.id = r.partner_id JOIN jobs j ON j.number = r.job_number "
        "ORDER BY r.sent_on DESC, r.id DESC")]
    owed = round(sum(r["fee_due"] for r in rows if r["status"] == "Won" and not r["fee_paid_on"]), 2)
    paid = round(sum(r["fee_due"] for r in rows if r["fee_paid_on"]), 2)
    won = sum(1 for r in rows if r["status"] == "Won")
    return {"rows": rows, "owed": owed, "paid": paid, "sent": len(rows), "won": won}


def summary(conn: sqlite3.Connection) -> dict:
    """Counts for the top of the page (and later the weekly report): leads by grade, overflow, fees."""
    ls = leads(conn)
    by = {g: sum(1 for j in ls if j["score"]["grade"] == g) for g in GRADES}
    return {"by_grade": by, "to_pass": sum(1 for j in ls if j["route"]["action"] in ("pass", "ask")),
            "ledger": ledger(conn), "capacity": capacity(conn)}
