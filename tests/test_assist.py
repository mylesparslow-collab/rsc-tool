import re

import pytest

from rsc import assist, books, estimates
from rsc.web import create_app


class ScriptedModel:
    """Answers by what is being asked for, like the real model with a JSON schema."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def extract(self, system, user, schema, images=None):
        self.calls.append((system, user))
        props = set(schema["properties"])
        if "phases" in props:
            return self.answers["scope"]
        if "lines" in props:
            return self.answers["prices"]
        if "last_name" in props:
            return self.answers["job"]
        if "direction" in props:
            return self.answers["change"]
        return self.answers["expense"]


SCOPE = {"job_type": "Kitchen", "duration": "5 to 6 weeks", "project": "Redo the kitchen.", "crew": "1 general contractor, 1 laborer",
         "materials_list": ["Cabinets", "5/4x6x16 treated decking, 44"], "payment_groups": "1-2; 3",
         "phases": [{"title": "Phase 1: Demolition", "steps": ["1. Protect the home", "Demolish old kitchen"]},
                    {"title": "Framing", "steps": ["Frame the new wall"]},
                    {"title": "Cabinets", "steps": ["Install cabinets"]}],
         "labor_not_included": ["Flooring"], "materials_not_included": ["Appliances"],
         "open_decisions": ["Counter color"], "unsure": ["Assumed 12x14 room."]}
PRICES = {"lines": [{"item": "Cabinets", "kind": "materials", "amount": 6000, "stated_by_nick": True},
                    {"item": "Counters and other materials", "kind": "materials", "amount": 2000, "stated_by_nick": False},
                    {"item": "Labor", "kind": "labor", "amount": 11000, "stated_by_nick": False},
                    {"item": "Dump fee", "kind": "debris", "amount": 300, "stated_by_nick": False},
                    {"item": "Electrician", "kind": "hired_labor", "amount": 1500, "stated_by_nick": False},
                    {"item": "Cabinets deposit", "kind": "other", "amount": 2000, "stated_by_nick": False}]}
KITCHEN = {"scope": SCOPE, "prices": PRICES}


def expense_fields(**kw):
    base = {"kind": "other", "confidence": .9, "vendor": "", "date": "", "total": 0, "description": "", "category": "",
            "rsc_code": "", "job_clue": "", "payer_name": "", "amount_received": 0, "reference": "", "lead_name": "",
            "lead_email": "", "lead_phone": "", "lead_address": "", "lead_project": ""}
    return {**base, **kw}


def test_draft_is_cleaned_and_saved(conn):
    n = books.create_job(conn, "Smith", first_name="Jane")
    job = books.get_job(conn, n)
    draft = assist.draft_estimate(ScriptedModel(**KITCHEN), conn, job, "kitchen redo")
    assert draft["phases"][0]["steps"] == ["Protect the home", "Demolish old kitchen"]  # typed numbering dropped
    assert draft["phases"][0]["title"] == "Demolition"
    assert [p["inspection"] for p in draft["phases"]] == ["", "Framing inspection", "Final inspection"]
    assist.apply_draft(conn, n, draft)
    est = estimates.get(conn, n)
    assert est["labor"] == 11000 and est["materials"] == 8000 and est["others"] == [{"label": "Cabinets deposit", "amount": 2000}]
    assert "Assumed 12x14 room." in est["assumptions"] and "Labor: $11,000" in est["assumptions"] and "Cabinets: $6,000" not in est["assumptions"]
    assert estimates.totals(est)["total"] == 8000 * 1.43 + 11000 + 300 + 2000
    assert len(estimates.build_schedule(est)) == 3  # first payment + the two payment groups "1-2; 3"


def test_bad_model_output_is_made_safe(conn):
    n = books.create_job(conn, "Smith")
    junk = {"job_type": "Spaceship", "duration": "", "phases": [], "labor_not_included": ["materials"],
            "materials_not_included": [], "open_decisions": [], "unsure": []}
    zeros = {"lines": [{"item": "x", "kind": "labor", "amount": -5, "stated_by_nick": False},
                       {"item": "y", "kind": "materials", "amount": "lots", "stated_by_nick": False}]}
    draft = assist.draft_estimate(ScriptedModel(scope=junk, prices=zeros), conn, books.get_job(conn, n), "x")
    assert draft["job_type"] == "Other" and draft["scalars"]["materials"] == 0 and draft["scalars"]["labor"] == 0
    assert draft["phases"]  # falls back to the template rather than an empty scope
    assert any("couldn't work out prices" in a for a in draft["assumptions"])


def test_revision_sends_current_draft_and_instruction(conn):
    n = books.create_job(conn, "Smith")
    job = books.get_job(conn, n)
    model = ScriptedModel(**KITCHEN)
    assist.apply_draft(conn, n, assist.draft_estimate(model, conn, job, "kitchen"))
    assist.draft_estimate(model, conn, job, "kitchen", current=estimates.get(conn, n), instruction="labor is $12,000")
    sent = model.calls[-1][1]
    assert "labor is $12,000" in sent and "Labor: 11000" in sent


def test_past_estimates_are_given_for_scale(conn):
    n = books.create_job(conn, "Old", job_type="Kitchen")
    assist.apply_draft(conn, n, assist.draft_estimate(ScriptedModel(**KITCHEN), conn, books.get_job(conn, n), "x"))
    m = books.create_job(conn, "New")
    model = ScriptedModel(**KITCHEN)
    assist.draft_estimate(model, conn, books.get_job(conn, m), "kitchen")
    assert any("recent estimates" in c[0] and "labor $11,000" in c[0] for c in model.calls)


def test_expense_from_a_line(conn):
    n = books.create_job(conn, "Smith")
    m = ScriptedModel(expense=expense_fields(kind="expense_receipt", vendor="Home Depot", total=109.91, description="studs",
                                              category="Materials", job_clue="Smith"))
    got = assist.parse_expense(m, conn, "Home Depot 109.91 studs for Smith")
    assert got["amount"] == 109.91 and got["charge_to"] == str(n) and got["vendor"] == "Home Depot"
    assert assist.parse_expense(ScriptedModel(expense=expense_fields()), conn, "hello") == {}


def test_change_order_text(conn):
    got = assist.parse_change(ScriptedModel(change={"description": "Add a window.", "amount": 1200, "direction": "add", "days_added": 2}), "x")
    assert got == {"description": "Add a window.", "amount": 1200.0, "days_added": 2}
    credit = assist.parse_change(ScriptedModel(change={"description": "Skip trim", "amount": 300, "direction": "credit", "days_added": 0}), "x")
    assert credit["amount"] == -300.0


# ---------------------------------------------------------------- through the web pages
def web(cfg, model):
    app = create_app(cfg, model=model)
    app.testing = True
    c = app.test_client()
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', c.get("/").get_data(as_text=True)).group(1)
    return c, tok


def test_new_job_from_pasted_email_makes_job_and_estimate(cfg, conn):
    model = ScriptedModel(job={"last_name": "Smith", "first_name": "Jane", "phone": "518-555-0101", "email": "",
                               "address": "45 Oak St", "job_type": "Kitchen", "notes": "Redo the kitchen"},
                          **KITCHEN)
    c, tok = web(cfg, model)
    page = c.post("/jobs/new", data={"csrf": tok, "about": "Jane Smith 45 Oak St wants a new kitchen"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Please check these" in page and "Assumed 12x14 room." in page
    job = books.get_job(conn, 1001)
    assert job["last_name"] == "Smith" and job["address"] == "45 Oak St"
    assert estimates.get(conn, 1001)["labor"] == 11000


def test_new_job_without_a_name_is_not_created(cfg, conn):
    model = ScriptedModel(job={"last_name": "", "first_name": "", "phone": "", "email": "", "address": "", "job_type": "", "notes": ""})
    c, tok = web(cfg, model)
    page = c.post("/jobs/new", data={"csrf": tok, "about": "need work done"}, follow_redirects=True).get_data(as_text=True)
    assert "find the client" in page and books.list_jobs(conn) == []


def test_model_down_gives_a_plain_message_and_manual_form_still_works(cfg, conn):
    c, tok = web(cfg, None)  # real Ollama client, nothing is listening on the test port
    cfg.model.url = "http://127.0.0.1:9"
    page = c.post("/jobs/new", data={"csrf": tok, "about": "Jane Smith kitchen"}, follow_redirects=True).get_data(as_text=True)
    assert "available" in page and books.list_jobs(conn) == []
    c.post("/jobs/new", data={"csrf": tok, "last_name": "Smith", "notes": "hand"})
    assert books.get_job(conn, 1001)["notes"] == "hand"


def test_estimate_page_draft_and_revise(cfg, conn):
    n = books.create_job(conn, "Smith")
    model = ScriptedModel(**KITCHEN)
    c, tok = web(cfg, model)
    c.post(f"/jobs/{n}/estimate/draft", data={"csrf": tok, "description": "kitchen redo"})
    assert estimates.get(conn, n)["labor"] == 11000
    model.answers["prices"] = {"lines": [{**l, "amount": 12000} if l["kind"] == "labor" else l for l in PRICES["lines"]]}
    c.post(f"/jobs/{n}/estimate/revise", data={"csrf": tok, "instruction": "labor 12000"})
    assert estimates.get(conn, n)["labor"] == 12000


def test_expense_read_prefills_form_and_adds_nothing(cfg, conn):
    n = books.create_job(conn, "Smith")
    model = ScriptedModel(expense=expense_fields(kind="expense_receipt", vendor="Home Depot", total=109.91,
                                                 description="studs", category="Materials", job_clue="Smith"))
    c, tok = web(cfg, model)
    page = c.post("/expenses/read", data={"csrf": tok, "typed": "Home Depot 109.91 studs Smith"}).get_data(as_text=True)
    assert "Check this, then add it" in page and 'value="109.91"' in page and 'value="Home Depot"' in page
    assert books.list_expenses(conn) == []


def test_change_order_from_a_sentence(cfg, conn):
    n = books.create_job(conn, "Smith", contract_total=10000)
    model = ScriptedModel(change={"description": "Add a second window on the east wall.", "amount": 1200, "direction": "add", "days_added": 2})
    c, tok = web(cfg, model)
    page = c.post(f"/jobs/{n}/change-orders", data={"csrf": tok, "description": "second window east wall $1,200, 2 days",
                                                   "amount": "", "direction": "add", "days_added": "0"},
                  follow_redirects=True).get_data(as_text=True)
    assert "1001-SMI-CO1" in page
    no_price = c.post(f"/jobs/{n}/change-orders", data={"csrf": tok, "description": "add a window", "amount": ""},
                      follow_redirects=True).get_data(as_text=True)
    assert "Include the price" in no_price


# ---------------------------------------------------------------- voice
def test_voice_endpoint(cfg, monkeypatch, conn):
    from rsc import voice
    c, tok = web(cfg, None)
    seen = {}

    def fake(audio, model, cache, suffix):
        seen.update(audio=audio, model=model, suffix=suffix)
        return "labor is eleven thousand"
    monkeypatch.setattr(voice, "transcribe", fake)
    from io import BytesIO
    r = c.post("/voice", data={"csrf": tok, "audio": (BytesIO(b"abc"), "clip", "audio/mp4")}, content_type="multipart/form-data")
    assert r.get_json() == {"text": "labor is eleven thousand"} and seen["suffix"] == ".mp4" and seen["model"] == "base.en"
    assert c.post("/voice", data={"csrf": tok}).status_code == 400
    assert c.post("/voice", data={"audio": (BytesIO(b"abc"), "clip")}, content_type="multipart/form-data").status_code == 400  # no CSRF token


def test_voice_not_installed_is_a_plain_message(cfg, monkeypatch):
    from io import BytesIO
    from rsc import voice
    monkeypatch.setattr(voice, "available", lambda: False)
    c, tok = web(cfg, None)
    r = c.post("/voice", data={"csrf": tok, "audio": (BytesIO(b"abc"), "clip")}, content_type="multipart/form-data")
    assert r.status_code == 503 and "isn't installed" in r.get_json()["error"]
    assert "voice.js" not in c.get("/jobs/new").get_data(as_text=True)


def test_mic_script_loads_only_when_voice_is_ready(cfg, monkeypatch):
    from rsc import voice
    monkeypatch.setattr(voice, "available", lambda: True)
    c, _ = web(cfg, None)
    page = c.get("/jobs/new").get_data(as_text=True)
    assert "voice.js" in page and "data-voice" in page


def test_draft_carries_nicks_estimate_fields(conn):
    n = books.create_job(conn, "Smith")
    assist.apply_draft(conn, n, assist.draft_estimate(ScriptedModel(**KITCHEN), conn, books.get_job(conn, n), "kitchen"))
    est = estimates.get(conn, n)
    assert est["project"] == "Redo the kitchen." and est["crew"].startswith("1 general") and est["milestones"] == "1-2; 3"
    assert "treated decking, 44" in est["materials_list"]
    # groups: first payment + 2 milestones
    assert len(estimates.build_schedule(est)) == 3


def test_invalid_payment_groups_are_dropped(conn):
    n = books.create_job(conn, "Smith")
    bad = {**SCOPE, "payment_groups": "1-9"}
    draft = assist.draft_estimate(ScriptedModel(scope=bad, prices=PRICES), conn, books.get_job(conn, n), "x")
    assert draft["extras"]["milestones"] == ""
