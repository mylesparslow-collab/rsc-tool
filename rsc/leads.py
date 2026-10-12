"""A new lead gets a reply drafted right away, with real visit times in it. Nothing is sent: Nick reads it, edits it, sends it."""
import re
import sqlite3
from datetime import date, timedelta

from . import brand, prefs

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ABBR = {d[:3]: i for i, d in enumerate(DAYS)}

REPLY_SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
REPLY_PROMPT = """You write a short, warm email reply for a small remodeling contractor, {owner}, to a new inquiry.
Rules: 4 to 6 sentences. Thank them by first name, mention in a few words what they asked about, offer exactly the
visit times given (do not invent others), and say the visit is free and takes about 30 minutes. Do not quote prices.
Sign it "{owner}, {biz}, {phone}". Plain text only, no subject line."""


def parse_availability(text: str) -> tuple[list[int], list[str]]:
    """'Tuesdays and Thursdays at 3:30pm or 5pm' -> ([1, 3], ['3:30 PM', '5:00 PM']). Blank means weekdays at 4 PM."""
    low = (text or "").lower()
    days = sorted({i for name, i in ABBR.items() if re.search(rf"\b{name}", low)})
    if "weekday" in low and not days:
        days = [0, 1, 2, 3, 4]
    if "weekend" in low:
        days = sorted(set(days) | {5, 6})
    times = []
    for h, m, ap in re.findall(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", low):
        h = int(h)
        if 1 <= h <= 12:
            times.append(f"{h}:{m or '00'} {ap[0].upper()}M")
    return days or [0, 1, 2, 3, 4], times or ["4:00 PM"]


def visit_slots(availability: str, today: date | None = None, n: int = 3) -> list[str]:
    """The next few visit times, starting no sooner than tomorrow, like 'Tuesday, October 13 at 4:00 PM'."""
    days, times = parse_availability(availability)
    d, out = (today or date.today()) + timedelta(days=1), []
    while len(out) < n and (d - (today or date.today())).days < 30:
        if d.weekday() in days:
            for t in times:
                out.append(f"{DAYS[d.weekday()].title()}, {d.strftime('%B')} {d.day} at {t}")
                if len(out) == n:
                    break
        d += timedelta(days=1)
    return out


def fallback_reply(name: str, project: str, slots: list[str], owner: str, phone: str) -> str:
    first = (name or "").split()[0] if name else "there"
    what = f" about {project.strip().rstrip('.')}" if project.strip() else ""
    times = "\n".join(f"  - {s}" for s in slots)
    return (f"Hi {first},\n\nThanks for reaching out{what}. I'd be glad to come take a look. The visit is free and takes about "
            f"30 minutes. Would one of these work?\n{times}\n\nIf not, tell me what suits you and I'll fit it in.\n\n"
            f"{owner}\n{brand.current()['name']}\n{phone}")


def draft_reply(model, conn: sqlite3.Connection, lead: dict, phone: str, today: date | None = None) -> str:
    """The reply text. If the model is unavailable or gives nothing usable, a plain template is used instead."""
    owner = prefs.get(conn, "owner_name") or "Nick"
    slots = visit_slots(prefs.get(conn, "visit_when"), today)
    try:
        user = (f"Inquiry from {lead.get('name', '')}: {lead.get('project', '')}\n\nVisit times to offer:\n" +
                "\n".join(f"- {s}" for s in slots))
        msg = (model.extract(REPLY_PROMPT.format(biz=brand.current()["name"], owner=owner, phone=phone), user, REPLY_SCHEMA).get("message") or "").strip()
        if len(msg) > 60 and all(s in msg for s in slots[:1]):
            return msg
    except Exception:
        pass
    return fallback_reply(lead.get("name", ""), lead.get("project", ""), slots, owner, phone)
