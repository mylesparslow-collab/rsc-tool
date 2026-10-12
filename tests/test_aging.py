from rsc import aging, books, estimates
from rsc.web import create_app


class Notes:
    def extract(self, system, user, schema, images=None):
        return {"items": [{"key": "grab_bar", "qty": 3, "where": "tub"}, {"key": "handrail", "qty": 1, "where": "front steps"},
                          {"key": "elevator", "qty": 1, "where": "x"}, {"key": "ramp", "qty": 500, "where": "side"}],
                "concerns": ["Hallway is narrow"]}


def test_prices_come_from_the_table_not_the_model():
    parsed = aging.read_notes(Notes(), "notes")
    assert [i["key"] for i in parsed["items"]] == ["grab_bar", "handrail", "ramp"]   # the unknown key is dropped
    assert parsed["items"][2]["qty"] == 20                                          # absurd quantities are capped
    p = aging.price(parsed["items"][:2])
    assert p["low"] == 3 * 90 + 800 and p["high"] == 3 * 300 + 1200


def test_notes_work_without_a_model():
    parsed = aging.read_notes(None, "Need two grab bars at the tub. Railing on front steps. Ramp to the side door.")
    keys = {i["key"]: i["qty"] for i in parsed["items"]}
    assert keys == {"grab_bar": 2, "handrail": 1, "ramp": 1}


def test_assessment_pages(cfg, conn, smith):
    c = create_app(cfg, model=Notes()).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    assert c.get(f"/jobs/{smith}/assessment").status_code == 200
    r = c.post(f"/jobs/{smith}/assessment", data={"csrf": "t", "notes": "bars at the tub"}, follow_redirects=True)
    assert b"Grab bar" in r.data and b"Also noticed" in r.data
    pr = c.get(f"/jobs/{smith}/assessment/print")
    assert b"HOME SAFETY ASSESSMENT" in pr.data


def test_aging_templates_exist_and_job_type_listed(conn, smith):
    names = [n for n in estimates.TEMPLATES if n.startswith("Aging in place")]
    assert len(names) == 4 and "Aging in place" in books.JOB_TYPES
    estimates.create(conn, smith, "Aging in place: ramp & entry")
    est = estimates.get(conn, smith)
    assert any("1 inch of rise per 12" in s for p in est["phases"] for s in p["steps"])


def test_inches_are_not_quantities():
    keys = {i["key"]: i["qty"] for i in aging.read_notes(None, "bathroom door is 28 inches").get("items", [])}
    assert keys == {"door_widen": 1}


def test_fine_things_are_not_fixes():
    keys = {i["key"] for i in aging.read_notes(None, "Front door is 36 inches, fine. Shower curtain is torn. Daylight is good.").get("items", [])}
    assert keys == set()


def test_room_checklist_makes_items_and_keeps_photos(cfg, conn, smith):
    items = aging.from_checks(["bath_bars_tub", "bath_bar_toilet", "entry_steps", "bogus"])
    assert {(i["key"], i["qty"], i["where"]) for i in items} == {("grab_bar", 2, "Bathroom"), ("grab_bar", 1, "Bathroom"), ("ramp", 1, "Entry")} or \
        {(i["key"], i["qty"]) for i in items} == {("grab_bar", 3), ("ramp", 1)}
    c = create_app(cfg, model=Notes()).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    jpg = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"0" * 50
    import io
    r = c.post(f"/jobs/{smith}/assessment", data={"csrf": "t", "action": "photos", "photo_room": "Bathroom",
                                                    "photos": [(io.BytesIO(jpg), "a.jpg"), (io.BytesIO(b"junk"), "b.jpg")]},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"Added 1 photo" in r.data
    pid = aging.photos(conn, smith)[0]["id"]
    assert c.get(f"/jobs/{smith}/assessment/photo/{pid}").data[:3] == b"\xff\xd8\xff"
    r = c.post(f"/jobs/{smith}/assessment", data={"csrf": "t", "action": "write", "check": ["bath_bars_tub", "entry_steps"]}, follow_redirects=True)
    assert b"Grab bar" in r.data and b"Wood ramp" in r.data
    assert b"<img" in c.get(f"/jobs/{smith}/assessment/print").data
    assert c.get(f"/jobs/{smith + 5}/assessment/photo/{pid}").status_code == 404
