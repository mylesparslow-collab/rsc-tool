"""The step tracker on job pages, the glow on the next thing to press, and the Next task button."""
from datetime import date

from rsc import books, estimates, guide
from rsc.web import create_app


def _app(cfg, setup_done=True):
    app = create_app(cfg)
    app.jinja_env.globals["setup_state"] = lambda: {"email": setup_done, "password": setup_done, "recipients": True}
    return app.test_client()


def _price_ok(conn, n):
    estimates.create(conn, n, "Kitchen")
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 4000, "markup_pct": 43, "windows_doors": 0, "labor": 12000, "debris": 0, "hired_labor": 0,
                             "upfront_pct": 10, "final_pct": 10},
                   {"duration": "10 days", "crew": "1 general contractor, 1 skilled laborer"}, est["phases"], [])


def _current(conn, n):
    return guide.stage(conn, books.get_job(conn, n))["label"]


def test_stage_moves_along_with_the_job(conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    assert _current(conn, n) == "Write the estimate"
    _price_ok(conn, n)
    assert _current(conn, n) == "Send it"
    books.update_job(conn, n, estimate_sent=date.today().isoformat())
    assert _current(conn, n) == "Get it signed"
    estimates.approve(conn, n, date.today().isoformat())
    st = guide.stage(conn, books.get_job(conn, n))
    assert st["label"] == "Do the work, get paid" and st["number"] == 4
    assert [s["state"] for s in st["stages"]] == ["done", "done", "done", "current", "todo"]


def test_signed_job_without_an_estimate_shows_earlier_stages_done(conn, smith):
    states = [s["state"] for s in guide.stage(conn, books.get_job(conn, smith))["stages"]]
    assert states[:3] == ["done", "done", "done"]


def test_next_task_snaps_to_the_field_and_glows_it(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    c = _app(cfg)
    r = c.get(f"/next?job={n}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/jobs/{n}/estimate")
    page = c.get(f"/jobs/{n}/estimate").data.decode()
    assert "textarea[name=description]" in page and '"scroll": true' in page
    assert "Stage 1 of 5" in page and "Next: Write the estimate" in page
    again = c.get(f"/jobs/{n}/estimate").data.decode()   # still lit, but no jump on a plain visit
    assert "textarea[name=description]" in again and '"scroll": false' in again


def test_job_page_tracker_button_glows_when_the_task_is_elsewhere(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    page = _app(cfg).get(f"/jobs/{n}").data.decode()
    assert 'class="btn go glow"' in page and f"/next?job={n}" in page


def test_waiting_steps_glow_nothing(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    _price_ok(conn, n)
    books.update_job(conn, n, estimate_sent=date.today().isoformat())
    page = _app(cfg).get(f"/jobs/{n}/estimate").data.decode()
    assert "Nothing to press until then" in page and "btn go glow" not in page and "glow_here" not in page
    assert '"target"' not in page
    assert guide.next_task(conn) is None   # only waiting: the Next task button has nothing to send you to


def test_next_task_order_and_all_caught_up(cfg, conn):
    c = _app(cfg, setup_done=False)
    r = c.get("/next")
    assert r.headers["Location"].endswith("/setup")
    c = _app(cfg)
    r = c.get("/next", follow_redirects=True)
    assert b"all caught up" in r.data
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    assert guide.next_task(conn)["title"] == "Okafor: Write the estimate"
    assert c.get("/next").headers["Location"].endswith(f"/jobs/{n}/estimate")


def test_payment_rows_carry_the_glow_target(cfg, conn):
    n = books.create_job(conn, "Okafor", first_name="Pat", status="Estimate")
    _price_ok(conn, n)
    estimates.approve(conn, n, date.today().isoformat())
    step = guide.next_step(conn, books.get_job(conn, n))
    page = _app(cfg).get(f"/jobs/{n}").data.decode()
    assert step["title"].startswith("Invoice payment 1")
    pid = books.list_payments(conn, n)[0]["id"]
    assert f'id="payrow-{pid}"' in page and f"#payrow-{pid} input[name=invoice_sent]" in page


def test_next_task_button_is_on_every_page(cfg, conn):
    c = _app(cfg)
    for path in ("/", "/jobs", "/expenses", "/crew", "/setup"):
        assert b'class="next-btn"' in c.get(path).data, path
