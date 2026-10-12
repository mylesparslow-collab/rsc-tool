"""Pricing check: how Nick's estimates compare with what jobs really cost, and the lowest price that still works.

Nothing here assumes a price, margin or overhead number. Overhead comes from what is logged under RSC codes
(truck, insurance, phone...) against signed contract totals. The target margin is entered by Nick.

    price floor = estimated direct costs / (1 - overhead % - target margin %)

Direct costs are the estimate's materials (at cost, before markup), windows and doors, debris fee, up-front
items and hired labor. Nick's own labor is what the margin pays for, so it is not a direct cost.
"""
import sqlite3
from datetime import date, timedelta

from . import books, crew, estimates, rates

MIN_JOBS_FOR_HISTORY = 3
WINDOW_DAYS = 365


def get_settings(conn: sqlite3.Connection) -> dict:
    out = {}
    for key, name in (("pricing_target_margin", "target_margin"), ("pricing_overhead_override", "overhead_override")):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        out[name] = float(row[0]) if row and row[0] != "" else None
    return out


def save_settings(conn: sqlite3.Connection, target_margin: float | None, overhead_override: float | None) -> None:
    for key, value in (("pricing_target_margin", target_margin), ("pricing_overhead_override", overhead_override)):
        if value is not None and not 0 <= value < 100:
            raise books.BooksError("Percentages must be between 0 and 100")
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, "" if value is None else str(value)))
    conn.commit()


def overhead(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Operations spend as a share of signed contract totals over the last 12 months."""
    start = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    spend = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE rsc_code IS NOT NULL AND date >= ?",
                         (start,)).fetchone()[0]
    revenue, jobs = conn.execute("SELECT COALESCE(SUM(contract_total), 0), COUNT(*) FROM jobs "
                                 "WHERE contract_total IS NOT NULL AND contract_signed >= ?", (start,)).fetchone()
    override = get_settings(conn)["overhead_override"]
    history_ok = jobs >= MIN_JOBS_FOR_HISTORY and revenue > 0 and spend > 0
    if override is not None:
        pct, source = override / 100, "entered"
    elif history_ok:
        pct, source = spend / revenue, "history"
    else:
        pct, source = None, None
    return {"spend": round(spend, 2), "revenue": round(revenue, 2), "jobs": jobs, "pct": pct, "source": source,
            "history_ok": history_ok, "history_pct": spend / revenue if history_ok else None}


def floor_price(direct_cost: float, overhead_pct: float, margin_pct: float) -> float | None:
    denominator = 1 - overhead_pct - margin_pct
    return round(direct_cost / denominator, 2) if denominator > 0 else None


def check_estimate(conn: sqlite3.Connection, job_number: int, today: date | None = None) -> dict | None:
    est = estimates.get(conn, job_number)
    if not est:
        return None
    t = estimates.totals(est)
    s = get_settings(conn)
    o = overhead(conn, today)
    out = {"price": t["total"], "direct_cost": t["direct_cost"], "overhead": o, "target_margin": s["target_margin"],
           "floor": None, "cushion": None, "status": "needs_settings", "gross_margin_pct": None,
           "rates": rates.analyze(est, rates.get_settings(conn), hours_logged=crew.hours_for_job(conn, job_number))}
    if t["total"] > 0:
        out["gross_margin_pct"] = (t["total"] - t["direct_cost"]) / t["total"]
    if s["target_margin"] is None or o["pct"] is None:
        return out
    floor = floor_price(t["direct_cost"], o["pct"], s["target_margin"] / 100)
    out["floor"] = floor
    if floor is None:
        out["status"] = "impossible"
    else:
        out["cushion"] = round(t["total"] - floor, 2)
        out["status"] = "above" if t["total"] >= floor else "below"
    return out


def accuracy(conn: sqlite3.Connection) -> dict:
    """Estimated direct cost against what was actually spent on each job that has an estimate."""
    rows = []
    for j in books.list_jobs(conn):
        est = estimates.get(conn, j["number"])
        if not est or j["expenses"] <= 0:
            continue
        direct = estimates.totals(est)["direct_cost"]
        rows.append({"job": j, "estimated": direct, "actual": j["expenses"],
                     "variance": round(j["expenses"] - direct, 2),
                     "variance_pct": (j["expenses"] - direct) / direct if direct else None,
                     "finished": j["status"] == "Complete"})
    finished = [r for r in rows if r["finished"] and r["estimated"]]
    est_sum = sum(r["estimated"] for r in finished)
    avg = (sum(r["actual"] for r in finished) / est_sum - 1) if est_sum else None
    return {"rows": rows, "finished_count": len(finished), "average_variance_pct": avg}
