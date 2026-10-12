"""What should happen next on this job? One plain next step, so nobody has to remember the order of things.

The same steps run from a lead to a finished job: write the estimate, check the price, send it, get it signed, invoice the
first payment, do the work (receipts and hours), invoice each phase, final payment, ask for the review.
"""
import sqlite3
from datetime import date

from . import books, crew, estimates, pricing


def _days_since(iso: str | None) -> int | None:
    try:
        return (date.today() - date.fromisoformat((iso or "")[:10])).days
    except ValueError:
        return None


def steps(conn: sqlite3.Connection, job: dict) -> dict:
    est = estimates.get(conn, job["number"])
    payments = books.list_payments(conn, job["number"])
    signed = job["status"] in ("Signed", "In Progress", "Complete") or bool(job.get("contract_signed"))
    check = pricing.check_estimate(conn, job["number"]) if est else None
    level = check["rates"]["level"] if check else "ok"
    first = payments[0] if payments else None
    work = bool(job.get("expenses")) or crew.hours_for_job(conn, job["number"]) > 0
    done = {
        "estimate": bool(est),
        "price": bool(est) and level != "bad",
        "sent": bool(job.get("estimate_sent")) or signed,
        "signed": signed,
        "invoiced": bool(first and first["invoice_sent"]) or bool(first and first["status"] == "Paid"),
        "paid": bool(first and first["status"] == "Paid"),
        "work": work,
        "final": bool(payments) and all(p["status"] == "Paid" for p in payments),
    }
    labels = [("estimate", "Estimate written"), ("price", "Price checked"), ("sent", "Estimate sent"), ("signed", "Contract signed"),
              ("invoiced", "First payment invoiced"), ("paid", "First payment paid"), ("work", "Receipts and hours logged"),
              ("final", "Final payment paid")]
    return {"done": done, "list": [(label, done[k]) for k, label in labels]}


def next_step(conn: sqlite3.Connection, job: dict) -> dict | None:
    """{'title','why','endpoint','label'} for the single next thing to do, or None when nothing is waiting."""
    n, name = job["number"], job.get("first_name") or job.get("last_name") or "the client"
    if job["status"] in ("Lost",):
        return None
    est = estimates.get(conn, n)
    if job["status"] == "Complete":
        pending = conn.execute("SELECT COUNT(*) FROM followups WHERE job_number = ? AND status = 'pending'", (n,)).fetchone()[0]
        if pending:
            return {"title": "Ask for a review", "why": f"{name}'s job is done. A short note now brings reviews and the next job.",
                    "endpoint": "followups_page", "args": {}, "label": "Open follow-ups"}
        return None
    if not est:
        return {"title": "Write the estimate", "why": "Tell me about the job in a few sentences. I draft the scope of work and the prices.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Start the estimate"}
    if job["status"] == "Estimate":
        check = pricing.check_estimate(conn, n)
        rt = check["rates"]
        if rt["level"] == "bad":
            return {"title": "Check the labor price", "why": rt["warnings"][0], "endpoint": "estimate_edit", "args": {"number": n},
                    "label": "Open the estimate"}
        if not job.get("estimate_sent"):
            return {"title": f"Send the estimate to {name}", "why": "Print the scope of work, send it, then put today's date in 'Estimate sent' on the job.",
                    "endpoint": "sow", "args": {"number": n}, "label": "Print the estimate"}
        days = _days_since(job["estimate_sent"])
        if days is not None and days >= 7:
            return {"title": f"Follow up with {name}", "why": f"The estimate went out {days} days ago with no answer yet.",
                    "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job"}
        return {"title": f"Waiting on {name}", "why": "When they say yes, open the estimate and press 'Contract signed'. That sets up the payments.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Open the estimate"}
    payments = books.list_payments(conn, n)
    unpaid = [p for p in payments if p["status"] != "Paid"]
    if not payments:
        return {"title": "Set up the payments", "why": "The job is signed but has no payment schedule yet.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Open the estimate"}
    invoice_next = next((p for p in payments if not p["invoice_sent"] and p["status"] != "Paid"), None)
    waiting = [p for p in payments if p["invoice_sent"] and p["status"] != "Paid"]
    if payments[0]["status"] != "Paid" and not payments[0]["invoice_sent"]:
        p = payments[0]
        return {"title": f"Invoice payment 1 (${p['amount']:,.0f})", "why": "The first payment holds the schedule and covers materials. Invoice it before ordering anything.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments"}
    if waiting:
        p = waiting[0]
        return {"title": f"Waiting on payment {p['payment_id']}", "why": f"${p['amount'] - (p['amount_paid'] or 0):,.0f} invoiced. When it arrives, the email check suggests it for approval.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job"}
    if not job.get("expenses") and crew.hours_for_job(conn, n) == 0:
        return {"title": "Start logging the work", "why": "Forward receipts to the business email or photograph them, and log who worked how many hours. That is how you see if the job is making money.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job"}
    if invoice_next:
        return {"title": f"Next invoice: {invoice_next['payment_id']} (${invoice_next['amount']:,.0f})",
                "why": f"Due when: {invoice_next['due_when'] or invoice_next['description']}. Invoice it when you get there.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments"}
    if unpaid:
        return {"title": "Collect the last payment", "why": "Then mark the job Complete; the review request and one-year check-in schedule themselves.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job"}
    return {"title": "Mark the job Complete", "why": "Everything is paid. Completing it schedules the review request and the one-year check-in.",
            "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job"}
