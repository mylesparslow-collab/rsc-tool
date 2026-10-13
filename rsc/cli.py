"""Command line: `rsc setup`, `rsc serve`, `rsc check-mail`, `rsc import`, `rsc export`."""
import argparse
import getpass
import logging
import os
import socket
import urllib.error
import sys
import webbrowser
from pathlib import Path

from . import books, config, db, estimates, models, sheets
from .llm import ModelUnavailable, OllamaModel

EXAMPLE_CONFIG = """# Reclaimed Space Crafters tool settings
first_job_number = 1001

[mail]
address = "{address}"
mailboxes = ["INBOX"]
first_run_days = 30      # how far back to look the first time
# ignore_senders = ["newsletter@example.com"]

[model]
url = "http://localhost:11434"
name = "{model}"          # reads email, writes estimates, fills in forms
vision = "{vision}"       # reads photos of receipts

[voice]
model = "{speech}"        # the microphone buttons
"""


def cmd_setup(cfg: config.Config, args) -> int:
    cfg.home.mkdir(parents=True, exist_ok=True)
    path = cfg.home / "config.toml"
    if not path.exists():
        address = (args.email if args.email is not None else input("Gmail address to read (Return to skip): ")).strip()
        pick = models.prefer_installed(models.recommend(models.total_ram_gb()), models.ollama_installed(cfg.model.url))
        path.write_text(EXAMPLE_CONFIG.format(address=address, model=args.text_model or pick["text"],
                                              vision=args.vision_model or pick["vision"], speech=pick["speech"]))
        print(f"Wrote {path}")
    cfg = config.load(cfg.home)
    conn = db.connect(cfg.db_path)
    db.init(conn, cfg.first_job_number)
    print(f"Database ready at {cfg.db_path}")
    if args.tracker:
        print("Imported:", sheets.import_tracker(conn, args.tracker))
    try:
        OllamaModel(cfg.model.url, cfg.model.name).check()
        print(f"Local model OK: {cfg.model.name}")
    except ModelUnavailable as exc:
        print(f"Local model not ready: {exc}")
    return 0


def cmd_models(cfg: config.Config, args) -> int:
    print("Which model does what:")
    for r in models.status(cfg):
        state = "ready" if r["ready"] else ("not downloaded" if r["model"] else "not chosen")
        print(f"  {r['role']:<7} {r['model'] or '-':<22} {state:<15} {r['what']}")
    if args.pull:
        print("Downloading what is missing:")
        problems = models.ensure(cfg)
        for p in problems:
            print("  !", p)
        return 1 if any("download" in p or "running" in p for p in problems) else 0
    return 0


def cmd_voice_setup(cfg: config.Config, _args) -> int:
    from . import voice
    if not voice.available():
        print("Voice typing isn't installed (pip install faster-whisper).")
        return 1
    print(f"Getting the speech model ({cfg.voice.model}); this downloads once...")
    voice.load(cfg.voice.model, cfg.voice_cache)
    print("Voice typing is ready.")
    return 0


def cmd_load_example(cfg: config.Config, args) -> int:
    import json
    conn = db.connect(cfg.db_path)
    db.init(conn, cfg.first_job_number)
    for path in args.paths:
        number = estimates.import_estimate(conn, json.loads(Path(path).read_text()))
        job = books.get_job(conn, number)
        print(f"Loaded {path} as job {job['job_id']}")
    return 0


def cmd_set_password(cfg: config.Config, _args) -> int:
    if not cfg.mail.address:
        print("Run `rsc setup` first.")
        return 1
    print("Create a Gmail app password at https://myaccount.google.com/apppasswords (needs 2-Step Verification).")
    pw = getpass.getpass(f"App password for {cfg.mail.address}: ").replace(" ", "")
    if not pw:
        print("Skipped. Run `rsc set-password` when you have it.")
        return 0
    config.save_mail_password(cfg.mail.address, pw)
    print("Saved to the macOS Keychain.")
    return 0


def _lan_address() -> str:
    """This computer's address on the local network (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "this-computer's-address"
    finally:
        s.close()


def cmd_serve(cfg: config.Config, args) -> int:
    from .web import create_app
    if args.lan and len(cfg.access_pin) < 6:
        print("Phone access needs a PIN first. Add this line to " + str(cfg.home / "config.toml") + ":\n\n"
              '    access_pin = "choose-6-or-more-characters"\n')
        return 1
    args.port = args.port or cfg.port
    app = create_app(cfg, lan=args.lan)
    url = f"http://localhost:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    print(f"RSC is running at {url}  (Ctrl+C to stop)")
    if args.lan:
        print(f"On your phone (same Wi-Fi), open http://{_lan_address()}:{args.port} and enter the PIN.")
        print("Home Wi-Fi only. Don't forward this port to the internet.")
    app.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
    return 0


def cmd_check_mail(cfg: config.Config, _args) -> int:
    from .web import run_mail_check
    if not cfg.mail.address:
        print("Email isn't set up yet. Open the app's Setup page.")  # the schedule runs from the start; this is not an error
        return 0
    try:
        config.mail_password(cfg.mail.address)
    except RuntimeError:
        print("No Gmail app password saved yet. Open the app's Setup page.")
        return 0
    db.init(db.connect(cfg.db_path), cfg.first_job_number)
    try:
        from . import backup
        backup.run(cfg.db_path, cfg.home)
    except Exception:
        pass
    try:
        report = run_mail_check(cfg)
    except Exception as exc:
        print(f"Email check failed: {exc}", file=sys.stderr)
        return 1
    print(report.summary())
    for err in report.errors:
        print("  could not read:", err, file=sys.stderr)
    return 0


def cmd_weekly_report(cfg: config.Config, args) -> int:
    from . import report
    conn = db.connect(cfg.db_path)
    db.init(conn, cfg.first_job_number)
    model = None
    try:
        model = OllamaModel(cfg.model.url, cfg.model.name, cfg.model.timeout_seconds)
        model.check()
    except ModelUnavailable:
        model = None  # the numbers don't need it; only the opening sentence does
    r = report.build(conn)
    text = report.render_text(r, report.opening(model, r))
    if not args.send:
        print(text)
        return 0
    try:
        to = report.send(conn, cfg.mail.address, config.mail_password(cfg.mail.address), text, report.subject(r))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Report not sent: {exc}", file=sys.stderr)
        return 1
    print("Sent to", ", ".join(to))
    return 0


def cmd_daily_sheet(cfg: config.Config, args) -> int:
    from datetime import date
    from . import daily
    conn = db.connect(cfg.db_path)
    db.init(conn, cfg.first_job_number)
    d = daily.build(conn)
    if not args.send:
        print(daily.render_text(d))
        return 0
    if not d["jobs"]:
        print("No jobs in progress today; nothing sent.")
        return 0
    try:
        to = daily.send(conn, cfg.mail.address, config.mail_password(cfg.mail.address), d)
    except ValueError as exc:   # nobody to send to yet: not an error, the Setup page explains
        print(f"Daily sheet not sent: {exc}")
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"Daily sheet not sent: {exc}", file=sys.stderr)
        return 1
    print("Sent to", ", ".join(to))
    return 0


def cmd_doctor(cfg: config.Config, _args) -> int:
    from . import doctor
    rows = doctor.run(cfg)
    print(doctor.render(rows))
    return 1 if any(r["level"] == "bad" for r in rows) else 0


def cmd_backup(cfg: config.Config, _args) -> int:
    from . import backup
    path = backup.run(cfg.db_path, cfg.home)
    print(f"Backed up to {path}" if path else "Today's backup already exists (or there is nothing to back up yet).")
    return 0


def cmd_open(cfg: config.Config, _args) -> int:
    """What the Desktop icon runs: start whatever isn't running, then open the app in the browser."""
    import subprocess
    import time
    import urllib.request
    import webbrowser
    models.start_ollama(cfg.model.url, wait_seconds=0)  # the AI is only needed once a form is filled in
    url = f"http://localhost:{cfg.port}"

    def up():
        try:
            urllib.request.urlopen(url, timeout=2).close()
            return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            return False
    if not up():
        subprocess.Popen([sys.executable, "-m", "rsc.cli", "serve", "--no-browser"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "RSC_HOME": str(cfg.home)})
        for _ in range(20):
            if up():
                break
            time.sleep(1)
    webbrowser.open(url)
    return 0


def cmd_desktop(cfg: config.Config, _args) -> int:
    from . import desktop
    return desktop.main(cfg.home)


def cmd_import(cfg: config.Config, args) -> int:
    conn = db.connect(cfg.db_path)
    db.init(conn, cfg.first_job_number)
    print("Imported:", sheets.import_tracker(conn, args.path))
    return 0


def cmd_export(cfg: config.Config, args) -> int:
    print("Wrote", sheets.export(db.connect(cfg.db_path), args.path))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rsc", description="Reclaimed Space Crafters jobs, billing and email assistant")
    parser.add_argument("--home", type=Path, help="data folder (default ~/RSC)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup", help="first-time setup")
    p.add_argument("--tracker", type=Path, help="import an existing RSC Job Tracker.xlsx")
    p.add_argument("--email", help="Gmail address to read (asked if not given)")
    p.add_argument("--text-model", help="override the text model (default is chosen from this computer's memory)")
    p.add_argument("--vision-model", help="override the photo model")
    p = sub.add_parser("models", help="show which model does which job, and download any that are missing")
    p.add_argument("--pull", action="store_true", help="download missing models")
    sub.add_parser("voice-setup", help="download the speech-to-text model for voice typing")
    p = sub.add_parser("load-example", help="load job + estimate files like examples/hartwell-1002.json")
    p.add_argument("paths", nargs="+", type=Path)
    sub.add_parser("set-password", help="store the Gmail app password in the Keychain")
    p = sub.add_parser("serve", help="open the app in the browser")
    p.add_argument("--port", type=int, default=None, help="default: the port in config.toml, else 5151")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--lan", action="store_true", help="also allow a phone on the same Wi-Fi (needs access_pin in config.toml)")
    p = sub.add_parser("weekly-report", help="show the weekly report (add --send to email it to the people on the Setup page)")
    p.add_argument("--send", action="store_true")
    p = sub.add_parser("daily-sheet", help="show today's work sheet (add --send to email it to the crew)")
    p.add_argument("--send", action="store_true")
    sub.add_parser("doctor", help="check that everything works and say how to fix what doesn't")
    sub.add_parser("backup", help="copy the database into the backups folder (done automatically each day)")
    sub.add_parser("open", help="open the app in the browser, starting it first if needed")
    sub.add_parser("desktop", help="open the app in its own window (what RSC.app runs)")
    sub.add_parser("check-mail", help="read new email and queue suggestions (for the schedule)")
    p = sub.add_parser("import", help="import an RSC Job Tracker.xlsx")
    p.add_argument("path", type=Path)
    p = sub.add_parser("export", help="export everything to Excel")
    p.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = config.load(args.home)
    handler = {"setup": cmd_setup, "set-password": cmd_set_password, "load-example": cmd_load_example, "voice-setup": cmd_voice_setup, "models": cmd_models, "serve": cmd_serve,
               "check-mail": cmd_check_mail, "doctor": cmd_doctor, "daily-sheet": cmd_daily_sheet, "backup": cmd_backup, "open": cmd_open, "desktop": cmd_desktop, "weekly-report": cmd_weekly_report, "import": cmd_import, "export": cmd_export}[args.cmd]
    return handler(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
