"""Website form emails and job applications.

A contact form on the website sends Nick an email like "Name: Jane Smith / Email: jane@x.com / Message: ...". Those are read
by plain code (no model needed, so it works even if Ollama is off) and land in To Review as a lead, or as an applicant when
the message is about working for him. Applications that arrive as ordinary emails are recognised the same way after the
model has read them. Nothing is added to the books until Nick approves it.
"""
import re

from . import brand, prefs

FIELD = re.compile(r"^\s*\**\s*([A-Za-z][A-Za-z /_-]{1,30}?)\s*\**\s*[:\-]\s*\**\s*(.+?)\s*$")
LABELS = {
    "name": {"name", "full name", "your name", "first name", "contact name"},
    "email": {"email", "e-mail", "email address", "your email", "e-mail address"},
    "phone": {"phone", "phone number", "telephone", "mobile", "cell", "your phone"},
    "address": {"address", "street address", "project address", "property address", "location", "city"},
    "message": {"message", "comments", "comment", "details", "project", "project details", "tell us about your project",
                "how can we help", "how can we help you", "your message", "description", "project description", "notes"},
}
APPLY_WORDS = re.compile(r"\b(resume|résumé|apply(?:ing)?|application|job opening|hiring|looking for (?:work|a job|employment)|"
                         r"open positions?|employment|seeking (?:work|employment|a position)|years of experience|"
                         r"join your (?:team|crew)|work for you)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def parse_form(subject: str, body: str) -> dict | None:
    """Fields from a website-form notification, or None when the email isn't one."""
    found: dict[str, str] = {}
    last = None
    for line in (body or "").splitlines():
        m = FIELD.match(line)
        if m:
            label = m.group(1).strip().lower().replace("_", " ")
            key = next((k for k, names in LABELS.items() if label in names), None)
            if key and key not in found:
                found[key] = m.group(2).strip()
                last = key
                continue
        # a message that runs onto following lines
        if last == "message" and line.strip() and not FIELD.match(line):
            found["message"] += " " + line.strip()
    mail = EMAIL.search(found.get("email", ""))
    if not mail or not (found.get("name") or found.get("message")):
        return None
    found["email"] = mail.group(0)
    if re.search(r"(?i)\bfirst name\b", body or "") and re.search(r"(?i)\blast name\b", body or ""):
        first = re.search(r"(?im)^\s*first name\s*:\s*(.+)$", body)
        last_n = re.search(r"(?im)^\s*last name\s*:\s*(.+)$", body)
        if first and last_n:
            found["name"] = f"{first.group(1).strip()} {last_n.group(1).strip()}"
    return found


def looks_like_application(subject: str, body: str) -> bool:
    return bool(APPLY_WORDS.search(f"{subject}\n{(body or '')[:2000]}"))


def applicant_reply(name: str, owner: str, phone: str) -> str:
    first = (name or "").split()[0] if name else "there"
    return (f"Hi {first},\n\nThanks for your interest in working with {brand.current()['name']}. I'd like to hear more about your "
            f"experience. Could you send a few lines on the kind of work you've done and when you're available? If it looks like a "
            f"fit, we can set up a time to talk.\n\n{owner}\n{brand.current()['name']}\n{phone}")


def suggestion_from_form(conn, mail, phone: str):
    """A Suggestion (lead or applicant) for a website form email, or None."""
    from .extract import Suggestion
    f = parse_form(mail.subject, mail.body)
    if not f:
        return None
    owner = prefs.get(conn, "owner_name") or brand.current()["owner"]
    msg = f.get("message", "")
    if looks_like_application(mail.subject, f"{msg}\n{mail.body}"):
        data = {"applicant": True, "name": f.get("name", ""), "email": f["email"], "phone": f.get("phone", ""), "address": "",
                "project": msg[:400] or mail.subject, "reply": applicant_reply(f.get("name", ""), owner, phone)}
        note = "job application sent through the website form"
    else:
        data = {"name": f.get("name", ""), "email": f["email"], "phone": f.get("phone", ""), "address": f.get("address", ""),
                "project": msg[:400] or mail.subject}
        note = "website contact form"
    return Suggestion("lead", data, note, 0.9)
