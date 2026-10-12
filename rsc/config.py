"""Settings live in config.toml next to the database. See config.example.toml."""
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOME = Path(os.environ.get("RSC_HOME", Path.home() / "RSC"))
KEYCHAIN_SERVICE = "rsc-tool-gmail"


@dataclass
class MailConfig:
    address: str = ""
    host: str = "imap.gmail.com"
    mailboxes: list[str] = field(default_factory=lambda: ["INBOX"])
    first_run_days: int = 30
    max_per_run: int = 200
    # Only emails that look like business go to the model. Everything else is skipped unread.
    keywords: list[str] = field(default_factory=lambda: [
        "receipt", "order", "invoice", "payment", "paid", "purchase", "statement", "deposit",
        "estimate", "quote", "remodel", "renovat", "kitchen", "bath", "deck", "porch", "addition",
        "contractor", "project", "job",
    ])
    ignore_senders: list[str] = field(default_factory=list)


@dataclass
class ModelConfig:
    url: str = "http://localhost:11434"
    name: str = "llama3.1:8b"      # the text model
    vision: str = ""               # reads photos of receipts; `rsc setup` picks one
    timeout_seconds: int = 180


@dataclass
class VoiceConfig:
    model: str = "base.en"     # speech-to-text model, about 150 MB, downloaded once


@dataclass
class QuickBooksConfig:
    client_id: str = ""        # from developer.intuit.com; leave empty to use the CSV files only
    client_secret: str = ""
    environment: str = "sandbox"   # "sandbox" (a fake company) or "production"
    redirect_uri: str = ""    # blank: http://localhost:<port>/quickbooks/callback


@dataclass
class Config:
    home: Path = DEFAULT_HOME
    first_job_number: int = 1001
    port: int = 5151          # where the app listens on this computer; the installer moves it if something else is using 5151
    business_name: str = "Reclaimed Space Crafters"
    business_phone: str = "518-932-9919"
    business_email: str = "nfparslow@gmail.com"
    business_extra: dict = field(default_factory=dict)   # [business] in config.toml: short, owner, legal, address, city, region, county, tagline
    access_pin: str = ""      # needed only for `rsc serve --lan` (phone on the same Wi-Fi)
    mail: MailConfig = field(default_factory=MailConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    quickbooks: QuickBooksConfig = field(default_factory=QuickBooksConfig)

    @property
    def qb_redirect_uri(self) -> str:
        return self.quickbooks.redirect_uri or f"http://localhost:{self.port}/quickbooks/callback"

    @property
    def voice_cache(self) -> Path:
        return self.home / "voice-models"

    @property
    def db_path(self) -> Path:
        return self.home / "rsc.db"


def load(home: Path | None = None) -> Config:
    home = Path(home or DEFAULT_HOME)
    cfg = Config(home=home)
    path = home / "config.toml"
    if path.exists():
        raw = tomllib.loads(path.read_text())
        cfg.first_job_number = int(raw.get("first_job_number", cfg.first_job_number))
        cfg.access_pin = str(raw.get("access_pin", cfg.access_pin))
        cfg.port = int(raw.get("port", cfg.port))
        for key in ("business_name", "business_phone", "business_email"):
            setattr(cfg, key, str(raw.get(key, getattr(cfg, key))))
        cfg.business_extra = {k: str(v) for k, v in raw.get("business", {}).items()}
        for key, value in raw.get("mail", {}).items():
            setattr(cfg.mail, key, value)
        for key, value in raw.get("model", {}).items():
            setattr(cfg.model, key, value)
        for key, value in raw.get("voice", {}).items():
            setattr(cfg.voice, key, value)
        for key, value in raw.get("quickbooks", {}).items():
            setattr(cfg.quickbooks, key, value)
        if cfg.quickbooks.environment not in ("sandbox", "production"):
            raise ValueError('[quickbooks] environment must be "sandbox" or "production"')
    return cfg


def mail_password(address: str) -> str:
    """The Gmail app password: from RSC_GMAIL_APP_PASSWORD, else the macOS Keychain."""
    env = os.environ.get("RSC_GMAIL_APP_PASSWORD")
    if env:
        return env
    if sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", address, "-w"],
            capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    raise RuntimeError(
        "No Gmail app password found. Run `rsc set-password` (Mac) or set RSC_GMAIL_APP_PASSWORD.")


def save_mail_password(address: str, password: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("Keychain storage is Mac only. Set RSC_GMAIL_APP_PASSWORD instead.")
    subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", address,
                    "-w", password], check=True, capture_output=True)


def update_config(home: Path, address: str | None = None) -> None:
    """Set the Gmail address in config.toml, keeping everything else the person has written there."""
    import re
    path = Path(home) / "config.toml"
    text = path.read_text() if path.exists() else ""
    line = f'address = "{address}"'
    if re.search(r"^address\s*=.*$", text, re.M):
        text = re.sub(r"^address\s*=.*$", lambda _: line, text, count=1, flags=re.M)
    elif re.search(r"^\[mail\]\s*$", text, re.M):
        text = re.sub(r"^\[mail\]\s*$", lambda m: f"[mail]\n{line}", text, count=1, flags=re.M)
    else:
        text += f"\n[mail]\n{line}\n"
    path.write_text(text)
