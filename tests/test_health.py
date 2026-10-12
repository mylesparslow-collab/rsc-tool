from datetime import date

from rsc import backup, config, doctor
from rsc.web import create_app


def test_backup_once_a_day_and_keeps_thirty(cfg, conn):
    first = backup.run(cfg.db_path, cfg.home, today=date(2026, 1, 1))
    assert first and first.exists()
    assert backup.run(cfg.db_path, cfg.home, today=date(2026, 1, 1)) is None
    for d in range(2, 40):
        backup.run(cfg.db_path, cfg.home, today=date.fromordinal(date(2026, 1, 1).toordinal() + d))
    assert len(list(backup.folder(cfg.home).glob("rsc-*.db"))) == backup.KEEP


def test_backup_is_a_working_database(cfg, conn):
    import sqlite3
    path = backup.run(cfg.db_path, cfg.home, today=date(2026, 3, 3))
    assert sqlite3.connect(str(path)).execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_app_start_makes_a_backup(cfg):
    create_app(cfg)
    assert backup.latest(cfg.home)


def test_port_comes_from_config_and_sets_quickbooks_redirect(tmp_path):
    (tmp_path / "config.toml").write_text('port = 5199\n')
    cfg = config.load(tmp_path)
    assert cfg.port == 5199 and cfg.qb_redirect_uri == "http://localhost:5199/quickbooks/callback"


def test_doctor_reports_plain_rows(cfg, conn, monkeypatch):
    monkeypatch.setattr("rsc.models.ollama_installed", lambda url: None)
    rows = doctor.run(cfg, include_app=False)
    by = {r["name"]: r for r in rows}
    assert by["Database"]["ok"] and by["Data folder"]["ok"]
    assert by["Ollama (the AI program)"]["level"] == "bad" and by["Ollama (the AI program)"]["fix"]
    assert "problem" in doctor.render(rows)


def test_setup_page_shows_health(cfg):
    c = create_app(cfg).test_client()
    assert b"Health check" in c.get("/setup").data


def test_installer_scripts_parse():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for rel in ("deploy/install.sh", "deploy/uninstall.sh", "Install RSC.command", "Uninstall RSC.command"):
        assert subprocess.run(["bash", "-n", str(root / rel)]).returncode == 0, rel
