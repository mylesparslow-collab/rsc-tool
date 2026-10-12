from rsc import assist, brand, contract, followups, leads
from rsc.web import create_app


def test_defaults_are_rsc(conn):
    b = brand.load(conn)
    assert b["name"] == "Reclaimed Space Crafters" and b["owner"] == "Nick"


def test_another_contractor_changes_one_place(cfg, conn, smith):
    c = create_app(cfg).test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    data = {"csrf": "t", "brand_name": "Hudson Valley Builders", "brand_short": "HVB", "brand_owner": "Dana",
            "brand_legal": "Dana Cole LLC", "brand_address": "9 Main St", "brand_city": "Troy, NY 12180", "brand_phone": "518-555-0100",
            "brand_email": "dana@hvb.example", "brand_region": "Troy, NY", "brand_county": "Rensselaer County, New York",
            "brand_tagline": "Remodeling"}
    try:
        assert c.post("/setup", data=data, follow_redirects=True).status_code == 200
        home = c.get("/").data
        assert b"Hudson Valley Builders" in home and b"Reclaimed Space Crafters" not in home and b"HVB" in home
        sow_like = c.get(f"/jobs/{smith}/contract").data
        assert b"Dana Cole LLC" in sow_like and b"Rensselaer County" in sow_like and b"Briar Lane" not in sow_like
        assert "Hudson Valley Builders" in brand.localize(assist.SCOPE_PROMPT) and "Reclaimed" not in brand.localize(assist.SCOPE_PROMPT)
        assert "Nick" not in brand.localize(assist.SCOPE_PROMPT) and "Dana" in brand.localize(assist.SCOPE_PROMPT)
        assert not brand.is_default()
        assert "Hudson Valley Builders" in followups._template("review", "Pat", "", "Dana", "518")
        assert "Hudson Valley Builders" in leads.fallback_reply("Pat", "kitchen", ["Tue 4pm"], "Dana", "518")
    finally:
        brand.use(None)   # the brand is process-wide; put the defaults back for other tests
