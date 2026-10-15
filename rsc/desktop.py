"""The Mac app: the same local server, shown in its own window instead of a browser tab.

`rsc desktop` (or double-clicking RSC.app) does this:
  1. First launch only: makes ~/RSC with a settings file and an empty database (the same thing `rsc setup` does).
  2. Starts its own copy of the server inside this process, on this Mac only (the settings' port if it is free, otherwise any
     free one). It never attaches to a server that is already running, so it can't land on a PIN page left by a phone or
     Tailscale setup. The window itself needs no PIN: nothing outside this Mac can reach it. Your settings file is not changed.
  3. Opens a window. Mail drafts (mailto:) and anything outside the app open in the normal apps.
Nothing here talks to the internet; the window only ever shows http://127.0.0.1.
"""
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

from . import config, db, models

TITLE = "Reclaimed Space Crafters"

# Runs in the page: sends mailto: links and links to other sites to the normal apps. A window has no address bar.
LINK_HANDLER = """
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a[href]'); if (!a) return;
  var u = new URL(a.href, location.href);
  if (u.protocol === 'mailto:' || u.protocol === 'tel:' || (u.protocol.indexOf('http') === 0 && u.origin !== location.origin)) {
    e.preventDefault(); window.pywebview.api.open_outside(a.href);
  }
}, true);
"""


def is_up(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2).close()
        return True
    except urllib.error.HTTPError:
        return True  # it answered (for example with the PIN page)
    except (urllib.error.URLError, OSError):
        return False


def first_run_setup(cfg: config.Config) -> config.Config:
    """Create the data folder, settings and database if this Mac has none yet. Never touches existing ones."""
    if (cfg.home / "config.toml").exists() and cfg.db_path.exists():
        return cfg
    from . import cli
    cli.cmd_setup(cfg, SimpleNamespace(email="", text_model=None, vision_model=None, tracker=None))
    return config.load(cfg.home)


def start_server(cfg: config.Config, port: int, quit_app=None):
    """Serve the app in a background thread of this process, on this Mac only. Returns the server so it can be shut down.
    The PIN is for phones and other computers; this server can't be reached from them, so the window skips it."""
    from werkzeug.serving import make_server
    from . import updater
    from .web import create_app
    cfg.access_pin = ""  # in memory only; config.toml keeps the PIN for the background app that serves the phone
    app = create_app(cfg)
    app.config["CHECK_UPDATES"] = updater.register(app, cfg, lambda: db.connect(cfg.db_path), quit_app or (lambda: None))
    server = make_server("127.0.0.1", port, app, threaded=True)
    server.app = app
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def open_outside(target: str) -> None:
    """Hand a mail draft or outside link to macOS (Mail, the browser)."""
    if target.startswith(("mailto:", "tel:", "http://", "https://")):
        subprocess.Popen(["open", target] if sys.platform == "darwin" else ["xdg-open", target])


def main(home=None) -> int:
    try:
        import webview
    except ImportError:
        print("The app window needs one more piece:  .venv/bin/pip install pywebview\n"
              "(Or just run  rsc open  to use it in the browser.)")
        return 1
    cfg = first_run_setup(config.load(home))
    models.apply_choice(cfg)
    server = start_server(cfg, cfg.port if not is_up(f"http://127.0.0.1:{cfg.port}") else 0, quit_app=lambda: window.destroy())
    url = f"http://127.0.0.1:{server.server_port}"
    if os.environ.get("RSC_DESKTOP_SELFTEST"):  # used when building RSC.app: prove the packaged pieces are all there, then quit
        ok = is_up(url) and b"stylesheet" in urllib.request.urlopen(url, timeout=5).read() \
            and urllib.request.urlopen(url + "/static/fonts/fonts.css", timeout=5).status == 200
        from . import estimate_mail
        ok = ok and estimate_mail.selftest()   # the PDF maker for emailed estimates must be inside the app too
        print("selftest ok" if ok else "selftest FAILED")
        return 0 if ok else 1

    class Api:
        def open_outside(self, target):
            open_outside(target)

        def open_in_browser(self):
            open_outside(window.get_current_url() or url)

    api = Api()
    window = webview.create_window(TITLE, url, js_api=api, width=1280, height=860, min_size=(480, 560), text_select=True)
    window.events.loaded += lambda: window.evaluate_js(LINK_HANDLER)
    menu = [webview.menu.Menu("Page", [
        webview.menu.MenuAction("Check for updates", lambda: window.load_url(url + "/update")),
        webview.menu.MenuAction("Open this page in the browser (to print or save)", api.open_in_browser)])]
    from . import autocheck
    from .web import run_mail_check
    server.app.config["AUTO_MAIL"] = True   # Setup and Home then describe the automatic email check
    checker = autocheck.Scheduler(cfg, run_mail_check)
    checker.start()
    server.app.config["CHECK_UPDATES"]()   # one quiet look at GitHub for a newer version; the banner appears if there is one
    webview.start(menu=menu)
    checker.stop()
    server.shutdown()
    return 0
