from datetime import date

from rsc import books, estimates, pricing


def job_with_estimate(conn, name, materials, labor, signed="2026-09-01", status="Signed"):
    n = books.create_job(conn, name, status=status)
    estimates.create(conn, n, "Other")
    estimates.save(conn, n, {"materials": materials, "markup_pct": 0, "labor": labor}, {}, [{"title": "A", "steps": []}], [])
    estimates.approve(conn, n, signed)
    books.update_job(conn, n, status=status)
    return n


def test_floor_price_math():
    assert pricing.floor_price(6000, 0.10, 0.20) == 8571.43
    assert pricing.floor_price(6000, 0.60, 0.40) is None


def test_nothing_is_assumed_until_nick_enters_numbers(conn):
    n = job_with_estimate(conn, "Lee", 5000, 5000)
    check = pricing.check_estimate(conn, n, date(2026, 10, 9))
    assert check["status"] == "needs_settings" and check["floor"] is None
    assert check["gross_margin_pct"] == 0.5


def test_floor_uses_entered_overhead_and_margin(conn):
    n = job_with_estimate(conn, "Lee", 5000, 5000)
    pricing.save_settings(conn, 20, 10)
    check = pricing.check_estimate(conn, n, date(2026, 10, 9))
    assert check["floor"] == 7142.86 and check["status"] == "above" and check["cushion"] == 2857.14
    books.update_job(conn, n, contract_total=10000)
    pricing.save_settings(conn, 60, 40)
    assert pricing.check_estimate(conn, n)["status"] == "impossible"


def test_below_floor(conn):
    n = job_with_estimate(conn, "Lee", 8000, 500)
    pricing.save_settings(conn, 20, 10)
    check = pricing.check_estimate(conn, n, date(2026, 10, 9))
    assert check["status"] == "below" and check["cushion"] < 0


def test_overhead_from_history_needs_enough_jobs(conn):
    for name in ("A", "B"):
        job_with_estimate(conn, name, 1000, 9000)
    books.add_expense(conn, "2026-09-10", "RSC-120", 2000, "Insurer")
    assert pricing.overhead(conn, date(2026, 10, 9))["pct"] is None
    job_with_estimate(conn, "C", 1000, 9000)
    o = pricing.overhead(conn, date(2026, 10, 9))
    assert o["jobs"] == 3 and o["revenue"] == 30000 and round(o["pct"], 4) == round(2000 / 30000, 4) and o["source"] == "history"
    pricing.save_settings(conn, None, 15)
    assert pricing.overhead(conn, date(2026, 10, 9))["pct"] == 0.15


def test_old_expenses_fall_out_of_the_window(conn):
    books.add_expense(conn, "2024-01-01", "RSC-120", 5000, "Insurer")
    assert pricing.overhead(conn, date(2026, 10, 9))["spend"] == 0


def test_estimate_accuracy(conn):
    a = job_with_estimate(conn, "Done", 1000, 2000, status="Complete")
    b = job_with_estimate(conn, "Going", 1000, 2000, status="In Progress")
    books.add_expense(conn, "2026-09-02", a, 1100, "Yard")
    books.add_expense(conn, "2026-09-02", b, 400, "Yard")
    acc = pricing.accuracy(conn)
    rows = {r["job"]["number"]: r for r in acc["rows"]}
    assert rows[a]["variance"] == 100 and round(rows[a]["variance_pct"], 2) == 0.10
    assert acc["finished_count"] == 1 and round(acc["average_variance_pct"], 2) == 0.10
