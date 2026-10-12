import json
from pathlib import Path

from rsc import estimates, playbook
from rsc.web import create_app

EX = Path(__file__).resolve().parent.parent / "examples"


def _load(conn):
    return [estimates.import_estimate(conn, json.load(open(EX / f))) for f in ("hartwell-1002.json", "delano-1003.json")]


def test_brief_is_built_from_the_estimate(conn):
    hartwell, delano = _load(conn)
    b = playbook.job_brief(conn, delano)
    assert b["total_steps"] == 41 and b["phases"][0]["steps"][0][0] == 1 and b["schedule"] and b["materials"]
    assert playbook.job_brief(conn, 999) is None


def test_library_groups_by_kind_with_counts(conn):
    _load(conn)
    kinds = {k["kind"]: k for k in playbook.library(conn)}
    assert len(kinds) == 2
    deck = kinds["Deck / Exterior"]
    assert deck["count"] == 1 and deck["avg_hours"] and deck["avg_labor"] > 0


def test_pages(cfg, conn):
    _, delano = _load(conn)
    c = create_app(cfg).test_client()
    assert b"How we build it" in c.get("/playbook").data
    r = c.get(f"/jobs/{delano}/crew-brief")
    assert b"Crew brief" in r.data and b"Before you start" in r.data and b"change order" in r.data
    assert c.get("/jobs/4242/crew-brief").status_code == 404
