"""How RSC builds things, written down: a one-page brief for the lead carpenter on each job, and a playbook by job type.

Nothing here is invented. Both are assembled from Nick's own estimates and scope-of-work steps, so as Nick writes more
estimates the playbook gets better, and a lead carpenter can run a job from the brief without Nick standing there.
"""
import re
import sqlite3
from collections import Counter, OrderedDict

from . import books, crew, estimates, rates


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def job_brief(conn: sqlite3.Connection, job_number: int) -> dict | None:
    job = books.get_job(conn, job_number)
    est = estimates.get(conn, job_number)
    if not job or not est:
        return None
    phases, n = [], 0
    for p, rng in zip(est["phases"], estimates.step_ranges(est["phases"])):
        steps = []
        for text in p["steps"]:
            n += 1
            steps.append((n, text))
        phases.append({"title": p["title"], "steps": steps, "inspection": p.get("inspection", "")})
    t = estimates.totals(est)
    rt = rates.analyze(est, rates.get_settings(conn))
    schedule = estimates.build_schedule(est) if t["total"] > 0 else []
    subs = [p["name"] for p in crew.people(conn, active_only=True) if p["role"] == "sub"]
    return {"job": job, "est": est, "phases": phases, "materials": _lines(est.get("materials_list", "")),
            "not_included": _lines(est.get("labor_not_included", "")) + _lines(est.get("materials_not_included", "")),
            "decisions": _lines(est.get("open_decisions", "")), "schedule": schedule, "crew_hours": rt["crew_hours"],
            "inspections": [(i + 1, p["title"], p["inspection"]) for i, p in enumerate(phases) if p["inspection"]],
            "subs": subs, "total_steps": n}


def _norm(step: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", step.lower()).strip()


def library(conn: sqlite3.Connection) -> list[dict]:
    """One entry per kind of job Nick has estimated: what he typically does, in order, with how many times he's done it."""
    groups: "OrderedDict[str, list]" = OrderedDict()
    for j in books.list_jobs(conn):
        est = estimates.get(conn, j["number"])
        if est and est["phases"] and any(p["steps"] for p in est["phases"]):
            groups.setdefault(est["template"] or j["job_type"] or "Other", []).append((j, est))
    out = []
    for kind, items in groups.items():
        phase_order: "OrderedDict[str, dict]" = OrderedDict()
        for _j, est in items:
            for p in est["phases"]:
                key = _norm(p["title"])
                ph = phase_order.setdefault(key, {"title": p["title"], "steps": OrderedDict(), "inspections": Counter(), "jobs": 0})
                ph["jobs"] += 1
                if p.get("inspection"):
                    ph["inspections"][p["inspection"]] += 1
                for s in p["steps"]:
                    ph["steps"].setdefault(_norm(s), [s, 0])[1] += 1
        hours = [rt for _j, e in items if (rt := rates.analyze(e)["crew_hours"])]
        labors = [e["labor"] for _j, e in items if e["labor"]]
        materials = Counter(m.lower() for _j, e in items for m in _lines(e.get("materials_list", "")))
        excluded = Counter(x for _j, e in items for x in _lines(e.get("labor_not_included", "")) + _lines(e.get("materials_not_included", "")))
        out.append({
            "kind": kind, "count": len(items), "jobs": [j for j, _ in items],
            "crew": Counter(e.get("crew", "") for _j, e in items if e.get("crew")).most_common(1)[0][0] if any(e.get("crew") for _j, e in items) else "",
            "duration": [e["duration"] for _j, e in items if e.get("duration")][:1],
            "avg_labor": round(sum(labors) / len(labors)) if labors else None,
            "avg_hours": round(sum(hours) / len(hours)) if hours else None,
            "phases": [{"title": ph["title"], "jobs": ph["jobs"], "inspection": ph["inspections"].most_common(1)[0][0] if ph["inspections"] else "",
                        "steps": [(s, c) for s, c in ph["steps"].values()]} for ph in phase_order.values()],
            "materials": [m for m, _c in materials.most_common(12)], "excluded": [x for x, _c in excluded.most_common(8)],
        })
    return out
