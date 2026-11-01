"""New homeowners: people who just bought a house in our towns, for a welcome letter in the mail.

Where the names come from (all public, no login, read-only):
  - Saratoga County's own parcel map (the county's map viewer service). It has the owner and the deed book and
    page, but no sale price or date. In Saratoga the deed "book" is the year the deed was recorded and the
    "page" is its number in that year, so DEED_BOOK 2026 means "bought in 2026" and a higher page is more recent.
  - New York State's tax parcel points, joined on SWIS + print key, add year built, living area and the
    assessor's full market value (and the property ZIP).
  - Warren County's parcel layer (Queensbury, Glens Falls) has the real sale date and price, months behind.

Code decides everything here: which owners count, the score and the letter. No model is used, nothing is sent:
Nick prints the letters (or hands the CSV to a printer) and presses "I mailed these".
Mail only. No phone numbers, no skip tracing, no texts.
"""
import csv
import io
import json
import re
import sqlite3
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

Congratulations on your new home on {street}, and welcome to {town}.

My name is {owner}. I run {business}, a small design-build remodeling company based in {region}. We do kitchens, bathrooms, porches and four-season rooms, and the careful repair and finish work that older houses need.

If there is a room you have been thinking about changing, this year or a few years from now, I would be glad to come by and walk through it with you. I'll listen to what you have in mind, tell you plainly what it would take, and give you a clear written plan before any work starts.

You can reach me at {phone} or {email}.

Welcome to the neighborhood,

{owner}
{business}"""

LETTER_KEY = "newowner_letter"
LAST_KEY = "newowner_last_at"
LAST_MSG = "newowner_last_message"
UA = "RSC-tool (local remodeling business; monthly public-records check)"



# ---------- fetching (public ArcGIS map services) ----------

def _post(url: str, params: dict, tries: int = 3) -> dict:
    data = urllib.parse.urlencode({**params, "f": "json"}).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
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
    """Year built, size, market value and ZIP from the state's parcel points, keyed by (swis, print key)."""
    out = {}
    for swis, keys in swis_keys.items():
        keys = sorted(k for k in keys if k)
        for i in range(0, len(keys), 80):
            where = f"SWIS = '{swis}' AND PRINT_KEY IN ({_sql_list(keys[i:i + 80])})"
            try:
                rows = fetch_all(STATE, where, "SWIS,PRINT_KEY,YR_BLT,SQFT_LIVING,FULL_MARKET_VAL,LOC_ZIP,PARCEL_ADDR,PROP_CLASS", post=post)
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
    """Post-office town and ZIP for the house. The state points give the ZIP; if the owner's mailing address is the
    house itself, the county gives the exact post office too."""
    zip_ = str(_get(detail or {}, "LOC_ZIP"))[:5]
    mail_street, mail_city, mail_zip = _mail(a, "ADD") or _mail(a, "STR"), _mail(a, "CITY"), _mail(a, "ZIP")[:5]
    if mail_street and _addr(mail_street) == _addr(street):
        return (mail_city.title() if mail_city else ZIP_CITY.get(mail_zip or zip_, "")), (mail_zip or zip_)
    if not zip_ and town.lower().startswith("glens falls"):
        zip_ = "12801"
    return ZIP_CITY.get(zip_, ""), zip_


def saratoga_leads(today: date, post=_post) -> tuple[list[dict], str]:
    years = (today.year, today.year - 1)
    where = f"DEED_BOOK IN ({_sql_list(years)})"
    rows = fetch_all(SARATOGA, where, post=post)
    houses = [a for a in rows if str(_get(a, "PRP_CLS_CODE", "PROP_CLASS_CODE", "PROP_CLASS"))[:3] in RESIDENTIAL]
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
    return leads, f"Saratoga County: {len(rows)} deeds recorded {years[1]}-{years[0]}, {len(houses)} houses"


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
        return (today or date.today()) - datetime.fromisoformat(last).date() >= timedelta(days=28)
    except ValueError:
        return True


def listing(conn: sqlite3.Connection, status: str = "new", grade: str = "", town: str = "") -> list[sqlite3.Row]:
    init(conn)
    sql, args = "SELECT * FROM new_owners WHERE status = ?", [status]
    if grade in ("A", "B", "C"):
        sql += " AND grade <= ?" if grade != "C" else " AND grade IN ('A','B','C')"
        if grade != "C":
            args.append(grade)
    if town:
        sql += " AND town = ?"
        args.append(town)
    sql += " ORDER BY score DESC, COALESCE(sale_date, '') DESC, deed DESC"
    return conn.execute(sql, args).fetchall()


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
    if status not in ("new", "mailed", "skip"):
        raise ValueError(status)
    mailed = (today or date.today()).isoformat() if status == "mailed" else ""
    n = 0
    for k in keys:
        n += conn.execute("UPDATE new_owners SET status = ?, mailed_on = ? WHERE key = ?", (status, mailed, k)).rowcount
    conn.commit()
    return n


# ---------- the letter and the mailing list ----------

def letter_template(conn: sqlite3.Connection) -> str:
    return prefs.get(conn, LETTER_KEY) or DEFAULT_LETTER


class _Blank(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def letter(conn: sqlite3.Connection, row) -> str:
    b = brand.current()
    owner = prefs.get(conn, "owner_name") or b.get("owner", "")
    town = row["city"] or row["town"]
    fields = _Blank(addressee=row["addressee"] or "Neighbor", street=_street_name(row["street"]), town=town,
                    owner=owner, business=b["name"], region=b["region"], phone=b["phone"], email=b["email"])
    return letter_template(conn).format_map(fields)


def _street_name(street: str) -> str:
    """'12 Maple Ave' -> 'Maple Ave' (a letter reads better naming the street, not the house number)."""
    return re.sub(r"^\s*[\d\-]+[A-Za-z]?\s+", "", street or "").strip() or street


CSV_COLS = ["addressee", "owner_on_record", "street", "city", "state", "zip", "town", "county", "grade", "score",
            "why", "year_built", "sale_date", "sale_price", "market_value", "deed", "key"]


def mailing_csv(conn: sqlite3.Connection, rows) -> str:
    """Mail-merge file: one line per letter, with the address lines a printer or Word mail merge expects."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow([r["addressee"], r["owner"], r["street"], r["city"], "NY", r["zip"], r["town"], r["county"],
                    r["grade"], r["score"], r["why"], r["year_built"] or "", r["sale_date"],
                    f"{r['sale_price']:.0f}" if r["sale_price"] else "", f"{r['market_value']:.0f}" if r["market_value"] else "",
                    r["deed"], r["key"]])
    return out.getvalue()
