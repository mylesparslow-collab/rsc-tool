"""QuickBooks files. The Payment ID is the invoice number, so nothing has to be retyped.

Three CSVs that QuickBooks Online's own importers accept (Sales > Invoices > Import, Banking > Upload, Customers > Import):
  invoices   one row per payment on the schedule, InvoiceNo = Payment ID
  expenses   date, description, amount (spending is negative), for the bank-upload screen
  customers  one row per job's client
"""
import csv
import io
from datetime import date, timedelta

from . import books

INVOICE_COLS = ["InvoiceNo", "Customer", "InvoiceDate", "DueDate", "Terms", "Memo", "Item(Product/Service)",
                "ItemDescription", "ItemQuantity", "ItemRate", "ItemAmount"]
SERVICE_ITEM = "Remodeling Services"


def _client(p: dict, jobs: dict) -> str:
    j = jobs.get(p["job_number"], {})
    name = f"{j.get('first_name', '')} {j.get('last_name', '')}".strip()
    return name or p["last_name"]


def _csv(cols, rows) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(cols)
    w.writerows(rows)
    return out.getvalue()


def invoices_csv(conn, open_only: bool = True, today: date | None = None) -> str:
    today = today or date.today()
    jobs = {j["number"]: j for j in books.list_jobs(conn)}
    rows = []
    for p in books.list_payments(conn, open_only=open_only):
        if not p["amount"]:
            continue
        sent = p["invoice_sent"] or today.isoformat()
        try:
            due = (date.fromisoformat(sent) + timedelta(days=7)).isoformat()
        except ValueError:
            due = sent
        rows.append([p["payment_id"], _client(p, jobs), sent, due, "Net 7",
                     f"{jobs.get(p['job_number'], {}).get('address', '')}".strip(), SERVICE_ITEM,
                     f"{p['description']} ({p['due_when']})" if p["due_when"] else p["description"], 1, f"{p['amount']:.2f}", f"{p['amount']:.2f}"])
    return _csv(INVOICE_COLS, rows)


def expenses_csv(conn) -> str:
    """Bank-upload format. The job is kept in the description so it can be matched in QuickBooks."""
    rows = [[e["date"], f"{e['vendor']} - {e['description']} [{e['charge_to']}]".strip(" -"), f"{-abs(e['amount']):.2f}"]
            for e in books.list_expenses(conn, limit=100000)]
    return _csv(["Date", "Description", "Amount"], rows)


def customers_csv(conn) -> str:
    rows = [[f"{j['first_name']} {j['last_name']}".strip(), j["first_name"], j["last_name"], j["email"], j["phone"],
             j["address"]] for j in books.list_jobs(conn)]
    return _csv(["Customer", "First Name", "Last Name", "Email", "Phone", "Address"], rows)
