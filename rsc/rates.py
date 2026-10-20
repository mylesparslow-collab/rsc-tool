"""Is this job priced so the work pays? Labor per crew-hour, markup, and gross margin.

Numbers come from the market research done for Reclaimed Space Crafters: a small remodeler needs to bill roughly
$65-72 per crew-hour, a carpenter costs about $43 an hour once taxes and insurance are added, and a healthy
remodeler keeps about 30% of the price after the direct cost of the job (that is materials at cost x 1.43).
All of these are defaults; Nick changes them on the Pricing page.

Crew-hours are worked out from the two plain sentences already in every estimate ("1 general contractor
full-time, 1 skilled laborer" and "9-11 days on-site"), so nobody types another field:

    crew-hours = people x 8 hours x days        (a part-time person counts as half)
    labor rate = labor price / crew-hours
"""
import math
import re
import sqlite3

from . import estimates

DEFAULTS = {"floor_rate": 65.0, "target_rate": 72.0, "loaded_cost": 43.0, "default_markup": 43.0,
            "gross_target": 30.0, "job_minimum": 500.0}
HOURS_PER_DAY = 8
WORKDAYS_PER_WEEK = 5
WORKDAYS_PER_MONTH = 21
WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_NUM = r"(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six)"


def _num(token: str) -> float:
    token = token.lower()
    return float(WORDS[token]) if token in WORDS else float(token)


def get_settings(conn: sqlite3.Connection) -> dict:
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"rates_{key}",)).fetchone()
        if row and row[0] != "":
            try:
                out[key] = float(row[0])
            except ValueError:
                pass
    return out


def save_settings(conn: sqlite3.Connection, values: dict) -> None:
    for key in DEFAULTS:
        if key not in values:
            continue
        raw = values[key]
        if raw in (None, ""):
            conn.execute("DELETE FROM settings WHERE key = ?", (f"rates_{key}",))
            continue
        v = float(raw)
        if not math.isfinite(v) or v < 0 or (key in ("gross_target",) and v >= 100):
            raise ValueError(f"{key.replace('_', ' ')} is out of range")
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (f"rates_{key}", str(v)))
    conn.commit()


def default_markup(conn: sqlite3.Connection) -> float:
    return get_settings(conn)["default_markup"]


def parse_headcount(text: str) -> float | None:
    """'1 general contractor full-time, 1 crew manager full-time, 1-2 laborers part-time' -> 2.75."""
    if not (text or "").strip():
        return None
    total = 0.0
    for part in re.split(r"[;,\n]+|\band\b|\+|&", text, flags=re.I):
        part = part.strip()
        if not re.search(r"[a-z]", part, re.I):
            continue
        m = re.match(rf"\s*{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?\b", part, re.I)
        if m and not re.match(r"\s*(a|an)\s+(few|couple)", part, re.I):
            n = _num(m.group(1))
            if m.group(2):
                n = (n + _num(m.group(2))) / 2
        else:
            n = 1.0   # "Nick", "Mike" - a name is one person
        if re.search(r"part[- ]?time|as needed|occasional", part, re.I):
            n *= 0.5
        total += n
    return total or None


def parse_days(text: str) -> float | None:
    """'9-11 days on-site', '4-5 weeks', '2 months' -> working days (midpoint of a range)."""
    m = re.search(rf"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*(day|week|wk|month)s?\b", text or "", re.I)
    if not m:
        return None
    n = float(m.group(1))
    if m.group(2):
        n = (n + float(m.group(2))) / 2
    unit = m.group(3).lower()
    return n * (1 if unit == "day" else WORKDAYS_PER_WEEK if unit in ("week", "wk") else WORKDAYS_PER_MONTH)


def analyze(est: dict, settings: dict | None = None, hours_logged: float | None = None) -> dict:
    """Everything the pricing warnings need. `hours_logged` replaces the guess once real hours pass it."""
    s = settings or DEFAULTS
    t = estimates.totals(est)
    heads, days = parse_headcount(est.get("crew", "")), parse_days(est.get("duration", ""))
    guessed = round(heads * days * HOURS_PER_DAY, 1) if heads and days else None
    # Hours logged so far on a job still underway are only part of the total, so they replace the guess only once
    # they exceed it (the job is running long) or when there is no guess.
    use_logged = bool(hours_logged) and (not guessed or hours_logged > guessed)
    hours = hours_logged if use_logged else guessed
    out = {"headcount": heads, "days": days, "crew_hours": hours, "hours_are_logged": use_logged,
           "labor": est["labor"], "rate": None, "gross_pct": None, "warnings": [], "suggested_labor": None,
           "price": t["total"], "level": "ok", "labor_gap": 0.0, "markup_gap": 0.0, "suggested_price": None,
           "summary": None}
    price = t["total"]
    if hours and est["labor"] > 0:
        out["rate"] = round(est["labor"] / hours, 2)
        out["suggested_labor"] = round(s["target_rate"] * hours, 2)
    if price > 0:
        cost = t["direct_cost"] + (hours or 0) * s["loaded_cost"]
        out["gross_pct"] = (price - cost) / price if hours else None
    warn = out["warnings"]
    if out["rate"] is not None:
        if out["rate"] < s["floor_rate"]:
            warn.append(f"Labor works out to ${out['rate']:.0f} per crew-hour ({hours:.0f} crew-hours). "
                        f"Below ${s['floor_rate']:.0f} a crew-hour the work doesn't pay for the crew, truck, insurance and your time. "
                        f"At ${s['target_rate']:.0f} labor would be about ${out['suggested_labor']:,.0f}.")
            out["level"] = "bad"
        elif out["rate"] < s["target_rate"]:
            warn.append(f"Labor works out to ${out['rate']:.0f} per crew-hour. Okay, but under the ${s['target_rate']:.0f} target.")
            out["level"] = "warn"
    if out["gross_pct"] is not None and out["gross_pct"] * 100 < s["gross_target"] - 0.5:
        warn.append(f"Estimated gross margin is {out['gross_pct'] * 100:.0f}% (after materials, subs and crew time at "
                    f"${s['loaded_cost']:.0f} an hour). The goal is {s['gross_target']:.0f}%.")
        if out["level"] == "ok":
            out["level"] = "warn"
    if est["materials"] > 0 and est["markup_pct"] < s["default_markup"] - 0.5:
        out["markup_gap"] = round(est["materials"] * (s["default_markup"] - est["markup_pct"]) / 100, 2)
    if out["markup_gap"] and est["markup_pct"] <= 0:
        warn.append(f"There is no markup on the ${est['materials']:,.0f} of materials, so you'd buy, haul and stand behind "
                    f"them for nothing. At the industry-standard {s['default_markup']:g}% markup that's ${out['markup_gap']:,.0f} more.")
        out["level"] = "bad"
    elif out["markup_gap"]:
        warn.append(f"Materials markup is {est['markup_pct']:g}%. At {s['default_markup']:g}% you'd keep about a "
                    f"{s['gross_target']:.0f}% margin on materials after overhead.")
        if out["level"] == "ok":
            out["level"] = "warn"
    if 0 < price < s["job_minimum"]:
        warn.append(f"This job is ${price:,.0f}. Small jobs take the same driving, setup and paperwork; the usual minimum is ${s['job_minimum']:,.0f}.")
        if out["level"] == "ok":
            out["level"] = "warn"
    if out["rate"] is not None and out["rate"] < s["target_rate"]:
        out["labor_gap"] = round(out["suggested_labor"] - est["labor"], 2)
    if out["labor_gap"] or out["markup_gap"]:
        out["suggested_price"] = round(price + out["labor_gap"] + out["markup_gap"])
        parts = ([f"${s['target_rate']:.0f} a crew-hour"] if out["labor_gap"] else []) + \
                ([f"the industry-standard {s['default_markup']:g}% markup on materials"] if out["markup_gap"] else [])
        out["summary"] = (f"At {' and '.join(parts)}, this job would be about ${out['suggested_price']:,.0f}, "
                          f"${out['suggested_price'] - price:,.0f} more than the ${price:,.0f} it says now.")
    if not hours and est["labor"] > 0:
        warn.append("I can't tell how many crew-hours this is. Say how many people and how many days (the Crew and Duration lines).")
    return out
