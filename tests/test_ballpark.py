from rsc import ballpark, books, estimates, pipeline, rates
from rsc.mail import Mail

from .test_web import client_and_token

KITCHEN = """New submission from your website

Name: Pat Jones
Email: pat.jones@example.com
Phone: 518-555-0142
Address: 12 Bath St, Wilton
Message: Our kitchen is from 1985. We'd like new cabinets and counters, same layout."""


def form(body=KITCHEN, images=None, mid="m1"):
    return Mail(message_id=mid, mailbox="INBOX", sender="no-reply@wixforms.com", sender_name="Website",
                subject="New form submission", received_at="2026-10-20T09:00:00", body=body,
                attachment_images=images or [])


class NoModel:
    def extract(self, *a, **k):
        raise RuntimeError("model is off")


class Answers:
    """Answers the rough-range question with a fixed reply; anything else (the email reply) gets nothing usable."""
    def __init__(self, found):
        self.found, self.calls = found, []

    def extract(self, system, user, schema, images=None):
        self.calls.append((user, images))
        return dict(self.found) if schema is ballpark.SCHEMA or schema is ballpark.PHOTO_SCHEMA else {}


def test_rough_range_with_the_model_off_comes_from_the_rates(cfg, conn):
    pipeline.process(conn, cfg, [form()], NoModel())
    d = pipeline.pending(conn)[0]["data"]
    bp = d["ballpark"]
    assert bp["kind"] == "kitchen" and bp["size"] == "medium"     # not "bathroom" from the street name
    h_lo, h_hi, m_lo, m_hi = ballpark.KINDS["kitchen"]["sizes"]["medium"]
    assert bp["low"] == ballpark._round_down(h_lo * 65 + m_lo * 1.43)
    assert bp["high"] == ballpark._round_up(h_hi * 72 + m_hi * 1.43)
    assert bp["low"] % 500 == 0 and bp["low"] < bp["high"]
    assert "$65-72 a crew-hour" in bp["basis"] and "not from your past jobs" in bp["basis"]
    assert bp["questions"] == ballpark.QUESTIONS["kitchen"]
    assert "$" not in d["reply"] and str(bp["low"]) not in d["reply"]     # never in what goes to the homeowner


def test_rates_from_the_pricing_page_are_used(cfg, conn):
    rates.save_settings(conn, {"floor_rate": "80", "target_rate": "90"})
    bp = ballpark.draft(NoModel(), conn, {"project": "Small bathroom refresh"})
    h_lo, h_hi, m_lo, m_hi = ballpark.KINDS["bathroom"]["sizes"]["small"]
    assert bp["size"] == "small" and bp["low"] == ballpark._round_down(h_lo * 80 + m_lo * 1.43)
    assert "$80-90 a crew-hour" in bp["basis"]


def test_model_picks_kind_size_and_questions_but_not_prices(conn):
    model = Answers({"kind": "enclosure", "size": "large",
                     "questions": ["Is the porch roof sound?", "It should cost about $20,000", "Is the porch roof sound?", "ok"]})
    bp = ballpark.draft(model, conn, {"project": "Turn our porch into a room we can use all year"})
    assert bp["kind"] == "enclosure" and bp["size"] == "large" and bp["job_type"] == "Addition / Enclosure"
    assert bp["questions"][0] == "Is the porch roof sound?"
    assert not any("$" in q for q in bp["questions"]) and len(bp["questions"]) == ballpark.MAX_QUESTIONS
    assert sum(q == "Is the porch roof sound?" for q in bp["questions"]) == 1


def test_unknown_answers_from_the_model_fall_back_to_word_matching(conn):
    bp = ballpark.draft(Answers({"kind": "spaceship", "size": "huge", "questions": "no"}), conn,
                        {"project": "Need grab bars in the bathroom for my dad"})
    assert bp["kind"] == "safety" and bp["size"] == "medium" and bp["questions"] == ballpark.QUESTIONS["safety"][:6]


def test_photo_is_read_by_the_vision_model(cfg, conn):
    vision = Answers({"shows": "An old deck with rotted boards and a loose railing, about 12 by 16 feet."})
    body = KITCHEN.replace("Our kitchen is from 1985. We'd like new cabinets and counters, same layout.", "Can you fix this? Photo attached.")
    pipeline.process(conn, cfg, [form(body, images=[b"jpeg-bytes"])], NoModel(), vision)
    bp = pipeline.pending(conn)[0]["data"]["ballpark"]
    assert vision.calls and vision.calls[0][1] == [b"jpeg-bytes"]
    assert "rotted" in bp["photo"] and bp["kind"] == "deck" and bp["photos"] == 1


def test_past_estimates_are_repriced_at_the_target_rates(conn):
    for name, labor in (("Bryk", 6000), ("Surber", 9000)):
        n = books.create_job(conn, name)
        estimates.create(conn, n, "Bathroom")
        est = estimates.get(conn, n)
        estimates.save(conn, n, {"materials": 4000, "markup_pct": 20, "labor": labor, "upfront_pct": 10, "final_pct": 10},
                       {"crew": "2 carpenters", "duration": "10 days"}, est["phases"], [])
    bp = ballpark.draft(NoModel(), conn, {"project": "Bathroom remodel"})
    assert bp["past_jobs"] == 2 and "Your 2 past bathroom estimates" in bp["basis"]
    assert bp["low"] == ballpark._round_down(160 * 65 + 4000 * 1.43)      # 2 people x 10 days x 8 hours, at $65
    assert bp["high"] == ballpark._round_up(160 * 72 + 4000 * 1.43)


def test_approved_lead_keeps_the_range_on_the_job_and_estimate_pages(cfg, conn):
    pipeline.process(conn, cfg, [form()], NoModel())
    s = pipeline.pending(conn)[0]
    pipeline.approve(conn, s["id"], {})
    number = conn.execute("SELECT number FROM jobs").fetchone()[0]
    assert books.get_job(conn, number)["job_type"] == "Kitchen"
    assert ballpark.for_job(conn, number)["kind"] == "kitchen"
    c, _ = client_and_token(cfg)
    for path in (f"/jobs/{number}", f"/jobs/{number}/estimate"):
        html = c.get(path).get_data(as_text=True)
        assert "Rough range, for you only" in html and "Same layout, or moving the sink" in html, path


def test_review_page_shows_the_range(cfg, conn):
    pipeline.process(conn, cfg, [form()], NoModel())
    c, _ = client_and_token(cfg)
    html = c.get("/review").get_data(as_text=True)
    assert "Rough range, for you only" in html and "Ask or check at the visit" in html


def test_applicants_get_no_range(cfg, conn):
    body = KITCHEN.replace("Our kitchen is from 1985. We'd like new cabinets and counters, same layout.",
                           "I'm looking for work as a carpenter, 6 years of experience.")
    pipeline.process(conn, cfg, [form(body)], NoModel())
    assert "ballpark" not in pipeline.pending(conn)[0]["data"]


def test_a_broken_range_never_loses_the_lead(cfg, conn, monkeypatch):
    def boom(*a, **k):
        raise ValueError("bad")
    monkeypatch.setattr(ballpark, "draft", boom)
    rep = pipeline.process(conn, cfg, [form()], NoModel())
    assert rep.suggestions == 1 and "ballpark" not in pipeline.pending(conn)[0]["data"]
