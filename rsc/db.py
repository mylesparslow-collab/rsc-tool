"""SQLite storage. One file on Nick's computer; nothing leaves the machine."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    number          INTEGER PRIMARY KEY,
    last_name       TEXT NOT NULL,
    code            TEXT NOT NULL,
    first_name      TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    job_type        TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'Estimate',
    estimate_sent   TEXT,
    contract_signed TEXT,
    contract_total  REAL,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number    INTEGER NOT NULL REFERENCES jobs(number),
    seq           INTEGER NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    due_when      TEXT NOT NULL DEFAULT '',
    amount        REAL NOT NULL DEFAULT 0,
    invoice_sent  TEXT,
    date_paid     TEXT,
    amount_paid   REAL,
    notes         TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL DEFAULT 'manual',   -- manual | schedule (from the estimate) | change_order
    change_order_id INTEGER,
    UNIQUE (job_number, seq)
);

-- One estimate / scope of work per job. Money is dollars; phases is a JSON list of
-- {title, steps: [...], inspection}; others is a JSON list of {label, amount} paid up front.
CREATE TABLE IF NOT EXISTS estimates (
    job_number     INTEGER PRIMARY KEY REFERENCES jobs(number),
    template       TEXT NOT NULL DEFAULT '',
    materials      REAL NOT NULL DEFAULT 0,
    markup_pct     REAL NOT NULL DEFAULT 20,
    windows_doors  REAL NOT NULL DEFAULT 0,
    labor          REAL NOT NULL DEFAULT 0,
    debris         REAL NOT NULL DEFAULT 0,
    hired_labor    REAL NOT NULL DEFAULT 0,
    others         TEXT NOT NULL DEFAULT '[]',
    upfront_pct    REAL NOT NULL DEFAULT 10,
    final_pct      REAL NOT NULL DEFAULT 10,
    duration       TEXT NOT NULL DEFAULT '',
    phases         TEXT NOT NULL DEFAULT '[]',
    labor_not_included     TEXT NOT NULL DEFAULT '',
    materials_not_included TEXT NOT NULL DEFAULT '',
    open_decisions TEXT NOT NULL DEFAULT '',
    assumptions    TEXT NOT NULL DEFAULT '',
    project        TEXT NOT NULL DEFAULT '',
    materials_list TEXT NOT NULL DEFAULT '',
    crew           TEXT NOT NULL DEFAULT '',
    labor_note     TEXT NOT NULL DEFAULT '',
    milestones     TEXT NOT NULL DEFAULT '',
    version        INTEGER NOT NULL DEFAULT 1,
    version_date   TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS change_orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number  INTEGER NOT NULL REFERENCES jobs(number),
    seq         INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount      REAL NOT NULL,
    days_added  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'signed', 'declined')),
    signer_name TEXT,
    signed_at   TEXT,
    signature   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (job_number, seq)
);

CREATE TABLE IF NOT EXISTS rsc_codes (
    code        TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    qb_account  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    job_number   INTEGER REFERENCES jobs(number),
    rsc_code     TEXT REFERENCES rsc_codes(code),
    vendor       TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    amount       REAL NOT NULL,
    paid_with    TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT 'manual',
    email_id     INTEGER REFERENCES emails(id),
    notes        TEXT NOT NULL DEFAULT '',
    CHECK ((job_number IS NULL) <> (rsc_code IS NULL))
);

-- Messages to send after a job is done: a review request, a one-year check-in.
CREATE TABLE IF NOT EXISTS followups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number INTEGER NOT NULL REFERENCES jobs(number),
    kind       TEXT NOT NULL CHECK (kind IN ('review', 'checkin')),
    due_date   TEXT NOT NULL,
    draft      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'skipped')),
    done_at    TEXT,
    UNIQUE (job_number, kind)
);

-- Photos of receipts, kept with the expense they became.
CREATE TABLE IF NOT EXISTS receipt_photos (
    token      TEXT PRIMARY KEY,
    expense_id INTEGER REFERENCES expenses(id),
    mime       TEXT NOT NULL,
    data       BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- The crew: employees, helpers paid by hand, and subcontractors. Wage is dollars per hour.
CREATE TABLE IF NOT EXISTS crew (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'helper' CHECK (role IN ('employee', 'helper', 'sub')),
    wage       REAL NOT NULL DEFAULT 0,
    burden_pct REAL NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1,
    note       TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT ''
);

-- Who is planned to be where, by day. crew_id NULL means "the crew" on that job, unnamed.
CREATE TABLE IF NOT EXISTS schedule (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number INTEGER NOT NULL REFERENCES jobs(number),
    crew_id    INTEGER REFERENCES crew(id),
    day        TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    UNIQUE (job_number, crew_id, day)
);

-- Payment reminders that were sent, so nobody is nagged twice in a week.
CREATE TABLE IF NOT EXISTS payment_reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    sent_on    TEXT NOT NULL,
    draft      TEXT NOT NULL DEFAULT ''
);

-- Steps of the scope of work that are finished, and the note for a day's work.
CREATE TABLE IF NOT EXISTS step_done (
    job_number INTEGER NOT NULL REFERENCES jobs(number),
    step_no    INTEGER NOT NULL,
    done_on    TEXT NOT NULL,
    PRIMARY KEY (job_number, step_no)
);
CREATE TABLE IF NOT EXISTS daily_notes (
    job_number INTEGER NOT NULL REFERENCES jobs(number),
    day        TEXT NOT NULL,
    note       TEXT NOT NULL,
    PRIMARY KEY (job_number, day)
);

-- Hours worked, by person and job.
CREATE TABLE IF NOT EXISTS crew_hours (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number INTEGER NOT NULL REFERENCES jobs(number),
    crew_id    INTEGER NOT NULL REFERENCES crew(id),
    work_date  TEXT NOT NULL,
    hours      REAL NOT NULL CHECK (hours > 0 AND hours <= 24),
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Insurance certificates. crew_id NULL means the business's own policy.
CREATE TABLE IF NOT EXISTS certificates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    crew_id    INTEGER REFERENCES crew(id),
    kind       TEXT NOT NULL DEFAULT 'General liability',
    insurer    TEXT NOT NULL DEFAULT '',
    policy_no  TEXT NOT NULL DEFAULT '',
    expires    TEXT NOT NULL DEFAULT '',
    mime       TEXT NOT NULL DEFAULT '',
    file       BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every email the tool has looked at, so nothing is read or suggested twice.
CREATE TABLE IF NOT EXISTS emails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT NOT NULL UNIQUE,
    mailbox     TEXT NOT NULL,
    received_at TEXT,
    sender      TEXT NOT NULL DEFAULT '',
    subject     TEXT NOT NULL DEFAULT '',
    skipped     TEXT,
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- What the local model proposes. Nothing touches the books until Nick approves it.
CREATE TABLE IF NOT EXISTS suggestions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id    INTEGER NOT NULL REFERENCES emails(id),
    kind        TEXT NOT NULL CHECK (kind IN ('expense', 'payment', 'lead')),
    data        TEXT NOT NULL,
    match_note  TEXT NOT NULL DEFAULT '',
    confidence  REAL NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'dismissed')),
    decided_at  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DEFAULT_RSC_CODES = [
    ("RSC-100", "Truck / vehicle: fuel, repairs, registration", "Car and truck expenses"),
    ("RSC-110", "Tools and equipment (purchased, kept)", "Tools and equipment"),
    ("RSC-120", "Insurance (liability, vehicle, workers comp)", "Insurance"),
    ("RSC-130", "Business licenses and registrations", "Taxes and licenses"),
    ("RSC-140", "Phone and internet", "Utilities"),
    ("RSC-150", "Software and subscriptions (QuickBooks, etc.)", "Office expenses"),
    ("RSC-160", "Office supplies, printing, postage", "Office expenses"),
    ("RSC-170", "Advertising and marketing (Nextdoor, website, signs)", "Advertising"),
    ("RSC-180", "Professional fees (lawyer, accountant)", "Legal and professional services"),
    ("RSC-190", "Shop / storage rent", "Rent or lease"),
    ("RSC-200", "Shop consumables not tied to one job", "Supplies"),
    ("RSC-210", "Safety gear and work clothes", "Supplies"),
    ("RSC-220", "Training, education, dues", "Other business expenses"),
    ("RSC-230", "Bank and card fees", "Bank charges and fees"),
    ("RSC-240", "Business meals", "Meals"),
    ("RSC-900", "Other / not sure (sort it out later)", "Ask My Accountant"),
]


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), detect_types=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a database made by an older version up to date."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(payments)")}
    if "kind" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN kind TEXT NOT NULL DEFAULT 'manual'")
    if "change_order_id" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN change_order_id INTEGER")
    crew_cols = {r[1] for r in conn.execute("PRAGMA table_info(crew)")}
    if crew_cols and "email" not in crew_cols:
        conn.execute("ALTER TABLE crew ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    est_cols = {r[1] for r in conn.execute("PRAGMA table_info(estimates)")}
    for col, ddl in (("assumptions", "TEXT NOT NULL DEFAULT ''"), ("project", "TEXT NOT NULL DEFAULT ''"),
                     ("materials_list", "TEXT NOT NULL DEFAULT ''"), ("crew", "TEXT NOT NULL DEFAULT ''"),
                     ("labor_note", "TEXT NOT NULL DEFAULT ''"), ("milestones", "TEXT NOT NULL DEFAULT ''"),
                     ("version", "INTEGER NOT NULL DEFAULT 1"), ("version_date", "TEXT NOT NULL DEFAULT ''")):
        if col not in est_cols:
            conn.execute(f"ALTER TABLE estimates ADD COLUMN {col} {ddl}")


def init(conn: sqlite3.Connection, first_job_number: int = 1001) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.executemany("INSERT OR IGNORE INTO rsc_codes VALUES (?, ?, ?)", DEFAULT_RSC_CODES)
    conn.execute("INSERT OR IGNORE INTO settings VALUES ('first_job_number', ?)", (str(first_job_number),))
    conn.commit()
