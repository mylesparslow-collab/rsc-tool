"""Gaps found by running one invented job from the first email to the review request (2026-10-15)."""
import csv
import io

from rsc import assist, books, daily, estimates, guide, leads, pipeline, quickbooks
from rsc.mail import parse
from rsc.web import create_app

from .conftest import FakeModel
from .test_workflow_web import client, token

FORM_LEAD = b"""From: Website <forms@example-site.com>
To: nfparslow@gmail.com
Subject: New message from your website
Message-ID: <form-1@example-site.com>
Content-Type: text/plain; charset=utf-8

Name: Theo Brandvold
Email: theo.b@example.net
Message: Looking for a quote on a new back deck, about 12x16.
"""


def test_expense_read_from_text_saves_to_the_expenses_page(cfg, conn, smith):
    """After 'Read it', the checked form must post to /expenses, not back to /expenses/read (which dropped it)."""
    model = FakeModel({})
    model.extract = lambda *a, **k: {**FakeModel.BLANK, "kind": "expense_receipt", "vendor": "Curtis Lumber",
                                     "total": 85, "job_clue": "Smith"}
    c = client(cfg, model=model)
    tok = token(c)
    html = c.post("/expenses/read", data={"csrf": tok, "typed": "Curtis 85 for Smith"}).get_data(as_text=True)
    assert 'action="/expenses"' in html.split("Check this, then add it")[0].rsplit("<form", 1)[1]
    c.post("/expenses", data={"csrf": tok, "charge_to": str(smith), "date": "2026-10-15", "vendor": "Curtis Lumber",
                              "description": "", "category": "Materials", "amount": "85.00", "paid_with": "", "notes": ""})
    assert [e["amount"] for e in books.list_expenses(conn, smith)] == [85]


def test_walk_through_is_not_a_rough_in():
    assert assist.inspection_for("Finish", ["Paint", "Punch list", "Walk-through"], True) == "Final inspection"
    assert assist.inspection_for("Rough-in", ["Rough plumbing"], False) == "Rough-in inspection"


def test_quickbooks_memo_keeps_its_closing_parenthesis(conn, smith):
    row = next(csv.DictReader(io.StringIO(quickbooks.invoices_csv(conn))))
    assert row["ItemDescription"] == "Deposit + materials (At signing)"


def test_date_paid_without_an_amount_means_paid_in_full(cfg, conn, smith):
    c = client(cfg)
    tok = token(c)
    pk = books.list_payments(conn, smith)[0]["id"]
    c.post(f"/payments/{pk}", data={"csrf": tok, "invoice_sent": "2026-10-01", "date_paid": "2026-10-10", "amount_paid": ""})
    p = books.list_payments(conn, smith)[0]
    assert p["status"] == "Paid" and p["amount_paid"] == 5000


def test_finished_phase_says_invoice_now(conn, smith):
    estimates.create(conn, smith, "Kitchen")
    books.update_payment(conn, books.list_payments(conn, smith)[0]["id"], invoice_sent="2026-10-01",
                         date_paid="2026-10-02", amount_paid=5000)
    books.add_expense(conn, "2026-10-03", str(smith), 100, "Home Depot", "studs")
    pk = books.list_payments(conn, smith)[1]["id"]
    books.update_payment(conn, pk, due_when="Upon completion of Phase 1 (Demo), Steps 1–3")
    job = books.get_job(conn, smith)
    assert guide.next_step(conn, job)["title"].startswith("Next invoice")
    daily.set_steps(conn, smith, [1, 2, 3], [1, 2, 3])
    assert guide.next_step(conn, job)["title"].startswith("Invoice ") and "now" in guide.next_step(conn, job)["title"]


def test_complete_job_with_final_payment_not_invoiced_asks_for_it_before_the_review(cfg, conn, smith):
    for p in books.list_payments(conn, smith)[:2]:
        books.update_payment(conn, p["id"], invoice_sent="2026-10-01", date_paid="2026-10-02", amount_paid=p["amount"])
    books.update_job(conn, smith, status="Complete")
    step = guide.next_step(conn, books.get_job(conn, smith))
    assert step["title"].startswith(f"Invoice {smith}-SMI-3")
    c = client(cfg)
    assert f"Invoice {smith}-SMI-3" in c.get("/").get_data(as_text=True)  # still on Home after leaving the open-jobs list


def test_start_estimate_goes_to_the_estimate(cfg, conn):
    pipeline.process(conn, cfg, [parse(FORM_LEAD)], FakeModel({}))
    sid = pipeline.pending(conn)[0]["id"]
    c = client(cfg)
    r = c.post(f"/review/{sid}", data={"csrf": token(c), "action": "approve", "name": "Theo Brandvold",
                                       "email": "theo.b@example.net", "phone": "", "address": "", "project": "Back deck"})
    number = books.list_jobs(conn)[0]["number"]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/jobs/{number}/estimate")


def test_form_leads_still_arrive_when_the_ai_is_off(cfg, conn, monkeypatch):
    from rsc import web
    from rsc.llm import ModelUnavailable

    class Off:
        def __init__(self, *a, **k):
            pass

        def check(self):
            raise ModelUnavailable("Ollama isn't running")

    class Reader:
        def __init__(self, *a, **k):
            pass

        def fetch_since(self, mailbox, since, limit):
            return [parse(FORM_LEAD)]

    monkeypatch.setattr(web, "OllamaModel", Off)
    monkeypatch.setattr(web, "GmailReader", Reader)
    monkeypatch.setattr(web, "mail_password", lambda a: "x")
    monkeypatch.setattr(web.models, "apply_choice", lambda cfg: None)
    report = web.run_mail_check(cfg)
    assert report.suggestions == 1
    lead = pipeline.pending(conn)[0]["data"]
    assert "your deck project" in lead["reply"]   # the plain template, worded for a client


def test_fallback_reply_names_the_kind_of_work():
    text = leads.fallback_reply("Theo B", "Looking for a quote on a new back deck", ["Fri 4 PM"], "Nick", "518")
    assert "reaching out about your deck project." in text and "Looking for" not in text
    assert "about your project." in leads.fallback_reply("Al", "Something odd", ["Fri 4 PM"], "Nick", "518")


def test_subcontractor_cost_is_flagged():
    out = assist._clean_prices({"lines": [{"item": "Plumber", "kind": "hired_labor", "amount": 2400, "stated_by_nick": True},
                                          {"item": "Labor", "kind": "labor", "amount": 9000, "stated_by_nick": True}]})
    assert any("not added to the client's price" in n for n in out["assumptions"])
