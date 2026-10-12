import pytest

from rsc import books, estimates


def whitcomb_estimate(conn):
    """The Whitcomb porch job as Nick priced it: 8 phases, $33,103."""
    n = books.create_job(conn, "Whitcomb", first_name="Charles", status="Estimate")
    estimates.create(conn, n, "Addition / Enclosure")
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 6500, "markup_pct": 0, "windows_doors": 9428, "labor": 16900, "debris": 275,
                             "upfront_pct": 10, "final_pct": 10},
                   {k: est[k] for k in estimates.TEXTS}, est["phases"], [])
    return n


def test_whitcomb_schedule_matches_the_signed_contract(conn):
    n = whitcomb_estimate(conn)
    est = estimates.get(conn, n)
    assert len(est["phases"]) == 8
    assert estimates.totals(est)["total"] == 33103
    amounts = [s["amount"] for s in estimates.build_schedule(est)]
    assert amounts == [17618, 1690, 1690, 1690, 1690, 1690, 1690, 1690, 1690, 1965]


def test_generate_schedule_sets_total_and_ids(conn):
    n = whitcomb_estimate(conn)
    assert estimates.generate_schedule(conn, n) == 10
    pays = books.list_payments(conn, n)
    assert [p["payment_id"] for p in pays][:2] == ["1001-WHI-1", "1001-WHI-2"] and pays[-1]["payment_id"] == "1001-WHI-10"
    job = books.get_job(conn, n)
    assert job["contract_total"] == 33103 and job["schedule_ok"] is True
    assert pays[0]["description"].startswith("Schedule hold + all materials, windows & door + 10% of labor")
    assert pays[-1]["description"] == "Final 10% of labor + debris / dump fee"
    assert pays[3]["due_when"].startswith("Upon completion of Phase 3 (Rough Electrical / Roofing), Step")


def test_steps_are_numbered_straight_through():
    phases = [{"steps": ["a", "b", "c"]}, {"steps": []}, {"steps": ["d", "e"]}]
    assert estimates.step_ranges(phases) == [(1, 3), None, (4, 5)]


def test_clean_steps_drops_typed_numbers_and_blanks():
    assert estimates.clean_steps("1. Frame walls\n\n  2) Roof\nPaint") == ["Frame walls", "Roof", "Paint"]


@pytest.mark.parametrize("labor,phases", [(10000.01, 3), (9999.99, 7), (1, 8), (100, 3)])
def test_schedule_always_adds_up_to_the_total_to_the_cent(conn, labor, phases):
    n = books.create_job(conn, "Lee")
    estimates.create(conn, n, "Other")
    est = estimates.get(conn, n)
    ph = [{"title": f"P{i}", "steps": ["x"], "inspection": ""} for i in range(phases)]
    estimates.save(conn, n, {"materials": 1234.56, "markup_pct": 20, "labor": labor, "debris": 99.99, "windows_doors": 0.1,
                             "upfront_pct": 10, "final_pct": 10}, {}, ph, [{"label": "Permit fee", "amount": 33.33}])
    est = estimates.get(conn, n)
    schedule = estimates.build_schedule(est)
    assert round(sum(s["amount"] for s in schedule), 2) == estimates.totals(est)["total"]
    assert all(s["amount"] > 0 for s in schedule)


def test_markup_applies_to_materials_only(conn):
    n = books.create_job(conn, "Lee")
    estimates.create(conn, n, "Other")
    estimates.save(conn, n, {"materials": 1000, "markup_pct": 20, "labor": 500}, {}, [{"title": "A", "steps": []}], [])
    t = estimates.totals(estimates.get(conn, n))
    assert (t["materials_price"], t["markup"], t["total"], t["direct_cost"]) == (1200, 200, 1700, 1000)


def test_cannot_rebuild_after_billing_or_with_other_payments(conn):
    n = whitcomb_estimate(conn)
    estimates.generate_schedule(conn, n)
    estimates.generate_schedule(conn, n)  # rebuilding an untouched schedule is fine
    assert len(books.list_payments(conn, n)) == 10
    books.update_payment(conn, books.list_payments(conn, n)[0]["id"], invoice_sent="2026-10-01")
    with pytest.raises(books.BooksError, match="invoiced or paid"):
        estimates.generate_schedule(conn, n)
    other = books.create_job(conn, "Smith")
    estimates.create(conn, other, "Other")
    estimates.save(conn, other, {"labor": 100}, {}, [{"title": "A", "steps": []}], [])
    books.add_payment(conn, other, 50, "hand-typed")
    with pytest.raises(books.BooksError, match="other payments"):
        estimates.generate_schedule(conn, other)


def test_approve_marks_the_job_signed(conn):
    n = whitcomb_estimate(conn)
    estimates.approve(conn, n, "2026-10-09")
    job = books.get_job(conn, n)
    assert (job["status"], job["contract_signed"], job["contract_total"]) == ("Signed", "2026-10-09", 33103)


@pytest.mark.parametrize("bad", [{"labor": -5}, {"upfront_pct": 60, "final_pct": 40}, {"upfront_pct": 150}])
def test_bad_numbers_are_refused(conn, bad):
    n = books.create_job(conn, "Lee")
    estimates.create(conn, n, "Other")
    with pytest.raises(books.BooksError):
        estimates.save(conn, n, bad, {}, [{"title": "A", "steps": []}], [])


def test_zero_total_cannot_make_a_schedule(conn):
    n = books.create_job(conn, "Lee")
    estimates.create(conn, n, "Kitchen")
    with pytest.raises(books.BooksError, match="Enter prices"):
        estimates.generate_schedule(conn, n)


def test_templates_all_start_cleanly(conn):
    for i, name in enumerate(estimates.TEMPLATES):
        n = books.create_job(conn, f"Test{i}")
        estimates.create(conn, n, name)
        assert estimates.get(conn, n)["phases"]


# ---------------------------------------------------------------- Nick's Hartwell and Delano estimates (October 2026)
def hartwell(conn):
    n = books.create_job(conn, "Hartwell", first_name="Paul", status="Estimate")
    estimates.create(conn, n, "Other")
    est = estimates.get(conn, n)
    phases = [{"title": f"P{i}", "steps": ["a", "b"], "inspection": ""} for i in range(1, 8)]
    estimates.save(conn, n, {"materials": 1780, "markup_pct": 0, "labor": 8500, "debris": 375},
                   {"milestones": "1-3; 4; 5-7", "labor_note": "$9,450 less 10% neighbor discount"}, phases, [])
    return n


def test_hartwell_schedule_matches_nicks_estimate(conn):
    est = estimates.get(conn, hartwell(conn))
    assert estimates.totals(est)["total"] == 10655
    sched = estimates.build_schedule(est)
    assert [s["amount"] for s in sched] == [3905, 2125, 2125, 2500]
    assert sched[1]["due_when"] == "Upon completion of Phases 1–3, Steps 1–6"
    assert sched[3]["description"].endswith("+ debris / dump fee")


def test_delano_schedule_matches_nicks_estimate(conn):
    n = books.create_job(conn, "Delano", first_name="Karen", status="Estimate")
    estimates.create(conn, n, "Deck / Exterior")
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 5920, "markup_pct": 0, "labor": 11400, "debris": 975},
                   {"milestones": "1-2 + dumpster; 3-4; 5; 6; 7-8"}, est["phases"], [])
    sched = estimates.build_schedule(estimates.get(conn, n))
    assert [s["amount"] for s in sched] == [7820, 2875, 1900, 1900, 1900, 1900]
    assert round(sum(s["amount"] for s in sched), 2) == 18295


def test_payment_groups_must_cover_every_phase(conn):
    n = hartwell(conn)
    est = estimates.get(conn, n)
    for bad in ("1-3; 5-7", "1-4; 4-7", "1-7; 8", "one; two"):
        with pytest.raises(books.BooksError):
            estimates.save(conn, n, {"materials": 1780, "labor": 8500}, {"milestones": bad}, est["phases"], [])
    assert estimates.parse_milestones("1-7", 7) == [{"phases": [1, 2, 3, 4, 5, 6, 7], "debris": False}]


def test_saving_without_new_fields_keeps_them(conn):
    n = hartwell(conn)
    est = estimates.get(conn, n)
    estimates.save(conn, n, {"materials": 1780, "labor": 8500}, {"duration": "9-11 days"}, est["phases"], [])
    again = estimates.get(conn, n)
    assert again["milestones"] == "1-3; 4; 5-7" and again["labor_note"].startswith("$9,450")


def test_revising_bumps_the_version(conn):
    n = hartwell(conn)
    assert estimates.get(conn, n)["version"] == 1
    estimates.bump_version(conn, n)
    est = estimates.get(conn, n)
    assert est["version"] == 2 and est["version_date"]


def test_nicks_real_estimates_load_and_add_up(conn):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "examples"
    ids = [estimates.import_estimate(conn, json.loads((root / f).read_text())) for f in ("hartwell-1002.json", "delano-1003.json")]
    assert [books.get_job(conn, n)["job_id"] for n in ids] == ["1001-HAR", "1002-DEL"]
    sur, bry = (estimates.get(conn, n) for n in ids)
    assert sum(len(p["steps"]) for p in sur["phases"]) == 98 and sum(len(p["steps"]) for p in bry["phases"]) == 41
    assert estimates.totals(sur)["total"] == 10655 and estimates.totals(bry)["total"] == 18295
    assert [s["amount"] for s in estimates.build_schedule(sur)] == [3905, 2125, 2125, 2500]
    assert [s["amount"] for s in estimates.build_schedule(bry)] == [7820, 2875, 1900, 1900, 1900, 1900]
    assert sur["version"] == 2 and bry["version"] == 3 and "Diamond Pier" in bry["materials_list"]
