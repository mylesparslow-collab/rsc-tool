"""A rough price range and site-visit questions for a new lead, from their words and any photo they sent.

For Nick only. It is never put in the reply to the homeowner, and it is not a quote: it tells him roughly what size of
job this is before he drives out, and what to look at and ask while he is there.

The model only reads: it says what kind of job this is, how big it looks, and what to ask. The dollars are worked out
here in code, from crew-hours and materials at the rates on the Pricing page ($65-72 a crew-hour and the materials
markup by default):

    low  = fewest crew-hours x floor rate  + least materials x (1 + markup)
    high = most crew-hours   x target rate + most materials  x (1 + markup)

Once Nick has two or more past estimates of the same kind (with crew and days filled in), those jobs' crew-hours and
materials are repriced the same way and used instead of the starting figures below. The starting figures are drafts
for Myles and Nick to adjust; they are not from Nick's books.
"""
import json
import math
import re
import sqlite3

from . import estimates, rates

# kind: label, estimate template (for matching past jobs; None when the template is shared), job type on the job page,
# words that point to it, and (crew-hours low, high, materials low, high) by size.
KINDS: dict[str, dict] = {
    "bathroom": {"label": "bathroom", "template": "Bathroom", "job_type": "Bathroom",
                 "words": r"bath|shower|tub|vanity|toilet",
                 "sizes": {"small": (50, 110, 2000, 5000), "medium": (130, 220, 5000, 11000), "large": (220, 330, 11000, 20000)}},
    "kitchen": {"label": "kitchen", "template": "Kitchen", "job_type": "Kitchen",
                "words": r"kitchen|cabinet|counter ?top|backsplash",
                "sizes": {"small": (100, 200, 6000, 14000), "medium": (220, 380, 15000, 30000), "large": (380, 560, 30000, 55000)}},
    "enclosure": {"label": "porch enclosure or addition", "template": "Addition / Enclosure", "job_type": "Addition / Enclosure",
                  "words": r"enclos|four[- ]season|3[- ]season|three[- ]season|sun ?room|screen(ed)? porch|addition|mudroom",
                  "sizes": {"small": (150, 260, 7000, 15000), "medium": (260, 420, 15000, 30000), "large": (420, 640, 30000, 55000)}},
    "deck": {"label": "deck or porch", "template": "Deck / Exterior", "job_type": "Deck / Exterior",
             "words": r"deck|porch|patio|pergola|railing|outdoor (steps|stairs)|bulkhead",
             "sizes": {"small": (30, 70, 1500, 4000), "medium": (90, 170, 5000, 12000), "large": (170, 300, 12000, 25000)}},
    "safety": {"label": "safety fixes (grab bars, rails)", "template": "Aging in place: safety fixes", "job_type": "Aging in place",
               "words": r"grab bar|handrail|hand rail|lever|fell|falling|walker|aging|elderly|safety",
               "sizes": {"small": (6, 16, 150, 600), "medium": (16, 48, 600, 2500), "large": (48, 110, 2500, 7000)}},
    "ramp": {"label": "ramp or safer entry", "template": "Aging in place: ramp & entry", "job_type": "Aging in place",
             "words": r"ramp|wheelchair|zero[- ]step",
             "sizes": {"small": (30, 70, 1200, 3000), "medium": (70, 130, 3000, 6000), "large": (130, 210, 6000, 10000)}},
    "builtins": {"label": "built-ins, trim or restoration", "template": None, "job_type": "Carpentry / Repair",
                 "words": r"built[- ]in|bookcase|bookshelf|shelv|trim|molding|moulding|wainscot|mantel|restor|staircase|banister",
                 "sizes": {"small": (12, 36, 300, 1500), "medium": (36, 110, 1500, 6000), "large": (110, 240, 6000, 15000)}},
    "repair": {"label": "repair or small project", "template": None, "job_type": "Carpentry / Repair",
               "words": r"repair|fix|rot|leak|replace|door|window|sill|stair|floor|drywall|siding",
               "sizes": {"small": (6, 20, 100, 600), "medium": (20, 70, 600, 3000), "large": (70, 180, 3000, 10000)}},
}
# a few words that settle it before the list above is tried in order
OVERRIDES = [(r"walk[- ]in shower|curbless|accessible (bath|shower)|tub[- ]to[- ]shower", "bathroom"),
             (r"grab bar", "safety"), (r"ramp", "ramp"), (r"porch enclos|enclose (the|our|a) porch", "enclosure")]
SIZE_WORDS = {"small": r"\b(small|minor|quick|little|simple|a few|couple of|single|patch|just)\b",
              "large": r"\b(whole|entire|gut|gutted|complete|large|big|from scratch|expand|move (the )?walls?)\b"}
SIZE_LABEL = {"small": "on the small side", "medium": "typical size", "large": "on the large side"}

QUESTIONS = {
    "bathroom": ["Keep the tub, or switch to a walk-in shower?", "Same layout, or moving the toilet, sink or shower?",
                 "Look for soft floor or old leaks around the tub and toilet.", "Is there a working exhaust fan vented outside?",
                 "Tile, vanity and fixtures: have they picked anything, and what budget?", "Is this the only bathroom in the house?"],
    "kitchen": ["Same layout, or moving the sink, range or walls?", "New cabinets, or keep and refinish the boxes?",
                "Countertop material they have in mind?", "Look at the electrical panel: room for new circuits?",
                "Are appliances new, reused, or theirs to buy?", "What budget range do they have in mind?"],
    "enclosure": ["Three-season or heated four-season room?", "Is the existing porch floor, roof and footing sound enough to build on?",
                  "Measure the opening sizes for windows and doors.", "Heat, electrical and lighting wanted?",
                  "Permit needed: check with the town before pricing.", "What budget range do they have in mind?"],
    "deck": ["Measure the deck and its height off the ground.", "Repair, resurface, or full rebuild? Check the framing and ledger.",
             "Wood or composite decking?", "Stairs and railings included? Count the steps.", "Is a permit needed for the size and height?"],
    "safety": ["Who is it for, and what do they struggle with most?", "Which rooms: bathroom, stairs, entry?",
               "Check the walls for studs or blocking where bars and rails go.", "Rails on both sides of the stairs?",
               "Any other small fixes they'd like while you're there?"],
    "ramp": ["Measure the total rise from the ground to the door threshold.", "Is there room for the run (1 foot per inch of rise) and landings?",
             "Wheelchair, walker, or easier steps?", "Wood or composite?", "Permit needed: check with the town."],
    "builtins": ["Measure the wall or opening.", "Paint-grade or stain-grade wood?", "Match existing trim or a new style?",
                 "Doors, drawers, or open shelves?", "Any lighting or outlets in the built-in?"],
    "repair": ["How long has it been like this, and has anyone looked at it before?", "Check for hidden damage (rot, water, soft spots) around it.",
               "Anything else on their list while you're there?", "Is this part of a bigger project later?"],
}
QUESTIONS_DEFAULT = ["What would they like done, room by room?", "Measure the space.", "When would they like it done?",
                     "What budget range do they have in mind?"]
MAX_QUESTIONS = 6
ROUND_TO = 500

SCHEMA = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": list(KINDS)},
    "size": {"type": "string", "enum": ["small", "medium", "large"]},
    "questions": {"type": "array", "items": {"type": "string"}}},
    "required": ["kind", "size", "questions"]}
PROMPT = """You help a small remodeling contractor get ready to visit a homeowner who asked for a quote.
From what they wrote (and notes on any photo), pick the kind of job, how big it looks, and list up to 5 short questions
the contractor should ask or things to check on site that would change the price. Kinds: {kinds}.
Size: small, medium or large for that kind of job. Do not give prices. One short sentence per question."""
PHOTO_SCHEMA = {"type": "object", "properties": {"shows": {"type": "string"}}, "required": ["shows"]}
PHOTO_PROMPT = """A homeowner sent this photo with a request for a remodeling quote. In one or two plain sentences, say what
the photo shows that matters for the job: the room or area, its condition, rough size, and anything that looks damaged."""


def guess_kind(text: str) -> str:
    low = (text or "").lower()
    for pattern, kind in OVERRIDES:
        if re.search(pattern, low):
            return kind
    return next((k for k, v in KINDS.items() if re.search(v["words"], low)), "repair")


def guess_size(text: str) -> str:
    low = (text or "").lower()
    if re.search(SIZE_WORDS["large"], low):
        return "large"
    if re.search(SIZE_WORDS["small"], low):
        return "small"
    return "medium"


def _round_down(x: float) -> int:
    return int(math.floor(x / ROUND_TO) * ROUND_TO)


def _round_up(x: float) -> int:
    return int(math.ceil(x / ROUND_TO) * ROUND_TO)


def _price(s: dict, hours: tuple[float, float], materials: tuple[float, float], fixed: tuple[float, float] = (0, 0)) -> tuple[int, int]:
    markup = 1 + s["default_markup"] / 100
    low = hours[0] * s["floor_rate"] + materials[0] * markup + fixed[0]
    high = hours[1] * s["target_rate"] + materials[1] * markup + fixed[1]
    low, high = max(low, s["job_minimum"]), max(high, s["job_minimum"])
    return _round_down(low), _round_up(high)


def past_jobs(conn: sqlite3.Connection, kind: str) -> list[dict]:
    """Nick's past estimates of this kind that say how many people and days, repriced at the Pricing page rates."""
    template = KINDS[kind]["template"]
    if not template:
        return []
    s, out = rates.get_settings(conn), []
    for (number,) in conn.execute("SELECT job_number FROM estimates WHERE template = ?", (template,)).fetchall():
        est = estimates.get(conn, number)
        a = rates.analyze(est, s) if est else None
        if not a or not a["crew_hours"]:
            continue
        t = estimates.totals(est)
        fixed = est["windows_doors"] + est["debris"] + t["others_total"]
        low, high = _price(s, (a["crew_hours"],) * 2, (est["materials"],) * 2, (fixed, fixed))
        out.append({"job_number": number, "crew_hours": a["crew_hours"], "was": t["total"], "low": low, "high": high})
    return out


def price_range(conn: sqlite3.Connection, kind: str, size: str) -> dict:
    s = rates.get_settings(conn)
    past = past_jobs(conn, kind)
    rate_words = f"${s['floor_rate']:.0f}-{s['target_rate']:.0f} a crew-hour and {s['default_markup']:g}% on materials"
    if len(past) >= 2:
        low, high = min(p["low"] for p in past), max(p["high"] for p in past)
        basis = (f"Your {len(past)} past {KINDS[kind]['label']} estimates ({min(p['crew_hours'] for p in past):.0f}-"
                 f"{max(p['crew_hours'] for p in past):.0f} crew-hours), repriced at {rate_words}.")
    else:
        h_lo, h_hi, m_lo, m_hi = KINDS[kind]["sizes"][size]
        low, high = _price(s, (h_lo, h_hi), (m_lo, m_hi))
        basis = (f"A {SIZE_LABEL[size]} {KINDS[kind]['label']}: about {h_lo}-{h_hi} crew-hours and ${m_lo:,}-${m_hi:,} in materials, "
                 f"at {rate_words}. Starting figures, not from your past jobs yet.")
    return {"low": low, "high": high, "basis": basis, "past_jobs": len(past)}


def _clean_questions(raw) -> list[str]:
    out = []
    for q in raw if isinstance(raw, list) else []:
        q = re.sub(r"\s+", " ", str(q)).strip(" -*•\t")
        if 8 <= len(q) <= 200 and not re.search(r"\$\s?\d", q) and q.lower() not in {x.lower() for x in out}:
            out.append(q)
    return out


def draft(model, conn: sqlite3.Connection, lead: dict, images: list[bytes] | None = None, vision=None) -> dict:
    """The rough range and questions for a lead. Works with the model off (plain word matching and standard questions)."""
    words = (lead.get("project") or "").strip()  # not the address: "12 Bath St" is not a bathroom
    seen = ""
    if images and vision is not None:
        try:
            seen = str(vision.extract(PHOTO_PROMPT, f"The homeowner wrote: {words}", PHOTO_SCHEMA,
                                      images=images[:3]).get("shows") or "").strip()[:400]
        except Exception:
            seen = ""
    kind, size, asked = guess_kind(f"{words} {seen}"), guess_size(words), []
    try:
        user = f"The homeowner wrote: {words}" + (f"\nTheir photo shows: {seen}" if seen else "")
        found = model.extract(PROMPT.format(kinds=", ".join(f"{k} ({v['label']})" for k, v in KINDS.items())), user, SCHEMA)
        if found.get("kind") in KINDS:
            kind = found["kind"]
        if found.get("size") in SIZE_LABEL:
            size = found["size"]
        asked = _clean_questions(found.get("questions"))
    except Exception:
        pass
    questions = asked[:MAX_QUESTIONS]
    for q in QUESTIONS.get(kind, QUESTIONS_DEFAULT):
        if len(questions) >= MAX_QUESTIONS:
            break
        if q.lower() not in {x.lower() for x in questions}:
            questions.append(q)
    out = {"kind": kind, "label": KINDS[kind]["label"], "size": size, "job_type": KINDS[kind]["job_type"],
           "photo": seen, "questions": questions, "photos": len(images or [])}
    out.update(price_range(conn, kind, size))
    return out


def for_job(conn: sqlite3.Connection, job_number: int) -> dict | None:
    """The rough range saved with the lead that started this job, if there was one."""
    row = conn.execute("SELECT data FROM suggestions WHERE kind = 'lead' AND status = 'approved' "
                       "AND json_extract(data, '$.job_number') = ? AND json_extract(data, '$.ballpark') IS NOT NULL "
                       "ORDER BY id DESC LIMIT 1", (job_number,)).fetchone()
    return json.loads(row[0])["ballpark"] if row else None
