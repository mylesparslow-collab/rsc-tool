from datetime import date, timedelta

from rsc import books, estimates, guide
from rsc.web import create_app


def _title(conn, n):
    s = guide.next_step(conn, books.get_job(conn, n))
    return s["title"] if s else None


def test_a_job_walks_from_lead_to_finished(conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    assert _title(conn, n) == "Write the estimate"
    estimates.create(conn, n, "Kitchen")
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 4000, "markup_pct": 43, "windows_doors": 0, "labor": 3000, "debris": 0, "hired_labor": 0,
                             "upfront_pct": 10, "final_pct": 10},
                   {"duration": "10 days", "crew": "1 general contractor, 1 skilled laborer"}, est["phases"], [])
    assert _title(conn, n) == "Check the labor price"           # $3,000 / 160 crew-hours is far under $65
    estimates.save(conn, n, {"materials": 4000, "markup_pct": 43, "windows_doors": 0, "labor": 12000, "debris": 0, "hired_labor": 0,
                             "upfront_pct": 10, "final_pct": 10},
                   {"duration": "10 days", "crew": "1 general contractor, 1 skilled laborer"}, est["phases"], [])
    assert _title(conn, n).startswith("Send the estimate")
    books.update_job(conn, n, estimate_sent=(date.today() - timedelta(days=9)).isoformat())
    assert _title(conn, n).startswith("Follow up")
    step = guide.next_step(conn, books.get_job(conn, n))
    assert "estimate" in step["draft"] and "$" not in step["draft"]
    assert "one last time" in guide.estimate_followup(books.get_job(conn, n), 25)
    books.update_job(conn, n, estimate_sent=date.today().isoformat())
    assert _title(conn, n).startswith("Waiting on")
    estimates.approve(conn, n, date.today().isoformat())
    assert _title(conn, n).startswith("Invoice payment 1")
    first = books.list_payments(conn, n)[0]
    books.update_payment(conn, first["id"], invoice_sent=date.today().isoformat())
    assert _title(conn, n).startswith("Waiting on payment")
    books.update_payment(conn, first["id"], date_paid=date.today().isoformat(), amount_paid=first["amount"])
    assert _title(conn, n) == "Start logging the work"
    books.add_expense(conn, date.today().isoformat(), n, 100, "Home Depot", "lumber", "Materials")
    assert _title(conn, n).startswith("Next invoice")
    done = guide.steps(conn, books.get_job(conn, n))["done"]
    assert done["estimate"] and done["signed"] and done["paid"] and done["work"] and not done["final"]


def test_home_and_job_pages_show_the_next_step(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    c = create_app(cfg).test_client()
    assert b"Write the estimate" in c.get("/").data and b"Next: Write the estimate" in c.get(f"/jobs/{n}").data


def test_empty_home_welcomes(cfg):
    assert b"how a job goes" in create_app(cfg).test_client().get("/").data


def test_job_page_offers_the_estimate_follow_up_note(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate", email="pat@example.com", phone="518-555-0100")
    estimates.create(conn, n, "Kitchen")
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 4000, "markup_pct": 43, "windows_doors": 0, "labor": 12000, "debris": 0, "hired_labor": 0,
                             "upfront_pct": 10, "final_pct": 10},
                   {"duration": "10 days", "crew": "1 general contractor, 1 skilled laborer"}, est["phases"], [])
    books.update_job(conn, n, estimate_sent=(date.today() - timedelta(days=10)).isoformat())
    page = create_app(cfg).test_client().get(f"/jobs/{n}").data
    assert b"Follow up with Pat" in page and b"mailto:pat@example.com" in page and b"sms:518-555-0100" in page
