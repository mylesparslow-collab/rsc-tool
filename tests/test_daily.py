import json
from datetime import date
from pathlib import Path

from rsc import books, crew, daily, estimates, prefs
from rsc.web import create_app

EX = Path(__file__).resolve().parent.parent / "examples"


def _delano(conn):
    n = estimates.import_estimate(conn, json.load(open(EX / "delano-1003.json")))
    books.update_job(conn, n, status="In Progress")
    return n


def test_sheet_shows_the_rest_of_the_current_phase(conn):
    n = _delano(conn)
    d = daily.build(conn, date(2026, 10, 12))
    p = d["jobs"][0]
    assert p["phase"].startswith("Field verification") and [s["n"] for s in p["steps"]] == [1, 2, 3, 4, 5]
    assert p["materials"] and p["total"] == 41
    daily.set_steps(conn, n, [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    p = daily.build(conn)["jobs"][0]
    assert p["phase"].startswith("Protection and demolition") and p["steps"][0]["n"] == 6 and not p["materials"]
    daily.set_steps(conn, n, [1, 2], [1])                       # unticking step 2 brings it back
    assert daily.done_steps(conn, n) == {1, 3, 4, 5}


def test_inspection_and_note_and_people_in_the_text(conn):
    n = _delano(conn)
    daily.set_steps(conn, n, list(range(1, 26)), list(range(1, 25)))     # phase 4 has one step left
    crew.add_person(conn, "Mike", "employee", 28)
    conn.execute("INSERT INTO crew_hours (job_number, crew_id, work_date, hours) VALUES (?, 1, ?, 8)", (n, date.today().isoformat()))
    conn.commit()
    daily.set_note(conn, n, date.today().isoformat(), "Dumpster arrives at 9")
    text = daily.render_text(daily.build(conn))
    assert "FROM NICK: Dumpster arrives at 9" in text and "Mike" in text and "[ ] 25." in text
    assert "DELANO" in text.split("\n")[2]


def test_nothing_to_do_when_no_job_is_in_progress(conn, smith):
    d = daily.build(conn)
    assert d["jobs"] == [] and "No jobs are in progress" in daily.render_text(d)


def test_recipients_combine_setup_list_and_crew_emails(conn):
    prefs.put(conn, "daily_to", "nick@gmail.com, bad, mike@x.com")
    crew.add_person(conn, "Mike", "employee", 28, email="MIKE@x.com")
    crew.add_person(conn, "Dave", "sub", 40, email="dave@x.com")
    assert daily.recipients(conn) == ["nick@gmail.com", "mike@x.com", "dave@x.com"]


def test_today_page_ticks_and_progress_page(cfg, conn):
    n = _delano(conn)
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    assert b"Today" in c.get("/today").data and b"Field verification" in c.get("/today").data
    r = c.post(f"/today/job/{n}", data={"csrf": "t", "shown": ["1", "2"], "done": ["1"], "note": "Gate code 1234", "back": "/today"}, follow_redirects=True)
    assert b"Gate code 1234" in r.data and daily.done_steps(conn, n) == {1}
    assert b"1 of 41" in c.get(f"/jobs/{n}/progress").data
    r = c.post(f"/today/job/{n}", data={"csrf": "t", "back": "//evil.example"})
    assert r.headers["Location"].endswith("/today")
    assert c.post(f"/today/job/{n}", data={"shown": "1"}).status_code in (400, 403)


def test_send_without_recipients_is_explained(cfg, conn):
    _delano(conn)
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    r = c.post("/today/send", data={"csrf": "t"}, follow_redirects=True)
    assert b"Not sent" in r.data
