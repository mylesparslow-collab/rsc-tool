from datetime import date, timedelta

import pytest

from rsc import books, funnel

from .test_web import client_and_token

NEXT_YEAR = (date.today() + timedelta(days=365)).isoformat()


def lead(conn, last, notes, **kw):
    return books.create_job(conn, last, notes=notes, **kw)


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


def test_booked_b_lead_needs_consent_before_passing(conn):
    books.create_job(conn, "One", status="Signed")
    books.create_job(conn, "Two", status="Signed")
    n = lead(conn, "Deckman", "New deck in Malta next few months")
    (j,) = funnel.leads(conn)
    assert j["number"] == n and j["route"]["action"] == "ask"
    pid = funnel.save_partner(conn, {"name": "Pat Builder", "email": "pat@example.com", "trades": "decks",
                                     "insurance_expires": NEXT_YEAR})
    with pytest.raises(books.BooksError, match="haven't said yes"):
        funnel.can_pass(conn, n, pid)
    funnel.record_consent(conn, n, "on the phone")
    (j,) = funnel.leads(conn)
    assert j["route"]["action"] == "pass"
    funnel.mark_passed(conn, n, pid)
    assert books.get_job(conn, n)["status"] == "Passed on"
    assert funnel.leads(conn) == []


def test_website_box_counts_as_consent_but_google_lsa_never_passes(conn):
    n = lead(conn, "Web", "Kitchen. If you're booked, it's OK to pass my request to one contractor you trust.")
    assert funnel.consent(conn, books.get_job(conn, n))["how"].startswith("Ticked the box")
    m = lead(conn, "Lsa", "Bathroom. OK to pass my request to one contractor you trust. (Found us: Google Local Services.)")
    pid = funnel.save_partner(conn, {"name": "Pat", "email": "pat@example.com", "insurance_expires": NEXT_YEAR})
    with pytest.raises(books.BooksError, match="Local Services"):
        funnel.can_pass(conn, m, pid)


def test_partner_without_current_insurance_gets_nothing(conn):
    n = lead(conn, "Roofer", "New roof please")
    funnel.record_consent(conn, n, "by email")
    old = funnel.save_partner(conn, {"name": "Old Ins", "email": "o@example.com", "insurance_expires": "2020-01-01"})
    none = funnel.save_partner(conn, {"name": "No Ins", "email": "n@example.com"})
    for pid in (old, none):
        with pytest.raises(books.BooksError, match="can't take leads"):
            funnel.can_pass(conn, n, pid)
    with pytest.raises(books.BooksError):
        funnel.save_partner(conn, {"name": "Bad", "fee_pct": "40"})


def test_fee_is_computed_in_code(conn):
    n = lead(conn, "Porch", "Porch enclosure")
    funnel.record_consent(conn, n, "in person")
    pid = funnel.save_partner(conn, {"name": "Pat", "email": "pat@example.com", "insurance_expires": NEXT_YEAR, "fee_pct": "5"})
    rid = funnel.mark_passed(conn, n, pid)
    with pytest.raises(books.BooksError):
        funnel.referral_outcome(conn, rid, "Paid")
    funnel.referral_outcome(conn, rid, "Won", "$24,500")
    L = funnel.ledger(conn)
    assert L["owed"] == 1225.0 and L["won"] == 1
    funnel.referral_outcome(conn, rid, "Paid")
    assert funnel.ledger(conn)["paid"] == 1225.0 and funnel.ledger(conn)["owed"] == 0


def test_handoff_drafts_share_only_what_the_partner_needs():
    job = {"number": 1, "first_name": "Ann", "last_name": "Lee", "email": "ann@example.com", "phone": "518-555-0100",
           "address": "Malta", "notes": "Deck. If you’re booked, it’s OK to pass my request to one contractor you trust."}
    d = funnel.handoff_drafts(job, {"name": "Pat Builder", "company": "", "phone": "", "email": "p@x.co", "fee_pct": 4.0}, "Nick")
    assert "Pat Builder" in d["client"]["text"] and d["client"]["to"] == "ann@example.com"
    assert "pass my request" not in d["partner"]["text"] and "Project: Deck." in d["partner"]["text"]
    assert "518-555-0100" in d["partner"]["text"] and "4% of the contract" in d["partner"]["text"]


def test_pages_render_and_pass_flow(cfg, conn):
    books.create_job(conn, "One", status="Signed")
    books.create_job(conn, "Two", status="Signed")
    n = lead(conn, "Deckman", "New deck in Malta", email="d@example.com")
    c, tok = client_and_token(cfg)
    assert "Deckman" in c.get("/leads").get_data(as_text=True)
    c.post("/partners", data={"csrf": tok, "name": "Pat Builder", "email": "pat@example.com", "trades": "decks",
                              "insurance_expires": NEXT_YEAR, "fee_pct": "4"})
    assert "Pat Builder" in c.get("/partners").get_data(as_text=True)
    pid = funnel.list_partners(conn)[0]["id"]
    r = c.get(f"/leads/{n}/pass/{pid}", follow_redirects=True)
    assert "haven" in r.get_data(as_text=True)    # no consent yet: sent back with the reason
    c.post(f"/leads/{n}/consent", data={"csrf": tok, "how": "on the phone"})
    r = c.get(f"/leads/{n}/pass/{pid}")
    assert r.status_code == 200 and "mailto:pat%40example.com" in r.get_data(as_text=True)
    c.post(f"/leads/{n}/pass/{pid}", data={"csrf": tok})
    assert books.get_job(conn, n)["status"] == "Passed on"
    c.post("/leads/slots", data={"csrf": tok, "crew_slots": "3"})
    assert funnel.crew_slots(conn) == 3
    assert c.get(f"/jobs/{n}").status_code == 200
