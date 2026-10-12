import re
from datetime import date

from rsc import books, config, followups, leads, margins, pipeline, prefs, report
from rsc.web import create_app

from .conftest import FIXTURES, FakeModel
from .test_pipeline import ANSWERS, load


def test_availability_is_read_from_plain_words():
    assert leads.parse_availability("Tuesdays and Thursdays at 3:30pm or 5pm") == ([1, 3], ["3:30 PM", "5:00 PM"])
    assert leads.parse_availability("") == ([0, 1, 2, 3, 4], ["4:00 PM"])
    assert leads.parse_availability("weekends 10am")[0] == [5, 6]


def test_visit_slots_start_tomorrow_and_follow_the_days():
    slots = leads.visit_slots("Tue and Thu at 4pm", today=date(2026, 10, 10), n=3)  # a Saturday
    assert slots == ["Tuesday, October 13 at 4:00 PM", "Thursday, October 15 at 4:00 PM", "Tuesday, October 20 at 4:00 PM"]


def test_new_lead_comes_with_a_reply_that_offers_visit_times(conn, cfg):
    pipeline.process(conn, cfg, [load("lead.eml")], FakeModel(ANSWERS))
    d = pipeline.pending(conn)[0]["data"]
    assert "Pat" in d["reply"] and "4:00 PM" in d["reply"] and d["reply_subject"].startswith("Re:")
    assert d["reply_to"]


def test_reply_falls_back_when_the_model_writes_nonsense(conn):
    class Bad:
        def extract(self, *a, **k):
            return {"message": "ok"}
    out = leads.draft_reply(Bad(), conn, {"name": "Pat Okafor", "project": "kitchen"}, "518-932-9919")
    assert out.startswith("Hi Pat") and "518-932-9919" in out


def test_completing_a_job_queues_follow_ups_and_reopening_drops_them(conn, smith):
    books.update_job(conn, smith, status="Complete")
    items = followups.upcoming(conn)
    assert [f["kind"] for f in items] == ["review", "checkin"]
    assert items[0]["due_date"] > date.today().isoformat() and items[1]["due_date"] > items[0]["due_date"]
    books.update_job(conn, smith, status="Complete", notes="again")  # no change in status: nothing doubles
    assert len(followups.upcoming(conn)) == 2
    books.update_job(conn, smith, status="In Progress")
    assert followups.upcoming(conn) == []


def test_follow_up_message_uses_the_review_link_and_is_kept(conn, smith):
    prefs.put(conn, "review_url", "https://g.page/r/abc")
    books.update_job(conn, smith, status="Complete")
    f = followups.upcoming(conn)[0]
    text = followups.draft(None, conn, f["id"], "518-932-9919")
    assert "https://g.page/r/abc" in text and text.startswith("Hi Jane")
    assert followups.draft(None, conn, f["id"], "x") == text
    followups.mark(conn, f["id"], "sent")
    assert [x["kind"] for x in followups.upcoming(conn)] == ["checkin"]
    assert followups.due(conn, today=date(2027, 12, 1))[0]["kind"] == "checkin"


def test_margin_flags_over_budget_and_target(conn, smith):
    from rsc import estimates
    conn.execute("INSERT INTO estimates (job_number, template, materials, markup_pct) VALUES (?, 'blank', 4000, 20)", (smith,))
    books.update_job(conn, smith, status="In Progress")
    m = margins.all_margins(conn)[0]
    assert m["status"] == "ok" and round(m["margin_projected"], 2) == 0.6  # 10,000 contract, 4,000 budget
    books.add_expense(conn, "2026-10-05", str(smith), 4500, "Lumber yard", "framing", "Materials", "")
    m = margins.all_margins(conn)[0]
    assert m["status"] == "over" and "500" in m["why"]


def test_weekly_report_numbers_and_text(conn, smith):
    books.update_job(conn, smith, status="In Progress")
    p = books.list_payments(conn)[0]
    books.update_payment(conn, p["id"], invoice_sent=date.today().isoformat())
    books.update_payment(conn, p["id"], date_paid=date.today().isoformat(), amount_paid=5000)
    r = report.build(conn)
    assert r["collected"] == 5000 and len(r["active"]) == 1
    text = report.render_text(r, report.opening(None, r))
    assert "Collected this week: $5,000" in text and "1001-SMI" in text
    assert "<h3" in report.render_html(text)


def test_report_sends_only_to_listed_people(conn, smith, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0): sent["host"] = host
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, user, pw): sent["login"] = user
        def send_message(self, msg): sent["to"] = msg["To"]; sent["subject"] = msg["Subject"]

    monkeypatch.setattr(report.smtplib, "SMTP_SSL", FakeSMTP)
    try:
        report.send(conn, "biz@gmail.com", "pw", "hello", "s")
        assert False, "no recipients yet"
    except ValueError:
        pass
    prefs.put(conn, "report_to", "nick@x.com, myles@x.com; bad address")
    assert report.send(conn, "biz@gmail.com", "pw", "hello", "s") == ["nick@x.com", "myles@x.com"]
    assert sent["to"] == "nick@x.com, myles@x.com" and sent["login"] == "biz@gmail.com"


def test_setup_page_saves_address_prefs_and_password(cfg, conn, monkeypatch):
    saved = {}
    monkeypatch.setattr(config, "save_mail_password", lambda a, p: saved.update(a=a, p=p))
    monkeypatch.setattr(config, "mail_password", lambda a: saved.get("p") or (_ for _ in ()).throw(RuntimeError("none")))
    monkeypatch.setattr("rsc.ops_web.GmailReader.check", lambda self: None)
    cfg.mail.address = ""
    app = create_app(cfg, model=FakeModel({}))
    app.testing = True
    c = app.test_client()
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', c.get("/setup").get_data(as_text=True)).group(1)
    page = c.post("/setup", data={"csrf": tok, "address": "biz@gmail.com", "password": "abcd efgh ijkl mnop", "report_to": "n@x.com",
                                  "owner_name": "Nick", "visit_when": "Tuesdays at 4pm", "review_url": "https://g.page/r/z"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Gmail is connected" in page and saved == {"a": "biz@gmail.com", "p": "abcdefghijklmnop"}
    assert 'address = "biz@gmail.com"' in (cfg.home / "config.toml").read_text()
    assert "Finish setup" not in c.get("/").get_data(as_text=True)
    assert "Tuesday" in page


def test_pages_render(cfg, conn, smith):
    books.update_job(conn, smith, status="Complete")
    app = create_app(cfg, model=FakeModel({}))
    app.testing = True
    c = app.test_client()
    for path in ("/", "/followups", "/report", "/margins", "/setup"):
        assert c.get(path).status_code == 200, path
    assert "Review" in c.get("/followups").get_data(as_text=True) or "review" in c.get("/followups").get_data(as_text=True)
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', c.get("/followups").get_data(as_text=True)).group(1)
    fid = followups.upcoming(conn)[0]["id"]
    out = c.post(f"/followups/{fid}/draft", data={"csrf": tok}, follow_redirects=True).get_data(as_text=True)
    assert "Hi Jane" in out and "Mark sent" in out
    out = c.post("/report/send", data={"csrf": tok}, follow_redirects=True).get_data(as_text=True)
    assert "Not sent" in out  # no recipients yet
