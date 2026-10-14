"""Which local model does which job, and getting them downloaded.

Three jobs, three models, all on this computer:
  text    reads emails, drafts estimates, fills in forms from typed text   (Ollama)
  vision  reads photos of receipts                                        (Ollama)
  speech  turns talking into text for the microphone buttons               (faster-whisper)

`recommend` picks the models from how much memory the computer has. `rsc models --pull` downloads whatever is
missing, so nobody has to know model names.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

TEXT_SMALL, TEXT_BIG = "llama3.2:3b", "llama3.1:8b"
VISION_SMALL, VISION_BIG = "qwen2.5vl:3b", "llama3.2-vision"
SPEECH = "base.en"

ROLES = (("text", "Reads email, writes estimates, fills in forms"),
         ("vision", "Reads photos of receipts"),
         ("speech", "Turns talking into text"))


def total_ram_gb() -> int:
    try:
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) // 2**30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2**30
    except (ValueError, OSError):
        return 8


def recommend(ram_gb: int) -> dict:
    """16 GB or more can run the 8B text model; 24 GB or more also the bigger vision model."""
    return {"text": TEXT_BIG if ram_gb >= 16 else TEXT_SMALL,
            "vision": VISION_BIG if ram_gb >= 24 else VISION_SMALL,
            "speech": SPEECH}


def prefer_installed(pick: dict, installed: set | None) -> dict:
    """Use a bigger model that is already downloaded instead of the one recommended, so nothing is fetched twice.
    A smaller one that happens to be installed doesn't replace the recommendation."""
    if not installed:
        return pick
    out = dict(pick)
    for role, options in (("text", (TEXT_BIG, TEXT_SMALL)), ("vision", (VISION_BIG, VISION_SMALL))):
        better = options[:options.index(out[role])] if out[role] in options else []
        out[role] = next((m for m in better if _has(installed, m)), out[role])
    return out


def wanted(cfg) -> dict:
    return {"text": cfg.model.name, "vision": cfg.model.vision, "speech": cfg.voice.model}


def apply_choice(cfg) -> None:
    """Use the models picked on the Setup page (kept in the database) instead of the ones in config.toml.
    Nothing picked means the automatic choice in config.toml stands. Cheap, so callers do it each time they need a model:
    that is how a pick made in one window reaches the background jobs without a restart."""
    import sqlite3
    cfg.file_models = cfg.file_models or (cfg.model.name, cfg.model.vision)
    cfg.model.name, cfg.model.vision = cfg.file_models
    if not cfg.db_path.exists():
        return
    try:
        conn = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True, timeout=3)
        try:
            picks = dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('model_text', 'model_vision')").fetchall())
        finally:
            conn.close()
    except sqlite3.Error:
        return
    cfg.model.name = picks.get("model_text") or cfg.model.name
    cfg.model.vision = picks.get("model_vision") or cfg.model.vision


def choices(cfg) -> dict:
    """What the Setup page needs for the pickers: models Ollama has, what's in use, what's automatic."""
    installed = ollama_installed(cfg.model.url)
    auto_text, auto_vision = cfg.file_models or (cfg.model.name, cfg.model.vision)
    return {"running": installed is not None, "installed": sorted(installed or ()),
            "text": cfg.model.name, "vision": cfg.model.vision, "auto_text": auto_text, "auto_vision": auto_vision}


def ollama_installed(url: str) -> set[str] | None:
    """Names Ollama has downloaded, or None if Ollama isn't running."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=5) as resp:
            return {m.get("name", "") for m in json.loads(resp.read()).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _has(installed: set[str], name: str) -> bool:
    return name in installed or (":" not in name and f"{name}:latest" in installed)


def status(cfg) -> list[dict]:
    """One row per job: which model, and whether it is downloaded."""
    from . import voice
    installed = ollama_installed(cfg.model.url)
    rows = []
    for role, what in ROLES:
        name = wanted(cfg)[role]
        if role == "speech":
            ready = voice.available() and voice.is_downloaded(name, cfg.voice_cache)
        elif not name:
            ready = False
        else:
            ready = installed is not None and _has(installed, name)
        rows.append({"role": role, "what": what, "model": name, "ready": ready,
                     "ollama_running": installed is not None})
    return rows


def pull_ollama(url: str, name: str, say=print) -> None:
    """Download an Ollama model, showing progress about every 10%."""
    req = urllib.request.Request(f"{url.rstrip('/')}/api/pull", data=json.dumps({"model": name, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    last = -10
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for line in resp:
            msg = json.loads(line)
            if msg.get("error"):
                raise RuntimeError(msg["error"])
            if msg.get("total") and msg.get("completed") is not None:
                pct = int(msg["completed"] * 100 / msg["total"])
                if pct >= last + 10:
                    last = pct - pct % 10
                    say(f"    {name}: {pct}%")


def ensure(cfg, say=print) -> list[str]:
    """Download every model the configuration needs that is missing. Returns problems (empty when all is well)."""
    from . import voice
    problems = []
    installed = ollama_installed(cfg.model.url)
    if installed is None:
        return ["Ollama isn't running. Open the Ollama app, then run this again."]
    for role, name in (("text", cfg.model.name), ("vision", cfg.model.vision)):
        if not name:
            continue
        if _has(installed, name):
            say(f"  {role}: {name} is ready")
            continue
        say(f"  {role}: downloading {name} (once; this can take a while)...")
        try:
            pull_ollama(cfg.model.url, name, say)
            say(f"  {role}: {name} is ready")
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            problems.append(f"Couldn't download {name} ({exc}).")
    if voice.available():
        say(f"  speech: getting {cfg.voice.model}...")
        try:
            voice.load(cfg.voice.model, cfg.voice_cache)
            say(f"  speech: {cfg.voice.model} is ready")
        except Exception as exc:
            problems.append(f"Couldn't download the speech model ({exc}).")
    else:
        problems.append("Voice typing isn't installed, so the microphone buttons are off.")
    return problems


# ---------------------------------------------------------------- starting Ollama without a person
OLLAMA_BINARIES = ("/Applications/Ollama.app/Contents/Resources/ollama", "~/Applications/Ollama.app/Contents/Resources/ollama",
                   "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama")


def find_ollama_binary() -> str | None:
    import shutil
    from pathlib import Path
    for p in OLLAMA_BINARIES:
        path = Path(p).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which("ollama")


def start_ollama(url: str, wait_seconds: int = 25) -> bool:
    """Make sure Ollama is answering. Starts it if it isn't (the app if it's installed, else its program). True if it answers."""
    import time
    if ollama_installed(url) is not None:
        return True
    started = False
    for app in ("/Applications/Ollama.app", os.path.expanduser("~/Applications/Ollama.app")):
        if sys.platform == "darwin" and os.path.isdir(app):
            subprocess.Popen(["open", "-ga", app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started = True
            break
    if not started:
        binary = find_ollama_binary()
        if not binary:
            return False
        subprocess.Popen([binary, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(wait_seconds):
        if ollama_installed(url) is not None:
            return True
        time.sleep(1)
    return False
