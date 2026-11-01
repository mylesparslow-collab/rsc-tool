from rsc import books, funnel

from .test_web import client_and_token


def test_grades_follow_what_nick_wants():
    a = funnel.score({"notes": "Full bathroom remodel in Wilton, about $25k, as soon as possible", "phone": "518", "email": "a@b.co"})
    assert a["grade"] == "A" and a["town"] == "Wilton"
    b = funnel.score({"notes": "New deck off the back, next few months", "address": "Clifton Park"})
    assert b["grade"] == "B"
    c = funnel.score({"notes": "Fix a sticky screen door, $200"})
    assert c["grade"] == "Pass"
    roof = funnel.score({"notes": "Need a new roof in Saratoga Springs asap"})
    assert roof["grade"] == "Pass" and roof["other_trade"]


def test_amounts_read_plain_numbers_only():
    assert funnel.amounts("about 15-20k for the kitchen") == [15000, 20000]
    assert funnel.amounts("$25k or 30,000") == [25000, 30000]
    assert funnel.amounts("1940s cape, 3 bedrooms") == []


def test_capacity_counts_running_jobs(conn):
    assert not funnel.capacity(conn)["booked"]
    books.create_job(conn, "One", status="Signed")
    books.create_job(conn, "Two", status="In Progress")
    cap = funnel.capacity(conn)
    assert cap["booked"] and cap["running"] == 2 and cap["slots"] == 2


def test_best_leads_first_and_booked_means_start_date(conn):
    books.create_job(conn, "Deck", notes="New deck in Malta next few months")
    books.create_job(conn, "Bath", notes="Bathroom remodel in Wilton, $30k, asap", phone="518-555-0100", email="b@x.co")
    books.create_job(conn, "Sent", notes="Kitchen", estimate_sent="2026-10-01")   # past the lead stage
    ls = funnel.leads(conn)
    assert [j["last_name"] for j in ls] == ["Bath", "Deck"]
    assert ls[0]["route"]["why"].startswith("Call today") and "start date" not in ls[0]["route"]["why"]
    books.create_job(conn, "One", status="Signed")
    books.create_job(conn, "Two", status="Signed")
    assert "start date" in funnel.leads(conn)[0]["route"]["why"]


def test_leads_page_and_crew_slots(cfg, conn):
    books.create_job(conn, "Deckman", notes="New deck in Malta", phone="518-555-0101")
    c, tok = client_and_token(cfg)
    html = c.get("/leads").get_data(as_text=True)
    assert "Deckman" in html and "tel:518-555-0101" in html
    c.post("/leads/slots", data={"csrf": tok, "crew_slots": "3"})
    assert funnel.crew_slots(conn) == 3
    r = c.post("/leads/slots", data={"csrf": tok, "crew_slots": "lots"}, follow_redirects=True)
    assert "how many jobs" in r.get_data(as_text=True) and funnel.crew_slots(conn) == 3
