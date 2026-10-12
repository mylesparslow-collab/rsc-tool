from pathlib import Path

import pytest

from rsc import books, db
from rsc.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


class FakeModel:
    """Stands in for Ollama: answers by subject, like the real model would."""

    BLANK = {"kind": "other", "confidence": 0.9, "vendor": "", "date": "", "total": 0, "description": "",
             "category": "", "rsc_code": "", "job_clue": "", "payer_name": "", "amount_received": 0,
             "reference": "", "lead_name": "", "lead_email": "", "lead_phone": "", "lead_address": "",
             "lead_project": ""}

    def __init__(self, answers: dict[str, dict]):
        self.answers = answers
        self.calls: list[str] = []

    def extract(self, system, user, schema, images=None):
        self.calls.append(user)
        for subject, fields in self.answers.items():
            if f"Subject: {subject}" in user:
                return {**self.BLANK, **fields}
        return dict(self.BLANK)


@pytest.fixture
def cfg(tmp_path):
    c = Config(home=tmp_path)
    c.mail.address = "nfparslow@gmail.com"
    return c


@pytest.fixture
def conn(cfg):
    c = db.connect(cfg.db_path)
    db.init(c)
    return c


@pytest.fixture
def smith(conn):
    """An open job with a 3-payment schedule, like a small Whitcomb."""
    n = books.create_job(conn, "Smith", first_name="Jane", address="45 Oak St, Saratoga Springs",
                         status="Signed", contract_total=10000)
    books.add_payment(conn, n, 5000, "Deposit + materials", "At signing")
    books.add_payment(conn, n, 2500, "Phase 1", "When Phase 1 is complete")
    books.add_payment(conn, n, 2500, "Final", "At sign-off")
    return n
