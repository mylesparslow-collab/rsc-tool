"""Receipts that arrive as photos (snapped, texted, or attached to an email), read by a local vision model.

The model only reads the receipt. Which job it belongs to is decided by the same rules as for emailed receipts,
from what Nick typed or what is printed on the receipt, and nothing is added until he checks it. The photo is
kept with the expense, which is the paper trail an accountant wants.
"""
import sqlite3
import uuid

from . import books, extract
from .mail import Mail
from .modeler import sniff

MAX_PHOTO_BYTES = 8 * 1024 * 1024

SCHEMA = {
    "type": "object",
    "properties": {
        "is_receipt": {"type": "boolean"},
        "vendor": {"type": "string"},
        "date": {"type": "string"},
        "total": {"type": "number"},
        "description": {"type": "string"},
        "category": {"type": "string", "enum": books.EXPENSE_CATEGORIES + [""]},
        "job_clue": {"type": "string"},
    },
    "required": ["is_receipt", "vendor", "date", "total", "description", "category", "job_clue"],
}

PROMPT = """This is a photo of a receipt or invoice for a small remodeling contractor. Read it and fill in:
vendor (the store or company name at the top), date (YYYY-MM-DD), total (the final amount paid, including tax; the
number next to TOTAL or AMOUNT DUE, not a subtotal), description (a few words on what was bought, such as
"lumber and screws"), category (Materials for lumber, hardware and building supplies; Hired Labor only for paying people), and job_clue (any job name, PO number, address or customer name printed on it).
Use "" for text you cannot read and 0 for a total you cannot read. Never guess a number. If the photo is not a
receipt, set is_receipt to false."""


class NotAPhoto(ValueError):
    pass


def check_photo(data: bytes) -> str:
    """The image type, or raise. The browser's claim about the file is not trusted."""
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise NotAPhoto("That photo is empty or too large (the limit is 8 MB).")
    mime = sniff(data)
    if not mime:
        raise NotAPhoto("That doesn't look like a photo (JPEG, PNG or WebP). Photos from an iPhone work.")
    return mime


def read_photo(model, conn: sqlite3.Connection, image: bytes, hint: str = "") -> dict:
    """Expense form fields from a receipt photo, or {} when it isn't a readable receipt."""
    user = "Read this receipt." + (f" Nick says it is for: {hint.strip()}" if hint.strip() else "")
    raw = model.extract(PROMPT, user, SCHEMA, images=[image])
    if raw.get("is_receipt") is False:
        return {}
    fields = {k: "" for k in extract.SCHEMA["properties"]}
    fields.update({"kind": "expense_receipt", "confidence": 0.7, "total": raw.get("total") or 0, "vendor": raw.get("vendor", ""),
                   "date": raw.get("date", ""), "description": raw.get("description", ""),
                   "category": raw.get("category", ""), "job_clue": raw.get("job_clue", "")})
    for k in ("amount_received",):
        fields[k] = 0
    mail = Mail(message_id="photo", mailbox="", sender="", sender_name="", subject="", received_at=None,
                body=hint.strip())
    suggestion = extract.build_suggestion(conn, mail, fields)
    if not suggestion or suggestion.kind != "expense":
        return {}
    d = dict(suggestion.data)
    d["note"] = suggestion.match_note
    return d


# ---------------------------------------------------------------- keeping the photo with the expense
def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS receipt_photos (
        token      TEXT PRIMARY KEY,
        expense_id INTEGER REFERENCES expenses(id),
        mime       TEXT NOT NULL,
        data       BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""")


def save_photo(conn: sqlite3.Connection, data: bytes, mime: str) -> str:
    ensure_table(conn)
    conn.execute("DELETE FROM receipt_photos WHERE expense_id IS NULL AND created_at < datetime('now', '-2 days') "
                 "AND token NOT IN (SELECT json_extract(data, '$.photo_token') FROM suggestions "
                 "WHERE status = 'pending' AND json_extract(data, '$.photo_token') IS NOT NULL)")
    token = uuid.uuid4().hex
    conn.execute("INSERT INTO receipt_photos (token, mime, data) VALUES (?, ?, ?)", (token, mime, data))
    conn.commit()
    return token


def attach(conn: sqlite3.Connection, token: str, expense_id: int) -> None:
    ensure_table(conn)
    conn.execute("UPDATE receipt_photos SET expense_id = ? WHERE token = ? AND expense_id IS NULL", (expense_id, token))
    conn.commit()


def photo_for(conn: sqlite3.Connection, expense_id: int):
    ensure_table(conn)
    row = conn.execute("SELECT mime, data FROM receipt_photos WHERE expense_id = ?", (expense_id,)).fetchone()
    return (row[0], bytes(row[1])) if row else None


def expenses_with_photos(conn: sqlite3.Connection) -> set[int]:
    ensure_table(conn)
    return {r[0] for r in conn.execute("SELECT expense_id FROM receipt_photos WHERE expense_id IS NOT NULL")}
