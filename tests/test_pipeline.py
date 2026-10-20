from rsc import books, pipeline
from rsc.mail import parse

from .conftest import FIXTURES, FakeModel


def load(name):
    return parse((FIXTURES / name).read_bytes())


ANSWERS = {
    "Your Electronic Receipt": {"kind": "expense_receipt", "vendor": "The Home Depot", "date": "2026-10-05",
                                "total": 109.91, "description": "2x4 studs", "category": "Materials",
                                "job_clue": "1002-SMI"},
    "Payment received: Invoice 1002-SMI-2": {"kind": "client_payment", "payer_name": "Jane Smith",
                                             "amount_received": 2500, "date": "2026-10-06",
                                             "reference": "1002-SMI-2"},
    "Kitchen remodel estimate?": {"kind": "new_lead", "lead_name": "Pat Okafor", "lead_phone": "518-555-0142",
                                  "lead_address": "12 Maple Ave, Wilton", "lead_project": "Kitchen remodel"},
}


def test_html_receipt_is_readable():
    mail = load("receipt.eml")
    assert mail.sender == "homedepotreceipt@email.homedepot.com"
    assert "1002-SMI" in mail.body and "$109.91" in mail.body
    assert mail.received_at == "2026-10-05"


def test_end_to_end_suggest_then_approve(conn, cfg):
    books.create_job(conn, "Whitcomb", status="Complete", contract_total=33103)
    smith = books.create_job(conn, "Smith", first_name="Jane", status="Signed", contract_total=10000)
    books.add_payment(conn, smith, 7500, "Deposit")
    books.add_payment(conn, smith, 2500, "Phase 1")
    model = FakeModel(ANSWERS)
    mails = [load(n) for n in ("receipt.eml", "payment.eml", "lead.eml", "newsletter.eml")]

    report = pipeline.process(conn, cfg, mails, model)
    assert (report.new, report.suggestions, report.skipped) == (4, 3, 1)
    assert len(model.calls) == 5 and not any("newsletter" in c.lower() for c in model.calls), "the newsletter must never reach the model (3 emails read + 1 lead reply drafted + 1 rough range)"

    items = {s["kind"]: s for s in pipeline.pending(conn)}
    assert items["expense"]["data"]["charge_to"] == "1002"
    assert items["payment"]["data"]["payment_id"] == "1002-SMI-2"
    assert items["lead"]["data"]["name"] == "Pat Okafor"

    # Nothing has touched the books yet.
    assert books.get_job(conn, smith)["expenses"] == 0

    assert "1002" in pipeline.approve(conn, items["expense"]["id"], {})
    assert "1002-SMI-2" in pipeline.approve(conn, items["payment"]["id"], {})
    assert "1003-OKA" in pipeline.approve(conn, items["lead"]["id"], {})

    job = books.get_job(conn, smith)
    assert job["expenses"] == 109.91 and job["paid"] == 2500
    lead = books.get_job(conn, 1003)
    assert (lead["status"], lead["first_name"], lead["phone"]) == ("Estimate", "Pat", "518-555-0142")
    assert pipeline.pending(conn) == []

    # Running again over the same mailbox does nothing twice.
    again = pipeline.process(conn, cfg, mails, model)
    assert again.new == 0 and len(model.calls) == 5


def test_unmatched_receipt_waits_for_a_choice(conn, cfg):
    answers = {"Your Electronic Receipt": {**ANSWERS["Your Electronic Receipt"], "job_clue": ""}}
    mail = load("receipt.eml")
    mail.body = mail.body.replace("1002-SMI", "")
    pipeline.process(conn, cfg, [mail], FakeModel(answers))
    item = pipeline.pending(conn)[0]
    assert item["data"]["charge_to"] == ""
    try:
        pipeline.approve(conn, item["id"], {})
        raise AssertionError("approve without a job should fail")
    except books.BooksError:
        pass
    books.create_job(conn, "Lee")
    pipeline.approve(conn, item["id"], {"charge_to": "RSC-200"})
    assert books.list_expenses(conn)[0]["rsc_code"] == "RSC-200"


def test_match_by_client_name_and_address(conn, smith):
    from rsc.extract import match_job
    assert match_job(conn, "Delivery to 45 Oak St")[0] == smith
    assert match_job(conn, "Order for Smith job")[0] == smith
    assert match_job(conn, "nothing useful here")[0] is None


def test_model_failure_on_one_email_is_retried_later(conn, cfg):
    class Broken:
        def extract(self, *a):
            raise TimeoutError("model timed out")

    report = pipeline.process(conn, cfg, [load("lead.eml")], Broken())
    assert report.errors and pipeline.pending(conn) == []
    report = pipeline.process(conn, cfg, [load("lead.eml")], FakeModel(ANSWERS))
    assert report.suggestions == 1


def test_dismiss(conn, cfg):
    pipeline.process(conn, cfg, [load("lead.eml")], FakeModel(ANSWERS))
    sid = pipeline.pending(conn)[0]["id"]
    pipeline.dismiss(conn, sid)
    assert pipeline.pending(conn) == [] and books.list_jobs(conn) == []
