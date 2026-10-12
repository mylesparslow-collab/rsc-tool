import json
from datetime import date

import pytest

from rsc import books, contract, crew, estimates, pricing, rates, report
from rsc.web import create_app


# ---------------------------------------------------------------- rates
def test_crew_text_becomes_hours():
    assert rates.parse_headcount("1 general contractor full-time, 1 crew manager full-time, 1-2 laborers part-time") == 2.75
    assert rates.parse_headcount("1 general contractor, 1 skilled laborer") == 2
    assert rates.parse_headcount("Nick and Mike") == 2
    assert rates.parse_headcount("") is None
    assert rates.parse_days("15-18 days on-site. Monday-Friday") == 16.5
    assert rates.parse_days("4-5 weeks") == 22.5
    assert rates.parse_days("whenever") is None


def _est(**kw):
    base = {"labor": 5000, "materials": 4000, "markup_pct": 43, "windows_doors": 0, "debris": 0, "hired_labor": 0,
            "others": [], "crew": "1 general contractor, 1 skilled laborer", "duration": "10 days on-site"}
    base.update(kw)
    return base


def test_hartwell_like_rate_is_flagged_between_floor_and_target():
    a = rates.analyze(_est(labor=8480))          # 2 people x 10 days x 8h = 160 crew-hours -> $53
    assert a["crew_hours"] == 160 and round(a["rate"]) == 53 and a["level"] == "bad"
    assert "$65" in a["warnings"][0] and a["suggested_labor"] == 72 * 160


def test_good_rate_is_quiet():
    a = rates.analyze(_est(labor=12000))
    assert a["level"] == "ok" and a["warnings"] == []


def test_low_markup_and_tiny_job_are_flagged():
    a = rates.analyze(_est(labor=12000, markup_pct=20))
    assert any("markup" in w for w in a["warnings"])
    b = rates.analyze(_est(labor=100, materials=0, crew="Nick", duration="1 day"))
    assert any("minimum" in w for w in b["warnings"])


def test_logged_hours_replace_the_guess():
    a = rates.analyze(_est(labor=8480), hours_logged=200)
    assert a["crew_hours"] == 200 and a["hours_are_logged"] and round(a["rate"]) == 42
    b = rates.analyze(_est(labor=8480), hours_logged=100)     # job still underway: the guess stands
    assert b["crew_hours"] == 160 and not b["hours_are_logged"]


def test_rate_settings_round_trip(conn):
    rates.save_settings(conn, {"floor_rate": "70", "gross_target": ""})
    s = rates.get_settings(conn)
    assert s["floor_rate"] == 70 and s["gross_target"] == 30
    with pytest.raises(ValueError):
        rates.save_settings(conn, {"gross_target": "150"})


def test_new_estimates_use_the_default_markup(conn, smith):
    estimates.create(conn, smith, next(iter(estimates.TEMPLATES)))
    assert estimates.get(conn, smith)["markup_pct"] == 43


def test_pricing_page_saves_rates(cfg):
    app = create_app(cfg)
    c = app.test_client()
    c.get("/pricing")
    with c.session_transaction() as s:
        token = s["csrf"]
    r = c.post("/pricing", data={"csrf": token, "which": "rates", "floor_rate": "68", "target_rate": "75", "loaded_cost": "45",
                                 "default_markup": "43", "gross_target": "30", "job_minimum": "500"}, follow_redirects=True)
    assert r.status_code == 200 and b"68" in r.data


# ---------------------------------------------------------------- contract
def test_contract_has_the_new_york_notice_flagged_for_a_lawyer(conn, smith):
    c = contract.build(conn, smith)
    titles = [t for t, _ in c["sections"]]
    assert any(t.startswith("18. Deposits, cancellation and liens") for t in titles) and titles[-1].startswith("19.")
    body = " ".join(" ".join(p) for t, p in c["sections"] if t.startswith("18."))
    assert "771" in body and "third business day" in body and "lien" in body.lower() and "ATTORNEY" in body.upper()
    assert any("771" in i for i in c["open_items"])


# ---------------------------------------------------------------- crew
class Hours:
    """Stand-in model that returns what a person would read out of the sentence."""
    def __init__(self, entries):
        self.entries = entries

    def extract(self, system, user, schema, images=None):
        if "is_certificate" in schema["properties"]:
            return {"is_certificate": True, "holder": "Dave Co", "kind": "General liability", "insurer": "Liberty",
                    "policy_no": "GL-1", "expires": "2027-03-01"}
        return {"entries": self.entries}


def test_hours_are_checked_and_saved(conn, smith):
    crew.add_person(conn, "Mike Rossi", "employee", 28)
    model = Hours([{"name": "mike", "hours": 8, "day": "Tue", "job_clue": "Smith", "note": ""},
                   {"name": "Dave", "hours": 6, "day": "", "job_clue": "", "note": "demo"},
                   {"name": "Ghost", "hours": 99, "day": "", "job_clue": "Smith", "note": ""},
                   {"name": "Zed", "hours": 4, "day": "", "job_clue": "Nobody", "note": ""}])
    res = crew.log_hours(conn, model, "whatever", default_job=smith, today=date(2026, 10, 9))
    assert [s["name"] for s in res["saved"]] == ["Mike Rossi", "Dave"] and res["new_people"] == ["Dave"]
    assert res["saved"][0]["date"] == "2026-10-06"               # Tuesday before Friday Oct 9
    assert len(res["problems"]) == 2
    assert crew.hours_for_job(conn, smith) == 14
    assert crew.labor_cost_for_job(conn, smith) == round(8 * 28 * 1.18, 2)


def test_hours_without_a_model(conn, smith):
    res = crew.log_hours(conn, None, "Tue Mike 8, Dave 6 on Smith", today=date(2026, 10, 9))
    assert [(s["name"], s["hours"]) for s in res["saved"]] == [("Mike", 8), ("Dave", 6)]
    assert res["saved"][0]["job"].startswith(str(smith))


def test_unknown_job_is_not_guessed(conn, smith):
    res = crew.log_hours(conn, None, "Mike 8 on Nowhere", today=date(2026, 10, 9))
    assert not res["saved"] and res["problems"]


def test_certificate_alerts(conn, smith):
    sub = crew.add_person(conn, "Dave Co", "sub", 45)
    conn.execute("INSERT INTO crew_hours (job_number, crew_id, work_date, hours) VALUES (?, ?, '2026-10-01', 8)", (smith, sub))
    conn.commit()
    today = date(2026, 10, 9)
    texts = " ".join(a["text"] for a in crew.alerts(conn, today))
    assert "no current insurance certificate" in texts and "business's own insurance" in texts
    crew.add_certificate(conn, sub, "General liability", "Liberty", "X1", "2026-10-30")
    assert any("expires in 21 day" in a["text"] for a in crew.alerts(conn, today))
    crew.add_certificate(conn, None, "Workers comp", expires="2026-10-01")
    assert any("expired 8 day" in a["text"] for a in crew.alerts(conn, today))
    assert not any("no current insurance" in a["text"] for a in crew.alerts(conn, today))


def test_certificate_dates_are_validated():
    assert crew.clean_date("3/1/27") == "2027-03-01" and crew.clean_date("2027-13-01") == "" and crew.clean_date("soon") == ""


def test_payroll_calculator_matches_the_research():
    r = crew.payroll_cost(3, 28, 1800)
    assert 26000 <= r["extra_total"] <= 32000 and 4.5 <= r["per_hour"] <= 6


def test_crew_pages_work(cfg, conn, smith):
    app = create_app(cfg, model=Hours([{"name": "Mike", "hours": 8, "day": "", "job_clue": "Smith", "note": ""}]),
                     vision=Hours([]))
    c = app.test_client()
    assert c.get("/crew").status_code == 200
    with c.session_transaction() as s:
        s["csrf"] = "t"
    r = c.post("/crew/hours", data={"csrf": "t", "text": "Mike 8 on Smith"}, follow_redirects=True)
    assert b"Logged Mike 8h" in r.data
    jpg = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"0" * 50
    r = c.post("/crew/certificate", data={"csrf": "t", "holder": "", "file": (__import__("io").BytesIO(jpg), "c.jpg")},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"2027-03-01" in r.data
    assert b"Crew hours" in c.get(f"/jobs/{smith}").data
    assert b"CREW HOURS" in report.render_text(report.build(db_conn(cfg)), "x").encode()
    assert c.post("/crew/hours", data={"text": "x"}).status_code in (400, 403)


def db_conn(cfg):
    from rsc import db
    return db.connect(cfg.db_path)


def test_names_that_start_like_a_weekday_are_names(conn, smith):
    res = crew.log_hours(conn, None, "Monica 8, Dave 6 on Smith", today=date(2026, 10, 9))
    assert [(s["name"], s["hours"]) for s in res["saved"]] == [("Monica", 8), ("Dave", 6)]
    assert res["saved"][0]["date"] == "2026-10-09"
    res = crew.log_hours(conn, None, "Fritz 8 on Smith", today=date(2026, 10, 9))
    assert res["saved"][0]["name"] == "Fritz"


def test_each_person_keeps_their_own_job(conn, smith):
    other = books.create_job(conn, "Delano", first_name="D", status="Signed", contract_total=1000)
    res = crew.log_hours(conn, None, "Mike 8 on Delano, Dave 6 on Smith", today=date(2026, 10, 9))
    assert {s["name"]: s["job"][:4] for s in res["saved"]} == {"Mike": str(other), "Dave": str(smith)}


def test_filler_words_and_lowercase_words_dont_make_people(conn, smith):
    res = crew.log_hours(conn, None, "Mike worked 8 hrs on Smith", today=date(2026, 10, 9))
    assert [s["name"] for s in res["saved"]] == ["Mike"]
    assert [p["name"] for p in crew.people(conn)] == ["Mike"]


def test_short_names_dont_match_longer_ones_and_ambiguity_is_reported(conn, smith):
    al = crew.add_person(conn, "Al", "helper", 20)
    assert crew.find_person(conn, "Alex") is None and crew.find_person(conn, "al")["id"] == al
    crew.add_person(conn, "Mike R"); crew.add_person(conn, "Mike S")
    res = crew.log_hours(conn, None, "Mike 8 on Smith", today=date(2026, 10, 9))
    assert not res["saved"] and "Which" in res["problems"][0]


def test_unreadable_days_are_not_turned_into_today(conn, smith):
    assert crew.resolve_day("2026-02-30") is None and crew.resolve_day("blorp") is None
    assert crew.resolve_day("last friday", date(2026, 10, 9)) == date(2026, 10, 2)
    res = crew.log_hours(conn, Hours([{"name": "Mike", "hours": 8, "day": "2/30", "job_clue": "Smith", "note": ""}]), "x")
    assert not res["saved"] and "day" in res["problems"][0]


def test_nan_is_refused(conn):
    with pytest.raises(ValueError):
        rates.save_settings(conn, {"gross_target": "nan"})
    with pytest.raises(crew.CrewError):
        crew.add_person(conn, "Zed", "helper", float("nan"))
