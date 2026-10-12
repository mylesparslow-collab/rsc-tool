from datetime import date, timedelta

from rsc import books, receivables, report
from rsc.web import create_app


class Echo:
    def extract(self, system, user, schema, images=None):
        return {"message": "Hi Jane, just a reminder that invoice 1001-SMI-1 for $5,000.00 is still open. Thank you, Nick"}


def _invoice(conn, smith, days_ago):
    p = books.list_payments(conn, smith)[0]
    books.update_payment(conn, p["id"], invoice_sent=(date.today() - timedelta(days=days_ago)).isoformat())
    return p["id"]


def test_aging_buckets_and_terms(conn, smith):
    pid = _invoice(conn, smith, 20)
    rows = receivables.outstanding(conn)
    assert len(rows) == 1 and rows[0]["days"] == 20 and rows[0]["needs_reminder"] and rows[0]["tone"] == "friendly"
    assert [b["label"] for b in receivables.buckets(rows) if b["rows"]] == ["14 to 29 days"]
    books.update_payment(conn, pid, invoice_sent=(date.today() - timedelta(days=5)).isoformat())
    assert not receivables.outstanding(conn)[0]["needs_reminder"]


def test_draft_uses_the_model_only_when_it_keeps_the_facts(conn, smith):
    pid = _invoice(conn, smith, 35)
    d = receivables.draft(Echo(), conn, pid, "518-555-0100")
    assert "1001-SMI-1" not in d["text"] or "$5,000.00" in d["text"]
    assert d["row"]["tone"] == "firm"
    class Bad:
        def extract(self, *a, **k):
            return {"message": "Pay up."}
    t = receivables.draft(Bad(), conn, pid, "518-555-0100")["text"]
    assert "past due" in t and "$5,000.00" in t and "threat" not in t.lower()
    assert "lawyer" not in t.lower()


def test_reminded_invoices_rest_for_a_week(conn, smith):
    pid = _invoice(conn, smith, 40)
    receivables.mark_reminded(conn, pid, "x")
    assert not receivables.outstanding(conn)[0]["needs_reminder"]
    assert receivables.outstanding(conn, date.today() + timedelta(days=8))[0]["needs_reminder"]


def test_pages_and_report(cfg, conn, smith):
    pid = _invoice(conn, smith, 33)
    c = create_app(cfg, model=Echo()).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    assert b"30 to 59 days" in c.get("/owed").data and b"late invoice" in c.get("/").data
    r = c.post(f"/owed/{pid}/draft", data={"csrf": "t"})
    assert b"Open in Mail" in r.data or b"No email on file" in r.data
    assert b"Marked as reminded" in c.post(f"/owed/{pid}/sent", data={"csrf": "t", "text": "x"}, follow_redirects=True).data
    assert "Late (over 14 days)" in report.render_text(report.build(conn), "x")
