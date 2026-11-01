"""Jobs, payments and expenses: the same rules as the spreadsheet tracker."""
import sqlite3
from dataclasses import dataclass

from . import ids

STATUSES = ["Estimate", "Signed", "In Progress", "Complete", "Lost", "On Hold"]
JOB_TYPES = ["Kitchen", "Bathroom", "Addition / Enclosure", "Deck / Exterior", "Whole House",
             "Carpentry / Repair", "Aging in place", "Other"]
EXPENSE_CATEGORIES = ["Materials", "Subcontractor", "Equipment Rental", "Permits & Fees", "Dump / Debris",
                      "Hired Labor", "Operations", "Other"]
PAID_WITH = ["Business card", "Business check", "Cash", "Personal card", "Other"]
ACTIVE = ("Estimate", "Signed", "In Progress", "On Hold")


class BooksError(ValueError):
    """A rule was broken; the message is safe to show Nick."""


@dataclass
class ChargeTo:
    job_number: int | None = None
    rsc_code: str | None = None

    @property
    def label(self) -> str:
        return str(self.job_number) if self.job_number is not None else (self.rsc_code or "")


def next_job_number(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(number) FROM jobs").fetchone()
    if row[0] is not None:
        return row[0] + 1
    first = conn.execute("SELECT value FROM settings WHERE key = 'first_job_number'").fetchone()
    return int(first[0]) if first else 1001


def create_job(conn: sqlite3.Connection, last_name: str, number: int | None = None, **fields) -> int:
    code = ids.client_code(last_name)
    number = number if number is not None else next_job_number(conn)
    if conn.execute("SELECT 1 FROM jobs WHERE number = ?", (number,)).fetchone():
        raise BooksError(f"Job {number} already exists")
    allowed = {"first_name", "email", "phone", "address", "job_type", "status", "estimate_sent",
               "contract_signed", "contract_total", "notes"}
    extra = {k: v for k, v in fields.items() if k in allowed and v not in (None, "")}
    cols = ["number", "last_name", "code", *extra]
    conn.execute(f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                 [number, last_name.strip(), code, *extra.values()])
    conn.commit()
    return number


def update_job(conn: sqlite3.Connection, number: int, **fields) -> None:
    allowed = {"first_name", "email", "phone", "address", "job_type", "status", "estimate_sent",
               "contract_signed", "contract_total", "notes"}
    sets = {k: (v if v != "" else None) if k in ("estimate_sent", "contract_signed", "contract_total") else v
            for k, v in fields.items() if k in allowed}
    if not sets:
        return
    before = conn.execute("SELECT status FROM jobs WHERE number = ?", (number,)).fetchone()
    conn.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in sets)} WHERE number = ?",
                 [*sets.values(), number])
    conn.commit()
    if "status" in sets and before and before[0] != sets["status"]:
        from . import followups  # a finished job gets a review request and a one-year check-in
        if sets["status"] == "Complete":
            followups.schedule(conn, number)
        elif before[0] == "Complete":
            followups.cancel(conn, number)


JOB_SUMMARY_SQL = """
SELECT j.*,
       j.number || '-' || j.code AS job_id,
       COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_number = j.number), 0)      AS scheduled,
       COALESCE((SELECT SUM(amount_paid) FROM payments p WHERE p.job_number = j.number), 0) AS paid,
       COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.job_number = j.number), 0)      AS expenses
FROM jobs j
"""


def _summarize(row: sqlite3.Row) -> dict:
    d = dict(row)
    total = d["contract_total"]
    d["owed"] = None if total is None else round(total - d["paid"], 2)
    d["profit"] = None if total is None else round(total - d["expenses"], 2)
    d["schedule_ok"] = None if total is None else round(d["scheduled"] - total, 2) == 0
    return d


def list_jobs(conn: sqlite3.Connection, active_only: bool = False) -> list[dict]:
    sql = JOB_SUMMARY_SQL
    params: tuple = ()
    if active_only:
        sql += f" WHERE j.status IN ({', '.join('?' * len(ACTIVE))})"
        params = ACTIVE
    return [_summarize(r) for r in conn.execute(sql + " ORDER BY j.number DESC", params)]


def get_job(conn: sqlite3.Connection, number: int) -> dict | None:
    row = conn.execute(JOB_SUMMARY_SQL + " WHERE j.number = ?", (number,)).fetchone()
    return _summarize(row) if row else None


def add_payment(conn: sqlite3.Connection, job_number: int, amount: float, description: str = "",
                due_when: str = "", notes: str = "", kind: str = "manual", change_order_id: int | None = None,
                commit: bool = True) -> int:
    if not get_job(conn, job_number):
        raise BooksError(f"No job {job_number}. Add the job first.")
    seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM payments WHERE job_number = ?",
                       (job_number,)).fetchone()[0]
    conn.execute("INSERT INTO payments (job_number, seq, description, due_when, amount, notes, kind, "
                 "change_order_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (job_number, seq, description, due_when, amount, notes, kind, change_order_id))
    if commit:
        conn.commit()
    return seq


def payment_status(p: dict) -> str:
    if p.get("amount_paid"):
        return "Paid" if p["amount_paid"] >= p["amount"] else "Part paid"
    return "Invoiced" if p.get("invoice_sent") else "Not yet"


def list_payments(conn: sqlite3.Connection, job_number: int | None = None, open_only: bool = False) -> list[dict]:
    sql = ("SELECT p.*, j.number || '-' || j.code || '-' || p.seq AS payment_id, j.last_name "
           "FROM payments p JOIN jobs j ON j.number = p.job_number")
    where, params = [], []
    if job_number is not None:
        where.append("p.job_number = ?")
        params.append(job_number)
    if open_only:
        where.append("(p.amount_paid IS NULL OR p.amount_paid < p.amount)")
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY p.job_number DESC, p.seq", params)]
    for r in rows:
        r["status"] = payment_status(r)
    return rows


def find_payment(conn: sqlite3.Connection, job_number: int, seq: int) -> dict | None:
    rows = [p for p in list_payments(conn, job_number) if p["seq"] == seq]
    return rows[0] if rows else None


def update_payment(conn: sqlite3.Connection, payment_pk: int, **fields) -> None:
    allowed = {"description", "due_when", "amount", "invoice_sent", "date_paid", "amount_paid", "notes"}
    sets = {k: (None if v == "" and k in ("invoice_sent", "date_paid", "amount_paid") else v)
            for k, v in fields.items() if k in allowed}
    if sets:
        conn.execute(f"UPDATE payments SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
                     [*sets.values(), payment_pk])
        conn.commit()


def parse_charge_to(conn: sqlite3.Connection, value: str | int) -> ChargeTo:
    text = str(value).strip().upper()
    if ids.is_rsc_code(text):
        if not conn.execute("SELECT 1 FROM rsc_codes WHERE code = ?", (text,)).fetchone():
            raise BooksError(f"{text} isn't on the RSC code list")
        return ChargeTo(rsc_code=text)
    digits = text.split("-")[0]
    if digits.isdigit() and get_job(conn, int(digits)):
        return ChargeTo(job_number=int(digits))
    raise BooksError(f"'{value}' isn't a job number or an RSC code")


def add_expense(conn: sqlite3.Connection, date: str, charge_to: str | int, amount: float, vendor: str = "",
                description: str = "", category: str = "", paid_with: str = "", notes: str = "",
                source: str = "manual", email_id: int | None = None) -> int:
    target = parse_charge_to(conn, charge_to)
    if target.rsc_code and not category:
        category = "Operations"
    cur = conn.execute(
        "INSERT INTO expenses (date, job_number, rsc_code, vendor, description, category, amount, paid_with, "
        "source, email_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (date, target.job_number, target.rsc_code, vendor, description, category, amount, paid_with,
         source, email_id, notes))
    conn.commit()
    return cur.lastrowid


def list_expenses(conn: sqlite3.Connection, job_number: int | None = None, limit: int = 500) -> list[dict]:
    sql = ("SELECT e.*, COALESCE(CAST(e.job_number AS TEXT), e.rsc_code) AS charge_to, "
           "CASE WHEN e.job_number IS NOT NULL THEN 'Job ' || j.number || '-' || j.code "
           "ELSE 'Operations: ' || r.description END AS goes_to "
           "FROM expenses e LEFT JOIN jobs j ON j.number = e.job_number "
           "LEFT JOIN rsc_codes r ON r.code = e.rsc_code")
    params: list = []
    if job_number is not None:
        sql += " WHERE e.job_number = ?"
        params.append(job_number)
    sql += " ORDER BY e.date DESC, e.id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def list_rsc_codes(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT r.*, COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.rsc_code = r.code), 0) AS spent "
        "FROM rsc_codes r ORDER BY r.code")]
