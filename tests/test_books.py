import pytest

from rsc import books


def test_numbering_starts_at_setting_and_counts_up(conn):
    assert books.next_job_number(conn) == 1001
    assert books.create_job(conn, "Whitcomb") == 1001
    assert books.create_job(conn, "Smith") == 1002
    assert books.get_job(conn, 1002)["job_id"] == "1002-SMI"


def test_payment_sequence_and_totals(conn, smith):
    pays = books.list_payments(conn, smith)
    assert [p["payment_id"] for p in pays] == ["1001-SMI-1", "1001-SMI-2", "1001-SMI-3"]
    books.update_payment(conn, pays[0]["id"], date_paid="2026-10-01", amount_paid=5000)
    books.add_expense(conn, "2026-10-02", smith, 1200, "Lumber yard", "framing")
    books.add_expense(conn, "2026-10-02", "RSC-100", 80, "Stewart's", "fuel")
    job = books.get_job(conn, smith)
    assert (job["scheduled"], job["paid"], job["owed"], job["expenses"], job["profit"]) == (10000, 5000, 5000, 1200, 8800)
    assert job["schedule_ok"] is True
    assert books.list_payments(conn, smith)[0]["status"] == "Paid"


def test_ops_expenses_stay_off_jobs(conn, smith):
    books.add_expense(conn, "2026-10-02", "rsc-120", 900, "Insurer", "liability")
    assert books.get_job(conn, smith)["expenses"] == 0
    assert next(c for c in books.list_rsc_codes(conn) if c["code"] == "RSC-120")["spent"] == 900


@pytest.mark.parametrize("bad", ["9999", "RSC-555", "hello", ""])
def test_bad_charge_to_is_refused(conn, smith, bad):
    with pytest.raises(books.BooksError):
        books.add_expense(conn, "2026-10-02", bad, 10)


def test_payment_needs_existing_job(conn):
    with pytest.raises(books.BooksError):
        books.add_payment(conn, 4242, 100)
