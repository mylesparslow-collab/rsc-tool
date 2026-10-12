import io
import json
import re

import pytest

from rsc.modeler import clean, sniff
from rsc.web import create_app

V1 = '{"w":168,"d":144,"h":96,"t":5,"next":2,"open":[{"id":1,"type":"door","wall":"S","off":24,"w":36,"h":80,"sill":0}]}'


def room(i, x=0, **kw):
    return {"id": i, "name": f"Room {i}", "x": x, "y": 0, "w": 120, "d": 120, "h": 96, "t": 5, "open": [], **kw}


def v2(*rooms, **kw):
    return json.dumps({"v": 2, "rooms": list(rooms), "sel": rooms[0]["id"], "nextRoom": 9, "nextOpen": 9,
                       "fin": {"floor": {"name": "Walnut", "note": "3/4 in"}}, **kw})


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def client_and_token(cfg):
    app = create_app(cfg)
    app.testing = True
    c = app.test_client()
    html = c.get("/").get_data(as_text=True)
    return c, re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def test_version_1_models_are_converted():
    m = clean(V1)
    assert m["v"] == 2 and len(m["rooms"]) == 1 and m["rooms"][0]["open"][0]["wall"] == "S" and m["nextOpen"] == 2


def test_finishes_fall_back_to_known_names():
    m = clean(v2(room(1)))
    assert m["fin"]["floor"] == {"name": "Walnut", "note": "3/4 in"}
    assert m["fin"]["siding"]["name"] == "White"  # missing -> first in list


@pytest.mark.parametrize("bad", ["not json", "[]", '{"w":0,"d":1,"h":1,"t":1,"open":[]}', '{"rooms":[]}',
                                 v2(room(1), room(1)), v2(room(1, w=-5)),
                                 v2(room(1, open=[{"id": 1, "type": "gate", "wall": "S", "off": 0, "w": 1, "h": 1, "sill": 0}]))])
def test_bad_models_are_refused(bad):
    with pytest.raises((ValueError, TypeError)):
        clean(bad)


def test_page_saves_and_reloads(cfg, conn, smith):
    c, token = client_and_token(cfg)
    page = c.get(f"/jobs/{smith}/model")
    assert page.status_code == 200 and b"Room model" in page.data
    r = c.post(f"/jobs/{smith}/model", data={"csrf": token, "model": v2(room(1), room(2, x=120))})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert b'"Room 2"' in c.get(f"/jobs/{smith}/model").data
    assert b"Client view" in c.get(f"/jobs/{smith}/model?view=client").data


def test_bad_post_is_400_and_unknown_job_404(cfg, conn, smith):
    c, token = client_and_token(cfg)
    assert c.post(f"/jobs/{smith}/model", data={"csrf": token, "model": "nope"}).status_code == 400
    assert c.get("/jobs/9999/model").status_code == 404


def test_photo_upload_serve_and_delete(cfg, conn, smith):
    c, token = client_and_token(cfg)
    url = f"/jobs/{smith}/model/photo/before"
    assert c.get(url).status_code == 404
    up = c.post(url, data={"csrf": token, "file": (io.BytesIO(PNG), "x.png")}, content_type="multipart/form-data")
    assert up.status_code == 200
    got = c.get(url)
    assert got.status_code == 200 and got.mimetype == "image/png" and got.headers["X-Content-Type-Options"] == "nosniff"
    assert c.post(url + "/delete", data={"csrf": token}).status_code == 200
    assert c.get(url).status_code == 404


def test_photo_rejects_non_images_and_wrong_kind(cfg, conn, smith):
    c, token = client_and_token(cfg)
    bad = c.post(f"/jobs/{smith}/model/photo/after", data={"csrf": token, "file": (io.BytesIO(b"<html>"), "x.png")},
                 content_type="multipart/form-data")
    assert bad.status_code == 400
    assert c.get(f"/jobs/{smith}/model/photo/side").status_code == 404
    assert sniff(JPEG) == "image/jpeg" and sniff(b"GIF89a") is None


def test_dashboard_lists_jobs_with_models(cfg, conn):
    from rsc import books
    from rsc.web import create_app
    a = books.create_job(conn, "Smith")
    books.create_job(conn, "Jones")
    app = create_app(cfg)
    app.testing = True
    c = app.test_client()
    home = c.get("/").get_data(as_text=True)
    assert "Room modeler" in home and f"/jobs/{a}/model" in home
    page = c.get("/models").get_data(as_text=True)
    assert "1001-SMI" in page and "1002-JON" in page and page.count("Start a model") == 2
    c.post(f"/jobs/{a}/model", data={"csrf": __import__("re").search(r'name="csrf" value="([0-9a-f]+)"', home).group(1),
                                      "model": v2(room(1))})
    assert "1 room" in c.get("/models").get_data(as_text=True)
