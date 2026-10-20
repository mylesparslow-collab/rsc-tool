"""Check email, ask the local model, and queue suggestions for Nick's review."""
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime


from . import ballpark, brand, books, crew, prefs, extract, intake, leads, receipts
from .config import Config
from .llm import Model
from .mail import Mail, lookback_start

log = logging.getLogger("rsc.pipeline")


@dataclass
class RunReport:
    seen: int = 0
    new: int = 0
    skipped: int = 0
    suggestions: int = 0
    errors: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        text = (f"Checked {self.new} new emails: {self.suggestions} to review, "
                f"{self.skipped} skipped as not business.")
        return text + (f" {len(self.errors)} could not be read." if self.errors else "") + (f" {self.note}" if self.note else "")


def _setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _record_email(conn: sqlite3.Connection, mail: Mail, skipped: str | None) -> int:
    cur = conn.execute("INSERT INTO emails (message_id, mailbox, received_at, sender, subject, skipped) "
                       "VALUES (?, ?, ?, ?, ?, ?)",
                       (mail.message_id, mail.mailbox, mail.received_at, mail.sender, mail.subject, skipped))
    return cur.lastrowid


def process(conn: sqlite3.Connection, cfg: Config, mails: list[Mail], model: Model, vision: Model | None = None) -> RunReport:
    report = RunReport(seen=len(mails))
    prompt = extract.system_prompt(conn)
    for mail in mails:
        if conn.execute("SELECT 1 FROM emails WHERE message_id = ?", (mail.message_id,)).fetchone():
            continue
        report.new += 1
        form = None
        if mail.sender != (cfg.mail.address or "").lower():
            try:
                form = intake.suggestion_from_form(conn, mail, cfg.business_phone)
            except Exception as exc:  # a strange email must not stop the run
                log.warning("Form parse failed on %r: %s", mail.subject, exc)
        if form:
            form.data.setdefault("reply", "")
            if not form.data["reply"]:
                form.data["reply"] = leads.draft_reply(model, conn, form.data, cfg.business_phone)
            form.data["reply_to"] = form.data["email"]
            form.data["reply_subject"] = "Re: " + mail.subject
            if not form.data.get("applicant"):
                _add_ballpark(conn, form.data, mail, model, vision)
            email_id = _record_email(conn, mail, None)
            conn.execute("INSERT INTO suggestions (email_id, kind, data, match_note, confidence) VALUES (?, ?, ?, ?, ?)",
                         (email_id, form.kind, json.dumps(form.data), form.match_note, form.confidence))
            report.suggestions += 1
            conn.commit()
            continue
        reason = extract.wants_model(mail, cfg.mail.keywords, cfg.mail.ignore_senders, cfg.mail.address)
        if reason:
            _record_email(conn, mail, reason)
            report.skipped += 1
            conn.commit()
            continue
        try:
            suggestions = _read_mail(conn, mail, model, vision, prompt)
        except Exception as exc:  # one bad email must not stop the run; it is retried next time
            log.warning("Could not read %r: %s", mail.subject, exc)
            report.errors.append(f"{mail.subject}: {exc}")
            continue
        for suggestion in suggestions:
            if suggestion.kind == "lead" and intake.looks_like_application(mail.subject, mail.body):
                suggestion.data.update(applicant=True, reply=intake.applicant_reply(
                    suggestion.data.get("name", ""), prefs.get(conn, "owner_name") or brand.current()["owner"], cfg.business_phone))
                suggestion.match_note = "someone asking about a job with you"
            if suggestion.kind == "lead" and not suggestion.data.get("applicant"):  # a reply is ready for Nick to read before the lead goes cold
                suggestion.data["reply"] = leads.draft_reply(model, conn, suggestion.data, cfg.business_phone)
            if suggestion.kind == "lead":
                suggestion.data["reply_to"] = suggestion.data.get("email") or mail.sender
                suggestion.data["reply_subject"] = "Re: " + mail.subject
            if suggestion.kind == "lead" and not suggestion.data.get("applicant"):
                _add_ballpark(conn, suggestion.data, mail, model, vision)
        email_id = _record_email(conn, mail, None if suggestions else "model: not business")
        for suggestion in suggestions:
            conn.execute("INSERT INTO suggestions (email_id, kind, data, match_note, confidence) "
                         "VALUES (?, ?, ?, ?, ?)",
                         (email_id, suggestion.kind, json.dumps(suggestion.data), suggestion.match_note,
                          suggestion.confidence))
            report.suggestions += 1
        if not suggestions:
            report.skipped += 1
        conn.commit()
    return report


def _add_ballpark(conn: sqlite3.Connection, data: dict, mail: Mail, model: Model, vision: Model | None) -> None:
    """A rough range and site-visit questions, for Nick only (never in the reply). A failure here never loses the lead."""
    try:
        data["ballpark"] = ballpark.draft(model, conn, data, mail.attachment_images, vision)
    except Exception as exc:
        log.warning("No rough range for %r: %s", mail.subject, exc)


def _read_mail(conn: sqlite3.Connection, mail: Mail, model: Model, vision: Model | None, prompt: str) -> list:
    """Every separate thing in one email becomes its own suggestion: each PDF when there are several, each receipt photo."""
    found = []
    for view in mail.split_documents():  # a lone PDF stays with its email; two or more are read one at a time
        fields = model.extract(prompt, view.text_for_model(), extract.SCHEMA)
        suggestion = extract.build_suggestion(conn, view, fields)
        if suggestion and view is not mail:
            suggestion.match_note += f" (from {view.documents[0][0]})"
        if suggestion:
            found.append(suggestion)
    if vision and mail.attachment_images and not any(s.kind == "expense" and s.data["amount"] for s in found):
        found += _photo_suggestions(conn, mail, vision)
    return found


def _photo_suggestions(conn: sqlite3.Connection, mail: Mail, vision: Model) -> list:
    """Each emailed photo that is a receipt becomes an expense suggestion, with the photo kept for the paper trail."""
    out = []
    for image in mail.attachment_images:
        try:
            mime = receipts.check_photo(image)
            found = receipts.read_photo(vision, conn, image, hint=f"{mail.subject} {mail.body[:200]}")
        except receipts.NotAPhoto:
            continue
        if found:
            note = found.pop("note", "")
            found["photo_token"] = receipts.save_photo(conn, image, mime)
            out.append(extract.Suggestion("expense", found, f"read from a photo; {note}", 0.6))
    return out


def check_mail(conn: sqlite3.Connection, cfg: Config, reader, model: Model, vision: Model | None = None) -> RunReport:
    since = lookback_start(_setting(conn, "last_mail_check"), cfg.mail.first_run_days)
    started = datetime.now().isoformat(timespec="seconds")
    mails: list[Mail] = []
    for mailbox in cfg.mail.mailboxes:
        mails += reader.fetch_since(mailbox, since, cfg.mail.max_per_run)
    report = process(conn, cfg, mails, model, vision)
    if not report.errors:
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('last_mail_check', ?)", (started,))
    conn.execute("INSERT OR REPLACE INTO settings VALUES ('last_mail_report', ?)", (report.summary(),))
    conn.commit()
    return report


# ----------------------------------------------------------------- review queue

def pending(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT s.*, e.sender, e.subject, e.received_at FROM suggestions s JOIN emails e ON e.id = s.email_id "
        "WHERE s.status = 'pending' ORDER BY s.kind, e.received_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"])
        out.append(d)
    return out


def _get(conn: sqlite3.Connection, suggestion_id: int) -> dict:
    row = conn.execute("SELECT * FROM suggestions WHERE id = ? AND status = 'pending'", (suggestion_id,)).fetchone()
    if not row:
        raise books.BooksError("That item was already handled")
    d = dict(row)
    d["data"] = json.loads(d["data"])
    return d


def _close(conn: sqlite3.Connection, suggestion_id: int, status: str, data: dict | None = None) -> None:
    sql = "UPDATE suggestions SET status = ?, decided_at = datetime('now')"
    params: list = [status]
    if data is not None:
        sql += ", data = ?"
        params.append(json.dumps(data))
    conn.execute(sql + " WHERE id = ?", [*params, suggestion_id])
    conn.commit()


def approve(conn: sqlite3.Connection, suggestion_id: int, edits: dict) -> str:
    """Apply a suggestion with Nick's edits. Returns a one-line confirmation."""
    s = _get(conn, suggestion_id)
    data = {**s["data"], **{k: v for k, v in edits.items() if v is not None}}

    if s["kind"] == "expense":
        if not str(data.get("charge_to", "")).strip():
            raise books.BooksError("Pick a job number or RSC code first")
        expense_id = books.add_expense(conn, date=data["date"], charge_to=data["charge_to"], amount=float(data["amount"]),
                                       vendor=data["vendor"], description=data["description"],
                                       category=data.get("category", ""), paid_with=data.get("paid_with", ""),
                                       source="email", email_id=s["email_id"])
        if data.get("photo_token"):
            receipts.attach(conn, data["photo_token"], expense_id)
        msg = f"Added ${float(data['amount']):,.2f} from {data['vendor']} to {str(data['charge_to']).upper()}"

    elif s["kind"] == "payment":
        if not data.get("payment_pk"):
            raise books.BooksError("Pick which payment this is")
        pk = int(data["payment_pk"])
        row = conn.execute("SELECT amount_paid FROM payments WHERE id = ?", (pk,)).fetchone()
        if not row:
            raise books.BooksError("That payment no longer exists")
        books.update_payment(conn, pk, date_paid=data["date"],
                             amount_paid=round((row["amount_paid"] or 0) + float(data["amount"]), 2))
        pid = conn.execute("SELECT j.number || '-' || j.code || '-' || p.seq FROM payments p "
                           "JOIN jobs j ON j.number = p.job_number WHERE p.id = ?", (pk,)).fetchone()[0]
        data["payment_id"] = pid
        msg = f"Marked ${float(data['amount']):,.2f} paid on {pid}"

    elif data.get("applicant"):
        name = (data.get("name") or "").strip()
        if not name:
            raise books.BooksError("The applicant needs a name")
        pid = crew.add_person(conn, name, "helper", email=data.get("email", ""))
        conn.execute("UPDATE crew SET active = 0, note = ? WHERE id = ?",
                     (("Applicant. " + (data.get("phone", "") + " " + data.get("project", "")).strip())[:300], pid))
        conn.commit()
        msg = f"Saved {name} as an applicant on the Crew page (not on the schedule until you make them active)"

    else:  # lead
        name = (data.get("name") or "").strip()
        last_name = name.split()[-1] if name else ""
        if not last_name:
            raise books.BooksError("The lead needs a last name")
        first_name = " ".join(name.split()[:-1])
        number = books.create_job(conn, last_name, first_name=first_name, email=data.get("email", ""),
                                  phone=data.get("phone", ""), address=data.get("address", ""),
                                  status="Estimate", notes=data.get("project", ""),
                                  job_type=(data.get("ballpark") or {}).get("job_type", ""))
        data["job_number"] = number
        msg = f"Started job {number}-{books.get_job(conn, number)['code']} for {name}"

    _close(conn, suggestion_id, "approved", data)
    return msg


def dismiss(conn: sqlite3.Connection, suggestion_id: int) -> None:
    _get(conn, suggestion_id)
    _close(conn, suggestion_id, "dismissed")
