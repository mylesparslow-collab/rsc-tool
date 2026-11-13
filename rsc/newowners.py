"""New homeowners: people who just bought a house in our towns, for a welcome letter in the mail.

Where the names come from (all public, no login, read-only):
  - Saratoga County's own parcel map (the county's map viewer service). It has the owner and the deed book and
    page, but no sale price or date. In Saratoga the deed "book" is the year the deed was recorded and the
    "page" is its number in that year, so DEED_BOOK 2026 means "bought in 2026" and a higher page is more recent.
  - New York State's tax parcel points, joined on SWIS + print key, add year built, living area and the
    assessor's full market value (and the property ZIP).
  - Warren County's parcel layer (Queensbury, Glens Falls) has the real sale date and price, months behind.

Code decides everything here: which owners count, the score, the cards and when each is due. No model is used,
nothing is sent: Nick prints the cards (or hands the CSV to a mailing service) and presses "I mailed these".

Each owner gets up to three cards: a welcome, a follow-up three weeks later, and a seasonal note about six weeks after
that, worded for the season it goes out in. Every card carries a short code and a QR code for rscbuilds.com/welcome, where they can ask
for a free walkthrough; that request comes back tagged "new homeowner mail", and the cards stop for that house.
Mail only. No phone numbers, no skip tracing, no texts.
"""
import csv
import io
import json
import re
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from . import brand, db, prefs

SARATOGA = "https://spatialags.vhb.com/arcgis/rest/services/29820_Saratoga/NY_County_Saratoga/MapServer/57/query"
STATE = "https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcel_Centroid_Points/MapServer/0/query"
WARREN = "https://services6.arcgis.com/Fg3XpDIUTR3JZZES/arcgis/rest/services/WCNY_Parcels_MASTER_new_view/FeatureServer/0/query"

# Towns Nick works in. Names as the county rolls spell them (matched without case). Ballston Spa is a village
# in the towns of Ballston and Milton; Gansevoort is in Northumberland; Schuylerville is in the town of Saratoga.
CORE_TOWNS = ("saratoga springs", "wilton", "malta", "ballston", "clifton park", "greenfield")
NEAR_TOWNS = ("milton", "northumberland", "saratoga", "stillwater", "queensbury", "glens falls")
WARREN_TOWNS = ("Queensbury", "Glens Falls")
# The Saratoga County municipalities in Nick's area (others, like Halfmoon or Corinth, are left out).
AREA = ("saratoga springs", "wilton", "malta", "ballston", "ballston spa", "milton", "clifton park", "greenfield",
        "northumberland", "saratoga", "schuylerville", "victory", "stillwater", "round lake")
# Villages and cities with one post office, for houses whose ZIP isn't in the state data.
TOWN_ZIP = {"saratoga springs": "12866", "ballston spa": "12020", "schuylerville": "12871", "victory": "12884",
            "round lake": "12151", "glens falls": "12801"}

# Houses only: 1, 2 and 3 family, rural homes, estates, two houses on one lot. Not mobile homes, apartments, land.
RESIDENTIAL = {"210", "215", "220", "230", "240", "241", "250", "280", "281", "283"}

# Owners that are companies, banks or the government: they don't hire a remodeler off a welcome letter.
NOT_A_FAMILY = re.compile(r"\b(LLC|L\.L\.C|INC|CORP|CORPORATION|COMPANY|CO\b|LP|LLP|BANK|MORTGAGE|FEDERAL|NATIONAL|"
                          r"SECRETARY|HOUSING|HOMES|BUILDERS?|DEVELOPMENT|DEVELOPERS|PROPERTIES|REALTY|HOLDINGS|"
                          r"INVESTMENTS?|ASSOCIATES|PARTNERS|CHURCH|COUNTY|STATE OF|CITY OF|TOWN OF|VILLAGE OF|ESTATE OF)\b")

# Post office town for each ZIP (the town on a letter is the post office, not the municipality).
ZIP_CITY = {
    "12866": "Saratoga Springs", "12831": "Gansevoort", "12020": "Ballston Spa", "12019": "Ballston Lake",
    "12065": "Clifton Park", "12118": "Mechanicville", "12170": "Stillwater", "12871": "Schuylerville",
    "12833": "Greenfield Center", "12850": "Middle Grove", "12822": "Corinth", "12188": "Waterford",
    "12151": "Round Lake", "12027": "Burnt Hills", "12803": "South Glens Falls", "12804": "Queensbury",
    "12801": "Glens Falls", "12859": "Porter Corners", "12884": "Victory Mills", "12074": "Galway",
    "12863": "Rock City Falls", "12835": "Hadley", "12846": "Lake Luzerne", "12845": "Lake George",
    "12828": "Fort Edward", "12148": "Rexford", "12302": "Schenectady", "12010": "Amsterdam",
}

DEFAULT_LETTER = """Dear {addressee},

Welcome to {town}, and congratulations on the house on {street}.

By now you have probably started a list: the bathroom you would do differently, the kitchen that almost works, the back steps that give a little underfoot. Most new owners have one.

I'm {owner}, and I run {business} here in {region}. We design and build kitchens, bathrooms, porches and four-season rooms, and we do the careful repair work older houses need, with trim, stairs and porches rebuilt to match what is already there.

When you're ready, I'll walk through the house with you at no charge. You'll get a straight answer on what needs doing now, what can wait, and what it would take to do it right. If you decide to go ahead, you get a written plan before any work starts.

Scan the code below, or call or text me at {phone}.

Welcome home,

{owner}
{business}"""

LETTER_KEY = "newowner_letter"
LAST_KEY = "newowner_last_at"
LAST_MSG = "newowner_last_message"
UA = "RSC-tool (local remodeling business; weekly public-records check)"



# ---------- fetching (public ArcGIS map services) ----------

_CTX = None


def _ssl_context():
    """Python's own certificate list can miss a root that macOS trusts (Saratoga's map server hits this), so also
    load certifi's list and, on a Mac, the system's root certificates. Checking stays on."""
    global _CTX
    if _CTX is not None:
        return _CTX
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    if sys.platform == "darwin":
        for keychain in ("/System/Library/Keychains/SystemRootCertificates.keychain", "/Library/Keychains/System.keychain"):
            try:
                pem = subprocess.run(["/usr/bin/security", "find-certificate", "-a", "-p", keychain],
                                     capture_output=True, text=True, timeout=20).stdout
                if "BEGIN CERTIFICATE" in pem:
                    ctx.load_verify_locations(cadata=pem)
            except Exception:
                pass
    _CTX = ctx
    return ctx


def _post(url: str, params: dict, tries: int = 3) -> dict:
    data = urllib.parse.urlencode({**params, "f": "json"}).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
                out = json.loads(r.read().decode("utf-8", "replace"))
            if "error" in out:
                raise RuntimeError(f"{url.split('/rest/')[0]} said: {out['error'].get('message', out['error'])}")
            return out
        except (OSError, ValueError, RuntimeError) as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Couldn't read {urllib.parse.urlparse(url).netloc}: {last}")


def fetch_all(url: str, where: str, fields: str = "*", chunk: int = 250, post=_post) -> list[dict]:
    """Every matching record's attributes. Asks for the ids first, then the records in chunks, so the server's
    page limit (often 1,000 or 2,000) never cuts the list short."""
    ids = post(url, {"where": where, "returnIdsOnly": "true"}).get("objectIds") or []
    rows = []
    for i in range(0, len(ids), chunk):
        part = post(url, {"objectIds": ",".join(str(x) for x in ids[i:i + chunk]), "outFields": fields,
                          "returnGeometry": "false"})
        rows += [f.get("attributes", {}) for f in part.get("features", [])]
    return rows


def _get(a: dict, *names, default=""):
    """A field by any of its likely names, ignoring case (the county and state layers name things differently)."""
    low = {k.lower(): v for k, v in a.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, "", " "):
            return v
    return default


def _mail(a: dict, part: str) -> str:
    for k, v in a.items():
        k2 = k.upper()
        if k2.startswith("MAIL") and part in k2 and v not in (None, ""):
            return str(v).strip()
    return ""


def _num(v):
    try:
        f = float(str(v).replace(",", "").replace("$", ""))
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _key(s) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(s or "").upper())


def _addr(s) -> str:
    s = re.sub(r"[^0-9A-Z ]", " ", str(s or "").upper())
    return re.sub(r"\s+", " ", s).strip()


def _sql_list(values) -> str:
    return ",".join("'" + str(v).replace("'", "''") + "'" for v in values)


def state_details(swis_keys: dict[str, set[str]], post=_post) -> dict[tuple, dict]:
    """Year built, size, market value and ZIP from the state's parcel points, keyed by (swis, print key).
    One request per few hundred houses (sent as a form, so a long list is fine)."""
    out, fields = {}, "SWIS,PRINT_KEY,YR_BLT,SQFT_LIVING,FULL_MARKET_VAL,LOC_ZIP"
    for swis, keys in swis_keys.items():
        keys = sorted(k for k in keys if k)
        for i in range(0, len(keys), 400):
            where = f"SWIS = '{swis}' AND PRINT_KEY IN ({_sql_list(keys[i:i + 400])})"
            try:
                part = post(STATE, {"where": where, "outFields": fields, "returnGeometry": "false"})
                rows = [f.get("attributes", {}) for f in part.get("features", [])]
                if part.get("exceededTransferLimit"):
                    rows = fetch_all(STATE, where, fields, post=post)
            except RuntimeError:
                continue      # extra detail only; the lead still counts without it
            for r in rows:
                out[(str(_get(r, "SWIS")), _key(_get(r, "PRINT_KEY")))] = r
    return out


# ---------- turning records into leads ----------

def addressee(owner: str) -> str:
    """'SMITH JOHN A' or 'Smith, John' -> 'The Smith Household'. Rolls list the last name first."""
    o = re.sub(r"\s+", " ", (owner or "").strip())
    if not o or NOT_A_FAMILY.search(o.upper()):
        return "Current Resident"
    last = o.split(",")[0].split(" ")[0] if "," in o else o.split(" ")[0]
    last = re.sub(r"[^A-Za-z'\-]", "", last)
    if len(last) < 2:
        return "Current Resident"
    pretty = "-".join(p[:1].upper() + p[1:].lower() for p in last.split("-"))
    pretty = re.sub(r"^(Mc|O')([a-z])", lambda m: m.group(1) + m.group(2).upper(), pretty)
    return f"The {pretty} Household"


def town_weight(town: str) -> int:
    t = (town or "").lower()
    if any(c in t for c in CORE_TOWNS):
        return 10
    return 5 if any(n in t for n in NEAR_TOWNS) else 0


def score(year_built, value, months_ago, town) -> tuple[int, str, list[str]]:
    """0-100 for how likely this buyer is to want a $15-40K kitchen or bath job, with the reasons in words."""
    why, s = [], 0
    if year_built:
        y = int(year_built)
        pts = 35 if y < 1950 else 30 if y < 1980 else 20 if y < 2000 else 8 if y < 2015 else 0
        s += pts
        why.append(f"built {y}")
    else:
        s += 15
    if value:
        v = float(value)
        s += 30 if 250_000 <= v <= 900_000 else 18 if 175_000 <= v < 250_000 or 900_000 < v <= 1_500_000 else 5
        why.append(f"${v / 1000:,.0f}K")
    else:
        s += 10
    if months_ago is not None:
        s += 25 if months_ago <= 6 else 15 if months_ago <= 12 else 5
    else:
        s += 10
    s += town_weight(town)
    s = min(100, s)
    return s, ("A" if s >= 70 else "B" if s >= 50 else "C"), why


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _city_zip(a: dict, detail: dict, street: str, town: str) -> tuple[str, str]:
    """Post-office town and ZIP for the house. If the owner's mailing address is the house itself, the county has
    the exact post office; otherwise the state points' ZIP, then the one ZIP of a city or village."""
    zip_ = str(_get(detail or {}, "LOC_ZIP"))[:5]
    mail_city, mail_zip = _mail(a, "CITY"), _mail(a, "ZIP")[:5]
    lines = [v for k, v in a.items() if k.upper().startswith("MAIL") and ("ADD" in k.upper() or "STR" in k.upper()) and v]
    if street and any(_addr(x) == _addr(street) for x in lines) and (mail_zip or zip_):
        return (mail_city.title() if mail_city else ZIP_CITY.get(mail_zip or zip_, "")), (mail_zip or zip_)
    zip_ = zip_ or TOWN_ZIP.get(town.strip().lower(), "")
    return ZIP_CITY.get(zip_, ""), zip_


def _fill_zips(leads: list[dict]) -> None:
    """A house with no ZIP takes the ZIP its neighbors on the same street (same town) have, when they all agree."""
    seen: dict[tuple, set] = {}
    for l in leads:
        if l["zip"]:
            seen.setdefault((l["town"].lower(), _street_name(l["street"]).upper()), set()).add(l["zip"])
    for l in leads:
        if not l["zip"]:
            z = seen.get((l["town"].lower(), _street_name(l["street"]).upper()), set())
            if len(z) == 1:
                l["zip"] = z.pop()
                l["city"] = ZIP_CITY.get(l["zip"], "")


def saratoga_leads(today: date, post=_post) -> tuple[list[dict], str]:
    years = (today.year, today.year - 1)
    where = f"DEED_BOOK IN ({_sql_list(years)})"
    rows = fetch_all(SARATOGA, where, post=post)
    houses = [a for a in rows if str(_get(a, "PRP_CLS_CODE", "PROP_CLASS_CODE", "PROP_CLASS"))[:3] in RESIDENTIAL
              and str(_get(a, "MUNI", "MUNI_NAME")).strip().lower() in AREA]
    want = {}
    for a in houses:
        want.setdefault(str(_get(a, "SWIS")), set()).add(str(_get(a, "PRINT_KEY")).strip())
    details = state_details(want, post=post)
    leads = []
    for a in houses:
        town = str(_get(a, "MUNI", "MUNI_NAME")).strip()
        street = str(_get(a, "PROP_ADDR", "PARCEL_ADDR")).strip()
        owner = str(_get(a, "OWNER", "PRIMARY_OWNER")).strip()
        book, page = str(_get(a, "DEED_BOOK")).strip(), str(_get(a, "DEED_PAGE")).strip()
        d = details.get((str(_get(a, "SWIS")), _key(_get(a, "PRINT_KEY"))), {})
        yb = _num(_get(d, "YR_BLT"))
        deed_year = int(book) if book.isdigit() else None
        leads.append(_lead("Saratoga", a, d, town, street, owner, yb and int(yb), _num(_get(d, "SQFT_LIVING")),
                           _num(_get(d, "FULL_MARKET_VAL") or _get(a, "FULL_MARKET_VAL")), None, "",
                           f"{book}-{page}", deed_year, today))
    _fill_zips(leads)
    return leads, f"Saratoga County: {len(rows)} deeds recorded {years[1]}-{years[0]}, {len(houses)} houses in your towns"


def warren_leads(today: date, post=_post) -> tuple[list[dict], str]:
    since = (today - timedelta(days=365)).isoformat()
    where = f"Muni IN ({_sql_list(WARREN_TOWNS)}) AND SALE_DATE >= DATE '{since}'"
    rows = fetch_all(WARREN, where, post=post)
    houses, leads = [], []
    for a in rows:
        code = str(_get(a, "PRP_CLS_CO", "PRP_CLS_CODE"))[:3]
        if code not in RESIDENTIAL:
            continue
        houses.append(a)
        price = _num(_get(a, "SALE_PRICE"))
        sd = _get(a, "SALE_DATE")
        sale = datetime.fromtimestamp(sd / 1000, timezone.utc).date() if isinstance(sd, (int, float)) else None
        if not sale or not price or price < 50_000:      # not an arm's-length sale (gift, family transfer)
            continue
        owner = " ".join(str(x).strip() for x in (_get(a, "OWNER1", "OWNER"),) if x)
        leads.append(_lead("Warren", a, {}, str(_get(a, "Muni")).strip(), str(_get(a, "PROP_ADDR")).strip(), owner,
                           _num(_get(a, "YR_BUILT")) and int(_num(_get(a, "YR_BUILT"))), _num(_get(a, "SQ_FT")),
                           _num(_get(a, "FULL_MARKE", "FULL_MARKET_VAL")), price, sale.isoformat(),
                           f"{_get(a, 'DEED_BOOK')}-{_get(a, 'DEED_PAGE')}", sale.year, today))
    _fill_zips(leads)
    newest = max((l["sale_date"] for l in leads), default="none")
    return leads, f"Warren County: {len(houses)} house sales in the last year (newest {newest})"


def _lead(county, a, d, town, street, owner, year_built, sqft, value, price, sale_date, deed, deed_year, today):
    if sale_date:
        months = _months_between(date.fromisoformat(sale_date), today)
    else:
        months = None if deed_year is None else (3 if deed_year == today.year else 12 if deed_year == today.year - 1 else 24)
    s, grade, why = score(year_built, price or value, months, town)
    city, zip_ = _city_zip(a, d, street, town)
    skip = []
    if NOT_A_FAMILY.search(owner.upper()):
        skip.append("owner is a company or bank")
    if year_built and deed_year and year_built >= deed_year - 2:
        skip.append("new construction")
    if not street:
        skip.append("no street address")
    return {"key": f"{county}|{_get(a, 'SWIS')}|{_key(_get(a, 'PRINT_KEY', 'SBL'))}|{deed}{'|' + sale_date if sale_date else ''}",
            "county": county, "town": town, "street": street.title() if street.isupper() else street,
            "city": city, "zip": zip_, "owner": owner, "addressee": addressee(owner),
            "prop_class": str(_get(a, "PROP_CLASS", "PRP_CLS_CODE")), "year_built": year_built,
            "sqft": int(sqft) if sqft else None, "market_value": value, "sale_price": price, "sale_date": sale_date,
            "deed": deed, "deed_year": deed_year, "score": 0 if skip else s, "grade": "skip" if skip else grade,
            "why": "; ".join(skip) if skip else ", ".join(why)}


# ---------- storing and reading ----------

def init(conn: sqlite3.Connection) -> None:
    conn.executescript(db.NEW_OWNERS)
    db.migrate_new_owners(conn)


def save(conn: sqlite3.Connection, leads: list[dict], today: date) -> int:
    """Add leads we haven't seen; refresh the details of ones we have (keeping whether they were mailed). Returns new."""
    init(conn)
    new = 0
    for l in leads:
        cur = conn.execute("SELECT status FROM new_owners WHERE key = ?", (l["key"],)).fetchone()
        cols = [k for k in l if k != "key"]
        if cur:
            conn.execute(f"UPDATE new_owners SET {', '.join(c + ' = ?' for c in cols)} WHERE key = ?",
                         [l[c] for c in cols] + [l["key"]])
        else:
            status = "skip" if l["grade"] == "skip" else "new"
            if status == "new" and _opted_out(conn, l):    # asked for no mail on an earlier record of this house
                status = "optout"
            conn.execute(f"INSERT INTO new_owners (key, {', '.join(cols)}, first_seen, status) VALUES "
                         f"(?, {', '.join('?' for _ in cols)}, ?, ?)", [l["key"]] + [l[c] for c in cols] + [today.isoformat(), status])
            new += status == "new"
    conn.commit()
    return new


def refresh(conn: sqlite3.Connection, today: date | None = None, post=_post) -> str:
    """Pull both counties, save what's new, and remember when. Returns a one-line summary for the page and the log."""
    today = today or date.today()
    init(conn)
    parts, total_new, failed = [], 0, []
    for name, pull in (("Saratoga", saratoga_leads), ("Warren", warren_leads)):
        try:
            leads, note = pull(today, post=post)
            n = save(conn, leads, today)
            total_new += n
            parts.append(f"{note}; {n} new to mail")
        except RuntimeError as exc:
            failed.append(f"{name} County couldn't be read ({exc})")
    msg = ". ".join(parts + failed) + "."
    prefs.put(conn, LAST_KEY, datetime.now().isoformat(timespec="seconds"))
    prefs.put(conn, LAST_MSG, msg)
    return msg


def due(conn: sqlite3.Connection, today: date | None = None) -> bool:
    last = prefs.get(conn, LAST_KEY)
    if not last:
        return True
    try:
        return (today or date.today()) - datetime.fromisoformat(last).date() >= timedelta(days=6)
    except ValueError:
        return True


def listing(conn: sqlite3.Connection, status: str = "new", grade: str = "", town: str = "",
            mailable: bool = False, limit: int | None = None) -> list[sqlite3.Row]:
    """Leads, best first. grade "A" = A only, "B" = A and B, "C" = everyone. mailable = only ones with a ZIP."""
    init(conn)
    sql, args = "SELECT * FROM new_owners WHERE status = ?", [status]
    if grade in ("A", "B"):
        sql += " AND grade <= ?"
        args.append(grade)
    if town:
        sql += " AND town = ?"
        args.append(town)
    if mailable:
        sql += " AND zip != '' AND street != ''"
    sql += " ORDER BY score DESC, deed_year DESC, sale_date DESC, CAST(substr(deed, instr(deed, '-') + 1) AS INTEGER) DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, args).fetchall()


def no_zip(conn: sqlite3.Connection) -> int:
    init(conn)
    return conn.execute("SELECT COUNT(*) FROM new_owners WHERE status = 'new' AND zip = ''").fetchone()[0]


def counts(conn: sqlite3.Connection) -> dict:
    init(conn)
    out = {"new": 0, "mailed": 0, "skip": 0, "A": 0, "B": 0, "C": 0}
    for st, n in conn.execute("SELECT status, COUNT(*) FROM new_owners GROUP BY status"):
        out[st] = n
    for g_, n in conn.execute("SELECT grade, COUNT(*) FROM new_owners WHERE status = 'new' GROUP BY grade"):
        out[g_] = n
    return out


def towns(conn: sqlite3.Connection) -> list[str]:
    init(conn)
    return [r[0] for r in conn.execute("SELECT DISTINCT town FROM new_owners WHERE status = 'new' ORDER BY town")]


def set_status(conn: sqlite3.Connection, keys: list[str], status: str, today: date | None = None) -> int:
    """'mailed' sends each house its next card (see mark_mailed); 'replied' stops the cards; 'skip' takes it off; 'new' puts it back."""
    if status == "mailed":
        return mark_mailed(conn, keys, today)
    if status not in ("new", "skip", "replied", "optout"):
        raise ValueError(status)
    today = today or date.today()
    n = 0
    for k in keys:
        if status == "new":   # back on the list from the start
            n += conn.execute("UPDATE new_owners SET status = 'new', mailed_on = '', step = 0, next_due = '', card2_on = '', "
                              "card3_on = '', replied_on = '' WHERE key = ?", (k,)).rowcount
        elif status == "replied":
            n += conn.execute("UPDATE new_owners SET status = 'replied', replied_on = ?, next_due = '' WHERE key = ?",
                              (today.isoformat(), k)).rowcount
        else:   # skip or optout ("never mail": they asked us to stop; it holds through later county checks)
            n += conn.execute("UPDATE new_owners SET status = ?, next_due = '' WHERE key = ? AND status != 'optout'",
                              (status, k)).rowcount
    conn.commit()
    return n


# ---------- "no more mail" ----------

STOP_UNMATCHED = "newowner_stop_unmatched"


def _opted_out(conn: sqlite3.Connection, lead: dict) -> bool:
    """Same house and same owner already asked for no mail (a corrected or re-recorded deed makes a new row)."""
    for r in conn.execute("SELECT street, owner FROM new_owners WHERE status = 'optout' AND county = ? AND town = ?",
                          (lead.get("county", ""), lead.get("town", ""))):
        if _addr(r["street"]) == _addr(lead.get("street")) and _key(r["owner"]) == _key(lead.get("owner")):
            return True
    return False


def stop_mail(conn: sqlite3.Connection, code: str = "", address: str = "", today: date | None = None) -> list:
    """Someone asked for no more mail. Find the house by its card code, or else by the street address they typed,
    and mark it never-mail. Returns the houses marked; when none match, the request is kept for Nick to see."""
    init(conn)
    rows = []
    row = by_code(conn, code)
    if row:
        rows = [row]
    elif address:
        want = _addr(address.split(",")[0])
        if want:
            rows = [r for r in conn.execute("SELECT * FROM new_owners WHERE status != 'optout' AND street != ''")
                    if _addr(r["street"]) == want]
    if rows:
        set_status(conn, [r["key"] for r in rows], "optout", today)
    else:
        pending = stop_requests(conn)
        pending.append({"on": (today or date.today()).isoformat(), "code": code[:12], "address": address[:120]})
        prefs.put(conn, STOP_UNMATCHED, json.dumps(pending[-50:]))
    return rows


def stop_requests(conn: sqlite3.Connection) -> list[dict]:
    """Stop-mail requests that matched no house, for Nick to take off the list by hand."""
    try:
        return json.loads(prefs.get(conn, STOP_UNMATCHED) or "[]")
    except ValueError:
        return []


# ---------- the three cards: welcome, follow-up, seasonal ----------

FOLLOW_UP_DAYS = 21          # card 2 goes about three weeks after the welcome
SEASON_GAP_DAYS = 42         # card 3, the seasonal note, about six weeks after card 2 (its words follow the season it goes in)
CARD_NAMES = {1: "Welcome", 2: "Follow-up", 3: "Seasonal"}
WELCOME_URL = "https://rscbuilds.com/welcome/"
SHORT_LINK = "rscbuilds.com/welcome"
LAST_BATCH = "newowner_last_batch"
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"   # no 0/O, 1/I/L: read off a card and typed by hand

FOLLOW_UP_LETTER = """Dear {addressee},

A few weeks in, the house has probably shown you a thing or two the inspection didn't.

That is the best time for a second set of eyes. I'll come by, look at whatever is on your list, and tell you plainly what is sound, what can wait, and what is worth doing first. The visit is free, and there is no pressure to hire us.

If now isn't the time, hang on to this card. We'll be here when you're ready.

{owner}
{business}, {phone}"""

SEASONAL_LETTER = """Dear {addressee},

{season_note}

If something on the house has been bothering you, or you're starting to picture a new kitchen or bathroom, I'd be glad to come take a look. The walkthrough is free, and you get a written plan before anything starts.

All the best in the new place,

{owner}
{business}, {phone}"""

SEASON_NOTES = {
    "winter": "Your first winter in a house teaches you a lot about it: which windows let the cold in, where ice builds up along the roof edge, which stair creaks. It is also the right time to plan a kitchen or bathroom, so the design is settled and the materials are chosen before the work starts.",
    "spring": "Spring shows you what the winter did: trim gone soft, a railing that wobbles, steps the frost has pushed out of line. It is a good time to get those fixed, and to think about the porch or deck you want for summer.",
    "summer": "Summer is when you live on the porch and the deck, and notice what needs work. It is also a good time to plan the inside projects you'd like done once the weather turns.",
    "fall": "Before the snow, it is worth a look at the gutters, the trim and the entry steps, so small problems don't turn into spring repairs. Fall is also the time to plan a kitchen or bathroom you'd like done over the winter.",
}

DEFAULT_CARDS = {1: DEFAULT_LETTER, 2: FOLLOW_UP_LETTER, 3: SEASONAL_LETTER}


def card_key(card: int) -> str:
    return LETTER_KEY if card == 1 else f"{LETTER_KEY}_{card}"


def season(d: date) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "fall")


def next_due_after(card: int, sent: date) -> str:
    """When the next card is due after this one went out ('' after the last card)."""
    if card == 1:
        return (sent + timedelta(days=FOLLOW_UP_DAYS)).isoformat()
    if card == 2:
        return (sent + timedelta(days=SEASON_GAP_DAYS)).isoformat()
    return ""


def _new_code(conn: sqlite3.Connection) -> str:
    import secrets
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))
        if not conn.execute("SELECT 1 FROM new_owners WHERE code = ?", (code,)).fetchone():
            return code


def ensure_codes(conn: sqlite3.Connection, keys: list[str]) -> None:
    for k in keys:
        conn.execute("UPDATE new_owners SET code = ? WHERE key = ? AND code = ''", (_new_code(conn), k))
    conn.commit()


def normal_code(text: str) -> str:
    """What someone typed from the card ('k7m 2p') -> 'K7M2P'; '' if it can't be one of ours."""
    code = re.sub(r"[^A-Za-z0-9]", "", text or "").upper()
    return code if len(code) == 5 and all(ch in CODE_ALPHABET for ch in code) else ""


def by_code(conn: sqlite3.Connection, code: str):
    code = normal_code(code)
    if not code:
        return None
    init(conn)
    return conn.execute("SELECT * FROM new_owners WHERE code = ?", (code,)).fetchone()


def mark_replied(conn: sqlite3.Connection, code: str, today: date | None = None):
    """Someone answered a card (the welcome page form). Stop their cards. Returns the house row, or None."""
    row = by_code(conn, code)
    if row and row["status"] in ("new", "mailed"):
        set_status(conn, [row["key"]], "replied", today)
        row = conn.execute("SELECT * FROM new_owners WHERE key = ?", (row["key"],)).fetchone()
    return row


def mark_mailed(conn: sqlite3.Connection, keys: list[str], today: date | None = None) -> int:
    """Each of these houses just got its next card. Returns how many were marked."""
    today = today or date.today()
    init(conn)
    n = 0
    for k in keys:
        r = conn.execute("SELECT step, status FROM new_owners WHERE key = ?", (k,)).fetchone()
        if not r or r["status"] not in ("new", "mailed") or r["step"] >= 3:
            continue
        card = r["step"] + 1
        sets = {"status": "mailed", "step": card, "next_due": next_due_after(card, today)}
        sets[{1: "mailed_on", 2: "card2_on", 3: "card3_on"}[card]] = today.isoformat()
        conn.execute(f"UPDATE new_owners SET {', '.join(c + ' = ?' for c in sets)} WHERE key = ?", [*sets.values(), k])
        n += 1
    ensure_codes(conn, keys)
    prefs.put(conn, LAST_BATCH, today.isoformat())
    conn.commit()
    return n


def follow_ups_due(conn: sqlite3.Connection, today: date | None = None) -> list[sqlite3.Row]:
    """Houses whose card 2 or 3 is due by today, oldest due first."""
    init(conn)
    return conn.execute("SELECT * FROM new_owners WHERE status = 'mailed' AND step BETWEEN 1 AND 2 AND next_due != '' "
                        "AND next_due <= ? ORDER BY next_due, score DESC", ((today or date.today()).isoformat(),)).fetchall()


def this_weeks_mail(conn: sqlite3.Connection, n: int | None = 50, grade: str = "A", town: str = "",
                    today: date | None = None) -> list[sqlite3.Row]:
    """This week's batch: every follow-up card that is due first, then new welcome cards (best first) up to n."""
    due_now = follow_ups_due(conn, today)
    if n and len(due_now) >= n:
        return due_now[:n]
    room = (n - len(due_now)) if n else None
    if room == 0:
        return due_now
    return due_now + listing(conn, "new", grade, town, mailable=True, limit=room)


def week_due(conn: sqlite3.Connection, today: date | None = None) -> dict | None:
    """For the Home page: {'follow_ups': n, 'new': n} when a week has passed since the last batch, else None.
    Only once Nick has started mailing (the first batch is his choice, from the New homeowners page)."""
    today = today or date.today()
    last = prefs.get(conn, LAST_BATCH)
    if not last:
        return None
    try:
        if today - date.fromisoformat(last) < timedelta(days=7):
            return None
    except ValueError:
        pass
    init(conn)
    ups = len(follow_ups_due(conn, today))
    new = conn.execute("SELECT COUNT(*) FROM new_owners WHERE status = 'new' AND zip != '' AND street != ''").fetchone()[0]
    return {"follow_ups": ups, "new": new} if ups or new else None


def in_the_mail(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    init(conn)
    return conn.execute("SELECT * FROM new_owners WHERE status IN ('mailed', 'replied') "
                        "ORDER BY (status = 'replied') DESC, COALESCE(NULLIF(replied_on, ''), NULLIF(card3_on, ''), "
                        "NULLIF(card2_on, ''), mailed_on) DESC LIMIT ?", (limit,)).fetchall()


def sequence_counts(conn: sqlite3.Connection, today: date | None = None) -> dict:
    init(conn)
    out = {"card1": 0, "card2": 0, "card3": 0, "replied": 0, "due": len(follow_ups_due(conn, today)),
           "optout": conn.execute("SELECT COUNT(*) FROM new_owners WHERE status = 'optout'").fetchone()[0]}
    for step, k in conn.execute("SELECT step, COUNT(*) FROM new_owners WHERE status = 'mailed' GROUP BY step"):
        if step in (1, 2, 3):
            out[f"card{step}"] = k
    out["replied"] = conn.execute("SELECT COUNT(*) FROM new_owners WHERE status = 'replied'").fetchone()[0]
    return out


def qr_svg(url: str) -> str:
    """The QR code as inline SVG, drawn here on the Mac (segno, no network). '' if segno isn't installed."""
    try:
        import segno
    except ImportError:
        return ""
    return segno.make(url, error="m").svg_inline(scale=3, border=2)


def card_link(row) -> str:
    return f"{WELCOME_URL}?c={row['code']}" if row["code"] else WELCOME_URL


# ---------- the letter and the mailing list ----------

def letter_template(conn: sqlite3.Connection, card: int = 1) -> str:
    return prefs.get(conn, card_key(card)) or DEFAULT_CARDS[card]


class _Blank(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def next_card(row) -> int:
    """Which card this house gets next: 1 for a new house, then 2, then 3."""
    return min((row["step"] or 0) + 1, 3) if row["status"] in ("new", "mailed") else 1


def greeting(addressee: str) -> str:
    """The name after "Dear": 'The Smith Household' (right on an envelope) reads 'Smith family' in a letter."""
    m = re.fullmatch(r"The (.+) Household", addressee or "")
    return f"{m.group(1)} family" if m else "Neighbor"


def letter(conn: sqlite3.Connection, row, card: int | None = None, today: date | None = None) -> str:
    b = brand.current()
    owner = prefs.get(conn, "owner_name") or b.get("owner", "")
    town = row["city"] or row["town"]
    card = card or next_card(row)
    fields = _Blank(addressee=greeting(row["addressee"]), street=_street_name(row["street"]), town=town,
                    owner=owner, business=b["name"], region=b["region"], phone=b["phone"], email=b["email"],
                    season_note=SEASON_NOTES[season(today or date.today())], link=SHORT_LINK, code=row["code"])
    return letter_template(conn, card).format_map(fields)


def _street_name(street: str) -> str:
    """'12 Maple Ave' -> 'Maple Ave' (a letter reads better naming the street, not the house number)."""
    return re.sub(r"^\s*[\d\-]+[A-Za-z]?\s+", "", street or "").strip() or street


CSV_COLS = ["addressee", "owner_on_record", "street", "city", "state", "zip", "town", "county", "grade", "score",
            "why", "year_built", "sale_date", "sale_price", "market_value", "deed", "key",
            "card", "card_name", "code", "link", "message"]


def mailing_csv(conn: sqlite3.Connection, rows) -> str:
    """Mail-merge file: one line per card, with the address lines a printer or Word mail merge expects, plus which
    card it is, its code and link (for the QR code) and the card's words, for a mailing service such as Thanks.io."""
    ensure_codes(conn, [r["key"] for r in rows])
    rows = [conn.execute("SELECT * FROM new_owners WHERE key = ?", (r["key"],)).fetchone() for r in rows]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow([r["addressee"], r["owner"], r["street"], r["city"], "NY", r["zip"], r["town"], r["county"],
                    r["grade"], r["score"], r["why"], r["year_built"] or "", r["sale_date"],
                    f"{r['sale_price']:.0f}" if r["sale_price"] else "", f"{r['market_value']:.0f}" if r["market_value"] else "",
                    r["deed"], r["key"], next_card(r), CARD_NAMES[next_card(r)], r["code"], card_link(r), letter(conn, r)])
    return out.getvalue()
