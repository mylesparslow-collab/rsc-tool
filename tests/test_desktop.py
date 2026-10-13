import urllib.request

from rsc import config, desktop


def test_first_run_makes_settings_and_database(tmp_path):
    cfg = desktop.first_run_setup(config.load(tmp_path / "RSC"))
    assert (cfg.home / "config.toml").exists() and cfg.db_path.exists()
    before = (cfg.home / "config.toml").read_text()
    desktop.first_run_setup(config.load(cfg.home))  # a second launch leaves everything alone
    assert (cfg.home / "config.toml").read_text() == before


def test_window_server_serves_the_app_on_this_mac_only(tmp_path):
    cfg = desktop.first_run_setup(config.load(tmp_path / "RSC"))
    server = desktop.start_server(cfg, 0)
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        assert desktop.is_up(url)
        assert b"Reclaimed Space Crafters" in urllib.request.urlopen(url).read()
        assert urllib.request.urlopen(url + "/static/fonts/fonts.css").status == 200
    finally:
        server.shutdown()


def test_only_mail_phone_and_web_links_leave_the_window(monkeypatch):
    opened = []
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda cmd: opened.append(cmd))
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "ssh://x"):
        desktop.open_outside(bad)
    assert opened == []
    desktop.open_outside("mailto:a@b.com?subject=Hi")
    assert len(opened) == 1 and opened[0][-1].startswith("mailto:")
