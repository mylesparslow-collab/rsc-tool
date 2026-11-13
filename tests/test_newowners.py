"""New homeowners: county records in, scored welcome-letter list out. The county servers are stood in for."""
import csv
import io
import re
from datetime import date

from rsc import newowners
from rsc.web import create_app

TODAY = date(2026, 11, 1)
SARATOGA_ROWS = [
    {"OBJECTID": 1, "SWIS": "411500", "PRINT_KEY": "165.12-1-3", "MUNI": "Saratoga Springs", "PROP_ADDR": "12 MAPLE AVE",
     "OWNER": "SMITH JOHN A", "DEED_BOOK": "2026", "DEED_PAGE": "18233", "PRP_CLS_CODE": "210",
     "MAIL_ADDR": "12 MAPLE AVE", "MAIL_CITY": "SARATOGA SPRINGS", "MAIL_ZIP": "12866"},
    {"OBJECTID": 2, "SWIS": "415200", "PRINT_KEY": "240.-2-7", "MUNI": "Malta", "PROP_ADDR": "5 New Rd",
     "OWNER": "BIG BUILDERS LLC", "DEED_BOOK": "2026", "DEED_PAGE": "20001", "PRP_CLS_CODE": "210"},
    {"OBJECTID": 3, "SWIS": "415200", "PRINT_KEY": "241.-1-1", "MUNI": "Malta", "PROP_ADDR": "9 Field Ln",
     "OWNER": "Jones, Mary", "DEED_BOOK": "2025", "DEED_PAGE": "30010", "PRP_CLS_CODE": "311"},   # vacant land
    {"OBJECTID": 4, "SWIS": "414800", "PRINT_KEY": "150.-3-9", "MUNI": "Wilton", "PROP_ADDR": "40 Ridge Rd",
     "OWNER": "O'BRIEN KATE", "DEED_BOOK": "2025", "DEED_PAGE": "41000", "PRP_CLS_CODE": "210",
     "MAIL_ADDR": "1 Elsewhere St", "MAIL_CITY": "ALBANY", "MAIL_ZIP": "12203"},
    {"OBJECTID": 5, "SWIS": "413800", "PRINT_KEY": "1.-1-1", "MUNI": "Halfmoon", "PROP_ADDR": "1 Far Rd",
     "OWNER": "Lee, Ann", "DEED_BOOK": "2026", "DEED_PAGE": "100", "PRP_CLS_CODE": "210"},
]
STATE_ROWS = [
    {"OBJECTID": 11, "SWIS": "411500", "PRINT_KEY": "165.12-1-3", "YR_BLT": 1925, "SQFT_LIVING": 1800,
     "FULL_MARKET_VAL": 520000, "LOC_ZIP": "12866"},
    {"OBJECTID": 12, "SWIS": "415200", "PRINT_KEY": "240.-2-7", "YR_BLT": 2025, "FULL_MARKET_VAL": 610000, "LOC_ZIP": "12020"},
    {"OBJECTID": 14, "SWIS": "414800", "PRINT_KEY": "150.-3-9", "YR_BLT": 1988, "FULL_MARKET_VAL": 410000, "LOC_ZIP": "12831"},
]
WARREN_ROWS = [
    {"OBJECTID": 21, "SWIS": "523400", "PRINT_KEY": "289.5-1-1", "Muni": "Queensbury", "PROP_ADDR": "212 FIFTH ST. EXT.",
     "PRP_CLS_CO": "210", "PROP_CLASS": "1 Family Res", "SALE_DATE": 1779408000000, "SALE_PRICE": 160000,
     "YR_BUILT": 1953, "OWNER1": "DOE JANE", "DEED_BOOK": "7000", "DEED_PAGE": "12"},
    {"OBJECTID": 22, "SWIS": "523400", "PRINT_KEY": "289.5-1-2", "Muni": "Queensbury", "PROP_ADDR": "214 FIFTH ST",
     "PRP_CLS_CO": "210", "SALE_DATE": 1779408000000, "SALE_PRICE": 1, "YR_BUILT": 1950, "OWNER1": "DOE SAM"},  # family transfer
]


def fake_post(calls=None):
    def post(url, params):
        if calls is not None:
            calls.append((url, params))
        rows = SARATOGA_ROWS if url == newowners.SARATOGA else WARREN_ROWS if url == newowners.WARREN else STATE_ROWS
        if url == newowners.STATE:
            m = re.search(r"SWIS = '(\d+)' AND PRINT_KEY IN \((.*)\)", params.get("where", ""))
            if m:
                keys = re.findall(r"'([^']*)'", m.group(2))
                rows = [r for r in rows if r["SWIS"] == m.group(1) and r["PRINT_KEY"] in keys]
        if "objectIds" not in params and not params.get("returnIdsOnly"):
            return {"features": [{"attributes": r} for r in rows]}
        if params.get("returnIdsOnly"):
            return {"objectIds": [r["OBJECTID"] for r in rows]}
        ids = {int(x) for x in params["objectIds"].split(",")}
        return {"features": [{"attributes": r} for r in rows if r["OBJECTID"] in ids]}
    return post


def test_refresh_finds_families_scores_and_skips_builders(conn):
    msg = newowners.refresh(conn, TODAY, post=fake_post())
    assert "Saratoga County: 5 deeds" in msg and "3 houses in your towns" in msg and "Warren County" in msg
    rows = {r["street"]: r for r in conn.execute("SELECT * FROM new_owners")}
    smith = rows["12 Maple Ave"]
    assert smith["grade"] == "A" and smith["year_built"] == 1925 and smith["zip"] == "12866"
    assert smith["city"] == "Saratoga Springs" and smith["addressee"] == "The Smith Household"
    assert smith["status"] == "new" and smith["sale_date"] == "" and smith["deed"] == "2026-18233"
    assert rows["5 New Rd"]["status"] == "skip" and "company" in rows["5 New Rd"]["why"]
    assert "9 Field Ln" not in rows                          # land, not a house
    assert "1 Far Rd" not in rows                            # Halfmoon isn't one of Nick's towns
    obrien = rows["40 Ridge Rd"]
    assert obrien["city"] == "Gansevoort" and obrien["addressee"] == "The O'Brien Household"
    doe = rows["212 Fifth St. Ext."]
    assert doe["sale_price"] == 160000 and doe["sale_date"] == "2026-05-22" and doe["county"] == "Warren"
    assert "214 Fifth St" not in rows                        # $1 transfer isn't a sale


def test_second_check_keeps_mailed_and_only_counts_new(conn):
    newowners.refresh(conn, TODAY, post=fake_post())
    key = conn.execute("SELECT key FROM new_owners WHERE street = '12 Maple Ave'").fetchone()[0]
    newowners.set_status(conn, [key], "mailed", TODAY)
    msg = newowners.refresh(conn, TODAY, post=fake_post())
    assert "0 new to mail" in msg
    row = conn.execute("SELECT status, mailed_on FROM new_owners WHERE key = ?", (key,)).fetchone()
    assert tuple(row) == ("mailed", "2026-11-01")
    assert not newowners.due(conn)


def test_server_down_is_a_message_not_a_crash(conn):
    def down(url, params):
        raise RuntimeError("timed out")
    msg = newowners.refresh(conn, TODAY, post=down)
    assert "couldn't be read" in msg and newowners.counts(conn)["new"] == 0


def test_letter_and_csv(conn):
    newowners.refresh(conn, TODAY, post=fake_post())
    rows = newowners.listing(conn, "new", "C")
    assert [r["grade"] for r in rows] == sorted(r["grade"] for r in rows)
    assert len(newowners.listing(conn, "new", "C", limit=1)) == 1 and newowners.listing(conn, "new", "A")
    smith = [r for r in rows if r["street"] == "12 Maple Ave"][0]
    text = newowners.letter(conn, smith)
    assert text.startswith("Dear Smith family,") and "Maple Ave" in text and "12 Maple" not in text
    assert "$" not in text and "{" not in text
    out = list(csv.DictReader(io.StringIO(newowners.mailing_csv(conn, rows))))
    assert out[0]["addressee"] and out[0]["state"] == "NY" and {"street", "city", "zip"} <= set(out[0])


def test_addressee():
    assert newowners.addressee("MCDONALD RUTH") == "The McDonald Household"
    assert newowners.addressee("Federal National Mortgage") == "Current Resident"
    assert newowners.addressee("") == "Current Resident"
    assert newowners.greeting("The O'Brien Household") == "O'Brien family"
    assert newowners.greeting("Current Resident") == "Neighbor"


def test_page_buttons(cfg, conn, monkeypatch):
    import time
    monkeypatch.setattr(newowners.refresh, "__defaults__", (None, fake_post()))
    app = create_app(cfg)
    c = app.test_client()
    html = c.get("/new-owners").get_data(as_text=True)
    assert "Check for new buyers" in html
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)
    r = c.post("/new-owners/refresh", data={"csrf": tok}, follow_redirects=True)
    assert "5 to 10 minutes" in r.get_data(as_text=True)
    for _ in range(50):          # the check runs in the background
        if "12 Maple Ave" in c.get("/new-owners?grade=C").get_data(as_text=True):
            break
        time.sleep(0.1)
    assert "12 Maple Ave" in c.get("/new-owners?grade=C").get_data(as_text=True)
    assert "Dear Smith family" in c.get("/new-owners/letters?grade=C").get_data(as_text=True)
    assert c.get("/new-owners/list.csv?grade=C").get_data(as_text=True).startswith("addressee,")
    r = c.post("/new-owners/mark", data={"csrf": tok, "status": "mailed", "all": "1", "grade": "C", "n": "25"}, follow_redirects=True)
    assert "Marked 2 as mailed" in r.get_data(as_text=True)   # the Warren house has no ZIP, so no letter
    r = c.post("/new-owners/letter", data={"csrf": tok, "letter": "Hello {addressee}"}, follow_redirects=True)
    assert "Welcome card saved" in r.get_data(as_text=True)


# ---------- the three cards ----------

def _two_mailable(conn):
    newowners.refresh(conn, TODAY, post=fake_post())
    return [r["key"] for r in newowners.listing(conn, "new", "C", mailable=True)]


def test_card_sequence_dates_and_weekly_batch(conn):
    keys = _two_mailable(conn)
    assert len(keys) == 2
    assert newowners.mark_mailed(conn, keys[:1], TODAY) == 1
    r = conn.execute("SELECT * FROM new_owners WHERE key = ?", (keys[0],)).fetchone()
    assert (r["step"], r["mailed_on"], r["next_due"]) == (1, "2026-11-01", "2026-11-22") and len(r["code"]) == 5
    # before card 2 is due, the batch is just new welcome cards
    assert [x["key"] for x in newowners.this_weeks_mail(conn, 50, "C", today=date(2026, 11, 10))] == keys[1:]
    # once it's due, the follow-up comes first
    batch = newowners.this_weeks_mail(conn, 50, "C", today=date(2026, 11, 23))
    assert [x["key"] for x in batch] == keys and newowners.next_card(batch[0]) == 2 and newowners.next_card(batch[1]) == 1
    assert "A few weeks in" in newowners.letter(conn, batch[0])
    newowners.mark_mailed(conn, keys[:1], date(2026, 11, 23))
    r = conn.execute("SELECT * FROM new_owners WHERE key = ?", (keys[0],)).fetchone()
    assert (r["step"], r["card2_on"], r["next_due"]) == (2, "2026-11-23", "2027-01-04")


def test_season_rules():
    assert newowners.next_due_after(1, date(2026, 11, 1)) == "2026-11-22"
    assert newowners.next_due_after(2, date(2026, 11, 23)) == "2027-01-04"
    assert newowners.next_due_after(3, date(2026, 12, 1)) == ""
    assert newowners.season(date(2027, 1, 5)) == "winter" and newowners.season(date(2026, 10, 1)) == "fall"


def test_third_card_is_seasonal_and_last(conn):
    k = _two_mailable(conn)[0]
    for d in (date(2026, 9, 1), date(2026, 9, 22), date(2026, 12, 1)):  # Nick can mail late; the dates follow
        newowners.mark_mailed(conn, [k], d)
    r = conn.execute("SELECT * FROM new_owners WHERE key = ?", (k,)).fetchone()
    assert (r["step"], r["card3_on"], r["next_due"]) == (3, "2026-12-01", "")
    assert newowners.mark_mailed(conn, [k], date(2027, 1, 1)) == 0          # no fourth card
    assert "Your first winter" in newowners.letter(conn, r, card=3, today=date(2026, 12, 1))


def test_reply_by_code_stops_cards(conn):
    k = _two_mailable(conn)[0]
    newowners.mark_mailed(conn, [k], TODAY)
    code = conn.execute("SELECT code FROM new_owners WHERE key = ?", (k,)).fetchone()[0]
    row = newowners.mark_replied(conn, code.lower()[:2] + " " + code.lower()[2:], TODAY)
    assert row["status"] == "replied" and row["next_due"] == ""
    assert newowners.follow_ups_due(conn, date(2027, 1, 1)) == []
    assert newowners.mark_replied(conn, "ZZZZZ") is None and newowners.normal_code("O0I1L") == ""


def test_welcome_page_form_becomes_tagged_lead(cfg, conn):
    from rsc import intake
    k = _two_mailable(conn)[0]
    newowners.mark_mailed(conn, [k], TODAY)
    code = conn.execute("SELECT code FROM new_owners WHERE key = ?", (k,)).fetchone()[0]

    class Mail:
        subject = "New homeowner walkthrough"
        sender = "noreply@formspree.io"
        body = (f"name: Jane Smith\nreply to: jane@example.com\ncard code: {code}\nsource: new homeowner mail\n"
                "message: Would love a walkthrough of the kitchen.")
    s = intake.suggestion_from_form(conn, Mail(), "518-932-9919")
    assert s.kind == "lead" and "new homeowner mail" in s.data["project"] and s.data["new_owner_code"] == code
    assert s.data["address"].startswith("12 Maple Ave") and "cards are stopped" in s.match_note
    assert conn.execute("SELECT status FROM new_owners WHERE key = ?", (k,)).fetchone()[0] == "replied"


def test_old_mailed_rows_become_card_one(tmp_path):
    import sqlite3
    from rsc import db
    c = sqlite3.connect(tmp_path / "old.db")
    c.row_factory = sqlite3.Row
    c.executescript(db.NEW_OWNERS)
    c.execute("INSERT INTO new_owners (key, county, first_seen, status, mailed_on) VALUES ('a', 'Saratoga', '2026-10-01', 'mailed', '2026-10-05')")
    db.migrate_new_owners(c)
    r = c.execute("SELECT step, next_due FROM new_owners").fetchone()
    assert (r["step"], r["next_due"]) == (1, "2026-10-26")


def test_home_reminds_weekly(conn):
    from rsc import prefs
    keys = _two_mailable(conn)
    assert newowners.week_due(conn, TODAY) is None           # nothing until the first batch is mailed
    newowners.mark_mailed(conn, keys[:1], TODAY)
    assert newowners.week_due(conn, date(2026, 11, 5)) is None
    assert newowners.week_due(conn, date(2026, 11, 23)) == {"follow_ups": 1, "new": 1}


def test_print_has_qr_and_code(cfg, conn):
    _two_mailable(conn)
    app = create_app(cfg)
    html = app.test_client().get("/new-owners/letters?grade=C").get_data(as_text=True)
    code = conn.execute("SELECT code FROM new_owners WHERE code != '' LIMIT 1").fetchone()[0]
    assert "rscbuilds.com/welcome" in html and code in html and "<svg" in html


# ---------- no more mail ----------

class _StopMail:
    subject = "Stop mail"
    sender = "noreply@formspree.io"
    message_id = "stop-1"

    def __init__(self, body):
        self.body = body


def test_stop_by_code_marks_never_mail_without_a_lead(cfg, conn):
    from rsc import intake
    k = _two_mailable(conn)[0]
    newowners.mark_mailed(conn, [k], TODAY)
    code = conn.execute("SELECT code FROM new_owners WHERE key = ?", (k,)).fetchone()[0]
    note = intake.stop_mail_request(conn, _StopMail(f"card code: {code}\nrequest: No more mail"))
    assert note.startswith("no more mail: 12 Maple Ave")
    assert conn.execute("SELECT status FROM new_owners WHERE key = ?", (k,)).fetchone()[0] == "optout"
    assert newowners.follow_ups_due(conn, date(2027, 1, 1)) == []
    assert intake.suggestion_from_form(conn, _StopMail("card code: X\nrequest: No more mail"), "") is None   # no lead


def test_stop_by_address_and_it_holds_after_the_next_check(conn):
    _two_mailable(conn)
    assert [r["street"] for r in newowners.stop_mail(conn, "", "12 maple ave., Saratoga Springs")] == ["12 Maple Ave"]
    newowners.refresh(conn, TODAY, post=fake_post())
    assert conn.execute("SELECT status FROM new_owners WHERE street = '12 Maple Ave'").fetchone()[0] == "optout"
    assert newowners.set_status(conn, [conn.execute("SELECT key FROM new_owners WHERE street = '12 Maple Ave'").fetchone()[0]], "skip") == 0


def test_unmatched_stop_request_is_kept_for_nick(cfg, conn):
    _two_mailable(conn)
    assert newowners.stop_mail(conn, "", "99 Nowhere Rd", TODAY) == []
    assert newowners.stop_requests(conn) == [{"on": "2026-11-01", "code": "", "address": "99 Nowhere Rd"}]
    app = create_app(cfg)
    assert "99 Nowhere Rd" in app.test_client().get("/new-owners").get_data(as_text=True)


def test_stop_request_email_is_skipped_by_the_mail_check(cfg, conn):
    from rsc import pipeline
    _two_mailable(conn)

    from rsc.mail import Mail
    m = Mail("stop-2", "INBOX", "noreply@formspree.io", "Formspree", "Stop mail", "2026-11-01",
             "address: 12 Maple Ave\nrequest: No more mail")

    class NoModel:
        def extract(self, *a, **k):
            raise AssertionError("the model must not be asked")
    r = pipeline.process(conn, cfg, [m], NoModel())
    assert r.skipped == 1 and r.suggestions == 0
    assert conn.execute("SELECT status FROM new_owners WHERE street = '12 Maple Ave'").fetchone()[0] == "optout"
