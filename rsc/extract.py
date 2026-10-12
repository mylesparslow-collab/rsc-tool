"""Turn one email into at most one suggestion (expense, client payment, or new lead).

The model only reads and fills in fields. Which job something belongs to is
decided here, by rules, against Nick's real job list, and every suggestion
waits for his approval.
"""
import re
import sqlite3
from dataclasses import dataclass

from . import brand, books, ids, intake
from .mail import Mail

KINDS = ["expense_receipt", "client_payment", "new_lead", "other"]

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "confidence": {"type": "number"},
        "vendor": {"type": "string"},
        "date": {"type": "string"},
        "total": {"type": "number"},
        "description": {"type": "string"},
        "category": {"type": "string", "enum": books.EXPENSE_CATEGORIES + [""]},
        "rsc_code": {"type": "string"},
        "job_clue": {"type": "string"},
        "payer_name": {"type": "string"},
        "amount_received": {"type": "number"},
        "reference": {"type": "string"},
        "lead_name": {"type": "string"},
        "lead_email": {"type": "string"},
        "lead_phone": {"type": "string"},
        "lead_address": {"type": "string"},
        "lead_project": {"type": "string"},
    },
    "required": ["kind", "confidence", "vendor", "date", "total", "description", "category", "rsc_code",
                 "job_clue", "payer_name", "amount_received", "reference", "lead_name", "lead_email",
                 "lead_phone", "lead_address", "lead_project"],
}

SYSTEM_PROMPT = """You read emails for Reclaimed Space Crafters (RSC), a small remodeling contractor
in Saratoga Springs, NY owned by Nick Parslow. Classify the email and pull out facts. Never guess:
use "" for unknown text and 0 for unknown numbers.

kind:
- expense_receipt: a receipt, order confirmation or bill for something RSC bought or owes
  (lumber, hardware, tools, fuel, subcontractor bill, insurance, software, dump fees...).
- client_payment: a client paid RSC (QuickBooks payment received, Zelle, Venmo, check deposit notice).
- new_lead: a person asking RSC for an estimate, quote, site visit or help with a project.
- other: everything else (newsletters, marketing, shipping updates with no price, personal mail).

For expense_receipt: vendor, date (YYYY-MM-DD), total (the final amount charged, including tax),
description (a few words: what was bought), category. If it's a business cost not tied to one job,
set rsc_code from this list, else "":
{rsc_codes}
job_clue: copy any job name, job number, PO number, client name or job address written on the receipt.

For client_payment: payer_name, amount_received, date, reference (invoice number or memo, copied exactly).
For new_lead: lead_name, lead_email, lead_phone, lead_address, lead_project (one sentence).
confidence: 0 to 1, how sure you are about kind and amounts."""


@dataclass
class Suggestion:
    kind: str           # expense | payment | lead
    data: dict
    match_note: str
    confidence: float


def wants_model(mail: Mail, keywords: list[str], ignore_senders: list[str], own_address: str) -> str | None:
    """Return a reason to skip the email, or None if the model should read it."""
    if mail.attachment_images and not any(x and x.lower() in mail.sender for x in ignore_senders):
        return None  # a photo (even one Nick emails himself) might be a receipt, whatever the subject says
    if own_address and mail.sender == own_address.lower():
        return "sent by RSC"
    if any(s and s.lower() in mail.sender for s in ignore_senders):
        return "ignored sender"
    haystack = f"{mail.subject}\n{mail.body[:3000]}\n{' '.join(mail.attachment_names)}".lower()
    if ids.find_payment_ids(f"{mail.subject}\n{mail.body}") or ids.find_job_numbers(haystack):
        return None
    if any(k.lower() in haystack for k in keywords):
        return None
    if intake.looks_like_application(mail.subject, mail.body):
        return None   # someone asking for work is worth a look even without the usual keywords
    return "no business keywords"


def system_prompt(conn: sqlite3.Connection) -> str:
    codes = "\n".join(f"  {c['code']}: {c['description']}" for c in books.list_rsc_codes(conn))
    return brand.localize(SYSTEM_PROMPT).replace("{rsc_codes}", codes)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def match_job(conn: sqlite3.Connection, text: str) -> tuple[int | None, str]:
    """Find the job an email is about, most reliable evidence first."""
    jobs = {j["number"]: j for j in books.list_jobs(conn)}
    for number in ids.find_job_numbers(text):
        if number in jobs:
            return number, f"job number {jobs[number]['job_id']} is written in the email"
    words = _words(text)
    active = [j for j in jobs.values() if j["status"] in books.ACTIVE]
    by_address = []
    for j in active:
        street = re.match(r"\s*(\d+\s+[A-Za-z]+)", j["address"] or "")
        if street and street.group(1).lower() in text.lower():
            by_address.append(j)
    if len(by_address) == 1:
        return by_address[0]["number"], f"job address ({by_address[0]['address']}) is in the email"
    by_name = [j for j in active if j["last_name"].lower() in words]
    if len(by_name) == 1:
        return by_name[0]["number"], f"client name {by_name[0]['last_name']} is in the email"
    if len(by_name) > 1:
        return None, "more than one open job matches the client name; pick one"
    return None, "no job found in the email; pick one"


def _money(value) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _date(value: str, fallback: str | None) -> str:
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or "") else (fallback or "")


def build_suggestion(conn: sqlite3.Connection, mail: Mail, fields: dict) -> Suggestion | None:
    kind = fields.get("kind")
    confidence = max(0.0, min(1.0, _money(fields.get("confidence"))))
    full_text = f"{mail.subject}\n{mail.body}\n{mail.attachment_text}\n{fields.get('job_clue', '')}"

    if kind == "expense_receipt":
        total = _money(fields.get("total"))
        if total <= 0:
            return None
        data = {
            "date": _date(fields.get("date", ""), mail.received_at),
            "vendor": (fields.get("vendor") or mail.sender_name or mail.sender)[:80],
            "description": (fields.get("description") or mail.subject)[:120],
            "category": fields.get("category") or "",
            "amount": total,
            "charge_to": "",
        }
        job_number, note = match_job(conn, full_text)
        code = (fields.get("rsc_code") or "").strip().upper()
        if job_number is not None:
            data["charge_to"] = str(job_number)
        elif ids.is_rsc_code(code) and conn.execute("SELECT 1 FROM rsc_codes WHERE code = ?", (code,)).fetchone():
            data["charge_to"] = code
            data["category"] = "Operations"
            note = "looks like a business cost, not a job"
        return Suggestion("expense", data, note, confidence)

    if kind == "client_payment":
        amount = _money(fields.get("amount_received"))
        if amount <= 0:
            return None
        data = {"date": _date(fields.get("date", ""), mail.received_at), "amount": amount,
                "payer": fields.get("payer_name", ""), "reference": fields.get("reference", ""),
                "payment_pk": None, "payment_id": ""}
        note = "no matching payment found; pick one"
        for number, code, seq in ids.find_payment_ids(f"{full_text}\n{data['reference']}"):
            p = books.find_payment(conn, number, seq)
            if p and p["payment_id"].split("-")[1] == code:
                data.update(payment_pk=p["id"], payment_id=p["payment_id"])
                note = f"payment ID {p['payment_id']} is written in the email"
                break
        else:
            job_number, _ = match_job(conn, f"{full_text}\n{data['payer']}")
            if job_number is not None:
                open_p = [p for p in books.list_payments(conn, job_number, open_only=True)
                          if abs(p["amount"] - amount) < 0.01]
                if open_p:
                    p = open_p[0]
                    data.update(payment_pk=p["id"], payment_id=p["payment_id"])
                    note = f"amount matches open payment {p['payment_id']} for this client"
        return Suggestion("payment", data, note, confidence)

    if kind == "new_lead":
        name = (fields.get("lead_name") or mail.sender_name or "").strip()
        data = {"name": name, "email": fields.get("lead_email") or mail.sender,
                "phone": fields.get("lead_phone", ""), "address": fields.get("lead_address", ""),
                "project": fields.get("lead_project", "") or mail.subject}
        return Suggestion("lead", data, "new person asking about work", confidence)

    return None
