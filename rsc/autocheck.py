"""Checks Gmail by itself while RSC.app is open, so the .dmg alone is enough (no installer, no background agent).

Every 30 minutes, and once shortly after the app opens, it runs the same email check as the Check email button.
It only runs when Gmail is set up, when the switch on Setup is on, and when this Mac doesn't already check in the
background (the installer's launchd agent), so nothing is checked twice. Whatever it finds waits in To Review.
Nothing is ever sent. When the window is closed the app quits and the checks stop; the installer's agent is what
keeps checking with the app closed.
"""
import threading
from datetime import datetime
from pathlib import Path

from . import config, db, prefs

INTERVAL = 30 * 60
FIRST_DELAY = 20
AGENT = Path("~/Library/LaunchAgents/com.reclaimedspacecrafters.checkmail.plist").expanduser()


def agent_installed() -> bool:
    return AGENT.exists()


def gmail_ready(cfg) -> bool:
    if not cfg.mail.address:
        return False
    try:
        config.mail_password(cfg.mail.address)
        return True
    except RuntimeError:
        return False


def enabled(conn) -> bool:
    return prefs.get(conn, "auto_mail") != "off"


def record(cfg, message: str, now: datetime | None = None) -> None:
    """Remember when email was last checked and how it went, so every page and the next launch can say so."""
    conn = db.connect(cfg.db_path)
    try:
        prefs.put(conn, "mail_last_at", (now or datetime.now()).isoformat(timespec="seconds"))
        prefs.put(conn, "mail_last_message", message)
    finally:
        conn.close()


def ago(iso: str, now: datetime | None = None) -> str:
    try:
        secs = int(((now or datetime.now()) - datetime.fromisoformat(iso)).total_seconds())
    except ValueError:
        return ""
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} minutes ago"
    if secs < 86400:
        return f"{secs // 3600} hour{'s' if secs // 3600 != 1 else ''} ago"
    return f"{secs // 86400} day{'s' if secs // 86400 != 1 else ''} ago"


def describe(cfg, conn, active: bool, now: datetime | None = None) -> dict:
    """What Setup and Home say about automatic checking. `active` is True inside RSC.app, which is what runs the timer."""
    last = prefs.get(conn, "mail_last_at")
    return {"active": active, "enabled": enabled(conn), "agent": agent_installed(), "gmail": gmail_ready(cfg),
            "last_ago": ago(last, now) if last else "", "message": prefs.get(conn, "mail_last_message")}


def tick(cfg, run, now: datetime | None = None) -> str:
    """One scheduled check. Returns what happened: off, agent, no_gmail, busy, ok or failed."""
    conn = db.connect(cfg.db_path)
    try:
        if not enabled(conn):
            return "off"
    finally:
        conn.close()
    if agent_installed():
        return "agent"
    if not gmail_ready(cfg):
        return "no_gmail"
    try:
        message = run(cfg).summary()
    except RuntimeError as exc:
        if "Already checking" in str(exc):
            return "busy"
        record(cfg, f"Email check failed: {exc}", now)
        return "failed"
    except Exception as exc:
        record(cfg, f"Email check failed: {exc}", now)
        return "failed"
    record(cfg, message, now)
    return "ok"


class Scheduler(threading.Thread):
    """Runs `tick` after a short delay and then every `interval` seconds, until the app quits."""

    def __init__(self, cfg, run, interval: float = INTERVAL, first_delay: float = FIRST_DELAY):
        super().__init__(daemon=True, name="rsc-auto-mail")
        self.cfg, self.run_check, self.interval, self.first_delay = cfg, run, interval, first_delay
        self.stopping = threading.Event()
        self.results: list[str] = []

    def run(self):
        wait = self.first_delay
        while not self.stopping.wait(wait):
            try:
                self.results.append(tick(self.cfg, self.run_check))
            except Exception:
                self.results.append("failed")   # never let the timer die
            wait = self.interval

    def stop(self):
        self.stopping.set()
