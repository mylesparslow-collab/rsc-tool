import json
from datetime import date

from rsc import books, crew, db, estimates, report, scorecard
from rsc.web import create_app

TODAY = date(2026, 10, 21)          # a Wednesday; the week starts Monday 2026-10-19


def lead(conn, name, notes="", created="2026-10-19 09:00:00", **fields):
    n = books.create_job(conn, name, notes=notes, **fields)
    conn.execute("UPDATE jobs SET created_at = ? WHERE number = ?", (created, n))
    conn.commit()
    return n


def quote(conn, n, labor, crew_text="2 people", duration="10 days on-site"):
    estimates.create(conn, n, "Other")
    estimates.save(conn, n, {"labor": labor, "markup_pct": 43}, {"crew": crew_text, "duration": duration},
                   [{"title": "A", "steps": []}], [])


def test_source_comes_from_the_notes():
    assert scorecard.lead_source("Bathroom redo. (Found us: nextdoor.)") == "Nextdoor"
    assert scorecard.lead_source("clicked rscrafters.com/?src=tiktok") == "TikTok"
    assert scorecard.lead_source("Deck. Referred by the Hendersons") == "Referral"
    assert scorecard.lead_source("Saw us on Facebook last week") == "Facebook"
    assert scorecard.lead_source("Found us: the farmers market") == "The farmers market"
    assert scorecard.lead_source("Wants a quote on a porch") == "Not recorded"
    assert scorecard.lead_source("Kitchen with a big island, needs design help") == "Not recorded"


def test_week_counts_win_rate_and_rates(conn):
    a = lead(conn, "Avery", "(Found us: google.)")
    quote(conn, a, 11520)                                   # 160 crew-hours -> $72
    books.update_job(conn, a, estimate_sent="2026-10-19", contract_signed="2026-10-20", status="Signed", contract_total=20000)
    b = lead(conn, "Baker", "(Found us: nextdoor.)")
    quote(conn, b, 8000)                                    # $50 a crew-hour, under the floor
    books.update_job(conn, b, estimate_sent="2026-10-20", status="Lost")
    lead(conn, "Cole", "Old lead", created="2026-10-13 12:00:00")
    p = books.add_payment(conn, a, 5000, "Deposit")
    pk = books.find_payment(conn, a, p)["id"]
    books.update_payment(conn, pk, date_paid="2026-10-20", amount_paid=5000)

    card = scorecard.build(conn, TODAY)
    w = card["this_week"]
    assert (w["start"], w["leads"], w["quotes"], w["won"], w["sold"], w["collected"]) == ("2026-10-19", 2, 2, 1, 20000, 5000)
    assert card["last_week"]["leads"] == 1
    assert card["win"]["rate"] == 0.5 and card["win"]["won"] == 1 and card["win"]["lost"] == 1
    assert card["quoted"]["rate"] == round((11520 + 8000) / 320, 2)
    assert [r["job"]["number"] for r in card["quoted"]["below"]] == [b]
    src = {s["source"]: s for s in card["sources"]}
    assert src["Google"]["won"] == 1 and src["Google"]["sold"] == 20000 and src["Nextdoor"]["quotes"] == 1
    assert card["unrecorded"] == 1
    assert scorecard.level(72, card) == "ok" and scorecard.level(66, card) == "rate-warn" and scorecard.level(50, card) == "bad"


def test_earned_rate_uses_logged_hours_on_finished_jobs(conn):
    n = lead(conn, "Dunn")
    quote(conn, n, 7000)
    books.update_job(conn, n, status="Complete", contract_total=12000)
    pid = crew.add_person(conn, "Mike", "employee", 28)
    for day in range(1, 11):                                # 10 days x 10 hours = 100 hours -> $70
        conn.execute("INSERT INTO crew_hours (job_number, crew_id, work_date, hours) VALUES (?, ?, ?, 10)", (n, pid, f"2026-10-{day:02d}"))
    conn.commit()
    assert scorecard.build(conn, TODAY)["earned"]["rate"] == 70


def test_pending_website_lead_counts_but_applicants_dont(conn):
    for i, data in enumerate([{"name": "Eve Ford", "project": "Shower (Found us: instagram.)"},
                              {"name": "Job Seeker", "project": "hiring?", "applicant": True}]):
        conn.execute("INSERT INTO emails (message_id, mailbox) VALUES (?, 'INBOX')", (f"m{i}",))
        conn.execute("INSERT INTO suggestions (email_id, kind, data, created_at) VALUES (?, 'lead', ?, '2026-10-20 08:00:00')",
                     (i + 1, json.dumps(data)))
    conn.commit()
    card = scorecard.build(conn, TODAY)
    assert card["this_week"]["leads"] == 1 and card["pending_leads"] == 1
    assert card["sources"][0]["source"] == "Instagram"


def test_empty_books_still_render(conn, cfg):
    card = scorecard.build(conn, TODAY)
    assert card["win"]["rate"] is None and card["quoted"]["rate"] is None and len(card["weeks"]) == 8
    c = create_app(cfg).test_client()
    page = c.get("/scorecard?date=2026-10-21").get_data(as_text=True)
    assert "Scorecard" in page and "Not connected yet" in page and "Website visits" in page


def test_page_and_monday_report_show_the_numbers(conn, cfg):
    a = lead(conn, "Avery", "(Found us: google.)", created="2026-10-14 09:00:00")
    quote(conn, a, 11520)
    books.update_job(conn, a, estimate_sent="2026-10-15", contract_signed="2026-10-16", status="Signed", contract_total=20000)
    page = create_app(cfg).test_client().get("/scorecard?date=2026-10-21").get_data(as_text=True)
    assert "Google" in page and "$72" in page and "100%" in page
    text = report.render_text(report.build(conn, TODAY), "Intro.")
    assert "LEADS AND SALES" in text and "Last week: 1 new leads, 1 estimates sent, 1 signed" in text
    assert "Where leads came from: Google 1" in text
