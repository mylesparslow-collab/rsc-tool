"""Aging-in-place and accessibility jobs: the standard measurements, price ranges, and a written home safety assessment.

Nick has not done much accessibility work yet, so this is built to keep him safe and consistent: the measurements below
are the common ADA / ANSI A117.1 figures that accessibility training teaches (CAPS course material). Local code and the
specific client's needs decide the final numbers, so every printed assessment says to confirm with the inspector.

The model only listens: it turns Nick's walk-through notes ("two grab bars at the tub, railing on the front steps, kitchen
door is 28 inches") into catalog items. Every price comes from the table below (the national ranges in the aging-in-place
research report, from Fixr), never from the model.
"""
import json
import re
import sqlite3

DIMENSIONS = """ACCESSIBILITY MEASUREMENTS (confirm with the local code official and the client's therapist):
- Grab bars: centered 33-36 in above the floor, 1.25-2 in diameter, 1.5 in clearance to the wall, blocked into studs or solid blocking, rated 250 lb.
- Doors: 32 in minimum clear opening (36 in door preferred); lever handles; threshold no higher than 1/2 in.
- Ramps: 1 in of rise per 12 in of run at most (1:12), 36 in minimum clear width, level 5 ft x 5 ft landing at top, bottom and at every door, handrails 34-38 in high on both sides over 6 in of rise, 2 in edge protection.
- Stair handrails: both sides, 34-38 in high, continuous, graspable (1.25-2 in round), extending 12 in past the top step.
- Toilet: comfort height seat 17-19 in; grab bar behind and beside; 60 in turning circle in the bathroom where possible.
- Showers: curbless or 1/2 in maximum threshold; slope to drain about 1/4 in per foot; full waterproofing; fold-down seat 17-19 in; handheld shower on a slide bar; slip-resistant floor.
- Hallways 36 in wide minimum, 42 in preferred; lighting with no dark stairs or thresholds."""

# key: (label, unit, low, high, note). Prices are the national ranges from the aging-in-place report.
CATALOG = {
    "grab_bar": ("Grab bar, installed and blocked", "each", 90, 300, "Centered 33-36 in high; fastened into solid blocking, not drywall anchors."),
    "lever_handles": ("Lever door handles, whole house", "whole house", 350, 800, "Replace round knobs; easier for arthritic hands."),
    "comfort_toilet": ("Comfort-height toilet", "each", 400, 1600, "17-19 in seat height; a plumbing sub may be needed."),
    "door_widen": ("Widen a doorway to 32+ in clear", "per door", 300, 2500, "Check for wiring, plumbing and load-bearing framing before opening."),
    "handrail": ("Stair handrails, both sides", "per staircase", 800, 1200, "34-38 in high, continuous, ends returned to the wall."),
    "ramp": ("Wood ramp (1:12 slope) with landings and rails", "per ramp", 1400, 3000, "Every 1 in of rise needs 12 in of run; long ramps cost more."),
    "curbless_shower": ("Curbless (roll-in) shower", "each", 2500, 9000, "Needs a recessed floor, slope to a drain and full waterproofing; training or an experienced tile sub first."),
    "nonslip_floor": ("Non-slip bathroom flooring", "each room", 4500, 8000, "Bundles with the shower."),
    "stairlift_prep": ("Stairlift: handrail and electrical prep (dealer supplies the lift)", "each", 0, 0, "Price on site; the dealer quotes the lift."),
    "lighting": ("Night lighting and brighter stair/entry lights", "each area", 0, 0, "Price on site."),
}
FEE_RANGE = (150, 250)
FEE_CREDIT_OVER = 2500

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "key": {"type": "string", "enum": list(CATALOG)}, "qty": {"type": "number"}, "where": {"type": "string"}},
        "required": ["key", "qty", "where"]}},
        "concerns": {"type": "array", "items": {"type": "string"}}},
    "required": ["items", "concerns"],
}
PROMPT = ("A contractor walked through a client's home and made notes about what would make it safer and easier to live in. "
          "For each fix the notes call for, pick the matching key from the list and give a quantity and where it goes "
          "(like 'tub wall' or 'front steps'). Only include things the notes mention or clearly imply. In concerns, list "
          "up to 4 safety problems the notes mention that no key covers (for example a narrow hallway or loose carpet), "
          "in plain words. Never invent measurements.\nKeys: " + "; ".join(f"{k} = {v[0]}" for k, v in CATALOG.items()))

_KEYWORDS = [("grab", "grab_bar"), ("ramp", "ramp"), ("railing", "handrail"), ("handrail", "handrail"), ("lever", "lever_handles"),
             ("toilet", "comfort_toilet"), ("curbless", "curbless_shower"), ("roll-in", "curbless_shower"),
             ("shower", "curbless_shower"), ("floor", "nonslip_floor"), ("stairlift", "stairlift_prep"),
             ("stair lift", "stairlift_prep"), ("light", "lighting"), ("door", "door_widen")]
_WORDS = {"one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _fallback(notes: str) -> dict:
    items = []
    for part in re.split(r"[.;,\n]+|\band\b", notes.lower()):
        if re.search(r"\b(fine|ok|okay|good|already|no problem|curtain)\b", part):
            continue   # something that's already fine isn't a fix
        w = re.search(r"(\d+)\s*(?:inch|in\b|\")", part)
        if "door" in part and w and int(w.group(1)) >= 32:
            continue   # 32 in or wider is already wide enough
        for word, key in _KEYWORDS:
            if re.search(r"\b" + re.escape(word), part):
                m = re.search(r"\b(\d+(?!\s*(?:\"|in\b|inch|ft\b|feet|foot|')|\d)|one|two|three|four|five|six)\b", part)
                qty = 1
                if m:
                    qty = int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1)]
                if qty <= 12 and not any(i["key"] == key for i in items):
                    items.append({"key": key, "qty": qty, "where": part.strip()[:60]})
                break
    return {"items": items, "concerns": []}


def read_notes(model, notes: str) -> dict:
    raw = None
    if model is not None:
        try:
            raw = model.extract(PROMPT, notes, SCHEMA)
        except Exception:
            raw = None
    if not raw or not raw.get("items"):
        raw = _fallback(notes)
    items, seen = [], set()
    for it in raw.get("items", []):
        key = it.get("key")
        if key not in CATALOG:
            continue
        try:
            qty = int(round(float(it.get("qty") or 1)))
        except (TypeError, ValueError):
            qty = 1
        qty = min(max(qty, 1), 20)
        where = str(it.get("where", ""))[:60]
        if (key, where) in seen:
            continue
        seen.add((key, where))
        items.append({"key": key, "qty": qty, "where": where})
    concerns = [str(c)[:140] for c in raw.get("concerns", []) if str(c).strip()][:4]
    return {"items": items, "concerns": concerns}


def price(items: list[dict]) -> dict:
    rows, low, high, open_price = [], 0, 0, False
    for it in items:
        label, unit, lo, hi, note = CATALOG[it["key"]]
        rows.append({**it, "label": label, "unit": unit, "low": lo * it["qty"], "high": hi * it["qty"], "note": note,
                     "priced": hi > 0})
        low += lo * it["qty"]
        high += hi * it["qty"]
        open_price |= hi == 0
    return {"rows": rows, "low": low, "high": high, "has_open_price": open_price,
            "fee_credited": high > FEE_CREDIT_OVER}


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_number INTEGER NOT NULL REFERENCES jobs(number),
        notes TEXT NOT NULL, items TEXT NOT NULL, concerns TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""")


def save(conn: sqlite3.Connection, job_number: int, notes: str, parsed: dict) -> int:
    ensure_table(conn)
    cur = conn.execute("INSERT INTO assessments (job_number, notes, items, concerns) VALUES (?, ?, ?, ?)",
                       (job_number, notes, json.dumps(parsed["items"]), json.dumps(parsed["concerns"])))
    conn.commit()
    return cur.lastrowid


def latest(conn: sqlite3.Connection, job_number: int) -> dict | None:
    ensure_table(conn)
    r = conn.execute("SELECT * FROM assessments WHERE job_number = ? ORDER BY id DESC LIMIT 1", (job_number,)).fetchone()
    if not r:
        return None
    items = json.loads(r["items"])
    return {"id": r["id"], "notes": r["notes"], "items": items, "concerns": json.loads(r["concerns"]),
            "created": r["created_at"][:10], "priced": price(items)}


# ---------------------------------------------------------------- room-by-room checklist
# (id, what Nick sees, catalog key, quantity)
CHECKLIST = [
    ("Entry", [("entry_steps", "Steps up to the entry door, no ramp", "ramp", 1),
               ("entry_rail", "No handrail at the entry steps", "handrail", 1),
               ("entry_door", "Entry door under 32 in clear", "door_widen", 1),
               ("entry_light", "Entry is dark at night", "lighting", 1)]),
    ("Stairs and halls", [("stair_rail", "Stairs missing a rail on one or both sides", "handrail", 1),
                          ("stair_light", "Stairs or hall are dim", "lighting", 1),
                          ("halls_doors", "Interior doorways under 32 in", "door_widen", 1),
                          ("knobs", "Round door knobs", "lever_handles", 1)]),
    ("Bathroom", [("bath_bars_tub", "No grab bars at the tub or shower", "grab_bar", 2),
                  ("bath_bar_toilet", "No grab bar at the toilet", "grab_bar", 1),
                  ("bath_toilet", "Low toilet (under 17 in)", "comfort_toilet", 1),
                  ("bath_tub", "Tub is hard to step into", "curbless_shower", 1),
                  ("bath_floor", "Slippery floor", "nonslip_floor", 1),
                  ("bath_door", "Bathroom door under 32 in", "door_widen", 1)]),
    ("Bedroom and kitchen", [("bed_light", "Poor lighting or no night light on the way to the bathroom", "lighting", 1),
                             ("bed_door", "Bedroom door under 32 in", "door_widen", 1)]),
]
ROOMS = [r for r, _ in CHECKLIST]
CHECK_INDEX = {i: (room, label, key, qty) for room, items in CHECKLIST for i, label, key, qty in items}


def from_checks(checked: list[str]) -> list[dict]:
    items = []
    for cid in checked:
        if cid in CHECK_INDEX:
            room, _label, key, qty = CHECK_INDEX[cid]
            where = room
            existing = next((i for i in items if i["key"] == key and i["where"] == where), None)
            if existing:
                existing["qty"] += qty
            else:
                items.append({"key": key, "qty": qty, "where": where})
    return items


def merge(*lists: list[dict]) -> list[dict]:
    out: list[dict] = []
    for lst in lists:
        for it in lst:
            hit = next((o for o in out if o["key"] == it["key"] and o["where"].lower() == it["where"].lower()), None)
            if hit:
                hit["qty"] = min(20, max(hit["qty"], it["qty"]))
            else:
                out.append(dict(it))
    return out


def ensure_photo_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS assessment_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_number INTEGER NOT NULL REFERENCES jobs(number),
        room TEXT NOT NULL, mime TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))""")


def add_photo(conn: sqlite3.Connection, job_number: int, room: str, mime: str, data: bytes) -> int:
    ensure_photo_table(conn)
    if room not in ROOMS:
        room = "Other"
    cur = conn.execute("INSERT INTO assessment_photos (job_number, room, mime, data) VALUES (?, ?, ?, ?)", (job_number, room, mime, data))
    conn.commit()
    return cur.lastrowid


def photos(conn: sqlite3.Connection, job_number: int) -> list[dict]:
    ensure_photo_table(conn)
    return [dict(r) for r in conn.execute("SELECT id, room FROM assessment_photos WHERE job_number = ? ORDER BY id", (job_number,))]


def photo_file(conn: sqlite3.Connection, job_number: int, photo_id: int):
    ensure_photo_table(conn)
    r = conn.execute("SELECT mime, data FROM assessment_photos WHERE id = ? AND job_number = ?", (photo_id, job_number)).fetchone()
    return (r["mime"], bytes(r["data"])) if r else None


def delete_photo(conn: sqlite3.Connection, job_number: int, photo_id: int) -> None:
    ensure_photo_table(conn)
    conn.execute("DELETE FROM assessment_photos WHERE id = ? AND job_number = ?", (photo_id, job_number))
    conn.commit()
