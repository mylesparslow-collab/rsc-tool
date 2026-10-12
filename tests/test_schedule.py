import json
from datetime import date
from pathlib import Path

from rsc import books, crew, estimates, schedule
from rsc.web import create_app

MON = date(2026, 10, 12)


def _setup(conn):
    mike, dave = crew.add_person(conn, "Mike Carter"), crew.add_person(conn, "Dave Ross")
    a = books.create_job(conn, "Delano", status="In Progress")
    b = books.create_job(conn, "Hartwell", status="In Progress")
    return mike, dave, a, b


def test_parse_ranges_and_plan(conn):
    mike, dave, a, b = _setup(conn)
    r = schedule.add(conn, "Mon-Wed Delano Mike Dave; Thu Hartwell Mike", MON)
    assert r == {"saved": 7, "problems": []}
    w = schedule.week(conn, MON)
    by = {j["job"]["last_name"]: j for j in w["jobs"]}
    assert [e["name"] for e in by["Delano"]["cells"]["2026-10-13"]] == ["Dave Ross", "Mike Carter"]
    assert [e["name"] for e in by["Hartwell"]["cells"]["2026-10-15"]] == ["Mike Carter"]
    assert not w["conflicts"]
    assert schedule.add(conn, "Mon-Wed Delano Mike Dave", MON)["saved"] == 0     # no duplicates


def test_conflicts_and_problems(conn):
    mike, dave, a, b = _setup(conn)
    schedule.add(conn, "Tue Delano Mike; Tue Hartwell Mike", MON)
    assert schedule.week(conn, MON)["conflicts"] == [("Mike Carter", "2026-10-13")]
    r = schedule.add(conn, "Delano Mike; Wed Nowhere Mike; Fri Mike", MON)
    assert r["saved"] == 0 and len(r["problems"]) == 3
    crew.add_person(conn, "Mike Dunn")
    assert "more than one" in schedule.add(conn, "Fri Delano Mike", MON)["problems"][0]


def test_unnamed_crew_and_page(cfg, conn):
    _setup(conn)
    schedule.add(conn, "Fri Delano", MON)
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    page = c.get("/week?start=2026-10-12").data
    assert b"Crew" in page and b"Delano" in page
    r = c.post("/week/plan", data={"csrf": "t", "start": "2026-10-12", "plan": "Sat Hartwell Mike"}, follow_redirects=True)
    assert b"Planned 1 spot" in r.data
    assert c.get("/week?start=garbage").status_code == 200


def test_planned_people_lead_the_daily_sheet(conn):
    from rsc import daily
    n = estimates.import_estimate(conn, json.load(open(Path(__file__).resolve().parent.parent / "examples" / "delano-1003.json")))
    books.update_job(conn, n, status="In Progress")
    crew.add_person(conn, "Mike Carter")
    schedule.add(conn, "Mon Delano Mike", MON)
    assert daily.build(conn, MON)["jobs"][0]["people"][0] == "Mike Carter"
    assert "Mike Carter" in daily.render_text(daily.build(conn, MON))
