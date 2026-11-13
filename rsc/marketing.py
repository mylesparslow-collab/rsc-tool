"""Marketing: social post drafts from real jobs, and a checklist of the business's online listings.

Nick types or speaks one line about a job ("finished the Wilton bathroom, walk-in shower, new tile"). The model drafts
a TikTok caption, a Facebook post and a Nextdoor post. Code then removes anything that must never be posted: the
client's name, a street address, phone numbers, emails, prices, and claims the business hasn't confirmed (licensed,
insured, warranties, years in business). If the model is off or drops the facts, a plain template is used.
Nothing is posted from here: Nick copies a draft into the app he posts from and presses "Posted" when it's up.

The listings checklist is a list of where the business shows up online (website, Yelp, Houzz, Google...) with the link
and what still needs fixing. The app never visits those sites; it only keeps the list.
"""
import re
import sqlite3
from datetime import date

from . import books, brand, prefs

# Where the business shows up online, with what was known when this was written (2026-10-29). Nick's edits on the
# Marketing page are stored in the database and win over these.
LISTINGS = [
    ("website", "Website", "https://rscbuilds.com", ""),
    ("google", "Google Business Profile", "",
     "Not set up yet. Waits for the business name and LLC, then create it under that exact name."),
    ("yelp", "Yelp", "https://www.yelp.com/biz/refined-space-crafters-saratoga-springs",
     "Hide the home address (you go to customers). Add your hours, the website, and the towns you work in."),
    ("houzz", "Houzz", "https://www.houzz.com/professionals/general-contractors/refined-space-crafters-pfvwus-pf~1862971900",
     "Hide the home address. Says 13 years in business "
     "but Yelp says 12: make them match."),
    ("nextdoor", "Nextdoor", "https://nextdoor.com/pages/reclaimed-space-crafters-saratoga-springs-ny/",
     "Still under the old name. Rename it once the new name is settled."),
    ("tiktok", "TikTok", "https://www.tiktok.com/@rscrafters", ""),
    ("facebook", "Facebook and Instagram", "", "Not set up yet. Needed before posting there."),
    ("email", "Business email", "", "nick@rscbuilds.com (GoDaddy). Use it on every listing."),
]
SCHEDULE_DEFAULT = "TikTok every day: weekdays at 6:30 PM, weekends at 10 AM (queued ahead in Buffer)."

SCHEMA = {"type": "object", "properties": {"tiktok": {"type": "string"}, "facebook": {"type": "string"},
                                           "nextdoor": {"type": "string"}},
          "required": ["tiktok", "facebook", "nextdoor"]}
PROMPT = """You write short social media posts for {biz}, a design-build remodeling business in {region}.
Use only the facts given. Plain, friendly words, like a tradesman talking. No prices, no client names, no street
addresses, no phone numbers, no claims about licenses, insurance, warranties or years in business. Mention the town
only if it is given. Return JSON with three posts:
- tiktok: one or two short lines for under a video, no hashtags.
- facebook: 2 to 4 sentences about the work and what the homeowner wanted.
- nextdoor: 2 to 3 neighborly sentences, as a local business sharing recent work."""

# Sentences that make claims the business hasn't confirmed, or talk money: dropped whole.
CLAIMS = re.compile(r"licen[cs]ed|insured|insurance|warrant|guarantee|bonded|\byears? (of|in) (experience|business)\b|"
                    r"\$\s?\d|\bdollars?\b|\bper (square|sq)", re.I)
PHONE = re.compile(r"\(?\b\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b")
EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
STREET = re.compile(r"\b\d+\s+(?:[A-Z][\w']*\s+){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Dr|Drive|Ct|Court|Way|"
                    r"Blvd|Pl|Place|Ter|Terrace|Cir|Circle|Pkwy|Hwy|Route|Rte)\b\.?", re.I)
# Surnames that are also everyday words ("stone", "wood"): only replaced when written with a capital letter.
COMMON_WORDS = {"stone", "wood", "woods", "brown", "white", "black", "green", "gray", "grey", "glass", "wall", "hall",
                "mason", "carpenter", "cook", "baker", "miller", "bath", "tile", "floor", "door", "king", "rose", "page",
                "may", "young", "long", "small", "field", "hill", "lane", "mill", "bush", "frost", "snow", "rice", "ford",
                "post", "bell", "price", "best", "little", "new", "case", "rich", "early", "love", "joy", "hope"}
TOWNS = ["Saratoga Springs", "Ballston Spa", "Clifton Park", "Wilton", "Malta", "Greenfield", "Gansevoort", "Glens Falls",
         "Queensbury", "Schuylerville", "Stillwater", "Mechanicville", "Halfmoon", "Lake George", "Corinth", "Galway"]


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS social_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_number INTEGER REFERENCES jobs(number), note TEXT NOT NULL DEFAULT '',
        tiktok TEXT NOT NULL DEFAULT '', facebook TEXT NOT NULL DEFAULT '', nextdoor TEXT NOT NULL DEFAULT '',
        posted_on TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS online_listings (
        key TEXT PRIMARY KEY, url TEXT NOT NULL DEFAULT '', todo TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""")


# ---------- listings ----------

def listings(conn: sqlite3.Connection) -> list[dict]:
    ensure_tables(conn)
    saved = {r["key"]: dict(r) for r in conn.execute("SELECT * FROM online_listings")}
    out = []
    for key, label, url, todo in LISTINGS:
        s = saved.get(key)
        url, todo = (s["url"], s["todo"]) if s else (url, todo)
        status = "Not set up" if not url else ("To fix" if todo.strip() else "Live")
        out.append({"key": key, "label": label, "url": url, "todo": todo, "status": status})
    return out


def save_listing(conn: sqlite3.Connection, key: str, url: str, todo: str) -> bool:
    if key not in {k for k, *_ in LISTINGS}:
        return False
    url = url.strip()
    if url and not re.match(r"https?://", url):
        url = "https://" + url
    ensure_tables(conn)
    conn.execute("INSERT INTO online_listings (key, url, todo) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                 "url = excluded.url, todo = excluded.todo, updated_at = datetime('now')", (key, url, todo.strip()))
    conn.commit()
    return True


def website(conn: sqlite3.Connection) -> str:
    """The website as people should type it ("rscbuilds.com"), from the listings checklist."""
    url = next((x["url"] for x in listings(conn) if x["key"] == "website"), "")
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def schedule(conn: sqlite3.Connection) -> str:
    return prefs.get(conn, "social_schedule") or SCHEDULE_DEFAULT


# ---------- post drafts ----------

def town_of(address: str) -> str:
    """The town from an address, never the street. "45 Oak St, Saratoga Springs, NY" -> "Saratoga Springs"."""
    for t in TOWNS:
        if t.lower() in (address or "").lower():
            return t
    parts = [p.strip() for p in (address or "").split(",")]
    if len(parts) > 1 and parts[1] and not re.search(r"\d", parts[1]):
        return parts[1]
    return ""


def scrub(text: str, job: dict | None = None) -> str:
    """Remove what must never be posted. Client names become "the homeowners"; a street address goes (with its "at");
    whole sentences with a phone number, email, price or unconfirmed claim are dropped."""
    text = text or ""
    if job:
        first, last = job.get("first_name", "") or "", job.get("last_name", "") or ""
        street = (job.get("address") or "").split(",")[0].strip()
        if street and re.search(r"\d", street):
            text = re.sub(r"(?:\b(?:at|on)\s+)?" + re.escape(street), "", text, flags=re.I)
        parts = [re.escape(x) if x.lower() not in COMMON_WORDS else "(?-i:" + re.escape(x.capitalize()) + ")"
                 for x in (first, last) if len(x) > 1]
        if parts:
            name = r"\b(?:the\s+)?(?:" + "|".join(parts) + r")(?:\s+(?:" + "|".join(parts) + r"))?"
            text = re.sub(name + r"(?:'s|s'|’s)", "the homeowners'", text, flags=re.I)
            text = re.sub(name + r"(?:es|s)?\b", "the homeowners", text, flags=re.I)
    text = re.sub(r"(?:\b(?:at|on)\s+)?" + STREET.pattern, "", text, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [x for x in sentences if x.strip() and not (CLAIMS.search(x) or PHONE.search(x) or EMAIL.search(x))]
    out = " ".join(kept)
    out = re.sub(r"\bthe the\b", "the", out, flags=re.I)
    out = re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([,.!?])", r"\1", out)).strip(" ,")
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)


def hashtags(town: str, kind: str) -> str:
    tags = ["#remodeling", "#beforeandafter"]
    k = (kind or "").lower()
    for word, tag in (("bath", "#bathroomremodel"), ("shower", "#bathroomremodel"), ("kitchen", "#kitchenremodel"),
                      ("porch", "#porch"), ("deck", "#deck"), ("built-in", "#builtins"), ("stair", "#stairs")):
        if word in k and tag not in tags:
            tags.insert(0, tag)
    if town:
        tags.append("#" + re.sub(r"[^A-Za-z]", "", town))
    tags.append("#upstateny")
    return " ".join(tags[:6])


def fallback(note: str, town: str) -> dict:
    where = f" in {town}" if town else ""
    line = note.strip().rstrip(".") or "Another project finished"
    line = line[0].upper() + line[1:]
    return {"tiktok": f"{line}{where}.",
            "facebook": f"Recent work{where}: {line[0].lower() + line[1:]}. Thanks to the homeowners for having us.",
            "nextdoor": f"Hi neighbors! We just wrapped up a project{where}: {line[0].lower() + line[1:]}. "
                        "If you're thinking about a project of your own, we're happy to come take a look."}


def draft(model, conn: sqlite3.Connection, note: str, job_number: int | None = None) -> dict:
    """Three drafts, scrubbed, saved as a new post. Returns the saved row."""
    ensure_tables(conn)
    job = books.get_job(conn, job_number) if job_number else None
    town = town_of(job["address"]) if job else ""
    kind = " ".join(filter(None, [job.get("job_type", "") if job else "", note]))
    clean_note = scrub(note, job)
    posts = {}
    if model is not None and clean_note:
        b = brand.current()
        try:
            user = f"What we did: {clean_note}." + (f" Town: {town}." if town else "") + \
                   (f" Kind of job: {job['job_type']}." if job and job.get("job_type") else "")
            got = model.extract(PROMPT.format(biz=b["name"], region=b["region"]), user, SCHEMA)
            posts = {k: scrub(str(got.get(k) or ""), job) for k in ("tiktok", "facebook", "nextdoor")}
        except Exception:
            posts = {}
    base = fallback(clean_note, town)
    for k in ("tiktok", "facebook", "nextdoor"):
        if len(posts.get(k, "")) < 20:
            posts[k] = scrub(base[k], job)
    site = website(conn)
    posts["tiktok"] = f"{posts['tiktok']}\n{hashtags(town, kind)}"
    if site:
        for k in ("facebook", "nextdoor"):
            if site not in posts[k]:
                posts[k] = f"{posts[k]}\n\nSee more of our work or ask for a visit: {site}"
    cur = conn.execute("INSERT INTO social_posts (job_number, note, tiktok, facebook, nextdoor) VALUES (?, ?, ?, ?, ?)",
                       (job_number or None, note.strip(), posts["tiktok"], posts["facebook"], posts["nextdoor"]))
    conn.commit()
    return get_post(conn, cur.lastrowid)


def get_post(conn: sqlite3.Connection, post_id: int) -> dict | None:
    ensure_tables(conn)
    r = conn.execute("SELECT * FROM social_posts WHERE id = ?", (post_id,)).fetchone()
    return dict(r) if r else None


def posts(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    ensure_tables(conn)
    rows = conn.execute("SELECT p.*, j.last_name, j.number || '-' || j.code AS job_id FROM social_posts p LEFT JOIN jobs j ON j.number = p.job_number "
                        "ORDER BY (p.posted_on IS NOT NULL), p.id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def update_post(conn: sqlite3.Connection, post_id: int, **fields) -> None:
    ensure_tables(conn)
    for k, v in fields.items():
        if k in ("tiktok", "facebook", "nextdoor"):
            conn.execute(f"UPDATE social_posts SET {k} = ? WHERE id = ?", (v.strip(), post_id))
    conn.commit()


def mark_posted(conn: sqlite3.Connection, post_id: int, today: date | None = None) -> None:
    ensure_tables(conn)
    conn.execute("UPDATE social_posts SET posted_on = ? WHERE id = ?", ((today or date.today()).isoformat(), post_id))
    conn.commit()


def delete_post(conn: sqlite3.Connection, post_id: int) -> None:
    ensure_tables(conn)
    conn.execute("DELETE FROM social_posts WHERE id = ?", (post_id,))
    conn.commit()


def jobs_to_post(conn: sqlite3.Connection) -> list[dict]:
    """Finished or underway jobs with no post yet: the best material for real-job posts."""
    ensure_tables(conn)
    done = {r[0] for r in conn.execute("SELECT DISTINCT job_number FROM social_posts WHERE job_number IS NOT NULL")}
    return [j for j in books.list_jobs(conn) if j["status"] in ("Complete", "In Progress") and j["number"] not in done]


def summary(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """For the Monday report and Home: drafts waiting, days since the last post, listings to fix."""
    ensure_tables(conn)
    today = today or date.today()
    waiting = conn.execute("SELECT COUNT(*) FROM social_posts WHERE posted_on IS NULL").fetchone()[0]
    last = conn.execute("SELECT MAX(posted_on) FROM social_posts").fetchone()[0]
    return {"drafts": waiting, "last_posted": last,
            "days_since": (today - date.fromisoformat(last)).days if last else None,
            "to_fix": [x["label"] for x in listings(conn) if x["status"] == "To fix"],
            "not_set_up": [x["label"] for x in listings(conn) if x["status"] == "Not set up"],
            "jobs_to_post": len(jobs_to_post(conn))}
