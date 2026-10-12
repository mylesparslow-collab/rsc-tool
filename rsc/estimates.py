"""Estimate / scope of work in Nick's Whitcomb format, and the payment schedule that comes out of it.

Format: phases, each with numbered steps (numbering runs straight through the whole job) and an inspection
point; fees; "not included" lists; open client decisions; then a separate Payment Schedule.

Payment rule, taken from the Whitcomb job: payment 1 is the schedule hold plus everything bought up front
(materials, windows and doors) plus a slice of labor; then one payment per phase; the last payment is the
final slice of labor plus the debris fee. Defaults are 10% of labor up front and 10% at the end, with the
remaining 80% split evenly across the phases. Whitcomb (8 phases) works out to $17,618, 8 x $1,690, $1,965.
"""
import json
import re
import sqlite3
from datetime import date

from . import books

# Starting points only. Whitcomb's phase names come from the signed SOW; the step lists, and every other
# template, are drafts for Nick to rewrite in the editor.
TEMPLATES: dict[str, dict] = {
    "Addition / Enclosure": {
        "phases": [
            ("Planning & Site Prep", ["Confirm layout and measurements with the client", "Order long-lead materials, windows and door",
                                      "Protect the house and set up the work area"], ""),
            ("Framing & Roof", ["Frame walls and floor", "Frame and sheathe the roof", "Install roof underlayment"],
             "Framing inspection"),
            ("Rough Electrical / Roofing", ["Licensed electrician runs rough-in wiring", "Install roofing, flashing and drip edge"],
             "Rough electrical inspection"),
            ("Windows, Door & Insulation", ["Install windows and door", "Insulate walls and ceiling"], "Insulation inspection"),
            ("Siding", ["Install house wrap", "Install siding, trim and soffits"], ""),
            ("Sheetrock", ["Hang sheetrock", "Tape, mud and sand"], ""),
            ("Paint & Trim", ["Prime and paint walls and ceiling", "Install interior trim and casings"], ""),
            ("Fixtures & Punch List", ["Electrician installs fixtures, outlets and switches", "Walk the job with the client and complete the punch list"],
             "Final inspection"),
        ],
        "labor_not_included": "HVAC\nFlooring\nRailings\nSpecialty lighting\nStaining\nSpecialty wall coverings\n"
                              "Landscaping and plant removal (arranged and paid for by the client)",
        "materials_not_included": "Appliances and furniture\nLight fixtures beyond the basic allowance\nFlooring materials",
        "open_decisions": "",
    },
    "Kitchen": {
        "phases": [
            ("Planning & Demolition", ["Confirm layout, appliances and finishes with the client", "Protect the home", "Demolish old kitchen"], ""),
            ("Rough-In", ["Rough electrical and plumbing changes", "Frame any wall or soffit changes"], "Rough-in inspection"),
            ("Walls & Ceilings", ["Insulate as needed", "Hang, tape and finish sheetrock", "Prime"], ""),
            ("Cabinets & Counters", ["Install cabinets", "Template and install countertops"], ""),
            ("Backsplash, Paint & Trim", ["Install backsplash", "Paint walls and ceiling", "Install trim"], ""),
            ("Fixtures & Punch List", ["Install sink, faucet, lighting and appliances", "Walk the job with the client and complete the punch list"],
             "Final inspection"),
        ],
        "labor_not_included": "Appliances (supplied by the client)\nFlooring\nHVAC changes",
        "materials_not_included": "Appliances\nFlooring materials",
        "open_decisions": "Cabinet style and color\nCountertop material\nBacksplash",
    },
    "Bathroom": {
        "phases": [
            ("Planning & Demolition", ["Confirm layout and finishes with the client", "Protect the home", "Demolish old bathroom"], ""),
            ("Rough-In", ["Rough plumbing and electrical", "Frame any wall changes"], "Rough-in inspection"),
            ("Waterproofing & Tile", ["Hang cement board and waterproof the shower", "Install tile"], ""),
            ("Fixtures & Vanity", ["Install vanity, toilet and shower fixtures", "Install mirror and accessories"], ""),
            ("Paint, Trim & Punch List", ["Paint", "Install trim", "Walk the job with the client and complete the punch list"],
             "Final inspection"),
        ],
        "labor_not_included": "Flooring beyond the bathroom\nHVAC changes",
        "materials_not_included": "Specialty fixtures beyond the basic allowance",
        "open_decisions": "Tile selection\nVanity and fixture finish",
    },
    "Deck / Exterior": {  # phase names are from the Delano deck estimate; the steps are generic drafts
        "phases": [
            ("Field verification, layout, and procurement", ["Measure the deck, walkway, door threshold and finished grades", "Confirm replacement limits and document existing house connections", "Verify spans, footing layout and required approvals before purchasing", "Finalize the takeoff, order materials, and arrange delivery and dumpster"], ""),
            ("Protection and demolition", ["Protect siding, doors, windows, lawn and access routes", "Remove existing railings, stairs, decking and framing", "Load demolition debris and secure the work area"], ""),
            ("Site preparation and footings", ["Set deck elevations and mark support locations", "Verify pier locations, soil suitability and buried utilities", "Install footings and support posts"], ""),
            ("Structural framing", ["Install ledger flashing and house attachment", "Set beams, joists, rim boards and hangers to the verified layout", "Check level, fastening and framing before covering"], "Framing inspection"),
            ("Decking and perimeter finish", ["Sort and select straight boards for exposed surfaces", "Install decking with proper spacing and compatible screws", "Install perimeter trim and fascia", "Treat field-cut ends and remove splinters"], ""),
            ("Stairs", ["Verify total rise and threshold transition", "Cut and install stringers, treads and risers at uniform dimensions"], ""),
            ("Railing", ["Install the railing and check attachment, spacing and finished ends"], ""),
            ("Final inspection and cleanup", ["Check fasteners, posts, rails, stairs and visible connections", "Complete punch-list adjustments and final inspection", "Remove debris and temporary protection", "Walk through the completed work with the client"], "Final inspection"),
        ],
        "labor_not_included": "Staining or sealing\nLandscaping",
        "materials_not_included": "",
        "open_decisions": "Decking material and color",
    },
    "Aging in place: safety fixes": {  # drafts for Nick to adjust; measurements are from accessibility (ADA / ANSI) guidance
        "phases": [
            ("Walk-through and layout", ["Measure doorways, stairs, tub and toilet areas with the client", "Mark grab bar, railing and handle locations with the client", "Locate studs and add solid blocking where bars will go"], ""),
            ("Bathroom safety", ["Install grab bars 33-36 inches high into blocking", "Install comfort-height toilet if included", "Install handheld shower on a slide bar if included"], ""),
            ("Stairs and entries", ["Install continuous handrails on both sides, 34-38 inches high", "Replace round door knobs with lever handles", "Install or repair stair and entry lighting"], "Final walk-through"),
            ("Final check", ["Test every bar and rail with load", "Walk the home with the client and complete the punch list"], ""),
        ],
        "labor_not_included": "Electrical work beyond simple fixture swaps\nStairlift (supplied and installed by a dealer)",
        "materials_not_included": "Specialty fixtures beyond the basic allowance",
        "open_decisions": "Grab bar finish\nWhich stairs get rails",
    },
    "Aging in place: ramp & entry": {
        "phases": [
            ("Layout and permits", ["Measure the total rise from ground to the door threshold", "Lay out the ramp at 1 inch of rise per 12 inches of run, with 5 x 5 foot landings at the top, bottom and any turn", "Confirm permit needs with the town"], ""),
            ("Footings and framing", ["Set footings or piers below frost depth", "Frame the ramp and landings"], "Framing inspection"),
            ("Surface and rails", ["Install slip-resistant decking, 36 inches clear width", "Install handrails 34-38 inches high on both sides with 2 inch edge protection"], ""),
            ("Door transition and final", ["Adjust the threshold so it is no higher than 1/2 inch", "Check slope and landings with a level", "Walk the job with the client and complete the punch list"], "Final inspection"),
        ],
        "labor_not_included": "Staining or sealing\nLandscaping\nPower door openers",
        "materials_not_included": "",
        "open_decisions": "Ramp material (treated wood or composite)\nRail style",
    },
    "Aging in place: accessible bath": {
        "phases": [
            ("Planning and demolition", ["Confirm the layout, door width and turning space with the client", "Protect the home", "Demolish the old tub or shower and flooring"], ""),
            ("Rough-in and framing", ["Widen the doorway to 32 inches clear if planned", "Add solid blocking for every grab bar and seat", "Recess the floor and set the drain for a curbless shower", "Rough plumbing and electrical"], "Rough-in inspection"),
            ("Waterproofing and tile", ["Slope the shower floor about 1/4 inch per foot to the drain", "Waterproof the whole shower floor and walls", "Install slip-resistant tile"], ""),
            ("Fixtures and safety", ["Install the fold-down seat, grab bars and handheld shower", "Install a comfort-height toilet and an accessible vanity", "Install lighting"], ""),
            ("Final", ["Paint and trim", "Walk the job with the client and complete the punch list"], "Final inspection"),
        ],
        "labor_not_included": "Flooring outside the bathroom\nHVAC changes",
        "materials_not_included": "Specialty fixtures beyond the basic allowance",
        "open_decisions": "Shower size and entry style\nTile selection\nSeat and grab bar finish",
    },
    "Aging in place: first-floor suite": {
        "phases": [
            ("Planning and permits", ["Confirm the layout of the bedroom, accessible bathroom and entry with the client", "Order long-lead materials, windows and doors", "Protect the house and set up the work area"], ""),
            ("Framing and rough-in", ["Frame walls, doorways at 36 inches and any floor changes", "Rough electrical, plumbing and heating", "Add blocking for grab bars"], "Framing and rough-in inspections"),
            ("Insulation and drywall", ["Insulate walls and ceiling", "Hang, tape and finish sheetrock"], "Insulation inspection"),
            ("Accessible bathroom", ["Waterproof and tile a curbless shower", "Install grab bars, seat, comfort-height toilet and vanity"], ""),
            ("Floors, paint and trim", ["Install slip-resistant flooring with no thresholds above 1/2 inch", "Prime and paint", "Install trim and lever door hardware"], ""),
            ("Entry and final", ["Build the ramp or zero-step entry with 5 x 5 foot landings", "Walk the job with the client and complete the punch list"], "Final inspection"),
        ],
        "labor_not_included": "HVAC\nAppliances and furniture\nLandscaping",
        "materials_not_included": "Appliances and furniture\nLight fixtures beyond the basic allowance",
        "open_decisions": "Which room becomes the bedroom\nShower size\nFlooring",
    },
    "Other": {
        "phases": [("Phase 1", [], "")],
        "labor_not_included": "",
        "materials_not_included": "",
        "open_decisions": "",
    },
}

SCALARS = ("materials", "markup_pct", "windows_doors", "labor", "debris", "hired_labor", "upfront_pct", "final_pct")
TEXTS = ("duration", "labor_not_included", "materials_not_included", "open_decisions", "project", "materials_list",
         "crew", "labor_note", "milestones")


def _cents(x: float) -> int:
    return int(round(float(x) * 100))


def _row_to_estimate(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["others"] = json.loads(d["others"])
    d["phases"] = json.loads(d["phases"])
    return d


def get(conn: sqlite3.Connection, job_number: int) -> dict | None:
    row = conn.execute("SELECT * FROM estimates WHERE job_number = ?", (job_number,)).fetchone()
    return _row_to_estimate(row) if row else None


def create(conn: sqlite3.Connection, job_number: int, template: str) -> None:
    if not books.get_job(conn, job_number):
        raise books.BooksError(f"No job {job_number}")
    if template not in TEMPLATES:
        raise books.BooksError(f"No template called {template}")
    if get(conn, job_number):
        raise books.BooksError("This job already has an estimate")
    t = TEMPLATES[template]
    phases = [{"title": title, "steps": list(steps), "inspection": insp} for title, steps, insp in t["phases"]]
    from . import rates
    conn.execute("INSERT INTO estimates (job_number, template, phases, labor_not_included, materials_not_included, "
                 "open_decisions, markup_pct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (job_number, template, json.dumps(phases), t["labor_not_included"], t["materials_not_included"],
                  t["open_decisions"], rates.default_markup(conn)))
    conn.commit()


def clean_steps(text: str) -> list[str]:
    """One step per line; a leading '1.' or '12)' that Nick typed is dropped because numbering is automatic."""
    steps = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*\d+\s*[.)]\s*", "", line).strip()
        if line:
            steps.append(line)
    return steps


def save(conn: sqlite3.Connection, job_number: int, scalars: dict, texts: dict, phases: list[dict],
         others: list[dict]) -> None:
    if not get(conn, job_number):
        raise books.BooksError("Start the estimate first")
    values = {}
    for key in SCALARS:
        v = scalars.get(key)
        v = 0.0 if v in (None, "") else float(v)
        if v < 0:
            raise books.BooksError(f"{key.replace('_', ' ')} can't be negative")
        values[key] = v
    for pct in ("markup_pct", "upfront_pct", "final_pct"):
        if values[pct] > 100 and pct != "markup_pct":
            raise books.BooksError("Percentages can't be over 100")
    if values["upfront_pct"] + values["final_pct"] >= 100:
        raise books.BooksError("Up-front % and final % of labor must add to less than 100")
    clean_phases = [{"title": p["title"].strip(), "steps": p["steps"], "inspection": p.get("inspection", "").strip()}
                    for p in phases if p.get("title", "").strip()]
    if not clean_phases:
        raise books.BooksError("An estimate needs at least one phase")
    clean_others = []
    for o in others:
        label, amount = o.get("label", "").strip(), o.get("amount")
        if label or amount not in (None, "", 0):
            amount = float(amount or 0)
            if amount < 0:
                raise books.BooksError("Up-front items can't be negative")
            clean_others.append({"label": label or "Other item", "amount": amount})
    if "milestones" in texts and (texts["milestones"] or "").strip():
        if parse_milestones(texts["milestones"], len(clean_phases)) is None:
            raise books.BooksError("Payment groups must cover every phase in order, like: 1-3; 4; 5-7  "
                                   "(add + dumpster to a group to bill the dump fee with it)")
    cols = {**values, **{k: (texts.get(k) or "").strip() for k in TEXTS if k in texts},
            "phases": json.dumps(clean_phases), "others": json.dumps(clean_others)}
    conn.execute(f"UPDATE estimates SET {', '.join(f'{k} = ?' for k in cols)}, updated_at = datetime('now') "
                 "WHERE job_number = ?", [*cols.values(), job_number])
    conn.commit()


def totals(est: dict) -> dict:
    materials_price = round(est["materials"] * (1 + est["markup_pct"] / 100), 2)
    others_total = round(sum(o["amount"] for o in est["others"]), 2)
    total = round(materials_price + est["windows_doors"] + est["labor"] + est["debris"] + others_total, 2)
    direct_cost = round(est["materials"] + est["windows_doors"] + est["debris"] + others_total + est["hired_labor"], 2)
    return {"materials_price": materials_price, "others_total": others_total, "total": total,
            "direct_cost": direct_cost, "markup": round(materials_price - est["materials"], 2)}


def step_ranges(phases: list[dict]) -> list[tuple[int, int] | None]:
    """Steps are numbered straight through the job, like 'Steps 20-29' in Nick's Whitcomb payment schedule."""
    out, n = [], 0
    for p in phases:
        k = len(p["steps"])
        out.append((n + 1, n + k) if k else None)
        n += k
    return out


def parse_milestones(text: str, n_phases: int) -> list[dict] | None:
    """'1-3; 4; 5-7' -> [{'phases': [1, 2, 3]}, ...]. Add '+ dumpster' to bill the dump fee with that group.
    Returns None unless the groups run in order and cover every phase exactly once."""
    groups = []
    for part in re.split(r"[;\n]+", text or ""):
        part = part.strip()
        if not part:
            continue
        dump = bool(re.search(r"\+\s*(dumpster|debris|dump)", part, re.I))
        part = re.sub(r"\+.*$", "", part).strip()
        m = re.fullmatch(r"(\d+)(?:\s*(?:-|–|—|to|through)\s*(\d+))?", part, re.I)
        if not m:
            return None
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if hi < lo:
            return None
        groups.append({"phases": list(range(lo, hi + 1)), "debris": dump})
    flat = [p for g in groups for p in g["phases"]]
    return groups if groups and flat == list(range(1, n_phases + 1)) else None


def _range_label(nums: list[int]) -> str:
    return f"Phase {nums[0]}" if len(nums) == 1 else f"Phases {nums[0]}\u2013{nums[-1]}"


def _milestone_schedule(est: dict, groups: list[dict]) -> list[dict]:
    """Nick's Hartwell and Delano estimates: labor in equal shares, one share with the first payment and one
    with each group of phases; materials (and anything bought up front) with the first payment; the dump fee
    with the last group, or with the group marked for it."""
    t = totals(est)
    labor_c = _cents(est["labor"])
    n = len(groups) + 1
    per = labor_c // n
    shares = [per] * n
    shares[-1] += labor_c - per * n
    pct = round(per / labor_c * 100, 1) if labor_c else 0
    fixed_c = _cents(t["materials_price"]) + _cents(est["windows_doors"]) + sum(_cents(o["amount"]) for o in est["others"])
    parts = []
    if est["materials"]:
        parts.append("all materials")
    if est["windows_doors"]:
        parts.append("windows & door")
    parts += [o["label"] for o in est["others"] if o["amount"]]
    schedule = []
    first_c = fixed_c + shares[0]
    if first_c:
        what = "Schedule hold" + (" + " + ", ".join(parts) if parts else "")
        if shares[0]:
            what += f" + {pct:g}% of labor"
        schedule.append({"description": what, "due_when": "At acceptance of the estimate", "amount": first_c / 100})
    ranges = step_ranges(est["phases"])
    debris_idx = next((i for i, g in enumerate(groups) if g["debris"]), len(groups) - 1)
    for i, g in enumerate(groups):
        nums = g["phases"]
        steps = [ranges[k - 1] for k in nums if ranges[k - 1]]
        due = f"Upon completion of {_range_label(nums)}"
        if steps:
            lo, hi = steps[0][0], steps[-1][1]
            due += f", Step {lo}" if lo == hi else f", Steps {lo}\u2013{hi}"
        c = shares[i + 1] + (_cents(est["debris"]) if i == debris_idx else 0)
        what = f"{pct:g}% of labor: {_range_label(nums)}" if shares[i + 1] else "Debris / dump fee"
        if shares[i + 1] and i == debris_idx and est["debris"]:
            what += " + debris / dump fee"
        if c:
            schedule.append({"description": what, "due_when": due, "amount": c / 100})
    return schedule


def build_schedule(est: dict) -> list[dict]:
    groups = parse_milestones(est.get("milestones", ""), len(est["phases"]))
    if groups:
        return _milestone_schedule(est, groups)
    t = totals(est)
    labor_c = _cents(est["labor"])
    up_c = round(labor_c * est["upfront_pct"] / 100)
    fin_c = round(labor_c * est["final_pct"] / 100)
    mid_c = labor_c - up_c - fin_c
    phases = est["phases"]
    n = len(phases)
    per = mid_c // n
    shares = [per] * n
    shares[-1] += mid_c - per * n

    fixed_c = _cents(t["materials_price"]) + _cents(est["windows_doors"]) + sum(_cents(o["amount"]) for o in est["others"])
    parts = []
    if est["materials"]:
        parts.append("all materials")
    if est["windows_doors"]:
        parts.append("windows & door")
    parts += [o["label"] for o in est["others"] if o["amount"]]
    schedule = []
    first_c = fixed_c + up_c
    if first_c:
        what = "Schedule hold"
        if parts:
            what += " + " + ", ".join(parts)
        if up_c:
            what += f" + {est['upfront_pct']:g}% of labor"
        schedule.append({"description": what, "due_when": "At contract signing", "amount": first_c / 100})
    ranges = step_ranges(phases)
    for i, (p, c, rng) in enumerate(zip(phases, shares, ranges), start=1):
        pct = round(c / labor_c * 100, 1) if labor_c else 0
        due = f"Upon completion of Phase {i} ({p['title']})"
        if rng:
            due += f", Step {rng[0]}" if rng[0] == rng[1] else f", Steps {rng[0]}–{rng[1]}"
        if c:
            schedule.append({"description": f"{pct:g}% of labor: Phase {i}, {p['title']}", "due_when": due, "amount": c / 100})
    last_c = fin_c + _cents(est["debris"])
    if last_c:
        what = f"Final {est['final_pct']:g}% of labor" if fin_c else "Debris / dump fee"
        if fin_c and est["debris"]:
            what += " + debris / dump fee"
        schedule.append({"description": what, "due_when": "At final walkthrough and sign-off", "amount": last_c / 100})
    return schedule


def generate_schedule(conn: sqlite3.Connection, job_number: int) -> int:
    """Replace the job's generated payments with the schedule from its estimate and set the contract total."""
    est = get(conn, job_number)
    if not est:
        raise books.BooksError("Start the estimate first")
    total = totals(est)["total"]
    if total <= 0:
        raise books.BooksError("Enter prices first. The estimate total is $0.")
    existing = books.list_payments(conn, job_number)
    if any(p["kind"] != "schedule" for p in existing):
        raise books.BooksError("This job already has other payments or change orders. Add changes as a change order instead.")
    if any(p["invoice_sent"] or p["date_paid"] or p["amount_paid"] for p in existing):
        raise books.BooksError("Some payments are already invoiced or paid, so the schedule can't be rebuilt.")
    schedule = build_schedule(est)
    if round(sum(s["amount"] for s in schedule), 2) != total:
        raise books.BooksError("The payments don't add up to the total. Check the percentages.")
    try:
        conn.execute("DELETE FROM payments WHERE job_number = ? AND kind = 'schedule'", (job_number,))
        for s in schedule:
            books.add_payment(conn, job_number, s["amount"], s["description"], s["due_when"], kind="schedule", commit=False)
        conn.execute("UPDATE jobs SET contract_total = ? WHERE number = ?", (total, job_number))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(schedule)


def approve(conn: sqlite3.Connection, job_number: int, when: str | None = None) -> int:
    """The client signed: build the payments, set the contract total, mark the job Signed."""
    count = generate_schedule(conn, job_number)
    books.update_job(conn, job_number, status="Signed", contract_signed=when or date.today().isoformat())
    return count


def bump_version(conn: sqlite3.Connection, job_number: int) -> None:
    """A revised estimate goes to the client as the next version, dated today."""
    conn.execute("UPDATE estimates SET version = version + 1, version_date = ? WHERE job_number = ?",
                 (date.today().isoformat(), job_number))
    conn.commit()


def import_estimate(conn: sqlite3.Connection, data: dict) -> int:
    """Load a job and its estimate from a JSON file (see examples/). Returns the new job number."""
    job = dict(data["job"])
    number = books.create_job(conn, job.pop("last_name"), **job)
    e = data["estimate"]
    conn.execute("INSERT INTO estimates (job_number, template) VALUES (?, ?)", (number, e.get("template", "Other")))
    conn.commit()
    save(conn, number, {k: e.get(k, 0) for k in SCALARS if k in e} | {"upfront_pct": e.get("upfront_pct", 10),
                                                                       "final_pct": e.get("final_pct", 10)},
         {k: e[k] for k in TEXTS if k in e}, e["phases"], e.get("others", []))
    conn.execute("UPDATE estimates SET version = ?, version_date = ? WHERE job_number = ?",
                 (e.get("version", 1), e.get("version_date", ""), number))
    conn.commit()
    return number
