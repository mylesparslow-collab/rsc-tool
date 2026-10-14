"""Updates for RSC.app: check GitHub for a newer release, and swap it in when the person presses the button.

Only used by the Mac app window (see desktop.py). Nothing is checked or installed without it, and installing always waits for
a button press. The check is one request to the GitHub releases page for this project; no data about the business is sent.

How a release is found: a version tag like v0.2.0 on GitHub with an asset named RSC-mac.zip (the app) and RSC-mac.zip.sha256
(its fingerprint). The mac-app workflow makes both. The download is checked against the fingerprint before anything is replaced.
"""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from flask import flash, redirect, render_template, request, url_for

from . import __version__, prefs

REPO = "mylesparslow-collab/rsc-tool"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET, ASSET_SHA = "RSC-mac.zip", "RSC-mac.zip.sha256"
MAX_BYTES = 400 * 2**20


def parse_version(text: str) -> tuple:
    """'v0.2.10' -> (0, 2, 10). Anything that isn't plain numbers sorts as (0,) so it never looks newer."""
    try:
        return tuple(int(p) for p in text.strip().lstrip("vV").split("."))
    except ValueError:
        return (0,)


def check(fetch=None, current: str = __version__) -> dict:
    """Ask GitHub for the newest release. Returns {"current", "latest", "newer", "url", "sha_url", "notes"} or {"error": "..."}.
    `fetch(url) -> bytes` lets tests stand in for the internet."""
    fetch = fetch or _fetch
    try:
        rel = json.loads(fetch(API))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": f"Couldn't reach GitHub ({getattr(exc, 'reason', exc)}). Try again when you're online."}
    tag = str(rel.get("tag_name", ""))
    assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
    if not tag:
        return {"error": "GitHub didn't list a release."}
    info = {"current": current, "latest": tag.lstrip("vV"), "notes": str(rel.get("body") or "").strip()[:600],
            "newer": parse_version(tag) > parse_version(current), "url": assets.get(ASSET), "sha_url": assets.get(ASSET_SHA)}
    if info["newer"] and not (info["url"] and info["sha_url"]):
        return {"error": f"Version {info['latest']} is out, but its download isn't ready yet. Try again later."}
    return info


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "rsc-app-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(MAX_BYTES + 1)


def app_bundle() -> Path | None:
    """The RSC.app this program is running from, or None when it isn't the packaged Mac app."""
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    p = Path(sys.executable).resolve()
    bundle = p.parents[2]   # RSC.app/Contents/MacOS/RSC
    return bundle if bundle.suffix == ".app" else None


def download(info: dict, folder: Path, fetch=None) -> Path:
    """Download the release zip into `folder` and refuse it unless it matches its published fingerprint."""
    fetch = fetch or _fetch
    expected = fetch(info["sha_url"]).decode().split()[0].lower()
    data = fetch(info["url"])
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("The download didn't match its fingerprint, so I didn't install it. Try again.")
    path = folder / ASSET
    path.write_bytes(data)
    return path


def swap_script(zip_path: Path, bundle: Path, pid: int) -> str:
    """A small shell script that waits for this app to quit, replaces it with the new copy, and opens it again."""
    q = shlex.quote
    work = zip_path.parent
    return f"""#!/bin/bash
# Replaces {bundle.name} with the downloaded update. Written by RSC; safe to delete.
while kill -0 {int(pid)} 2>/dev/null; do sleep 0.5; done
set -e
/usr/bin/ditto -x -k {q(str(zip_path))} {q(str(work / 'new'))}
NEW={q(str(work / 'new' / 'RSC.app'))}
[ -d "$NEW/Contents/MacOS" ] || exit 1
/usr/bin/xattr -dr com.apple.quarantine "$NEW" 2>/dev/null || true
mv {q(str(bundle))} {q(str(work / 'old.app'))}
if mv "$NEW" {q(str(bundle))}; then rm -rf {q(str(work / 'old.app'))}; else mv {q(str(work / 'old.app'))} {q(str(bundle))}; exit 1; fi
/usr/bin/open {q(str(bundle))}
rm -rf {q(str(work))}
"""


def install(info: dict, quit_app, fetch=None) -> None:
    """Download, verify, then hand over to the swap script and quit. Raises RuntimeError with a plain message if it can't."""
    bundle = app_bundle()
    if bundle is None:
        raise RuntimeError("Updating only works from the installed RSC app.")
    if not os.access(bundle.parent, os.W_OK):
        raise RuntimeError("I can't replace RSC where it is. Drag it into the Applications folder first, then try again.")
    folder = Path(tempfile.mkdtemp(prefix="rsc-update-", dir=bundle.parent))   # same disk, so the swap is a rename
    try:
        zip_path = download(info, folder, fetch)
        script = folder / "swap.sh"
        script.write_text(swap_script(zip_path, bundle, os.getpid()))
        script.chmod(0o755)
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
    subprocess.Popen(["/bin/bash", str(script)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    quit_app()


def register(app, cfg, conn, quit_app, fetch=None):
    """The /update page, the banner, and the Install button. Only the Mac app window calls this."""
    state = {"info": None}

    def refresh():
        state["info"] = check(fetch)
        return state["info"]

    app.jinja_env.globals["update_banner"] = lambda: (state["info"] or {}) if (state["info"] or {}).get("newer") else None

    def check_in_background():
        if prefs.get(conn(), "update_check") != "off":
            threading.Thread(target=refresh, daemon=True).start()

    @app.route("/update", methods=["GET", "POST"])
    def update_page():
        c = conn()
        if request.method == "POST" and request.form.get("action") == "toggle":
            prefs.put(c, "update_check", "off" if prefs.get(c, "update_check") != "off" else "on")
            return redirect(url_for("update_page"))
        info = refresh()
        return render_template("update.html", info=info, current=__version__, can_install=app_bundle() is not None,
                               auto=prefs.get(c, "update_check") != "off")

    @app.post("/update/install")
    def update_install():
        info = state["info"] or refresh()
        if not info.get("newer"):
            flash("You already have the newest version.")
            return redirect(url_for("update_page"))
        try:
            install(info, quit_app, fetch)
        except (RuntimeError, urllib.error.URLError, OSError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("update_page"))
        return render_template("update.html", info=info, current=__version__, can_install=True, auto=True, installing=True)

    return check_in_background
