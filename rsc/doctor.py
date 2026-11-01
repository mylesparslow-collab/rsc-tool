"""`rsc doctor`: is everything this app needs actually working? Plain words, one fix per problem.

Used from Terminal, and on the Setup page, so Nick (or Myles over the phone) can see what's wrong in ten seconds.
"""
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import backup, brand, config, models

AGENTS = {"app": "keeps the app running", "checkmail": "checks email every 10 minutes",
          "weeklyreport": "sends the Monday report", "dailysheet": "sends the weekday work sheet"}


def _row(name, level, detail, fix=""):
    return {"name": name, "level": level, "ok": level == "ok", "detail": detail, "fix": fix}


def _disk(cfg):
    try:
        free = shutil.disk_usage(cfg.home if cfg.home.exists() else cfg.home.parent).free / 2**30
    except OSError:
        return _row("Disk space", "warn", "Couldn't check.")
    if free < 3:
        return _row("Disk space", "bad", f"Only {free:.1f} GB free.", "Free up space (empty the Trash, remove old downloads). The AI models need about 10 GB.")
    if free < 10:
        return _row("Disk space", "warn", f"{free:.1f} GB free.", "Models and backups need room; free up some space soon.")
    return _row("Disk space", "ok", f"{free:.0f} GB free")


def _folder(cfg):
    try:
        cfg.home.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cfg.home):
            pass
        return _row("Data folder", "ok", str(cfg.home))
    except OSError as exc:
        return _row("Data folder", "bad", f"Can't write to {cfg.home} ({exc}).", "Check the folder's permissions, or run Install RSC again.")


def _database(cfg):
    if not cfg.db_path.exists():
        return _row("Database", "bad", "Not created yet.", "Run Install RSC again.")
    try:
        c = sqlite3.connect(str(cfg.db_path))
        try:
            result = c.execute("PRAGMA quick_check").fetchone()[0]
            jobs = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        finally:
            c.close()
    except sqlite3.Error as exc:
        return _row("Database", "bad", f"Can't read it ({exc}).", f"Restore the newest file in {backup.folder(cfg.home)}.")
    if result != "ok":
        return _row("Database", "bad", f"Problems found: {result}", f"Restore the newest file in {backup.folder(cfg.home)}.")
    return _row("Database", "ok", f"{jobs} jobs")


def _backups(cfg):
    got = backup.latest(cfg.home)
    if not got:
        return _row("Backups", "warn", "No backup yet (one is made each day the app runs).")
    path, age = got
    if age > 3:
        return _row("Backups", "warn", f"Newest backup is {age} days old.", "Open the app; a backup is made on start.")
    return _row("Backups", "ok", f"Newest is {'today' if age == 0 else f'{age} day(s) old'} ({path.name})")


def _ollama(cfg):
    installed = models.ollama_installed(cfg.model.url)
    if installed is None:
        return _row("Ollama (the AI program)", "bad", "Not running.",
                    "Double-click RSC on the Desktop (it starts Ollama), or open the Ollama app.")
    return _row("Ollama (the AI program)", "ok", "Running")


def _models(cfg):
    """Rows for the AI models. A model that isn't downloaded is only a problem when nothing usable is: if the model
    in use works, a missing default or extra model is not mentioned at all."""
    out = []
    for r in models.status(cfg):
        label = f"Model: {r['what'].lower()}"
        if r["ready"]:
            out.append(_row(label, "ok", r["model"]))
        elif r["role"] != "speech" and not r["ollama_running"]:
            out.append(_row(label, "ok", "Can't check while Ollama isn't running."))
        elif r["role"] == "text":
            out.append(_row(label, "warn", "No model installed yet.", "Open Setup and press Download on the suggested model."))
        elif r["role"] == "vision":
            out.append(_row(label, "ok", "Not set up (optional). Setup can download one for reading receipt photos."))
        else:
            out.append(_row(label, "ok", "Not downloaded (optional). The microphone buttons stay off until it is."))
    return out


def _email(cfg):
    if not cfg.mail.address:
        return _row("Email", "warn", "No Gmail address yet.", "Add it on the Setup page.")
    try:
        config.mail_password(cfg.mail.address)
    except RuntimeError:
        return _row("Email", "warn", f"{cfg.mail.address}, but no app password saved.", "Paste the Gmail app password on the Setup page.")
    return _row("Email", "ok", f"{cfg.mail.address} (password saved)")


def _app_running(cfg):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/", timeout=3) as resp:
            if brand.current()["name"].encode() in resp.read(20000):
                return _row("The app", "ok", f"Answering on port {cfg.port}")
    except urllib.error.HTTPError:
        return _row("The app", "ok", f"Answering on port {cfg.port}")  # e.g. the PIN page
    except (urllib.error.URLError, OSError):
        return _row("The app", "bad", f"Not answering on port {cfg.port}.", "Double-click RSC on the Desktop.")
    return _row("The app", "warn", f"Something else may be using port {cfg.port}.", "Run Install RSC again; it picks a free port.")


def _agents(cfg):
    if sys.platform != "darwin":
        return []
    import os
    uid = os.getuid()
    out = []
    for key, what in AGENTS.items():
        label = f"com.reclaimedspacecrafters.{key}"
        r = subprocess.run(["launchctl", "print", f"gui/{uid}/{label}"], capture_output=True, text=True)
        out.append(_row(f"Background job: {what}", "ok" if r.returncode == 0 else "warn",
                        "Loaded" if r.returncode == 0 else "Not loaded", "" if r.returncode == 0 else "Run Install RSC again."))
    return out


def _voice(cfg):
    from . import voice
    if not voice.available():
        return _row("Voice typing", "warn", "Not installed (the microphone buttons are off).", "Run Install RSC again.")
    return _row("Voice typing", "ok", "Installed")


def run(cfg, include_app: bool = True) -> list[dict]:
    rows = [_folder(cfg), _disk(cfg), _database(cfg), _backups(cfg), _ollama(cfg), *_models(cfg), _voice(cfg), _email(cfg)]
    if include_app:
        rows.append(_app_running(cfg))
    rows += _agents(cfg)
    return rows


def render(rows: list[dict]) -> str:
    mark = {"ok": "ok  ", "warn": "WARN", "bad": "FAIL"}
    lines = []
    for r in rows:
        lines.append(f"  [{mark[r['level']]}] {r['name']}: {r['detail']}")
        if r["fix"]:
            lines.append(f"         -> {r['fix']}")
    bad = sum(r["level"] == "bad" for r in rows)
    warn = sum(r["level"] == "warn" for r in rows)
    lines.append("")
    lines.append("Everything looks good." if not (bad or warn) else f"{bad} problem(s), {warn} warning(s).")
    return "\n".join(lines)
