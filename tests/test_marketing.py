from datetime import date

from rsc import books, client_update, marketing, report
from rsc.web import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


class Model:
    def __init__(self, answer):
        self.answer = answer

    def extract(self, system, user, schema, images=None):
        self.user = user
        return self.answer


def _job(conn):
    return books.create_job(conn, "Hartwell", first_name="Dana", address="12 Maple Ave, Wilton, NY 12831",
                            phone="518-555-0101", job_type="Bathroom", status="Complete")


def test_scrub_removes_private_details_and_claims():
    job = {"first_name": "Dana", "last_name": "Hartwell", "address": "12 Maple Ave, Wilton, NY"}
    t = marketing.scrub("We redid Dana Hartwell's shower at 12 Maple Ave. Call 518-555-0101 or a@b.com. "
                        "Fully licensed and insured. It cost $14,000. New tile and a glass panel!", job)
    for bad in ("Dana", "Hartwell", "Maple", "518", "a@b.com", "licensed", "14,000"):
        assert bad not in t
    assert "New tile and a glass panel!" in t


def test_town_never_street():
    assert marketing.town_of("12 Maple Ave, Wilton, NY 12831") == "Wilton"
    assert marketing.town_of("45 Oak St, saratoga springs") == "Saratoga Springs"
    assert marketing.town_of("") == ""


def test_draft_with_model_is_scrubbed_and_tagged(conn):
    n = _job(conn)
    m = Model({"tiktok": "Dana's old tub is gone, walk-in shower at 12 Maple Ave now.",
               "facebook": "We turned Dana Hartwell's tub into a walk-in shower. We are fully insured. Bright new tile.",
               "nextdoor": "Hi neighbors, just finished a walk-in shower in Wilton. Call us at 518-555-0101."})
    p = marketing.draft(m, conn, "tub out, walk-in shower in for the Hartwells", n)
    assert "Hartwell" not in m.user and "Town: Wilton" in m.user
    for k in ("tiktok", "facebook", "nextdoor"):
        assert "Dana" not in p[k] and "Hartwell" not in p[k] and "Maple" not in p[k] and "518" not in p[k]
    assert "insured" not in p["facebook"] and "Bright new tile." in p["facebook"]
    assert "#Wilton" in p["tiktok"] and "#bathroomremodel" in p["tiktok"]
    assert "rscbuilds.com" in p["facebook"] and "rscbuilds.com" in p["nextdoor"]


def test_draft_without_model_uses_template(conn):
    n = _job(conn)
    p = marketing.draft(None, conn, "new curbless shower and a bench", n)
    assert "in Wilton" in p["tiktok"] and "curbless shower" in p["facebook"] and "neighbors" in p["nextdoor"]
    broken = Model({"tiktok": "", "facebook": "x", "nextdoor": ""})
    assert "curbless" in marketing.draft(broken, conn, "new curbless shower", n)["nextdoor"]


def test_listings_defaults_edit_and_status(conn):
    ls = {x["key"]: x for x in marketing.listings(conn)}
    assert ls["website"]["status"] == "Live" and ls["houzz"]["status"] == "To fix" and ls["google"]["status"] == "Not set up"
    assert marketing.website(conn) == "rscbuilds.com"
    assert marketing.save_listing(conn, "houzz", ls["houzz"]["url"], "")
    assert marketing.save_listing(conn, "google", "g.page/refined", "")
    ls = {x["key"]: x for x in marketing.listings(conn)}
    assert ls["houzz"]["status"] == "Live" and ls["google"]["url"] == "https://g.page/refined"
    assert not marketing.save_listing(conn, "nope", "", "")


def test_summary_and_weekly_report(conn):
    n = _job(conn)
    p = marketing.draft(None, conn, "new deck stairs", n)
    s = marketing.summary(conn)
    assert s["drafts"] == 1 and s["last_posted"] is None and s["jobs_to_post"] == 0 and "Houzz" in s["to_fix"]
    marketing.mark_posted(conn, p["id"], date(2026, 11, 1))
    s = marketing.summary(conn, date(2026, 11, 4))
    assert s["drafts"] == 0 and s["days_since"] == 3
    text = report.render_text(report.build(conn, date(2026, 11, 4)), "Hi")
    assert "MARKETING" in text and "Last job post: 3 day(s) ago" in text and "Listings to fix:" in text


def test_page_flow(cfg, conn):
    n = _job(conn)
    client_update.add_photo(conn, n, "image/png", PNG)
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    page = c.get("/marketing")
    assert page.status_code == 200 and b"Hartwell" in page.data and b"Yelp" in page.data
    assert c.post("/marketing/draft", data={"csrf": "t", "note": ""}, follow_redirects=True).data.count(b"Type or say") == 1
    r = c.post("/marketing/draft", data={"csrf": "t", "note": "new vanity and tile", "job_number": str(n)}, follow_redirects=True)
    assert b"new vanity and tile" in r.data and b"/update/photo/1" in r.data and b"Copy" in r.data
    pid = marketing.posts(conn)[0]["id"]
    c.post(f"/marketing/post/{pid}", data={"csrf": "t", "action": "posted", "tiktok": "Edited caption"})
    got = marketing.get_post(conn, pid)
    assert got["posted_on"] and got["tiktok"] == "Edited caption"
    c.post("/marketing/listing/yelp", data={"csrf": "t", "url": "https://yelp.com/x", "todo": ""})
    assert {x["key"]: x for x in marketing.listings(conn)}["yelp"]["status"] == "Live"
    c.post("/marketing/schedule", data={"csrf": "t", "schedule": "Fridays"})
    assert marketing.schedule(conn) == "Fridays"
    assert c.post("/marketing/listing/bogus", data={"csrf": "t"}).status_code == 404
    c.post(f"/marketing/post/{pid}", data={"csrf": "t", "action": "delete"})
    assert marketing.get_post(conn, pid) is None


def test_surname_that_is_a_word_only_replaced_capitalized():
    job = {"first_name": "Al", "last_name": "Stone", "address": ""}
    assert marketing.scrub("New stone patio for Al Stone.", job) == "New stone patio for the homeowners."
