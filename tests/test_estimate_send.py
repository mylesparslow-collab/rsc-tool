import io
import re
import smtplib

import pytest
from pypdf import PdfReader

from rsc import books, estimates
from rsc.web import create_app


@pytest.fixture
def c(cfg, conn):
    n = books.create_job(conn, "Smith", first_name="Pat", email="pat@example.com", address="12 Maple Ave")
    estimates.create(conn, n, "Other")
    app = create_app(cfg)
    app.testing = True
    return app.test_client()


def token(c):
    return re.search(r'name="csrf" value="([0-9a-f]+)"', c.get("/").get_data(as_text=True)).group(1)


class Outbox:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, *args, **kw):
        if self.fail:
            raise smtplib.SMTPAuthenticationError(535, b"bad password")
        self.sent.append(args)


def test_pdf_is_a_real_estimate(c, conn):
    res = c.get("/jobs/1001/sow.pdf")
    assert res.mimetype == "application/pdf"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(res.data)).pages)
    assert "SCOPE OF WORK / ESTIMATE" in text and "Pat Smith" in text and "TOTAL FEES" in text


def test_preview_has_a_send_button_and_the_send_page_is_prefilled(c):
    assert "Send to Pat" in c.get("/jobs/1001/sow").get_data(as_text=True)
    page = c.get("/jobs/1001/sow/send").get_data(as_text=True)
    assert 'value="pat@example.com"' in page and "Estimate-1001" in page


def test_without_email_set_up_it_says_so_and_sends_nothing(c, conn, monkeypatch):
    out = Outbox()
    monkeypatch.setattr("rsc.estimate_mail.send", out)
    monkeypatch.delenv("RSC_GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    page = c.get("/jobs/1001/sow/send").get_data(as_text=True)
    assert "Set up email first" in page
    c.post("/jobs/1001/sow/send", data={"csrf": token(c), "to": "pat@example.com", "subject": "s", "body": "b"})
    assert out.sent == [] and books.get_job(conn, 1001)["estimate_sent"] is None


def test_press_send_emails_the_pdf_and_marks_the_job_only_after(c, cfg, conn, monkeypatch):
    monkeypatch.setenv("RSC_GMAIL_APP_PASSWORD", "x")
    out = Outbox()
    monkeypatch.setattr("rsc.estimate_mail.send", out)
    assert books.get_job(conn, 1001)["estimate_sent"] is None
    c.post("/jobs/1001/sow/send", data={"csrf": token(c), "to": "pat@example.com", "subject": "Your estimate", "body": "Hi Pat"})
    assert len(out.sent) == 1
    address, password, to, subject, body, pdf, name = out.sent[0]
    assert (to, subject, body) == ("pat@example.com", "Your estimate", "Hi Pat") and name.startswith("Estimate-1001")
    assert pdf.startswith(b"%PDF")
    assert books.get_job(conn, 1001)["estimate_sent"]


def test_a_failed_send_does_not_mark_the_job(c, conn, monkeypatch):
    monkeypatch.setenv("RSC_GMAIL_APP_PASSWORD", "x")
    monkeypatch.setattr("rsc.estimate_mail.send", Outbox(fail=True))
    page = c.post("/jobs/1001/sow/send", data={"csrf": token(c), "to": "pat@example.com", "subject": "s", "body": "b"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Not sent" in page
    assert books.get_job(conn, 1001)["estimate_sent"] is None


def test_a_bad_address_is_refused(c, conn, monkeypatch):
    monkeypatch.setenv("RSC_GMAIL_APP_PASSWORD", "x")
    out = Outbox()
    monkeypatch.setattr("rsc.estimate_mail.send", out)
    c.post("/jobs/1001/sow/send", data={"csrf": token(c), "to": "a@b.com\nBcc: x@y.com", "subject": "s", "body": "b"})
    assert out.sent == []


def test_an_address_typed_here_is_remembered(c, conn, monkeypatch):
    books.update_job(conn, 1001, email="")
    monkeypatch.setenv("RSC_GMAIL_APP_PASSWORD", "x")
    monkeypatch.setattr("rsc.estimate_mail.send", Outbox())
    c.post("/jobs/1001/sow/send", data={"csrf": token(c), "to": "new@example.com", "subject": "s", "body": "b"})
    assert books.get_job(conn, 1001)["email"] == "new@example.com"


def test_send_page_warns_about_a_low_price_but_still_lets_him_send(c, conn):
    estimates.save(conn, 1001, {"materials": 4000, "markup_pct": 0, "labor": 8480},
                   {"crew": "1 general contractor, 1 skilled laborer", "duration": "10 days on-site"},
                   [{"title": "A", "steps": []}], [])
    page = c.get("/jobs/1001/sow/send").get_data(as_text=True)
    assert "Before you send: check the price" in page and "$53 per crew-hour" in page
    assert "Suggested price" in page and "Send to the client" in page


def test_send_page_is_quiet_when_the_price_is_healthy(c, conn):
    estimates.save(conn, 1001, {"materials": 4000, "markup_pct": 43, "labor": 12000},
                   {"crew": "1 general contractor, 1 skilled laborer", "duration": "10 days on-site"},
                   [{"title": "A", "steps": []}], [])
    assert "Before you send" not in c.get("/jobs/1001/sow/send").get_data(as_text=True)
