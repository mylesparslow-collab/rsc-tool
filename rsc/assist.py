"""Plain-language helpers for the local model: type or paste a few lines, get the form filled in.

The model drafts and Nick checks. Where the text states a number, the model must use it as written; any number
it had to guess is listed under "assumptions" so it shows up on the page for Nick to confirm. Nothing here
writes anything outside the estimate, job, expense or change order the person asked for.
"""
import re
import sqlite3
from datetime import date

from . import books, brand, estimates, extract, rates
from .mail import Mail

NUM = {"type": "number"}
STR = {"type": "string"}
STRS = {"type": "array", "items": STR}

SCOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "job_type": {"type": "string", "enum": list(estimates.TEMPLATES)},
        "project": STR, "duration": STR, "crew": STR, "materials_list": STRS, "payment_groups": STR,
        "phases": {"type": "array", "items": {"type": "object", "properties": {
            "title": STR, "steps": STRS}, "required": ["title", "steps"]}},
        "labor_not_included": STRS, "materials_not_included": STRS, "open_decisions": STRS,
        "unsure": STRS,
    },
    "required": ["job_type", "project", "duration", "crew", "materials_list", "payment_groups", "phases",
                 "labor_not_included", "materials_not_included", "open_decisions", "unsure"],
}

PRICE_KINDS = ["materials", "labor", "windows_doors", "debris", "hired_labor", "other"]
PRICE_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"type": "object", "properties": {
        "item": STR, "kind": {"type": "string", "enum": PRICE_KINDS}, "amount": NUM, "stated_by_nick": {"type": "boolean"}},
        "required": ["item", "kind", "amount", "stated_by_nick"]}}},
    "required": ["lines"],
}

SCOPE_PROMPT = """You write scopes of work for Reclaimed Space Crafters (RSC), a small design-build remodeling
contractor in Saratoga Springs, NY. The owner, Nick, will read and correct your draft.

Nick's estimates have this shape. "project": two or three sentences saying what is being built or repaired and any
condition that could change it. "phases": 4 to 8 in build order. "materials_list": the materials RSC buys, one line
each, with a quantity when it is known ("interior paint, 2 gallons"). "duration": business days on site, like
"9-11 days on-site. Monday-Friday". "crew": like "1 general contractor, 1 skilled laborer".
"payment_groups": how the phases are grouped into payments, in order, covering every phase once, like "1-3; 4; 5-7"
for 7 phases (3 or 4 payments after the first is typical).
For aging-in-place or accessibility jobs, use job_type "Aging in place: ..." and the correct measurements: grab bars 33-36 in high into solid blocking; doors 32 in clear minimum; ramps 1 in of rise per 12 in of run with 36 in clear width, 5 x 5 ft landings and handrails 34-38 in high; curbless showers slope about 1/4 in per foot to the drain and are fully waterproofed.
Write 4 to 8 phases in build order. Each phase has 2 to 5 short, plain steps like "Frame the new wall" or
"Hang, tape and finish sheetrock". Do not number steps. "duration" is like "5 to 6 weeks".
labor_not_included and materials_not_included: real things this job does NOT cover (for example "Appliances",
"Flooring", "HVAC changes"), one per entry. open_decisions: choices the client still has to make (finishes,
colors, layout). "unsure": facts about THIS job that Nick did not say and you assumed (room size, who supplies the appliances,
which walls move), in plain words, at most 3. Not general risks or advice."""

PRICE_PROMPT = """You price remodeling jobs for Reclaimed Space Crafters (RSC), Saratoga Springs, NY. Nick will check
your numbers, so give real dollar amounts, not zeros. List cost lines. Each line has a kind:
- materials: what RSC pays suppliers for materials (lumber, cabinets, tile, counters, fixtures, paint), before markup
- labor: RSC's price for its own labor on the whole job
- windows_doors: windows and doors, at cost
- debris: dump fee
- hired_labor: subcontractors RSC pays (electrician, plumber)
- other: anything bought up front that does not fit above
RULES: If Nick wrote a dollar amount for something, use it exactly and set stated_by_nick true. Everything else you
must estimate with a realistic upstate New York number and set stated_by_nick false. A remodel always has materials
and labor, so never leave them out. Do not add up the lines yourself. Never return a line with amount 0.

EXAMPLE, for a different job (a 5x8 bathroom redo, Nick said "tile is about $1,800"):
{"lines": [
 {"item": "Tile and setting materials", "kind": "materials", "amount": 1800, "stated_by_nick": true},
 {"item": "Vanity, toilet, faucet and shower fixtures", "kind": "materials", "amount": 2400, "stated_by_nick": false},
 {"item": "Cement board, waterproofing, paint, trim", "kind": "materials", "amount": 900, "stated_by_nick": false},
 {"item": "RSC labor, about 3 weeks", "kind": "labor", "amount": 8500, "stated_by_nick": false},
 {"item": "Plumber for rough-in", "kind": "hired_labor", "amount": 1200, "stated_by_nick": false},
 {"item": "Dump fee", "kind": "debris", "amount": 350, "stated_by_nick": false}]}
Now do the same for the job below.
{past}"""


NICK_REFERENCE = ("- Home repairs (PVC porch trim, bathroom fixtures and drywall, kitchen ceiling, stair refinish), 9 to 11 "
                  "days, crew of 2: labor $8,500, materials $1,780, dump fee $375.\n"
                  "- Deck, walkway and stairs replacement with railing, 15 to 18 days: labor $11,400, materials $5,920, "
                  "dumpster $975.\n"
                  "Labor has run about $750 to $1,050 per day on site.\n"
                  "Price labor so that it works out to at least $65 and ideally $72 per crew-hour (people on the crew x 8 hours x days on site). "
                  "Materials are marked up about 43%.\n"
                  "- Aging-in-place work: grab bars $90-300 each installed, stair handrails $800-1,200, wood ramp $1,400-3,000, "
                  "doorway widening $300-2,500, curbless shower $2,500-9,000, full accessible bathroom $18,000-40,000 locally.")


def _past_jobs(conn: sqlite3.Connection) -> str:
    rows = [NICK_REFERENCE] if brand.is_default() else []   # Nick's own past prices only make sense for Nick
    for j in books.list_jobs(conn):
        est = estimates.get(conn, j["number"])
        if not est or not estimates.totals(est)["total"]:
            continue
        t = estimates.totals(est)
        rows.append(f"- {j['job_type'] or est['template']}: total ${t['total']:,.0f}, labor ${est['labor']:,.0f}, "
                    f"materials at cost ${est['materials']:,.0f}, windows/doors ${est['windows_doors']:,.0f}, "
                    f"{len(est['phases'])} phases")
    if not rows:
        return ""
    return brand.localize("\nRSC's recent estimates, for scale (match their style and price level):\n") + "\n".join(rows if len(rows) <= 6 else rows[:1] + rows[-5:])


def _money(v) -> float:
    try:
        return max(0.0, round(float(v), 2))
    except (TypeError, ValueError):
        return 0.0


def _lines(v) -> str:
    return "\n".join(str(x).strip() for x in (v or []) if str(x).strip())


FILLER = {"materials", "labor", "n/a", "none", "other", "tbd"}


def _list_or_default(items, default: str) -> str:
    """The model sometimes answers a 'not included' list with one bare word; use the template's list then."""
    kept = [str(x).strip() for x in (items or []) if len(str(x).strip()) > 3 and str(x).strip().lower() not in FILLER]
    return "\n".join(kept) if kept else default


def inspection_for(title: str, steps: list[str], is_last: bool) -> str:
    """Inspections follow from the kind of work, so they are decided here and not left to a small model."""
    text = f"{title} {' '.join(steps)}".lower()
    if re.search(r"\bfram", text):
        return "Framing inspection"
    if re.search(r"\brough", text):  # not "walk-through"
        return "Rough-in inspection"
    if re.search(r"\binsulat", text):
        return "Insulation inspection"
    return "Final inspection" if is_last else ""


def _clean_scope(raw: dict) -> dict:
    job_type = raw.get("job_type") if raw.get("job_type") in estimates.TEMPLATES else "Other"
    tpl = estimates.TEMPLATES[job_type]
    phases = []
    for p in raw.get("phases") or []:
        title = re.sub(r"^\s*phase\s*\d+\s*[:.)-]*\s*", "", str(p.get("title", "")), flags=re.I).strip()
        steps = estimates.clean_steps("\n".join(str(x) for x in p.get("steps") or []))
        if title:
            phases.append({"title": title[:80], "steps": steps[:10], "inspection": ""})
    for i, p in enumerate(phases):
        p["inspection"] = inspection_for(p["title"], p["steps"], i == len(phases) - 1)
    if not phases:  # fall back to Nick's template phases rather than saving an empty scope
        phases = [{"title": t, "steps": list(st), "inspection": i} for t, st, i in tpl["phases"]]
    groups = str(raw.get("payment_groups", "") or "").strip()
    if estimates.parse_milestones(groups, len(phases[:12])) is None:
        groups = ""  # an invalid grouping falls back to one payment per phase
    return {"job_type": job_type, "duration": str(raw.get("duration", "")).strip()[:160], "phases": phases[:12],
            "extras": {"project": str(raw.get("project", "") or "").strip()[:900],
                       "crew": str(raw.get("crew", "") or "").strip()[:200],
                       "materials_list": _lines(raw.get("materials_list")), "milestones": groups},
            "texts": {"labor_not_included": _list_or_default(raw.get("labor_not_included"), tpl["labor_not_included"]),
                      "materials_not_included": _list_or_default(raw.get("materials_not_included"), tpl["materials_not_included"]),
                      "open_decisions": _list_or_default(raw.get("open_decisions"), tpl["open_decisions"])},
            "assumptions": [str(a).strip() for a in (raw.get("unsure") or []) if str(a).strip()][:3]}


def _clean_prices(raw: dict) -> dict:
    """Add up the model's cost lines here (models are poor at arithmetic) and say which numbers were guesses."""
    sums = {k: 0.0 for k in ("materials", "windows_doors", "labor", "debris", "hired_labor")}
    others, guesses = [], []
    for line in raw.get("lines") or []:
        amount, kind = _money(line.get("amount")), line.get("kind")
        if not amount:
            continue
        item = str(line.get("item", "")).strip()[:60]
        if kind in sums:
            sums[kind] = round(sums[kind] + amount, 2)
        else:
            others.append({"label": item or "Other item", "amount": amount})
        if not line.get("stated_by_nick"):
            guesses.append(f"{item or kind}: ${amount:,.0f}")
    notes = []
    if guesses:
        notes.append("The assistant estimated these prices. Replace any that are off: " + "; ".join(guesses[:8]) + ".")
    if sums["hired_labor"]:
        notes.append(f"Subcontractors (${sums['hired_labor']:,.0f}) are your cost and are not added to the client's price "
                     "by themselves. Make sure Labor covers them, or say 'add the subs to labor'.")
    if not (sums["materials"] or sums["labor"]):
        notes.append("I couldn't work out prices from that. Tell me some, like 'labor is $9,000 and materials about $6,000'.")
    return {"scalars": sums, "others": others[:3], "assumptions": notes}


def _estimate_as_text(est: dict) -> str:
    out = [f"Job type: {est['template']}", f"Duration: {est['duration']}",
           f"Materials at cost: {est['materials']}", f"Windows and doors: {est['windows_doors']}",
           f"Labor: {est['labor']}", f"Debris: {est['debris']}", f"Hired labor: {est['hired_labor']}"]
    out += [f"Up-front item {o['label']}: {o['amount']}" for o in est["others"]]
    for i, p in enumerate(est["phases"], 1):
        out.append(f"Phase {i}: {p['title']} (inspection: {p['inspection'] or 'none'})")
        out += [f"  - {s}" for s in p["steps"]]
    out += ["Labor not included: " + est["labor_not_included"].replace("\n", "; "),
            "Materials not included: " + est["materials_not_included"].replace("\n", "; "),
            "Open decisions: " + est["open_decisions"].replace("\n", "; ")]
    return "\n".join(out)


def draft_estimate(model, conn: sqlite3.Connection, job: dict, description: str, current: dict | None = None,
                   instruction: str = "") -> dict:
    """Two small questions are easier for a small model than one big one: first the scope, then the prices.
    With `current` and `instruction` it revises the existing estimate instead of starting over."""
    who = (f"Client: {job['first_name']} {job['last_name']}. Address: {job['address'] or 'unknown'}. "
           f"Job type on file: {job['job_type'] or 'unknown'}.")
    revising = bool(current and instruction.strip())
    if revising:
        base = (f"{who}\n\nCURRENT DRAFT:\n{_estimate_as_text(current)}\n\nORIGINAL DESCRIPTION:\n{description}\n\n"
                f"CHANGE REQUESTED BY NICK:\n{instruction.strip()}\n\n")
        scope_user = base + "Return the full scope of work with only that change made. Keep everything else the same."
        price_user = base + ("Return the full list of cost lines for the job as it stands after the change. Keep every "
                             "current price the same unless the change affects it. Use any number Nick states exactly.")
    else:
        base = f"{who}\n\nWHAT NICK TOLD YOU ABOUT THE JOB:\n{description.strip()}"
        scope_user = base
        price_user = base + "\n\nList the cost lines to price this whole job."
    scope = _clean_scope(model.extract(brand.localize(SCOPE_PROMPT), scope_user, SCOPE_SCHEMA))
    steps_text = "\n".join(f"Phase {i}: {p['title']}: " + "; ".join(p["steps"]) for i, p in enumerate(scope["phases"], 1))
    prices = _clean_prices(model.extract(brand.localize(PRICE_PROMPT).replace("{past}", _past_jobs(conn)),
                                         f"{price_user}\n\nSCOPE OF WORK:\n{steps_text}", PRICE_SCHEMA))
    scope["assumptions"] += prices["assumptions"]
    return {**scope, "scalars": prices["scalars"], "others": prices["others"]}


def apply_draft(conn: sqlite3.Connection, job_number: int, draft: dict) -> None:
    """Write a draft into the job's estimate, creating the estimate if there isn't one."""
    est = estimates.get(conn, job_number)
    if not est:
        conn.execute("INSERT INTO estimates (job_number, template, markup_pct) VALUES (?, ?, ?)",
                     (job_number, draft["job_type"], rates.default_markup(conn)))
        conn.commit()
        est = estimates.get(conn, job_number)
    scalars = {**draft["scalars"], "markup_pct": est["markup_pct"], "upfront_pct": est["upfront_pct"],
               "final_pct": est["final_pct"]}
    texts = {**draft["texts"], "duration": draft["duration"] or est["duration"]}
    texts.update({k: v for k, v in draft.get("extras", {}).items() if v})
    estimates.save(conn, job_number, scalars, texts, draft["phases"], draft["others"])
    notes = list(draft["assumptions"])
    notes += rates.analyze(estimates.get(conn, job_number), rates.get_settings(conn))["warnings"]
    conn.execute("UPDATE estimates SET assumptions = ? WHERE job_number = ?", ("\n".join(notes), job_number))
    conn.commit()


# ------------------------------------------------------------------ new job from a few lines
JOB_SCHEMA = {
    "type": "object",
    "properties": {"last_name": STR, "first_name": STR, "phone": STR, "email": STR, "address": STR,
                   "job_type": {"type": "string", "enum": books.JOB_TYPES + [""]}, "notes": STR},
    "required": ["last_name", "first_name", "phone", "email", "address", "job_type", "notes"],
}
JOB_PROMPT = """Pull the client's details out of what Nick typed or pasted (often an email or text from a client).
Use "" for anything not written there. Never guess. last_name and first_name are the CLIENT, never Nick or
Reclaimed Space Crafters. notes: one short sentence about what they want done. Phone as written."""


def parse_job(model, text: str) -> dict:
    raw = model.extract(brand.localize(JOB_PROMPT), text.strip()[:6000], JOB_SCHEMA)
    out = {k: str(raw.get(k, "") or "").strip() for k in JOB_SCHEMA["properties"]}
    if out["job_type"] not in books.JOB_TYPES:
        out["job_type"] = ""
    return out


# ------------------------------------------------------------------ expense from a line or a pasted receipt
def parse_expense(model, conn: sqlite3.Connection, text: str) -> dict:
    """Returns the expense form's fields: date, charge_to, vendor, description, category, amount, plus a note."""
    mail = Mail(message_id="typed", mailbox="", sender="", sender_name="", subject="", received_at=date.today().isoformat(),
                body=text.strip())
    fields = model.extract(extract.system_prompt(conn), mail.text_for_model(), extract.SCHEMA)
    if fields.get("kind") != "expense_receipt" and float(fields.get("total") or 0) > 0:
        fields = {**fields, "kind": "expense_receipt"}
    suggestion = extract.build_suggestion(conn, mail, fields)
    if not suggestion or suggestion.kind != "expense":
        return {}
    d = dict(suggestion.data)
    d["note"] = suggestion.match_note
    return d


# ------------------------------------------------------------------ change order from a sentence
CHANGE_SCHEMA = {
    "type": "object",
    "properties": {"description": STR, "amount": NUM, "direction": {"type": "string", "enum": ["add", "credit"]},
                   "days_added": {"type": "integer"}},
    "required": ["description", "amount", "direction", "days_added"],
}
CHANGE_PROMPT = """Nick is writing up a change order for a client. Turn what he typed into one clear sentence or two
describing the work, written so the client understands it. amount: the dollar figure he stated (positive number);
0 if he gave none. Never invent a price. direction: "credit" only if the change lowers the price. days_added: extra
days if he said so, else 0."""


def parse_change(model, text: str) -> dict:
    raw = model.extract(brand.localize(CHANGE_PROMPT), text.strip()[:3000], CHANGE_SCHEMA)
    amount = _money(raw.get("amount"))
    if raw.get("direction") == "credit":
        amount = -amount
    try:
        days = max(0, int(raw.get("days_added") or 0))
    except (TypeError, ValueError):
        days = 0
    return {"description": str(raw.get("description") or text).strip(), "amount": amount, "days_added": days}


def has_amount(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))
