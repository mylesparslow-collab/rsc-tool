from rsc import crew, intake, pipeline
from rsc.mail import Mail

FORM = """New submission from your website

Name: Pat Jones
Email: pat.jones@example.com
Phone: 518-555-0142
Address: 12 Elm St, Ballston Spa
Message: We want to turn the garage into a bedroom for my mom.
She is 80 and needs a wide doorway."""

APPLY = """New submission from your website

Name: Sam Lee
Email: sam@example.com
Phone: 518-555-0199
Message: I'm looking for work as a carpenter. 6 years of experience, resume attached."""


def mail(body, subject="New form submission", sender="no-reply@wixforms.com", mid="m1"):
    return Mail(message_id=mid, mailbox="INBOX", sender=sender, sender_name="Website", subject=subject,
                received_at="2026-10-12T09:00:00", body=body)


class NoModel:
    def extract(self, *a, **k):
        raise RuntimeError("model is off")


def test_parse_form_fields():
    f = intake.parse_form("x", FORM)
    assert f["name"] == "Pat Jones" and f["email"] == "pat.jones@example.com" and "garage" in f["message"] and "doorway" in f["message"]
    assert intake.parse_form("hi", "Just wondering about your prices") is None
    assert intake.parse_form("x", "Email: not-an-address\nName: A") is None


def test_form_becomes_a_lead_even_with_the_model_off(cfg, conn):
    rep = pipeline.process(conn, cfg, [mail(FORM)], NoModel())
    assert rep.suggestions == 1 and not rep.errors
    s = pipeline.pending(conn)[0]
    assert s["kind"] == "lead" and not s["data"].get("applicant")
    assert s["data"]["email"] == "pat.jones@example.com" and s["data"]["reply_to"] == "pat.jones@example.com"
    assert "Pat" in s["data"]["reply"]
    assert "Started job" in pipeline.approve(conn, s["id"], {})


def test_application_becomes_an_applicant_and_a_crew_record(cfg, conn):
    pipeline.process(conn, cfg, [mail(APPLY, "Job inquiry")], NoModel())
    s = pipeline.pending(conn)[0]
    assert s["data"]["applicant"] and "experience" in s["data"]["reply"].lower()
    assert "applicant" in pipeline.approve(conn, s["id"], {})
    p = [x for x in crew.people(conn) if x["name"] == "Sam Lee"][0]
    assert not p["active"] and p["email"] == "sam@example.com"
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0    # no job was started for an applicant


def test_plain_email_application_is_recognised_after_the_model(cfg, conn):
    answers = {"kind": "new_lead", "confidence": 0.8, "vendor": "", "date": "", "total": 0, "description": "", "category": "",
               "rsc_code": "", "job_clue": "", "payer_name": "", "amount_received": 0, "reference": "", "lead_name": "Ana Cruz",
               "lead_email": "ana@example.com", "lead_phone": "", "lead_address": "", "lead_project": "wants a job"}
    class M:
        def extract(self, *a, **k):
            return answers
    m = mail("Hi, I'd like to apply for a carpenter position. Attached is my resume. Ana Cruz", "Carpenter position", "ana@example.com", "m2")
    pipeline.process(conn, cfg, [m], M())
    s = pipeline.pending(conn)[0]
    assert s["data"]["applicant"] and s["match_note"].startswith("someone asking about a job")


SITE = """New submission from rscrafters.com

name: Dana Ruiz
contact: (518) 555-0177
town: Wilton
source: Google
message: Hi Nick, this is Dana Ruiz. I'm planning a bathroom remodel in Wilton, in the next few months."""


def test_website_quote_form_with_only_a_phone_becomes_a_lead(cfg, conn):
    f = intake.parse_form("x", SITE)
    assert f["phone"] == "(518) 555-0177" and f["email"] == "" and f["address"] == "Wilton"
    pipeline.process(conn, cfg, [mail(SITE, "New quote request")], NoModel())
    s = pipeline.pending(conn)[0]
    assert s["kind"] == "lead" and s["data"]["reply_to"] == "" and "Dana" in s["data"]["reply"]
    assert "Found us: Google" in s["data"]["project"] and "Google" in s["match_note"]
    assert "Started job" in pipeline.approve(conn, s["id"], {})
    assert conn.execute("SELECT phone FROM jobs").fetchone()[0] == "(518) 555-0177"


def test_contact_box_with_an_email_fills_the_email():
    f = intake.parse_form("x", "Name: Al Moe\nContact: al@example.com\nMessage: deck")
    assert f["email"] == "al@example.com" and f["phone"] == ""
    assert intake.parse_form("x", "Name: Al Moe\nContact: call me\nMessage: deck") is None


def test_quote_sent_from_the_persons_own_mail_app_replies_to_them(cfg, conn):
    body = "Name: Kim Ode\nPhone: 518-555-0123\nTown: Malta\nSource: Nextdoor\nMessage: Hi Nick, this is Kim Ode. I'm planning a deck."
    pipeline.process(conn, cfg, [mail(body, "Quote request from the website", sender="kim.ode@example.com")], NoModel())
    s = pipeline.pending(conn)[0]
    assert s["data"]["reply_to"] == "kim.ode@example.com" and s["data"]["phone"] == "518-555-0123"
    pipeline.process(conn, cfg, [mail(SITE, "New quote request", sender="noreply@formspree.io", mid="m2")], NoModel())
    assert pipeline.pending(conn)[-1]["data"]["reply_to"] == ""
