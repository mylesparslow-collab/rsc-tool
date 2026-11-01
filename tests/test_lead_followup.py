"""Instant thank-you to website requests (off by default) and the 7/21-day check-in on leads with no estimate."""
from datetime import date, timedelta

import pytest

from rsc import books, config, guide, leads, pipeline, prefs

from .test_intake import FORM, NoModel, mail
from .test_web import client_and_token


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(leads, "send_ack", lambda address, password, to, subject, body: out.append((to, subject, body)))
    monkeypatch.setattr(config, "mail_password", lambda address: "app-password")
    return out


def today_mail(body=FORM, mid="m1"):
    m = mail(body, mid=mid)
    m.received_at = date.today().isoformat()
    return m


def test_no_thank_you_unless_switched_on(cfg, conn, sent):
    pipeline.process(conn, cfg, [today_mail()], NoModel())
    assert sent == [] and "ack_sent" not in pipeline.pending(conn)[0]["data"]


def test_thank_you_goes_out_once_with_no_price_or_promised_time(cfg, conn, sent):
    prefs.put(conn, "lead_ack", "on")
    pipeline.process(conn, cfg, [today_mail(), today_mail(mid="m2")], NoModel())
    assert len(sent) == 1, "the same person sending twice in a day gets one thank-you"
    to, subject, body = sent[0]
    assert to == "pat.jones@example.com" and body.startswith("Hi Pat,") and "free visit" in body
    assert "$" not in body and "within" not in body and "hour" not in body
    data = pipeline.pending(conn)[0]["data"]
    assert data["ack_sent"] and data["reply"], "Nick's own reply is still drafted for him"


def test_old_requests_and_phone_only_requests_get_no_thank_you(cfg, conn, sent):
    prefs.put(conn, "lead_ack", "on")
    old = today_mail()
    old.received_at = (date.today() - timedelta(days=5)).isoformat()
    phone_only = today_mail("name: Dana Ruiz\ncontact: (518) 555-0177\nmessage: bathroom remodel", mid="m3")
    pipeline.process(conn, cfg, [old, phone_only], NoModel())
    assert sent == [] and len(pipeline.pending(conn)) == 2


def test_gmail_failure_keeps_the_lead_and_says_so(cfg, conn, monkeypatch):
    prefs.put(conn, "lead_ack", "on")
    monkeypatch.setattr(config, "mail_password", lambda address: (_ for _ in ()).throw(RuntimeError("no password")))
    rep = pipeline.process(conn, cfg, [today_mail()], NoModel())
    assert rep.suggestions == 1 and not rep.errors
    assert "didn't go out" in pipeline.pending(conn)[0]["data"]["ack_error"]


def test_setup_switch(cfg, conn):
    c, tok = client_and_token(cfg)
    page = c.get("/setup").get_data(as_text=True)
    assert "Thank new customers right away" in page and "Hi Jane" in page
    c.post("/setup/lead-ack", data={"csrf": tok, "on": "1"})
    assert leads.ack_on(conn)
    c.post("/setup/lead-ack", data={"csrf": tok})
    assert not leads.ack_on(conn)


def test_lead_with_no_estimate_gets_a_check_in_at_7_and_21_days(conn):
    n = books.create_job(conn, "Jones", first_name="Pat", status="Estimate", notes="new back deck")
    assert "draft" not in guide.next_step(conn, books.get_job(conn, n))
    conn.execute("UPDATE jobs SET created_at = ? WHERE number = ?", ((date.today() - timedelta(days=8)).isoformat(), n))
    step = guide.next_step(conn, books.get_job(conn, n))
    assert step["title"] == "Write the estimate" and "8 days ago" in step["why"]
    assert step["draft"].startswith("Hi Pat,") and "deck project" in step["draft"] and "$" not in step["draft"]
    assert "one last time" in leads.lead_checkin(books.get_job(conn, n), 22)
