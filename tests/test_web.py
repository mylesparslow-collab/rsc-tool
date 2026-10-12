import re

from rsc import books, db, pipeline
from rsc.web import create_app

from .conftest import FakeModel
from .test_pipeline import ANSWERS, load


def client_and_token(cfg):
    app = create_app(cfg)
    app.testing = True
    c = app.test_client()
    html = c.get("/").get_data(as_text=True)
    return c, re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def test_every_page_renders(cfg, conn, smith):
    books.add_expense(conn, "2026-10-01", smith, 50, "Lumber")
    pipeline.process(conn, cfg, [load(n) for n in ("receipt.eml", "payment.eml", "lead.eml")], FakeModel(ANSWERS))
    c, _ = client_and_token(cfg)
    for path in ("/", "/review", "/jobs", "/jobs/new", f"/jobs/{smith}", "/expenses", "/codes"):
        r = c.get(path)
        assert r.status_code == 200, path
    assert "3 to review" in c.get("/").get_data(as_text=True)
    r = c.get("/export")
    assert r.status_code == 200 and r.data[:2] == b"PK"


def test_forms_need_csrf(cfg):
    c, _ = client_and_token(cfg)
    assert c.post("/jobs/new", data={"last_name": "Smith"}).status_code == 400


def test_new_job_payment_and_expense_through_the_app(cfg):
    c, tok = client_and_token(cfg)
    r = c.post("/jobs/new", data={"csrf": tok, "last_name": "Parker", "first_name": "Ann"}, follow_redirects=True)
    assert "1001-PAR" in r.get_data(as_text=True)
    c.post("/jobs/1001", data={"csrf": tok, "status": "Signed", "contract_total": "$4,000"})
    c.post("/jobs/1001/payments", data={"csrf": tok, "description": "Deposit", "amount": "4000"})
    r = c.post("/expenses", data={"csrf": tok, "date": "2026-10-08", "charge_to": "1001", "amount": "125.50",
                                  "vendor": "Curtis Lumber"}, follow_redirects=True)
    assert "Expense added" in r.get_data(as_text=True)
    conn = db.connect(cfg.db_path)
    job = books.get_job(conn, 1001)
    assert job["contract_total"] == 4000 and job["schedule_ok"] and job["expenses"] == 125.5


def test_review_approve_with_edit(cfg, conn, smith):
    pipeline.process(conn, cfg, [load("receipt.eml")], FakeModel(ANSWERS))
    sid = pipeline.pending(conn)[0]["id"]
    c, tok = client_and_token(cfg)
    r = c.post(f"/review/{sid}", data={"csrf": tok, "action": "approve", "charge_to": str(smith),
                                       "amount": "109.91", "date": "2026-10-05", "vendor": "Home Depot",
                                       "description": "studs", "category": "Materials"}, follow_redirects=True)
    assert "Added $109.91" in r.get_data(as_text=True)
    assert books.get_job(conn, smith)["expenses"] == 109.91


def test_mail_check_runs_one_at_a_time(cfg):
    import fcntl

    import pytest

    from rsc.web import run_mail_check
    cfg.home.mkdir(exist_ok=True)
    with open(cfg.home / ".mail-check.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(RuntimeError, match="Already checking"):
            run_mail_check(cfg)


def test_jobs_list_links_to_room_model(cfg, conn, smith):
    c, _ = client_and_token(cfg)
    assert f'/jobs/{smith}/model' in c.get("/jobs").get_data(as_text=True)
    assert c.get(f"/jobs/{smith}/model").status_code == 200
