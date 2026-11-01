"""What should happen next on this job? One plain next step, so nobody has to remember the order of things.

The same steps run from a lead to a finished job: write the estimate, check the price, send it, get it signed, invoice the
first payment, do the work (receipts and hours), invoice each phase, final payment, ask for the review.
"""
import re
import sqlite3
from datetime import date

from . import books, brand, crew, daily, estimates, leads, pricing


def _days_since(iso: str | None) -> int | None:
    try:
        return (date.today() - date.fromisoformat((iso or "")[:10])).days
    except ValueError:
        return None


def _phase_done(conn: sqlite3.Connection, n: int, payment: dict) -> bool:
    """True when every step the payment is tied to ('... Steps 4–6') has been ticked on the Today or Progress page."""
    m = re.search(r"Steps? (\d+)(?:\s*[–-]\s*(\d+))?", payment.get("due_when") or "")
    if not m:
        return False
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    return set(range(first, last + 1)) <= daily.done_steps(conn, n)


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


def _invoice_target(p: dict) -> list[str]:
    return [f"#payrow-{p['id']} button[value=invoiced]", f"#payrow-{p['id']} input[name=invoice_sent]"]


def _paid_target(p: dict) -> list[str]:
    return [f"#payrow-{p['id']} button[value=paid]", f"#payrow-{p['id']} input[name=date_paid]"]


def next_step(conn: sqlite3.Connection, job: dict) -> dict | None:
    """{'title','why','endpoint','args','label'} for the single next thing to do, or None when nothing is waiting.

    'target' lists CSS selectors (first match wins) for the field or button to glow on that page. 'wait' marks a step where
    the next move is someone else's (the client answering, a payment arriving): it's shown, but nothing glows for it."""
    n, name = job["number"], job.get("first_name") or job.get("last_name") or "the client"
    if job["status"] in ("Lost",):
        return None
    est = estimates.get(conn, n)
    if job["status"] == "Complete":
        unpaid = [p for p in books.list_payments(conn, n) if p["status"] != "Paid"]
        if unpaid and not unpaid[0]["invoice_sent"]:  # finished work, money not asked for yet: this comes before the review
            p = unpaid[0]
            return {"title": f"Invoice {p['payment_id']} (${p['amount'] - (p['amount_paid'] or 0):,.0f})",
                    "why": f"{name}'s job is marked Complete but this payment hasn't been invoiced yet.",
                    "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments", "target": _invoice_target(p)}
        if unpaid:
            p = unpaid[0]
            return {"title": f"Waiting on payment {p['payment_id']}", "why": f"${p['amount'] - (p['amount_paid'] or 0):,.0f} invoiced. When it arrives, the email check suggests it for approval.",
                    "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "wait": True, "target": _paid_target(p)}
        row = conn.execute("SELECT id FROM followups WHERE job_number = ? AND status = 'pending' ORDER BY due_date", (n,)).fetchone()
        if row:
            fid = row[0]
            return {"title": "Ask for a review", "why": f"{name}'s job is done. A short note now brings reviews and the next job.",
                    "endpoint": "followups_page", "args": {}, "label": "Open follow-ups",
                    "target": [f"#f{fid} a.btn", f"#f{fid} button.btn"]}
        return None
    if not est:
        step = {"title": "Write the estimate", "why": "Tell me about the job in a few sentences. I draft the scope of work and the prices.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Start the estimate",
                "target": ["textarea[name=description]"]}
        days = _days_since(job.get("created_at"))
        if job["status"] == "Estimate" and days is not None and days >= 7:  # a lead that may have gone quiet
            step.update(why=f"{name} asked {days} days ago and there's no estimate yet. If you haven't been out to see it, "
                            f"a short check-in is ready below.",
                        draft=leads.lead_checkin(job, days), subject=f"Your {(job.get('job_type') or 'project').lower()} request")
        return step
    if job["status"] == "Estimate":
        check = pricing.check_estimate(conn, n)
        rt = check["rates"]
        if rt["level"] == "bad":
            return {"title": "Check the labor price", "why": rt["warnings"][0], "endpoint": "estimate_edit", "args": {"number": n},
                    "label": "Open the estimate", "target": ["input[name=instruction]"]}
        if not job.get("estimate_sent"):
            return {"title": f"Send the estimate to {name}", "why": "Look it over, then send it from the next screen. The job is marked sent for you.",
                    "endpoint": "sow", "args": {"number": n}, "label": "Preview and send", "target": ["a.btn.send"]}
        days = _days_since(job["estimate_sent"])
        if days is not None and days >= 7:
            return {"title": f"Follow up with {name}", "why": f"The estimate went out {days} days ago with no answer yet. A short note is ready below.",
                    "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "target": [".tracker .contact a"],
                    "draft": estimate_followup(job, days), "subject": f"Your {(job.get('job_type') or 'project').lower()} estimate"}
        return {"title": f"Waiting on {name}", "why": "When they say yes, open the estimate and press 'Contract signed'. That sets up the payments.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Open the estimate", "wait": True}
    payments = books.list_payments(conn, n)
    unpaid = [p for p in payments if p["status"] != "Paid"]
    if not payments:
        return {"title": "Set up the payments", "why": "The job is signed but has no payment schedule yet.",
                "endpoint": "estimate_edit", "args": {"number": n}, "label": "Open the estimate",
                "target": ["form[action$='/estimate/schedule'] button", "form[action$='/estimate/approve'] button"]}
    invoice_next = next((p for p in payments if not p["invoice_sent"] and p["status"] != "Paid"), None)
    waiting = [p for p in payments if p["invoice_sent"] and p["status"] != "Paid"]
    if payments[0]["status"] != "Paid" and not payments[0]["invoice_sent"]:
        p = payments[0]
        return {"title": f"Invoice payment 1 (${p['amount']:,.0f})", "why": "The first payment holds the schedule and covers materials. Invoice it before ordering anything.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments", "target": _invoice_target(p)}
    if waiting:
        p = waiting[0]
        return {"title": f"Waiting on payment {p['payment_id']}", "why": f"${p['amount'] - (p['amount_paid'] or 0):,.0f} invoiced. When it arrives, the email check suggests it for approval.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "wait": True, "target": _paid_target(p)}
    if not job.get("expenses") and crew.hours_for_job(conn, n) == 0:
        return {"title": "Start logging the work", "why": "Forward receipts to the business email or photograph them, and log who worked how many hours. That is how you see if the job is making money.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "target": ["#hours + form input[name=text]"]}
    if invoice_next and _phase_done(conn, n, invoice_next):
        return {"title": f"Invoice {invoice_next['payment_id']} now (${invoice_next['amount']:,.0f})",
                "why": f"The crew has ticked off every step it covers ({invoice_next['due_when']}).",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments", "target": _invoice_target(invoice_next)}
    if invoice_next:
        return {"title": f"Next invoice: {invoice_next['payment_id']} (${invoice_next['amount']:,.0f})",
                "why": f"Due when: {invoice_next['due_when'] or invoice_next['description']}. Invoice it when you get there.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the payments", "wait": True, "target": _invoice_target(invoice_next)}
    if unpaid:
        return {"title": "Collect the last payment", "why": "Then mark the job Complete; the review request and one-year check-in schedule themselves.",
                "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "target": _paid_target(unpaid[0])}
    return {"title": "Mark the job Complete", "why": "Everything is paid. Completing it schedules the review request and the one-year check-in.",
            "endpoint": "job_detail", "args": {"number": n}, "label": "Open the job", "target": ["select[name=status]"]}


STAGES = [("estimate", "Write the estimate"), ("sent", "Send it"), ("signed", "Get it signed"), ("work", "Do the work, get paid"),
          ("finished", "Wrap up")]


def stage(conn: sqlite3.Connection, job: dict) -> dict:
    """Where the job is, as five big stages for the tracker at the top of every job page.

    {'stages': [{'key','label','state'}], 'number', 'count', 'label', 'next', 'status'}; state is done, current or todo.
    A stage counts as done when any later one is, so an imported, already-signed job doesn't show 'Estimate' as unfinished."""
    d = steps(conn, job)["done"]
    nxt = next_step(conn, job)
    done = [d["estimate"] and d["price"], d["sent"], d["signed"], d["final"] and bool(books.list_payments(conn, job["number"])),
            job["status"] == "Complete" and nxt is None]
    for i in range(len(done) - 2, -1, -1):
        done[i] = done[i] or done[i + 1]
    current = next((i for i, x in enumerate(done) if not x), None)
    stages = [{"key": k, "label": label, "state": "done" if done[i] else ("current" if i == current else "todo")}
              for i, (k, label) in enumerate(STAGES)]
    return {"stages": stages, "number": (current + 1) if current is not None else len(STAGES), "count": len(STAGES),
            "label": STAGES[current][1] if current is not None else "Finished", "next": nxt, "status": job["status"]}


def next_task(conn: sqlite3.Connection, setup_ok: bool = True) -> dict | None:
    """The one most useful thing to do now, across the whole business, for the Next task button.

    Same order as Home's 'Needs your attention': setup, email suggestions, late invoices, follow-ups, then each open job's
    next step. Steps that only wait on someone else are skipped. None means all caught up."""
    from . import followups, pipeline, receivables  # here, not at the top: they import more of the app than guide needs
    if not setup_ok:
        return {"title": "Finish setup", "why": "Add the business Gmail and its app password so the assistant can read receipts and emails.",
                "endpoint": "setup_page", "args": {}, "label": "Open Setup",
                "target": ["input[name=address][value='']", "input[name=password]"]}
    pending = pipeline.pending(conn)
    if pending:
        return {"title": f"Look over {len(pending)} thing{'s' if len(pending) != 1 else ''} from your email",
                "why": "Receipts, payments and new customers the assistant found. Check each one and press the green button.",
                "endpoint": "review", "args": {}, "label": "Review now", "target": [".review-item button[value=approve]"]}
    late = [r for r in receivables.outstanding(conn) if r["needs_reminder"]]
    if late:
        r = late[0]
        return {"title": f"Remind {r['last_name']} about {r['payment_id']}", "why": f"Invoiced {r['days']} days ago and not paid yet.",
                "endpoint": "owed_page", "args": {}, "label": "Write a reminder",
                "target": [f"form[action$='/owed/{r['id']}/draft'] button"]}
    due = followups.due(conn)
    if due:
        f = due[0]
        return {"title": f"{f['title']}: {f['first_name']} {f['last_name']}".strip(), "why": "The message is written for you. Open it, send it, mark it sent.",
                "endpoint": "followups_page", "args": {}, "label": "Open follow-ups",
                "target": [f"#f{f['id']} a.btn", f"#f{f['id']} button.btn"]}
    for job in books.list_jobs(conn, active_only=True):
        step = next_step(conn, job)
        if step and not step.get("wait"):
            return {**step, "title": f"{job['last_name']}: {step['title']}"}
    return None


def estimate_followup(job: dict, days: int) -> str:
    """A polite check-in on an estimate that has had no answer. Plain template: it names no price and never pushes."""
    b = brand.current()
    first = job.get("first_name") or job.get("last_name") or "there"
    what = (job.get("job_type") or "project").lower()
    if days < 21:
        body = (f"I wanted to make sure the estimate for your {what} reached you, and see if any questions came up. "
                f"Happy to go over it by phone or walk through it again in person, and to adjust the scope if something "
                f"doesn't fit your budget or timing.")
    else:
        body = (f"Checking in one last time on the estimate for your {what}. If the timing isn't right or you've gone another "
                f"way, no problem at all, just let me know so I can plan my schedule. If you'd still like to go ahead, "
                f"I can hold a spot for you.")
    return f"Hi {first},\n\n{body}\n\n{b['owner']}\n{b['name']}\n{b['phone']}"
