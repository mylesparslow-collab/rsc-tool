"""The Monday report: where the money and the jobs stand, in a page Nick and Myles can read in a minute.

Numbers come straight from the books. The model only writes the one-sentence opening, and a plain sentence is used
if it is unavailable. Sent from the business Gmail to the people listed on the Setup page, only when asked
(`rsc weekly-report --send`, the Monday schedule, or the Send now button).
"""
import html
import smtplib
import sqlite3
from datetime import date, timedelta
from email.message import EmailMessage

from . import receivables, books, brand, crew, estimates, followups, margins, pipeline, prefs, pricing, scorecard

OPENING_SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
OPENING_PROMPT = ("Write ONE plain sentence (under 30 words) opening a weekly business report for a remodeling contractor. "
                  "Use only the facts given; do not add numbers. No greeting.")


def money(v) -> str:
    return "-" if v is None else (f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}")


def rates_floor(conn) -> float:
    from . import rates
    return rates.get_settings(conn)["floor_rate"]


def build(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    start = (today - timedelta(days=7)).isoformat()
    jobs = books.list_jobs(conn)
    active = [j for j in jobs if j["status"] in ("Signed", "In Progress", "On Hold")]
    payments = books.list_payments(conn)
    got = [p for p in payments if p["date_paid"] and p["date_paid"] >= start and p["amount_paid"]]
    open_pay = [p for p in payments if p["status"] != "Paid" and any(j["number"] == p["job_number"] and j["status"] != "Lost" for j in jobs)]
    waiting = [j for j in jobs if j["status"] == "Estimate" and j["estimate_sent"] and
               (today - date.fromisoformat(j["estimate_sent"][:10])).days >= 7]
    spent = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date >= ?", (start,)).fetchone()[0]
    flagged = [m for m in margins.all_margins(conn) if m["status"] != "ok" and m["job"]["status"] != "Complete"]
    underpriced = []
    for j in jobs:
        if j["status"] == "Estimate" and estimates.get(conn, j["number"]):
            rt = pricing.check_estimate(conn, j["number"])["rates"]
            if rt["level"] == "bad":
                underpriced.append({"job": j, "rate": rt["rate"], "floor": rates_floor(conn)})
    week_hours = [dict(r) for r in conn.execute(
        "SELECT c.name, SUM(h.hours) AS hours FROM crew_hours h JOIN crew c ON c.id = h.crew_id WHERE h.work_date >= ? "
        "GROUP BY c.id ORDER BY hours DESC", (start,))]
    return {
        "aging": receivables.buckets(receivables.outstanding(conn, today)), "crew_hours": week_hours, "crew_alerts": crew.alerts(conn, today), "underpriced": underpriced,
        "date": today.isoformat(), "collected": round(sum(p["amount_paid"] for p in got), 2), "collected_n": len(got),
        "owed": round(sum(p["amount"] - (p["amount_paid"] or 0) for p in open_pay if p["invoice_sent"]), 2),
        "to_invoice": [p for p in open_pay if not p["invoice_sent"] and p["status"] == "Not yet"][:8],
        "invoiced": [p for p in open_pay if p["invoice_sent"]],
        "active": active, "spent": round(spent, 2), "flagged": flagged, "waiting": waiting,
        "to_review": len(pipeline.pending(conn)), "followups": followups.due(conn, today, ahead_days=7),
        "new_this_week": [j for j in jobs if (j["created_at"] or "")[:10] >= start],
        "scorecard": scorecard.build(conn, today),
    }


def opening(model, r: dict) -> str:
    def n(k, one, many):
        return f"{k} {one if k == 1 else many}"
    facts = (f"Collected {money(r['collected'])} this week. {money(r['owed'])} invoiced and still unpaid. "
             f"{n(len(r['active']), 'job', 'jobs')} underway. {n(len(r['flagged']), 'job', 'jobs')} to watch. "
             f"{n(len(r['waiting']), 'estimate', 'estimates')} waiting for an answer.")
    if model is not None:
        try:
            msg = (model.extract(OPENING_PROMPT, facts, OPENING_SCHEMA).get("message") or "").strip()
            if 20 < len(msg) < 220:
                return msg
        except Exception:
            pass
    return facts


def render_text(r: dict, intro: str) -> str:
    L = [f"{brand.current()['name']}: week of {r['date']}", "", intro, ""]
    L += [f"MONEY", f"  Collected this week: {money(r['collected'])} ({r['collected_n']} payments)",
          f"  Invoiced, not yet paid: {money(r['owed'])}", f"  Spent on jobs and business this week: {money(r['spent'])}"]
    late = [(b["label"], b) for b in r["aging"][1:] if b["rows"]]
    if late:
        L.append("  Late (over 14 days): " + "; ".join(f"{label} {money(b['total'])} ({len(b['rows'])})" for label, b in late))
    if r["invoiced"]:
        L.append("  Waiting on:")
        L += [f"    {p['payment_id']} {p['last_name']}: {money(p['amount'] - (p['amount_paid'] or 0))} ({p['description']})" for p in r["invoiced"]]
    if r["to_invoice"]:
        L.append("  Ready to invoice when the work gets there:")
        L += [f"    {p['payment_id']} {p['last_name']}: {money(p['amount'])} ({p['due_when'] or p['description']})" for p in r["to_invoice"]]
    if r.get("scorecard"):
        L += ["", "LEADS AND SALES"] + scorecard.summary_lines(r["scorecard"])
    L += ["", "JOBS UNDERWAY"]
    L += [f"  {j['job_id']} {j['last_name']} ({j['status']}): contract {money(j['contract_total'])}, paid {money(j['paid'])}, spent {money(j['expenses'])}"
          for j in r["active"]] or ["  None"]
    if r["flagged"]:
        L += ["", "WATCH THESE (margin)"] + [f"  {m['job']['job_id']} {m['job']['last_name']}: {m['why']}" for m in r["flagged"]]
    if r["underpriced"]:
        L += ["", "PRICED TOO LOW"] + [f"  {u['job']['job_id']} {u['job']['last_name']}: labor works out to ${u['rate']:.0f} per crew-hour "
                                      f"(floor ${u['floor']:.0f})" for u in r["underpriced"]]
    if r["crew_hours"]:
        L += ["", "CREW HOURS THIS WEEK"] + [f"  {c['name']}: {c['hours']:g}" for c in r["crew_hours"]]
    if r["crew_alerts"]:
        L += ["", "INSURANCE"] + [f"  {a['text']}" for a in r["crew_alerts"]]
    L += ["", "NEEDS AN ANSWER"]
    L += [f"  {j['job_id']} {j['last_name']}: estimate sent {j['estimate_sent']}, no reply yet" for j in r["waiting"]] or ["  No estimates waiting a week or more"]
    if r["to_review"]:
        L.append(f"  {r['to_review']} items from email waiting under To Review")
    if r["followups"]:
        L += ["", "FOLLOW-UPS DUE"] + [f"  {f['title']}: {f['first_name']} {f['last_name']} ({f['job_id']}), due {f['due_date']}" for f in r["followups"]]
    return "\n".join(L) + "\n"


def render_html(text: str) -> str:
    out = []
    for line in text.splitlines():
        esc = html.escape(line)
        if line and not line.startswith(" ") and line.isupper():
            out.append(f'<h3 style="margin:18px 0 4px;color:#2F5D46;font-size:13px;letter-spacing:.08em">{esc}</h3>')
        elif ": week of" in line or ": work for" in line:
            out.append(f'<h2 style="margin:0 0 8px;color:#1f3d2e">{esc}</h2>')
        elif line:
            out.append(f'<div style="white-space:pre-wrap">{esc}</div>')
    return ('<div style="font:15px/1.5 -apple-system,Segoe UI,sans-serif;max-width:640px;color:#222">' + "".join(out) + "</div>")


def send(conn: sqlite3.Connection, address: str, password: str, text: str, subject: str, host: str = "smtp.gmail.com") -> list[str]:
    to = prefs.report_recipients(conn)
    if not to:
        raise ValueError("Add who should get the report on the Setup page first.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = address, ", ".join(to), subject
    msg.set_content(text)
    msg.add_alternative(render_html(text), subtype="html")
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(address, password)
        s.send_message(msg)
    return to


def subject(r: dict) -> str:
    return f"RSC weekly report, {r['date']}: {money(r['collected'])} collected, {money(r['owed'])} outstanding"
