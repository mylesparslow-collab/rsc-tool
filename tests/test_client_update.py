import json
from datetime import date, timedelta
from pathlib import Path

from rsc import books, client_update, daily, estimates
from rsc.web import create_app

EX = Path(__file__).resolve().parent.parent / "examples"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def _delano(conn):
    n = estimates.import_estimate(conn, json.load(open(EX / "delano-1003.json")))
    books.update_job(conn, n, status="In Progress", first_name="Pat", email="pat@example.com")
    return n


def test_facts_and_fallback(conn):
    n = _delano(conn)
    daily.set_steps(conn, n, [1, 2], [1, 2])
    f = client_update.facts(conn, n)
    assert len(f["this_week"]) == 2 and f["next"] and 0 < f["percent"] <= 100
    d = client_update.draft(None, conn, books.get_job(conn, n), "518-555-0100")
    assert "Hi Pat" in d["text"] and "Coming up next" in d["text"] and "518-555-0100" in d["text"]
    assert client_update.facts(conn, n, date.today() + timedelta(days=30))["this_week"] == []


def test_page_photo_and_draft(cfg, conn):
    n = _delano(conn)
    daily.set_steps(conn, n, [1], [1])
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    import io
    r = c.post(f"/jobs/{n}/update/photos", data={"csrf": "t", "photos": (io.BytesIO(PNG), "a.png")}, content_type="multipart/form-data", follow_redirects=True)
    assert b"Added 1 photo" in r.data
    assert c.get(f"/jobs/{n}/update/photo/1").data == PNG
    d = c.post(f"/jobs/{n}/update/draft", data={"csrf": "t"})
    assert b"mailto:pat@example.com" in d.data and b"attached a few photos" in d.data
    c.post(f"/jobs/{n}/update/photo/1/delete", data={"csrf": "t"})
    assert c.get(f"/jobs/{n}/update/photo/1").status_code == 404


def test_job_without_estimate_is_graceful(cfg, conn):
    n = books.create_job(conn, "Nobody", first_name="No")
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    assert c.get(f"/jobs/{n}/update").status_code == 200
    assert b"nothing to report" in c.post(f"/jobs/{n}/update/draft", data={"csrf": "t"}, follow_redirects=True).data
