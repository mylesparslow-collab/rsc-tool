"""Everything that names the business, in one place: name, logo letters, owner, address, phone, email, area, county.

Defaults are Reclaimed Space Crafters. Another contractor changes them on the Setup page (stored with the job data)
or in config.toml under [business]; nothing else in the app has to be edited. Pages and printouts read `biz` (see
`web.py`), and the model prompts, email drafts, contract and reports go through `localize()`.
"""
import sqlite3

DEFAULTS = {
    "name": "Reclaimed Space Crafters",
    "short": "RSC",
    "owner": "Nick",
    "legal": "Nicholas F. Parslow d/b/a Reclaimed Space Crafters",
    "address": "4 Briar Lane",
    "city": "Saratoga Springs, NY 12866",
    "phone": "518-932-9919",
    "email": "nfparslow@gmail.com",
    "region": "Saratoga Springs, NY",
    "county": "Saratoga County, New York",
    "tagline": "Jobs & billing",
}
LABELS = [
    ("name", "Business name"), ("short", "Short name (logo letters)"), ("owner", "Owner's first name"),
    ("legal", "Legal name on contracts"), ("address", "Street address"), ("city", "City, state ZIP"),
    ("phone", "Phone"), ("email", "Email"), ("region", "Where you work (town, state)"),
    ("county", "County for contract disputes"), ("tagline", "Tagline under the name"),
]
KEY = "brand_"
_current: dict = dict(DEFAULTS)


def current() -> dict:
    return _current


def load(conn: sqlite3.Connection | None, cfg=None) -> dict:
    """Defaults, then config.toml, then what was typed on the Setup page."""
    b = dict(DEFAULTS)
    if cfg is not None:
        for k, attr in (("name", "business_name"), ("phone", "business_phone"), ("email", "business_email")):
            b[k] = getattr(cfg, attr, b[k]) or b[k]
        b.update({k: v for k, v in (getattr(cfg, "business_extra", {}) or {}).items() if k in DEFAULTS and v})
        if b["legal"] == DEFAULTS["legal"] and b["name"] != DEFAULTS["name"]:
            b["legal"] = b["name"]          # a different business never inherits Nick's legal name
    if conn is not None:
        for k in DEFAULTS:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (KEY + k,)).fetchone()
            if row and row[0] != "":
                b[k] = row[0]
        row = conn.execute("SELECT value FROM settings WHERE key = 'owner_name'").fetchone()
        if row and row[0]:
            b["owner"] = row[0]
    return b


def use(conn: sqlite3.Connection | None, cfg=None) -> dict:
    global _current
    _current = load(conn, cfg)
    return _current


def save(conn: sqlite3.Connection, values: dict) -> None:
    for k in DEFAULTS:
        if k in values:
            v = str(values[k]).strip()[:120]
            if v:
                conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (KEY + k, v))
            else:
                conn.execute("DELETE FROM settings WHERE key = ?", (KEY + k,))
    conn.commit()


def is_default() -> bool:
    return _current["name"] == DEFAULTS["name"]


def localize(text: str) -> str:
    """Swap the default names inside a prompt or template for the current business."""
    import re
    b = _current
    if b == DEFAULTS:
        return text
    out = text.replace(DEFAULTS["legal"], b["legal"]).replace(DEFAULTS["name"], b["name"])
    out = out.replace(DEFAULTS["region"], b["region"]).replace(DEFAULTS["county"], b["county"])
    out = re.sub(r"\bRSC\b", b["short"], out)
    out = re.sub(r"\bNick\b", b["owner"], out)
    return out


def address_line() -> str:
    b = _current
    return f"{b['address']}, {b['city']}".strip(", ")
