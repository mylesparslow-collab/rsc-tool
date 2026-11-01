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
        if params.get("returnIdsOnly"):
            return {"objectIds": [r["OBJECTID"] for r in rows]}
        ids = {int(x) for x in params["objectIds"].split(",")}
        return {"features": [{"attributes": r} for r in rows if r["OBJECTID"] in ids]}
    return post


def test_refresh_finds_families_scores_and_skips_builders(conn):
    msg = newowners.refresh(conn, TODAY, post=fake_post())
    assert "Saratoga County: 4 deeds" in msg and "Warren County" in msg
    rows = {r["street"]: r for r in conn.execute("SELECT * FROM new_owners")}
    smith = rows["12 Maple Ave"]
    assert smith["grade"] == "A" and smith["year_built"] == 1925 and smith["zip"] == "12866"
    assert smith["city"] == "Saratoga Springs" and smith["addressee"] == "The Smith Household"
    assert smith["status"] == "new" and smith["sale_date"] == "" and smith["deed"] == "2026-18233"
    assert rows["5 New Rd"]["status"] == "skip" and "company" in rows["5 New Rd"]["why"]
    assert "9 Field Ln" not in rows                          # land, not a house
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
    smith = [r for r in rows if r["street"] == "12 Maple Ave"][0]
    text = newowners.letter(conn, smith)
    assert text.startswith("Dear The Smith Household,") and "Maple Ave" in text and "12 Maple" not in text
    assert "$" not in text and "{" not in text
    out = list(csv.DictReader(io.StringIO(newowners.mailing_csv(conn, rows))))
    assert out[0]["addressee"] and out[0]["state"] == "NY" and {"street", "city", "zip"} <= set(out[0])


def test_addressee():
    assert newowners.addressee("MCDONALD RUTH") == "The McDonald Household"
    assert newowners.addressee("Federal National Mortgage") == "Current Resident"
    assert newowners.addressee("") == "Current Resident"


def test_page_buttons(cfg, conn, monkeypatch):
    monkeypatch.setattr(newowners, "_post", fake_post())
    monkeypatch.setattr(newowners.refresh, "__defaults__", (None, fake_post()))
    app = create_app(cfg)
    c = app.test_client()
    html = c.get("/new-owners").get_data(as_text=True)
    assert "Check for new buyers" in html
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)
    r = c.post("/new-owners/refresh", data={"csrf": tok}, follow_redirects=True)
    assert "12 Maple Ave" in r.get_data(as_text=True)
    assert "Dear The Smith Household" in c.get("/new-owners/letters?grade=C").get_data(as_text=True)
    assert c.get("/new-owners/list.csv?grade=C").get_data(as_text=True).startswith("addressee,")
    r = c.post("/new-owners/mark", data={"csrf": tok, "status": "mailed", "all": "1", "grade": "C"}, follow_redirects=True)
    assert "Marked 3 as mailed" in r.get_data(as_text=True)
    r = c.post("/new-owners/letter", data={"csrf": tok, "letter": "Hello {addressee}"}, follow_redirects=True)
    assert "Letter saved" in r.get_data(as_text=True)
