from datetime import datetime, timedelta

from rsc import autocheck, prefs

from .test_web import client_and_token


class Report:
    def summary(self):
        return "Checked 4 emails: 1 expense to review."


def _ready(cfg, monkeypatch, agent=False, gmail=True):
    monkeypatch.setattr(autocheck, "gmail_ready", lambda cfg: gmail)
    monkeypatch.setattr(autocheck, "agent_installed", lambda: agent)


def test_a_check_runs_and_is_remembered(cfg, conn, monkeypatch):
    _ready(cfg, monkeypatch)
    now = datetime(2026, 10, 14, 9, 0)
    assert autocheck.tick(cfg, lambda c: Report(), now) == "ok"
    assert prefs.get(conn, "mail_last_message").startswith("Checked 4 emails")
    d = autocheck.describe(cfg, conn, True, now + timedelta(minutes=12))
    assert d["last_ago"] == "12 minutes ago" and d["enabled"] and d["active"]


def test_it_stays_quiet_when_it_should(cfg, conn, monkeypatch):
    ran = []
    run = lambda c: ran.append(1) or Report()
    _ready(cfg, monkeypatch, gmail=False)
    assert autocheck.tick(cfg, run) == "no_gmail"          # no Gmail set up yet
    _ready(cfg, monkeypatch, agent=True)
    assert autocheck.tick(cfg, run) == "agent"             # the installer's background agent already does it
    _ready(cfg, monkeypatch)
    prefs.put(conn, "auto_mail", "off")
    assert autocheck.tick(cfg, run) == "off"               # switched off on Setup
    assert ran == []


def test_busy_is_skipped_and_failure_is_reported_plainly(cfg, conn, monkeypatch):
    _ready(cfg, monkeypatch)

    def busy(c):
        raise RuntimeError("Already checking email")

    def broken(c):
        raise OSError("Gmail said no")
    assert autocheck.tick(cfg, busy) == "busy" and prefs.get(conn, "mail_last_message") == ""
    assert autocheck.tick(cfg, broken) == "failed"
    assert prefs.get(conn, "mail_last_message") == "Email check failed: Gmail said no"


def test_scheduler_runs_then_repeats_and_survives_errors(cfg, conn, monkeypatch):
    _ready(cfg, monkeypatch)
    calls = []

    def run(c):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("flaky")
        return Report()
    s = autocheck.Scheduler(cfg, run, interval=0.05, first_delay=0.01)
    s.start()
    for _ in range(100):
        if len(s.results) >= 2:
            break
        s.join(0.05)
    s.stop()
    assert s.results[:2] == ["failed", "ok"]


def test_setup_and_home_describe_it_only_inside_the_app(cfg, monkeypatch):
    _ready(cfg, monkeypatch)
    c, tok = client_and_token(cfg)
    assert "Check my email by myself" not in c.get("/setup").get_data(as_text=True)   # plain browser: no timer here
    from rsc.web import create_app
    app = create_app(cfg)
    app.config["AUTO_MAIL"] = True
    app.testing = True
    c2 = app.test_client()
    page = c2.get("/setup").get_data(as_text=True)
    assert "Check my email by myself every 30 minutes while RSC is open" in page and "checked" in page
    import re
    t2 = re.search(r'name="csrf" value="([0-9a-f]+)"', c2.get("/").get_data(as_text=True)).group(1)
    c2.post("/setup/auto-mail", data={"csrf": t2})   # box unticked
    assert "checked" not in c2.get("/setup").get_data(as_text=True).split("Checking your email")[1].split("</form>")[0]
