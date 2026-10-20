"""Website form emails and job applications.

A contact form on the website sends Nick an email like "Name: Jane Smith / Email: jane@x.com / Message: ...". Form services
lay it out differently (the label alone on one line and the value under it, or both in a table row); all three are read
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
    "address": {"address", "street address", "project address", "property address", "location", "city", "town"},
    "contact": {"contact", "phone or email", "reply to", "best way to reach you"},
    "source": {"source", "heard from", "found us", "found us through", "how did you hear about us", "how did you find us",
               "referred by", "referral"},
    "message": {"message", "comments", "comment", "details", "project", "project details", "tell us about your project",
                "how can we help", "how can we help you", "your message", "description", "project description", "notes",
                "concern", "experience"},
}
APPLY_WORDS = re.compile(r"\b(resume|résumé|apply(?:ing)?|application|job opening|hiring|looking for (?:work|a job|employment)|"
                         r"open positions?|employment|seeking (?:work|employment|a position)|years of experience|"
                         r"join your (?:team|crew)|work for you)\b", re.I)
AUTOMATED = re.compile(r"no-?reply|formspree|forms?@|mailer|notifications?@|wix|squarespace|bounce", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?1?[\s.(-]*\d{3}[\s.)-]*\d{3}[\s.-]*\d{4}\b")
CELLS = re.compile(r"^\s*([A-Za-z][A-Za-z /_-]{1,30}?)\s{2,}(\S.*?)\s*$")


def _label(text: str) -> str | None:
    text = text.strip().strip("*").strip().rstrip(":").strip().lower().replace("_", " ")
    return next((k for k, names in LABELS.items() if text in names), None)


def _starts_field(line: str) -> bool:
    m = FIELD.match(line) or CELLS.match(line)
    return bool(_label(line) or (m and _label(m.group(1))))


def _one_line_fields(body: str) -> list[str]:
    """Lines as "Label: value", also when a form service puts the value under its label or beside it in a table."""
    lines, out, i = (body or "").splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not FIELD.match(line) and _label(line):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not _starts_field(lines[j]):
                out.append(f"{line.strip().strip('*').rstrip(':').strip()}: {lines[j].strip()}")
                i = j + 1
                continue
        cells = CELLS.match(line)
        if cells and not FIELD.match(line) and _label(cells.group(1)):
            line = f"{cells.group(1)}: {cells.group(2)}"
        out.append(line)
        i += 1
    return out


def parse_form(subject: str, body: str) -> dict | None:
    """Fields from a website-form notification, or None when the email isn't one."""
    found: dict[str, str] = {}
    last = None
    for line in _one_line_fields(body):
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
    # "Phone or email" in one box: sort it into the right field
    contact = found.pop("contact", "")
    if EMAIL.search(contact) and not found.get("email"):
        found["email"] = contact
    elif PHONE.search(contact) and not found.get("phone"):
        found["phone"] = contact
    mail = EMAIL.search(found.get("email", ""))
    phone = PHONE.search(found.get("phone", ""))
    if not (mail or phone) or not (found.get("name") or found.get("message")):
        return None
    if found.get("email") and not mail:
        return None
    found["email"] = mail.group(0) if mail else ""
    found["phone"] = phone.group(0).strip() if phone else ""
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
    if not f["email"] and EMAIL.fullmatch(mail.sender or "") and not AUTOMATED.search(mail.sender):
        f["email"] = mail.sender    # sent from the person's own mail app (the website's email fallback)
    if looks_like_application(mail.subject, f"{msg}\n{mail.body}"):
        data = {"applicant": True, "name": f.get("name", ""), "email": f["email"], "phone": f.get("phone", ""), "address": "",
                "project": msg[:400] or mail.subject, "reply": applicant_reply(f.get("name", ""), owner, phone)}
        note = "job application sent through the website form"
    else:
        source = f.get("source", "").strip().rstrip(".")
        project = (msg[:400] or mail.subject) + (f" (Found us: {source[:60]}.)" if source else "")
        data = {"name": f.get("name", ""), "email": f["email"], "phone": f.get("phone", ""), "address": f.get("address", ""),
                "project": project}
        note = "website contact form" + (f", came from {source[:60]}" if source else "")
    return Suggestion("lead", data, note, 0.9)
