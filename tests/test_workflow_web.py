import base64
import re

import pytest

from rsc import books, changeorders, db, estimates
from rsc.config import Config
from rsc.web import create_app

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()


def client(cfg, **kw):
    app = create_app(cfg, **kw)
    app.testing = True
    c = app.test_client()
    return c


def token(c, path="/"):
    html = c.get(path).get_data(as_text=True)
    return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def test_estimate_to_signed_contract_through_the_app(cfg, conn):
    n = books.create_job(conn, "Parker", first_name="Ann", address="9 Elm St")
    c = client(cfg)
    tok = token(c)
    assert "Tell me about the job" in c.get(f"/jobs/{n}/estimate").get_data(as_text=True)
    c.post(f"/jobs/{n}/estimate/new", data={"csrf": tok, "template": "Addition / Enclosure"})
    est = estimates.get(conn, n)
    form = {"csrf": tok, "materials": "6,500", "markup_pct": "0", "windows_doors": "9428", "labor": "16900",
            "debris": "275", "hired_labor": "0", "upfront_pct": "10", "final_pct": "10", "duration": "7 to 8 weeks",
            "labor_not_included": "HVAC", "materials_not_included": "", "open_decisions": "Siding color",
            "phase_title": [p["title"] for p in est["phases"]] + [""],
            "phase_steps": ["\n".join(p["steps"]) for p in est["phases"]] + [""],
            "phase_inspection": [p["inspection"] for p in est["phases"]] + [""],
            "other_label": ["", "", ""], "other_amount": ["", "", ""]}
    assert "Saved" in c.post(f"/jobs/{n}/estimate", data=form, follow_redirects=True).get_data(as_text=True)
    page = c.get(f"/jobs/{n}/estimate").get_data(as_text=True)
    assert "$33,103.00" in page and "$17,618.00" in page
    r = c.post(f"/jobs/{n}/estimate/approve", data={"csrf": tok}, follow_redirects=True)
    assert "Contract signed" in r.get_data(as_text=True)
    job = books.get_job(conn, n)
    assert (job["status"], job["contract_total"], job["schedule_ok"]) == ("Signed", 33103, True)

    sow = c.get(f"/jobs/{n}/sow").get_data(as_text=True)
    assert "PLANNING &amp; SITE PREP" in sow and f"{job['job_id']}-10" in sow and "Open decisions" in sow
    contract = c.get(f"/jobs/{n}/contract").get_data(as_text=True)
    for must in ("not legal advice", "five (5) years", "Change Order", "Saratoga County", "binding arbitration",
                 "Exhibit B", "[OPEN: mutual attorneys"):
        assert must in contract, must


def test_change_order_flow_through_the_app(cfg, conn, smith):
    c = client(cfg)
    tok = token(c)
    r = c.post(f"/jobs/{smith}/change-orders", data={"csrf": tok, "description": "Add a window", "direction": "add",
                                                      "amount": "$1,200", "days_added": "2"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "1001-SMI-CO1" in html and "$11,200.00" in html and "Sign change order" in html
    co = changeorders.list_for_job(conn, smith)[0]
    bad = c.post(f"/change-orders/{co['id']}/sign", data={"csrf": tok, "signer_name": "Jane", "signature": ""},
                 follow_redirects=True).get_data(as_text=True)
    assert "Not signed" in bad and books.get_job(conn, smith)["contract_total"] == 10000
    ok = c.post(f"/change-orders/{co['id']}/sign", data={"csrf": tok, "signer_name": "Jane Smith", "signature": PNG},
                follow_redirects=True).get_data(as_text=True)
    assert "Signed" in ok and books.get_job(conn, smith)["contract_total"] == 11200
    assert c.get(f"/change-orders/{co['id']}/print").status_code == 200
    assert "Add a window" in c.get(f"/jobs/{smith}/contract").get_data(as_text=True)


def test_pricing_page_and_job_links(cfg, conn, smith):
    c = client(cfg)
    tok = token(c)
    assert c.post("/pricing", data={"csrf": tok, "target_margin": "20", "overhead_override": "10"}).status_code == 302
    assert "Pricing check" in c.get("/pricing").get_data(as_text=True)
    job_page = c.get(f"/jobs/{smith}").get_data(as_text=True)
    assert f"/jobs/{smith}/estimate" in job_page and f"/jobs/{smith}/change-orders" in job_page
    assert c.get(f"/jobs/{smith}/contract").status_code == 200  # a contract draft even before an estimate exists


def test_unknown_pages_404(cfg, conn):
    c = client(cfg)
    for path in ("/jobs/999/estimate", "/jobs/999/sow", "/jobs/999/contract", "/change-orders/999", "/jobs/999/change-orders"):
        assert c.get(path).status_code == 404, path


# ---------------------------------------------------------------- phone access
def lan_cfg(tmp_path, pin="correct horse"):
    c = Config(home=tmp_path)
    c.access_pin = pin
    return c


def test_phone_mode_needs_a_pin_in_config(tmp_path):
    with pytest.raises(ValueError):
        create_app(lan_cfg(tmp_path, pin="123"), lan=True)


def test_phone_mode_locks_every_page_until_the_pin_is_entered(tmp_path):
    cfg = lan_cfg(tmp_path)
    c = client(cfg, lan=True)
    for path in ("/", "/jobs", "/pricing", "/export", "/jobs/1001/estimate"):
        r = c.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path
    tok = token(c, "/login")
    assert c.post("/jobs/new", data={"csrf": tok, "last_name": "Hacker"}).status_code == 403
    assert c.post("/login", data={"csrf": tok, "pin": "wrong"}).status_code == 401
    assert c.get("/").status_code == 302
    r = c.post("/login", data={"csrf": tok, "pin": "correct horse"})
    assert r.status_code == 302
    assert c.get("/").status_code == 200


def test_pin_guessing_is_throttled(tmp_path):
    from rsc import web
    web._LOGIN_FAILS.clear()
    c = client(lan_cfg(tmp_path), lan=True)
    tok = token(c, "/login")
    codes = [c.post("/login", data={"csrf": tok, "pin": f"guess{i}"}).status_code for i in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert c.post("/login", data={"csrf": tok, "pin": "correct horse"}).status_code == 429
    web._LOGIN_FAILS.clear()


def test_normal_mode_has_no_login(cfg):
    c = client(cfg)
    assert c.get("/").status_code == 200
    assert c.get("/login").status_code == 302


def test_old_database_is_upgraded(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE jobs (number INTEGER PRIMARY KEY, last_name TEXT, code TEXT);
        CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, job_number INTEGER NOT NULL, seq INTEGER NOT NULL,
          description TEXT NOT NULL DEFAULT '', due_when TEXT NOT NULL DEFAULT '', amount REAL NOT NULL DEFAULT 0,
          invoice_sent TEXT, date_paid TEXT, amount_paid REAL, notes TEXT NOT NULL DEFAULT '', UNIQUE (job_number, seq));
        INSERT INTO payments (job_number, seq, amount) VALUES (1001, 1, 500);""")
    old.commit()
    old.close()
    conn = db.connect(path)
    db.init(conn)
    row = conn.execute("SELECT kind, change_order_id, amount FROM payments").fetchone()
    assert tuple(row) == ("manual", None, 500)
    db.init(conn)  # running it again is harmless


def test_negative_money_reads_naturally(cfg, conn):
    from rsc.web import create_app
    app = create_app(cfg)
    with app.test_request_context("/"):
        money = app.jinja_env.globals.get("money") or app.update_template_context({}) or {}
        ctx = {}
        app.update_template_context(ctx)
        assert ctx["money"](-1475) == "-$1,475.00" and ctx["money"](1475) == "$1,475.00"


def test_phone_mode_also_locks_model_pages_and_photos(tmp_path):
    c = client(lan_cfg(tmp_path), lan=True)
    for path in ("/jobs/1001/model", "/jobs/1001/model?view=client", "/jobs/1001/photo/before"):
        r = c.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path


def test_oversized_upload_is_refused(cfg, conn, smith):
    import io
    c = client(cfg)
    tok = token(c)
    big = io.BytesIO(b"\xff\xd8\xff" + b"0" * (13 * 1024 * 1024))
    r = c.post(f"/jobs/{smith}/photo/before", data={"csrf": tok, "file": (big, "x.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 413


def test_pin_in_config_gates_even_without_lan_flag(cfg):
    cfg.access_pin = "sawdust42"
    c = client(cfg)
    r = c.get("/jobs")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert c.get("/login").status_code == 200
