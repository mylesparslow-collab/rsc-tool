"""The scorecard: is the business turning attention into paid jobs? One screen, read on Monday.

Everything comes from what the app already has, so nobody types anything new:

    lead         a job created in the app, plus a website or email lead still waiting under To Review
    source       read from the job notes ("Found us: nextdoor." from the website form, "?src=tiktok", "came from ...",
                 "referred by ..."); "Not recorded" when the notes don't say
    quote sent   the job's "Estimate sent" date
    job won      the job's "Contract signed" date
    win rate     of estimates sent in the last 90 days that have an answer, how many were signed
    revenue      payments received (date paid), and the contract value signed
    $/crew-hour  labor price / crew-hours, the same sum as the pricing check (rates.py). "Quoted" uses the
                 estimate's crew and days; "earned" uses hours actually logged on finished jobs

Numbers the app can't see (website visits, TikTok views, Google profile calls, ad spend) are listed as not connected
instead of guessed. Weeks start on Monday.
"""
import json
import re
import sqlite3
from datetime import date, timedelta

from . import books, crew, estimates, rates

WEEKS = 8
WINDOW_DAYS = 90
WON = ("Signed", "In Progress", "Complete")

# What a source word means. Checked in order; the first match names the source.
SOURCES = [
    ("TikTok", r"tik\s*tok"), ("Nextdoor", r"next\s*door"), ("Facebook", r"facebook|\bfb\b|\bmeta\b"),
    ("Instagram", r"instagram|\binsta\b|\big\b"), ("Google", r"google|\bgbp\b"), ("Bing", r"\bbing\b"),
    ("Apple Maps", r"\bapple\b"), ("Houzz", r"houzz"), ("Yelp", r"yelp"), ("Angi", r"\bangi\b|angie"),
    ("Thumbtack", r"thumbtack"), ("Flyer", r"flyer|mailer|postcard"), ("Yard sign", r"\bsign\b"),
    ("Truck", r"\btruck\b|\bvan\b"), ("Referral", r"referr|friend|neighbou?r|word of mouth|family|past client"),
    ("Website", r"website|\bsite\b|rscrafters|\bweb\b"),
]
# Phrases that say where a lead came from. Anything after them is the source.
SAID = [r"found us(?: on| through| via| at)?\s*:?\s*([^.)\n]+)", r"[?&]src=([\w-]+)", r"came from\s+([^.,)\n]+)",
        r"(?:lead )?source\s*:\s*([^.)\n]+)", r"heard (?:about us )?(?:from|on|through)\s+([^.,)\n]+)",
        r"saw (?:us|you|our ad|the ad)(?: on| at| in)\s+([^.,)\n]+)", r"(referred by [^.,)\n]+)"]
# Platforms named anywhere in the notes are clear enough to count even without one of those phrases.
PLAIN = ("TikTok", "Nextdoor", "Facebook", "Instagram", "Houzz", "Yelp", "Angi", "Thumbtack")
NOT_RECORDED = "Not recorded"

NOT_CONNECTED = [
    ("Website visits", "Cloudflare shows these for rscrafters.com; the app doesn't read them yet."),
    ("TikTok and social views", "Buffer has the post numbers; the app doesn't read them yet."),
    ("Google profile calls and views", "Google Business Profile isn't set up yet."),
    ("Ad spend", "No paid ads are tracked in the app yet."),
]


def _name(text: str) -> str | None:
    t = text.lower()
    for label, pattern in SOURCES:
        if re.search(pattern, t):
            return label
    return None


def lead_source(notes: str) -> str:
    """Where a lead came from, from the plain words in its notes."""
    notes = notes or ""
    for pattern in SAID:
        m = re.search(pattern, notes, re.I)
        if m and m.group(1).strip():
            said = m.group(1).strip().strip("'\"")
            return _name(said) or said[:30].strip().capitalize()
    low = notes.lower()
    for label, pattern in SOURCES:
        if label in PLAIN and re.search(pattern, low):
            return label
    return NOT_RECORDED


def _day(v) -> str | None:
    return (v or "")[:10] or None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _leads(conn: sqlite3.Connection, jobs: list[dict]) -> list[dict]:
    out = [{"day": _day(j["created_at"]), "source": lead_source(j["notes"]), "job": j} for j in jobs]
    for r in conn.execute("SELECT s.data, s.created_at FROM suggestions s WHERE s.kind = 'lead' AND s.status = 'pending'"):
        try:
            data = json.loads(r["data"])
        except (TypeError, ValueError):
            continue
        if data.get("applicant"):
            continue
        out.append({"day": _day(r["created_at"]), "source": lead_source(data.get("project", "")), "job": None})
    return out


def _won(j: dict) -> bool:
    return j["status"] in WON or (bool(j.get("contract_signed")) and j["status"] != "Lost")


def _quoted(conn: sqlite3.Connection, jobs: list[dict], settings: dict) -> list[dict]:
    """Labor and crew-hours of each estimate that was sent, as the pricing check works them out."""
    out = []
    for j in jobs:
        sent = _day(j.get("estimate_sent"))
        est = estimates.get(conn, j["number"]) if sent else None
        if not est:
            continue
        a = rates.analyze(est, settings)
        out.append({"day": sent, "job": j, "labor": est["labor"], "hours": a["crew_hours"], "rate": a["rate"]})
    return out


def _rate(rows: list[dict]) -> float | None:
    rows = [r for r in rows if r["rate"] is not None]
    hours = sum(r["hours"] for r in rows)
    return round(sum(r["labor"] for r in rows) / hours, 2) if hours else None


def _between(day: str | None, start: date, end: date) -> bool:
    return bool(day) and start.isoformat() <= day < end.isoformat()


def build(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    settings = rates.get_settings(conn)
    jobs = books.list_jobs(conn)
    leads = _leads(conn, jobs)
    quoted = _quoted(conn, jobs, settings)
    paid = [dict(r) for r in conn.execute("SELECT date_paid, amount_paid FROM payments WHERE date_paid IS NOT NULL AND amount_paid > 0")]

    weeks = []
    this_monday = _monday(today)
    for i in range(WEEKS):
        start = this_monday - timedelta(weeks=i)
        end = start + timedelta(weeks=1)
        won = [j for j in jobs if _between(_day(j.get("contract_signed")), start, end)]
        q = [r for r in quoted if _between(r["day"], start, end)]
        weeks.append({
            "start": start.isoformat(), "current": i == 0,
            "leads": sum(1 for l in leads if _between(l["day"], start, end)),
            "quotes": sum(1 for j in jobs if _between(_day(j.get("estimate_sent")), start, end)),
            "won": len(won), "sold": round(sum(j["contract_total"] or 0 for j in won), 2),
            "collected": round(sum(p["amount_paid"] for p in paid if _between(p["date_paid"][:10], start, end)), 2),
            "quoted_rate": _rate(q),
        })

    since = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    sent = [j for j in jobs if (_day(j.get("estimate_sent")) or _day(j.get("contract_signed")) or "") >= since]
    won = [j for j in sent if _won(j)]
    lost = [j for j in sent if j["status"] == "Lost"]
    decided = len(won) + len(lost)

    by_source: dict[str, dict] = {}
    for l in leads:
        if (l["day"] or "") < since:
            continue
        s = by_source.setdefault(l["source"], {"source": l["source"], "leads": 0, "quotes": 0, "won": 0, "sold": 0.0})
        s["leads"] += 1
        j = l["job"]
        if j and j.get("estimate_sent"):
            s["quotes"] += 1
        if j and _won(j):
            s["won"] += 1
            s["sold"] = round(s["sold"] + (j["contract_total"] or 0), 2)
    sources = sorted(by_source.values(), key=lambda s: (s["source"] == NOT_RECORDED, -s["won"], -s["leads"], s["source"]))

    q90 = [r for r in quoted if r["day"] >= since]
    earned = []
    for j in jobs:
        if j["status"] != "Complete":
            continue
        est = estimates.get(conn, j["number"])
        hours = crew.hours_for_job(conn, j["number"])
        if est and est["labor"] > 0 and hours > 0:
            earned.append({"job": j, "labor": est["labor"], "hours": hours, "rate": round(est["labor"] / hours, 2)})

    return {
        "date": today.isoformat(), "weeks": weeks, "this_week": weeks[0], "last_week": weeks[1],
        "window_days": WINDOW_DAYS, "sources": sources,
        "unrecorded": by_source.get(NOT_RECORDED, {}).get("leads", 0),
        "win": {"sent": len(sent), "won": len(won), "lost": len(lost), "waiting": len(sent) - decided,
                "rate": len(won) / decided if decided else None,
                "sold": round(sum(j["contract_total"] or 0 for j in won), 2)},
        "quoted": {"rate": _rate(q90), "count": sum(1 for r in q90 if r["rate"] is not None),
                   "unknown": sum(1 for r in q90 if r["rate"] is None and r["labor"] > 0),
                   "below": [r for r in q90 if r["rate"] is not None and r["rate"] < settings["floor_rate"]]},
        "earned": {"rate": _rate(earned), "jobs": earned},
        "floor": settings["floor_rate"], "target": settings["target_rate"],
        "pending_leads": sum(1 for l in leads if l["job"] is None),
        "not_connected": NOT_CONNECTED,
    }


def level(rate: float | None, card: dict) -> str:
    """CSS class: ok at or above the target, rate-warn between the floor and the target, bad under the floor."""
    if rate is None:
        return ""
    return "ok" if rate >= card["target"] else "rate-warn" if rate >= card["floor"] else "bad"


def summary_lines(card: dict) -> list[str]:
    """A few plain lines for the Monday email."""
    w, last = card["this_week"], card["last_week"]
    win = card["win"]
    L = [f"  Last week: {last['leads']} new leads, {last['quotes']} estimates sent, {last['won']} signed",
         "  Win rate, last 90 days: " + (f"{win['rate']:.0%} ({win['won']} of {win['won'] + win['lost']} answered)"
                                         if win["rate"] is not None else "no answers yet")]
    q = card["quoted"]["rate"]
    if q is not None:
        L.append(f"  Quoted labor, last 90 days: ${q:.0f} per crew-hour (target ${card['target']:.0f}, floor ${card['floor']:.0f})")
    top = [s for s in card["sources"] if s["source"] != NOT_RECORDED][:3]
    if top:
        L.append("  Where leads came from: " + ", ".join(f"{s['source']} {s['leads']}" for s in top))
    if w["leads"] or w["quotes"] or w["won"]:
        L.append(f"  So far this week: {w['leads']} leads, {w['quotes']} sent, {w['won']} signed")
    return L
