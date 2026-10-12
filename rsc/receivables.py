"""Who owes what, how long it's been, and a polite reminder to send.

An invoice is "waiting" from the day it was sent until the payment arrives. Reminders are drafted only for invoices that
have waited past the payment terms (14 days by default) and haven't been reminded in the last week. The model writes the
note; if it leaves out the invoice number or amount, a plain template is used. Nothing is sent by the app: it opens in Mail.
"""
import sqlite3
from datetime import date, timedelta

from . import books, brand, prefs

TERMS_DAYS = 14
REMIND_EVERY = 7
BUCKETS = [("Waiting (under 14 days)", 0, 13), ("14 to 29 days", 14, 29), ("30 to 59 days", 30, 59), ("60 days or more", 60, 10**6)]
SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
PROMPT = """Write a short, polite email from a remodeling contractor, {owner} of {biz}, reminding a client about an unpaid invoice.
3 to 5 sentences. Mention the invoice number and amount exactly as given, and when it was sent. Tone: {tone}. Offer to answer
any question, say how to pay (reply or call {phone}), and thank them. Never threaten or mention fees or lawyers. Plain text,
no subject line. Sign it "{owner}, {biz}"."""
TONES = {"friendly": "friendly and light, assume it slipped their mind",
         "firm": "polite but clear that the invoice is now past due and you'd like it settled this week",
         "urgent": "polite and direct: the invoice is well past due, ask them to call or reply today to arrange payment"}


def terms(conn: sqlite3.Connection) -> int:
    try:
        return max(1, int(prefs.get(conn, "payment_terms_days") or TERMS_DAYS))
    except ValueError:
        return TERMS_DAYS


def tone_for(days: int) -> str:
    return "friendly" if days < 30 else "firm" if days < 60 else "urgent"


def outstanding(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for p in books.list_payments(conn, open_only=True):
        if not p["invoice_sent"]:
            continue
        job = books.get_job(conn, p["job_number"])
        if not job or job["status"] in ("Lost",):
            continue
        try:
            days = (today - date.fromisoformat(p["invoice_sent"][:10])).days
        except ValueError:
            continue
        last = conn.execute("SELECT MAX(sent_on) FROM payment_reminders WHERE payment_id = ?", (p["id"],)).fetchone()[0]
        owed = round(p["amount"] - (p["amount_paid"] or 0), 2)
        out.append({**p, "days": days, "owed": owed, "job": job, "email": job.get("email") or "", "last_reminder": last,
                    "needs_reminder": days >= terms(conn) and (not last or (today - date.fromisoformat(last)).days >= REMIND_EVERY),
                    "tone": tone_for(days)})
    out.sort(key=lambda r: -r["days"])
    return out


def buckets(rows: list[dict]) -> list[dict]:
    return [{"label": label, "rows": [r for r in rows if lo <= r["days"] <= hi],
             "total": round(sum(r["owed"] for r in rows if lo <= r["days"] <= hi), 2)} for label, lo, hi in BUCKETS]


def fallback(r: dict, owner: str, phone: str) -> str:
    first = r["job"].get("first_name") or r["last_name"]
    biz = brand.current()["name"]
    sent = date.fromisoformat(r["invoice_sent"][:10]).strftime("%B %-d")
    base = f"Invoice {r['payment_id']} for ${r['owed']:,.2f}, which we sent on {sent}"
    if r["tone"] == "friendly":
        body = (f"I wanted to send a quick reminder: {base}, is still open. If it's already on its way, thank you, and please "
                f"ignore this note.")
    elif r["tone"] == "firm":
        body = (f"{base}, is now past due. I'd appreciate it if you could get it settled this week.")
    else:
        body = (f"{base}, is well past due. Could you reply or call me today so we can arrange payment?")
    return (f"Hi {first},\n\n{body} If you have any questions about it, reply here or call {phone}.\n\n"
            f"Thank you,\n{owner}\n{biz}")


def draft(model, conn: sqlite3.Connection, payment_pk: int, phone: str, today: date | None = None) -> dict | None:
    row = next((r for r in outstanding(conn, today) if r["id"] == payment_pk), None)
    if not row:
        return None
    owner = prefs.get(conn, "owner_name") or brand.current()["owner"]
    text = ""
    if model is not None:
        try:
            sent = date.fromisoformat(row["invoice_sent"][:10]).strftime("%B %-d")
            user = (f"Client: {row['job'].get('first_name') or row['last_name']}. Invoice {row['payment_id']}, ${row['owed']:,.2f}, "
                    f"sent {sent} ({row['days']} days ago). For: {row['description'][:100]}.")
            text = (model.extract(PROMPT.format(owner=owner, biz=brand.current()["name"], tone=TONES[row["tone"]], phone=phone),
                                  user, SCHEMA).get("message") or "").strip()
        except Exception:
            text = ""
    if len(text) < 60 or row["payment_id"] not in text or f"{row['owed']:,.2f}" not in text:
        text = fallback(row, owner, phone)
    return {"row": row, "text": text, "subject": f"Invoice {row['payment_id']}: a reminder"}


def mark_reminded(conn: sqlite3.Connection, payment_pk: int, draft_text: str = "", today: date | None = None) -> None:
    conn.execute("INSERT INTO payment_reminders (payment_id, sent_on, draft) VALUES (?, ?, ?)",
                 (payment_pk, (today or date.today()).isoformat(), draft_text[:2000]))
    conn.commit()
