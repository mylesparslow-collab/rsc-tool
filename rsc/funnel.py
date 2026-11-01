"""Leads: a grade for every new lead and whether the crew is booked, so the best jobs get the fastest reply.

Plain code decides everything here (principle 2): the grade comes from words and numbers in the lead, never from the model.
Nothing is sent: the page only orders the leads and says what to do next.
"""
import re
import sqlite3
from datetime import date, timedelta

from . import prefs

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


# ---- the leads list ----

NEXT = {"A": "Call today: this is the kind of job you want most.",
        "B": "Reply within a day.",
        "C": "Reply when you can; ask a couple of questions before a visit.",
        "Pass": "Not a fit for the crew: send a polite no, or point them to someone you know."}


def route(sc: dict, cap: dict) -> dict:
    """What to do with a lead next: {'why'}; A and B leads get a start date when the crew is booked."""
    why = NEXT[sc["grade"]]
    if cap["booked"] and sc["grade"] in ("A", "B"):
        why += " The crew is booked, so offer a start date when a job finishes."
    return {"why": why}


def leads(conn: sqlite3.Connection, days: int = 120) -> list[dict]:
    """Open leads (jobs still at Estimate with no estimate sent), best grade first, newest first within a grade."""
    cap = capacity(conn)
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute("SELECT * FROM jobs WHERE status = 'Estimate' AND estimate_sent IS NULL AND created_at >= ? "
                        "ORDER BY created_at DESC, number DESC", (since,)).fetchall()
    out = []
    for r in rows:
        job = dict(r)
        job["job_id"] = f"{job['number']}-{job['code']}"
        sc = score(job)
        job.update(score=sc, route=route(sc, cap))
        out.append(job)
    order = {g: i for i, g in enumerate(GRADES)}
    return sorted(out, key=lambda j: order[j["score"]["grade"]])


def summary(conn: sqlite3.Connection) -> dict:
    """Counts for the top of the page (and later the weekly report): leads by grade and the crew's capacity."""
    ls = leads(conn)
    return {"by_grade": {g: sum(1 for j in ls if j["score"]["grade"] == g) for g in GRADES}, "capacity": capacity(conn)}
