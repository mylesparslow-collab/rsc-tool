"""Is each job still making money? Compares what has been spent with what the estimate said it would cost.
Crew hours logged on the job (hours x each person's pay) count as labor cost in the margin, on top of the budgeted items.

Margin here is gross margin: (contract - direct costs) / contract. Direct costs are the estimate's materials, windows and
doors, debris, up-front items and hired labor, the same as the pricing check; Nick's own labor is what the margin pays for.
The projected margin uses the larger of what has been spent and what was budgeted, so a job that has barely started
isn't shown as 100% profit. The target comes from the Pricing page; with none set, nothing is flagged.
"""
import sqlite3

from . import books, crew, estimates, pricing

ACTIVE_FOR_MARGIN = ("Signed", "In Progress", "On Hold", "Complete")


def job_margin(conn: sqlite3.Connection, job: dict, target_pct: float | None = None) -> dict | None:
    total = job.get("contract_total")
    if not total or total <= 0:
        return None
    est = estimates.get(conn, job["number"])
    budget = estimates.totals(est)["direct_cost"] if est else None
    labor_logged = crew.labor_cost_for_job(conn, job["number"])   # hours x pay for the people who worked on it
    spent = job["expenses"]
    expected_cost = (max(spent, budget) if budget else spent) + labor_logged
    projected = (total - expected_cost) / total
    out = {"job": job, "contract": total, "spent": spent, "labor_logged": labor_logged, "budget": budget,
           "spent_pct_of_budget": spent / budget if budget else None,
           "margin_now": (total - spent - labor_logged) / total, "margin_projected": projected, "status": "ok", "why": ""}
    if budget and spent > budget:
        out.update(status="over", why=f"Spent ${spent - budget:,.0f} more than the ${budget:,.0f} budgeted")
    elif budget and spent > 0.85 * budget and job["status"] in ("Signed", "In Progress"):
        out.update(status="watch", why=f"{spent / budget:.0%} of the budget is already spent")
    if target_pct is not None and projected * 100 < target_pct and out["status"] == "ok":
        out.update(status="watch", why=f"Projected margin {projected:.0%} is under the {target_pct:.0f}% target")
    return out


def all_margins(conn: sqlite3.Connection) -> list[dict]:
    target = pricing.get_settings(conn)["target_margin"]
    rows = [job_margin(conn, j, target) for j in books.list_jobs(conn) if j["status"] in ACTIVE_FOR_MARGIN]
    return [r for r in rows if r]
