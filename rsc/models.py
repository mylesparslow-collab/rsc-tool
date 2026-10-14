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
import threading
import time
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


VISION_HINTS = ("vl", "vision", "llava", "minicpm-v", "moondream", "gemma3")   # names of models that can look at pictures
NOT_CHAT = ("embed", "rerank")
BIG_GB = 12   # when picking among unknown models, the largest one under this size (bigger ones are slow here)


def can_see(name: str) -> bool:
    return any(h in name.lower() for h in VISION_HINTS)


def best_installed(installed: set[str], role: str, sizes: dict | None = None) -> str | None:
    """The model already on this Mac that suits a job best, whatever its name. The ones this app was tested with come first,
    then the largest that is not huge. None if nothing suits."""
    sizes = sizes or {}
    pool = [n for n in sorted(installed) if (can_see(n) if role == "vision" else not any(h in n.lower() for h in NOT_CHAT))]
    if not pool:
        return None
    known = (VISION_BIG, VISION_SMALL) if role == "vision" else (TEXT_BIG, TEXT_SMALL)
    for name in known:
        if any(_has({n}, name) for n in pool):
            return next(n for n in pool if _has({n}, name))
    gb = lambda n: sizes.get(n, 0) / 2**30
    fits = [n for n in pool if 0 < gb(n) <= BIG_GB]
    return max(fits, key=gb) if fits else min(pool, key=lambda n: (gb(n) or 1e9, n))


def automatic(cfg, installed: set[str] | None) -> tuple[str, str]:
    """What 'Automatic' means: the model in config.toml if it is on this Mac, else the best one that is. Nothing is
    ever reported missing just because a default isn't there while another working model is."""
    text, vision = cfg.file_models or (cfg.model.name, cfg.model.vision)
    if not installed:
        return text, vision
    if not (text and _has(installed, text)):
        text = best_installed(installed, "text", _sizes(cfg.model.url)) or text
    if not (vision and _has(installed, vision)):
        vision = best_installed(installed, "vision", _sizes(cfg.model.url)) or vision
    return text, vision


def wanted(cfg) -> dict:
    return {"text": cfg.model.name, "vision": cfg.model.vision, "speech": cfg.voice.model}


def apply_choice(cfg) -> None:
    """Use the models picked on the Setup page (kept in the database) instead of the ones in config.toml.
    Nothing picked means 'Automatic': the config.toml model if it is on this Mac, else the best model that is.
    Cheap, so callers do it each time they need a model: that is how a pick made in one window reaches the
    background jobs without a restart."""
    import sqlite3
    cfg.file_models = cfg.file_models or (cfg.model.name, cfg.model.vision)
    picks = {}
    if cfg.db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True, timeout=3)
            try:
                picks = dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('model_text', 'model_vision')").fetchall())
            finally:
                conn.close()
        except sqlite3.Error:
            picks = {}
    auto_text, auto_vision = cfg.file_models
    if not (picks.get("model_text") and picks.get("model_vision")):
        auto_text, auto_vision = automatic(cfg, ollama_installed(cfg.model.url))
    cfg.model.name = picks.get("model_text") or auto_text
    cfg.model.vision = picks.get("model_vision") or auto_vision


def choices(cfg) -> dict:
    """What the Setup page needs for the pickers: models Ollama has, what's in use, what 'Automatic' means right now."""
    installed = ollama_installed(cfg.model.url)
    auto_text, auto_vision = automatic(cfg, installed)
    return {"running": installed is not None, "installed": sorted(installed or ()),
            "text": cfg.model.name, "vision": cfg.model.vision, "auto_text": auto_text, "auto_vision": auto_vision}


def _tags(url: str) -> list[dict] | None:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=2) as resp:
            return json.loads(resp.read()).get("models", [])
    except (urllib.error.URLError, OSError, ValueError):
        return None


def ollama_installed(url: str) -> set[str] | None:
    """Names Ollama has downloaded, or None if Ollama isn't running."""
    tags = _tags(url)
    return None if tags is None else {m.get("name", "") for m in tags}


def _sizes(url: str) -> dict:
    return {m.get("name", ""): m.get("size", 0) for m in (_tags(url) or [])}


def _has(installed: set[str], name: str) -> bool:
    return name in installed or (":" not in name and f"{name}:latest" in installed)


def status(cfg, installed="ask") -> list[dict]:
    """One row per job: which model is in use, and whether it is on this Mac."""
    from . import voice
    if installed == "ask":
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


def pull_ollama(url: str, name: str, say=print, progress=None) -> None:
    """Download an Ollama model, showing progress about every 10%. `progress(pct)` hears every whole percent."""
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
                if progress:
                    progress(pct)
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


# ---------------------------------------------------------------- is it up and running?
def suggested(cfg=None, ram_gb: int | None = None) -> dict:
    return recommend(ram_gb if ram_gb is not None else total_ram_gb())


def health(cfg) -> dict:
    """Plain answer to 'are my models up and running?' for the Setup page and the Home pill.
    Suggestions appear only for a job with nothing usable on this Mac; a working model is never nagged about."""
    installed = ollama_installed(cfg.model.url)
    rows = status(cfg, installed)
    by = {r["role"]: r for r in rows}
    out = {"rows": rows, "running": installed is not None, "suggest": {}}
    if installed is None:
        out.update(state="off", headline="The AI program (Ollama) isn't running.",
                   detail="Open the Ollama app. Everything else in RSC still works; drafts use plain templates until then.", short="AI off")
    elif by["text"]["ready"]:
        out.update(state="up", headline="Your AI models are up and running.",
                   detail=f"Using {by['text']['model']} for email, estimates and forms."
                          + (f" Photos are read by {by['vision']['model']}." if by["vision"]["ready"] else ""),
                   short="AI ready")
    else:
        out.update(state="none", headline="No AI model is installed yet.",
                   detail="Download the suggested one below, or install any model in the Ollama app and pick it here.", short="AI not set up")
    if installed is not None:
        rec = suggested(cfg)
        if not by["text"]["ready"]:
            out["suggest"]["text"] = rec["text"]
        if not by["vision"]["ready"]:
            out["suggest"]["vision"] = rec["vision"]
    return out


def test_text(cfg) -> dict:
    """A real, tiny question to the text model: proves Ollama answers and the model works. Never touches any data."""
    from .llm import ModelUnavailable, OllamaModel
    started = time.time()
    try:
        got = OllamaModel(cfg.model.url, cfg.model.name, 90).extract(
            "You answer with JSON only.", "Set ok to true.",
            {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
    except (ModelUnavailable, ValueError, OSError) as exc:
        return {"ok": False, "model": cfg.model.name, "error": str(exc)[:200]}
    return {"ok": bool(got.get("ok")), "model": cfg.model.name, "seconds": round(time.time() - started, 1),
            "error": "" if got.get("ok") else "It answered, but not with what was asked."}


# ---------------------------------------------------------------- downloads that run in the background, with progress
_DOWNLOADS: dict[str, dict] = {}
_LOCK = threading.Lock()


def downloads() -> dict:
    with _LOCK:
        return {k: dict(v) for k, v in _DOWNLOADS.items()}


def downloading() -> dict | None:
    """The download in progress, if any: {'model', 'pct'}."""
    return next(({"model": k, **v} for k, v in downloads().items() if v["state"] == "running"), None)


def start_download(url: str, name: str) -> bool:
    """Start downloading a model in the background. False if that model is already being fetched."""
    with _LOCK:
        if _DOWNLOADS.get(name, {}).get("state") == "running":
            return False
        _DOWNLOADS[name] = {"state": "running", "pct": 0, "error": ""}

    def set_(**kw):
        with _LOCK:
            _DOWNLOADS[name].update(kw)

    def work():
        try:
            pull_ollama(url, name, say=lambda *_: None, progress=lambda pct: set_(pct=pct))
            set_(state="done", pct=100)
        except (RuntimeError, urllib.error.URLError, OSError, ValueError) as exc:
            set_(state="error", error=str(exc)[:200])
    threading.Thread(target=work, daemon=True).start()
    return True


def allowed_downloads() -> set[str]:
    return {TEXT_SMALL, TEXT_BIG, VISION_SMALL, VISION_BIG}


def auto_download(cfg, enabled: bool = True) -> str | None:
    """Only when no usable text model is on this Mac and Ollama is running: fetch the suggested one, in the background,
    once per name per run (a failed download is not retried in a loop). Returns the model being fetched, if one was started."""
    if not enabled:
        return None
    installed = ollama_installed(cfg.model.url)
    if installed is None or any(not any(h in n.lower() for h in NOT_CHAT) for n in installed):
        return None
    name = suggested(cfg)["text"]
    if name in downloads():
        return None
    return name if start_download(cfg.model.url, name) else None


_PILL: dict = {}


def pill(cfg, ttl: float = 15) -> dict:
    """A small cached answer for the status line on every page: {'state': up/off/none, 'short', 'model'}."""
    key = (str(cfg.home), cfg.model.url)
    hit = _PILL.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    installed = ollama_installed(cfg.model.url)
    if installed is None:
        got = {"state": "off", "short": "AI off", "model": ""}
    else:
        text = status(cfg, installed)[0]
        got = ({"state": "up", "short": "AI ready", "model": text["model"]} if text["ready"]
               else {"state": "none", "short": "AI not set up", "model": ""})
    _PILL[key] = (time.time(), got)
    return got
