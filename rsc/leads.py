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


TOPICS = [("bath", "bathroom"), ("shower", "bathroom"), ("kitchen", "kitchen"), ("deck", "deck"), ("porch", "porch"),
          ("basement", "basement"), ("addition", "addition"), ("sunroom", "sunroom"), ("ramp", "ramp"), ("grab bar", "safety"),
          ("roof", "roof"), ("siding", "siding"), ("window", "window"), ("floor", "flooring"), ("stair", "stairs")]


def topic(project: str) -> str:
    """'Looking for a quote on a new back deck' -> 'your deck project'. Their own words are often a whole sentence, which
    reads badly pasted into ours, so the template names the kind of work instead."""
    low = (project or "").lower()
    kind = next((word for key, word in TOPICS if key in low), "")
    return f"your {kind} project" if kind else "your project"


def fallback_reply(name: str, project: str, slots: list[str], owner: str, phone: str) -> str:
    first = (name or "").split()[0] if name else "there"
    what = f" about {topic(project)}" if project.strip() else ""
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


# ------------------------------------------------- the instant thank-you (off unless switched on in Setup)

ACK_MAX_AGE_DAYS = 1  # a first email check reaches back weeks; only today's and yesterday's requests get a thank-you


def ack_on(conn: sqlite3.Connection) -> bool:
    return prefs.get(conn, "lead_ack") == "on"


def ack_subject() -> str:
    return f"We got your request ({brand.current()['name']})"


def ack_text(name: str, project: str, owner: str, phone: str) -> str:
    """The short thank-you a website request gets within minutes. Plain template: no prices, no promised times."""
    first = (name or "").split()[0] if name and name.strip() else "there"
    what = topic(project) if (project or "").strip() else "your project"
    return (f"Hi {first},\n\nThanks for reaching out about {what}. Your request came through, and {owner} will get back to you "
            f"personally to set up a free visit. We come and look before we put a price on anything.\n\n"
            f"If it's easier, call or text {phone}.\n\n{brand.current()['name']}")


def ack_fresh(received_at: str | None, today: date | None = None) -> bool:
    try:
        return ((today or date.today()) - date.fromisoformat((received_at or "")[:10])).days <= ACK_MAX_AGE_DAYS
    except ValueError:
        return False


def send_ack(address: str, password: str, to: str, subject: str, body: str, host: str = "smtp.gmail.com") -> None:
    """Sent from Nick's Gmail, with a copy to him, only when the Setup switch is on."""
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Bcc"] = address, to, subject, address
    msg.set_content(body)
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(address, password)
        s.send_message(msg)


def lead_checkin(job: dict, days: int) -> str:
    """For a lead with no estimate yet, 7 and 21 days on: a polite nudge to book the visit. Never names a price."""
    b = brand.current()
    first = job.get("first_name") or job.get("last_name") or "there"
    what = (job.get("job_type") or "").lower() or topic(job.get("notes", "")).removeprefix("your ")
    if days < 21:
        body = (f"Following up on your request about your {what}. If you'd still like us to come take a look, "
                f"reply with a day and time that suits you and I'll fit it in. The visit is free.")
    else:
        body = (f"Checking in one last time about your {what}. If the timing isn't right or plans have changed, no problem "
                f"at all. If you'd still like a visit, just reply and we'll set one up.")
    return f"Hi {first},\n\n{body}\n\n{b['owner']}\n{b['name']}\n{b['phone']}"
