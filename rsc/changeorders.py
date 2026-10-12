"""Change orders: written up on the job, signed by the client on the screen, then the contract total and the
payment schedule are updated together.

A change order for $1,200 on job 1002-SMI becomes 1002-SMI-CO1, raises the contract total by $1,200 and adds
the next payment (1002-SMI-n) for $1,200. A credit is a negative amount and lowers the total.
"""
import base64
import binascii
import sqlite3

from . import books

MAX_SIGNATURE_BYTES = 300_000
PNG_PREFIX = "data:image/png;base64,"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def label(job: dict, seq: int) -> str:
    return f"{job['job_id']}-CO{seq}"


def _decorate(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    job = books.get_job(conn, d["job_number"])
    d["label"] = label(job, d["seq"])
    d["job"] = job
    return d


def create(conn: sqlite3.Connection, job_number: int, description: str, amount: float, days_added: int = 0) -> int:
    job = books.get_job(conn, job_number)
    if not job:
        raise books.BooksError(f"No job {job_number}")
    if job["contract_total"] is None:
        raise books.BooksError("This job has no signed contract yet. Use the estimate, not a change order.")
    description = (description or "").strip()
    if not description:
        raise books.BooksError("Describe the change")
    if not amount:
        raise books.BooksError("Enter the price change. Use a minus sign for a credit.")
    seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM change_orders WHERE job_number = ?", (job_number,)).fetchone()[0]
    cur = conn.execute("INSERT INTO change_orders (job_number, seq, description, amount, days_added) VALUES (?, ?, ?, ?, ?)",
                       (job_number, seq, description, round(float(amount), 2), int(days_added or 0)))
    conn.commit()
    return cur.lastrowid


def get(conn: sqlite3.Connection, co_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM change_orders WHERE id = ?", (co_id,)).fetchone()
    return _decorate(conn, row) if row else None


def list_for_job(conn: sqlite3.Connection, job_number: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM change_orders WHERE job_number = ? ORDER BY seq", (job_number,)).fetchall()
    return [_decorate(conn, r) for r in rows]


def check_signature(data_url: str) -> None:
    if not data_url.startswith(PNG_PREFIX):
        raise books.BooksError("Please sign in the box")
    if len(data_url) > MAX_SIGNATURE_BYTES:
        raise books.BooksError("That signature is too large")
    try:
        raw = base64.b64decode(data_url[len(PNG_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        raise books.BooksError("That signature couldn't be read") from None
    if not raw.startswith(PNG_MAGIC):
        raise books.BooksError("That signature couldn't be read")


def sign(conn: sqlite3.Connection, co_id: int, signer_name: str, signature: str) -> str:
    """Record the signature, raise the contract total and add the payment, all or nothing. Returns the new payment ID."""
    co = get(conn, co_id)
    if not co:
        raise books.BooksError("No such change order")
    if co["status"] != "draft":
        raise books.BooksError(f"This change order is already {co['status']}")
    signer_name = (signer_name or "").strip()
    if not signer_name:
        raise books.BooksError("Type the client's name")
    check_signature(signature)
    job = co["job"]
    try:
        conn.execute("UPDATE change_orders SET status = 'signed', signer_name = ?, signature = ?, signed_at = datetime('now') "
                     "WHERE id = ?", (signer_name, signature, co_id))
        conn.execute("UPDATE jobs SET contract_total = contract_total + ? WHERE number = ?", (co["amount"], co["job_number"]))
        seq = books.add_payment(conn, co["job_number"], co["amount"], f"Change Order {co['seq']}: {co['description']}",
                                "With the next invoice, or on completion of the change", kind="change_order",
                                change_order_id=co_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return f"{job['job_id']}-{seq}"


def decline(conn: sqlite3.Connection, co_id: int) -> None:
    co = get(conn, co_id)
    if not co or co["status"] != "draft":
        raise books.BooksError("Only an unsigned change order can be declined")
    conn.execute("UPDATE change_orders SET status = 'declined' WHERE id = ?", (co_id,))
    conn.commit()


def delete_draft(conn: sqlite3.Connection, co_id: int) -> None:
    co = get(conn, co_id)
    if not co or co["status"] != "draft":
        raise books.BooksError("Only an unsigned change order can be deleted")
    conn.execute("DELETE FROM change_orders WHERE id = ?", (co_id,))
    conn.commit()
