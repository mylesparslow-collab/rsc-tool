import base64

import pytest

from rsc import books, changeorders

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()


def test_signing_updates_total_and_adds_payment(conn, smith):
    co = changeorders.create(conn, smith, "Add a window on the east wall", 1200, days_added=2)
    assert changeorders.get(conn, co)["label"] == "1001-SMI-CO1"
    payment_id = changeorders.sign(conn, co, "Jane Smith", PNG)
    assert payment_id == "1001-SMI-4"
    job = books.get_job(conn, smith)
    assert job["contract_total"] == 11200 and job["scheduled"] == 11200 and job["schedule_ok"] is True
    pay = books.list_payments(conn, smith)[-1]
    assert (pay["amount"], pay["kind"], pay["change_order_id"]) == (1200, "change_order", co)
    signed = changeorders.get(conn, co)
    assert (signed["status"], signed["signer_name"]) == ("signed", "Jane Smith") and signed["signed_at"]


def test_credit_lowers_the_total(conn, smith):
    co = changeorders.create(conn, smith, "Skip the backsplash", -400)
    changeorders.sign(conn, co, "Jane Smith", PNG)
    job = books.get_job(conn, smith)
    assert job["contract_total"] == 9600 and job["schedule_ok"] is True


def test_cannot_sign_twice_or_after_decline(conn, smith):
    co = changeorders.create(conn, smith, "Extra outlet", 150)
    changeorders.sign(conn, co, "Jane", PNG)
    with pytest.raises(books.BooksError, match="already signed"):
        changeorders.sign(conn, co, "Jane", PNG)
    assert books.get_job(conn, smith)["contract_total"] == 10150
    co2 = changeorders.create(conn, smith, "Extra light", 90)
    changeorders.decline(conn, co2)
    with pytest.raises(books.BooksError, match="declined"):
        changeorders.sign(conn, co2, "Jane", PNG)


@pytest.mark.parametrize("sig", ["", "data:text/html;base64,AAAA", "data:image/png;base64,@@@",
                                 "data:image/png;base64," + base64.b64encode(b"not a png at all").decode(),
                                 "data:image/png;base64," + "A" * 400_000])
def test_bad_signatures_are_refused_and_nothing_changes(conn, smith, sig):
    co = changeorders.create(conn, smith, "Extra outlet", 150)
    with pytest.raises(books.BooksError):
        changeorders.sign(conn, co, "Jane", sig)
    assert books.get_job(conn, smith)["contract_total"] == 10000
    assert changeorders.get(conn, co)["status"] == "draft"


def test_needs_a_name_a_description_an_amount_and_a_contract(conn, smith):
    co = changeorders.create(conn, smith, "x", 10)
    with pytest.raises(books.BooksError, match="name"):
        changeorders.sign(conn, co, "  ", PNG)
    with pytest.raises(books.BooksError):
        changeorders.create(conn, smith, "  ", 10)
    with pytest.raises(books.BooksError):
        changeorders.create(conn, smith, "free", 0)
    lead = books.create_job(conn, "Lead")
    with pytest.raises(books.BooksError, match="no signed contract"):
        changeorders.create(conn, lead, "x", 10)


def test_numbering_per_job(conn, smith):
    a = changeorders.create(conn, smith, "one", 1)
    b = changeorders.create(conn, smith, "two", 2)
    assert [changeorders.get(conn, i)["seq"] for i in (a, b)] == [1, 2]
    changeorders.delete_draft(conn, b)
    assert changeorders.create(conn, smith, "three", 3) is not None
