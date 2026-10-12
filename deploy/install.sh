#!/bin/bash
# One-step setup for the RSC tool on a Mac. Safe to run again. No Homebrew, no administrator password.
#
#   Double-click "Install RSC.command" (or run ./deploy/install.sh)
#
# What it does, with no questions asked: gets Python (through uv), builds the app, installs Ollama if it's missing,
# downloads the three local models (text, photos, speech) sized to this Mac's memory, writes the settings, keeps the
# app running in the background (it starts at login), puts an "RSC" icon on the Desktop, checks email every 30
# minutes, emails the weekly report on Monday mornings, and opens the app on its Setup page, where the Gmail
# address and app password are entered once.
#
# Options:
#   --email ADDRESS     Gmail address to read (optional; the Setup page asks for it otherwise)
#   --model NAME        text model (default chosen from this Mac's memory)
#   --tracker FILE      import an "RSC Job Tracker.xlsx"
#   --home DIR          where data lives (default ~/RSC)
#   --skip-models       don't download models (Ollama and speech can be added later: rsc models --pull)
#   --no-voice          skip voice typing (the microphone buttons)
#   --no-launcher       no Desktop icon
#   --no-schedule       no automatic email check every 30 minutes
#   --yes               don't ask questions that have a sensible default
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${RSC_HOME:-$HOME/RSC}"
EMAIL=""; EMAIL_GIVEN=0; MODEL=""; TRACKER=""; SKIP_MODELS=0; NO_LAUNCHER=0; NO_SCHEDULE=0; NO_VOICE=0; YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --email|--model|--tracker|--home) [ $# -ge 2 ] || { echo "$1 needs a value (try --help)"; exit 2; } ;;
  esac
  case "$1" in
    --email) EMAIL="$2"; EMAIL_GIVEN=1; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --tracker) TRACKER="$2"; shift 2 ;;
    --home) DATA_DIR="$2"; shift 2 ;;
    --skip-models|--skip-model) SKIP_MODELS=1; shift ;;
    --no-voice) NO_VOICE=1; shift ;;
    --no-launcher) NO_LAUNCHER=1; shift ;;
    --no-schedule) NO_SCHEDULE=1; shift ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
  esac
done

mkdir -p "$DATA_DIR" 2>/dev/null || true
LOG="$DATA_DIR/install.log"
exec > >(tee -a "$LOG") 2>&1   # everything printed here is also saved, so Myles can read what happened
echo "=== Install started $(date) on $(uname -srm) ==="
STEP="starting"
on_error() { printf '\n\033[31mStopped during: %s.\033[0m\nNothing is broken: run Install RSC again and it picks up where it stopped.\nIf it stops again, send Myles the file  %s\n' "$STEP" "$LOG" >&2; }
trap on_error ERR

retry() { # retry N cmd...   (the network drops; try a few times before giving up)
  local n="$1" i=1; shift
  until "$@"; do
    [ "$i" -ge "$n" ] && return 1
    warn "That didn't work (try $i of $n). Trying again in $((i*5)) seconds..."; sleep $((i*5)); i=$((i+1))
  done
}
reachable() { curl -s -m 8 -o /dev/null -I "https://$1" ; }
port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
is_ours() { curl -s -m 3 "http://localhost:$1/" 2>/dev/null | grep -q "Reclaimed Space Crafters"; }

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mStopped:\033[0m %s\n' "$*" >&2; exit 1; }
ask()  { # ask "question" default  -> echoes answer
  if [ "$YES" = 1 ]; then echo "$2"; return; fi
  local reply; read -r -p "$1 " reply; echo "${reply:-$2}"
}

STEP="checking this Mac"
if [ "$(uname -s)" = "Darwin" ]; then
  MACVER="$(sw_vers -productVersion 2>/dev/null || echo 0)"
  [ "${MACVER%%.*}" -ge 12 ] 2>/dev/null || die "This needs macOS 12 or newer (this Mac has $MACVER). Ask Myles."
  FREE_GB="$(df -g "$HOME" | awk 'NR==2{print $4}')"
  if [ "${FREE_GB:-100}" -lt 12 ] 2>/dev/null; then
    die "Only ${FREE_GB} GB of disk space is free. The AI models need about 10 GB. Empty the Trash or remove old downloads, then run this again."
  fi
fi
[ "$(uname -s)" = "Darwin" ] || warn "This installer is written for macOS. Continuing, but the Keychain, Desktop icon and schedule steps are Mac only."
export PYTHONUNBUFFERED=1   # so download progress shows as it happens, not all at the end
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# ------------------------------------------------------------------ 1. Python (through uv: no Homebrew, no password)
STEP="getting ready (internet and Python)"
say "1. Getting ready"
if ! command -v uv >/dev/null 2>&1; then
  reachable astral.sh || die "Can't reach the internet (astral.sh). Check the Wi-Fi and run this again."
  echo "  Installing uv (a small tool that fetches Python)..."
  retry 3 sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1' || die "Couldn't download uv. Check the internet connection and run this again."
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv didn't install. Run this again, or ask Myles."
ok "uv is ready"

# ------------------------------------------------------------------ 2. App
STEP="installing the app"
say "2. The app"
xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null || true   # a downloaded zip is "quarantined"; this stops macOS nagging
if [ -x "$APP_DIR/.venv/bin/python" ] && ! "$APP_DIR/.venv/bin/python" -c "import sys" 2>/dev/null; then
  warn "The old Python setup is broken; rebuilding it."; rm -rf "$APP_DIR/.venv"
fi
[ -x "$APP_DIR/.venv/bin/python" ] || retry 3 uv venv --quiet --python 3.12 "$APP_DIR/.venv" || die "Couldn't set up Python 3.12. Check the internet and run this again."
EXTRA=""; [ "$NO_VOICE" = 0 ] && EXTRA="[voice]"
if ! retry 3 uv pip install --quiet --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR$EXTRA"; then
  warn "Voice typing could not be installed. The app works without it."
  retry 3 uv pip install --quiet --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR" || die "Couldn't install the app. Check the internet and run this again."
fi
RSC="$APP_DIR/.venv/bin/rsc"
ok "Installed in $APP_DIR"

# ------------------------------------------------------------------ 3. Settings and data
STEP="saving settings"
say "3. Settings and data"
mkdir -p "$DATA_DIR"
export RSC_HOME="$DATA_DIR"
SETUP_ARGS=()
if [ ! -f "$DATA_DIR/config.toml" ]; then
  SETUP_ARGS+=(--email "$EMAIL")  # blank is fine: the Setup page in the app collects it
  [ -n "$MODEL" ] && SETUP_ARGS+=(--text-model "$MODEL")
else
  ok "Keeping your existing $DATA_DIR/config.toml"
fi
[ -n "$TRACKER" ] && SETUP_ARGS+=(--tracker "$TRACKER")
SETUP_OUT="$(mktemp)"
"$RSC" setup ${SETUP_ARGS[@]+"${SETUP_ARGS[@]}"} > "$SETUP_OUT" 2>&1 || { cat "$SETUP_OUT"; false; }
grep -v "^Local model" "$SETUP_OUT" || true; rm -f "$SETUP_OUT"
EMAIL="$(sed -n 's/^address *= *"\(.*\)"/\1/p' "$DATA_DIR/config.toml" | head -1)"

# Which port? Keep the one already chosen; otherwise 5151, or the next free one if something else is using it.
PORT="$(sed -n 's/^port *= *\([0-9][0-9]*\).*/\1/p' "$DATA_DIR/config.toml" | head -1)"
if [ -z "$PORT" ]; then
  PORT=5151
  while port_busy "$PORT"; do PORT=$((PORT+1)); done   # a fresh install never shares a port, even with another RSC copy
  if [ "$PORT" != 5151 ]; then
    warn "Port 5151 is used by something else; using $PORT instead."
    "$APP_DIR/.venv/bin/python" - "$DATA_DIR/config.toml" "$PORT" <<'PYEOF'
import sys
p, port = sys.argv[1], sys.argv[2]
t = open(p).read()
open(p, "w").write(f"port = {port}\n" + t)
PYEOF
  fi
fi
ok "The app will live at http://localhost:$PORT"

# ------------------------------------------------------------------ 4. Models (Ollama + text + photos + speech)
OLLAMA_APP=""; OLLAMA_OURS=0; OLLAMA_BIN=""
if [ "$SKIP_MODELS" = 0 ]; then
  STEP="installing the local AI (Ollama)"
  say "4. Local AI (runs on this Mac; nothing is sent anywhere)"
  for d in "/Applications/Ollama.app" "$HOME/Applications/Ollama.app"; do [ -d "$d" ] && OLLAMA_APP="$d"; done
  if [ -z "$OLLAMA_APP" ] && ! command -v ollama >/dev/null 2>&1; then
    reachable ollama.com || die "Can't reach ollama.com. Check the internet and run this again."
    echo "  Installing Ollama (the program that runs the AI), about 200 MB..."
    mkdir -p "$HOME/Applications"
    TMPZ="$(mktemp -t ollama).zip"
    retry 3 curl -fL --progress-bar -o "$TMPZ" https://ollama.com/download/Ollama-darwin.zip || die "Couldn't download Ollama. Get it from https://ollama.com/download, open it once, and run this again."
    ditto -x -k "$TMPZ" "$HOME/Applications" && rm -f "$TMPZ"
    xattr -dr com.apple.quarantine "$HOME/Applications/Ollama.app" 2>/dev/null || true
    OLLAMA_APP="$HOME/Applications/Ollama.app"; OLLAMA_OURS=1
    ok "Ollama installed"
  fi
  # When we installed Ollama ourselves, run its engine directly. (Opening the app the first time can ask for an
  # administrator password to install a command-line tool; the engine doesn't.)
  [ -n "$OLLAMA_APP" ] && [ -x "$OLLAMA_APP/Contents/Resources/ollama" ] && OLLAMA_BIN="$OLLAMA_APP/Contents/Resources/ollama"
  if ! curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "  Starting Ollama..."
    if [ "$OLLAMA_OURS" = 1 ] && [ -n "$OLLAMA_BIN" ]; then (nohup "$OLLAMA_BIN" serve >/dev/null 2>&1 &)
    elif [ -n "$OLLAMA_APP" ]; then open -ga "$OLLAMA_APP" 2>/dev/null || true
    else (nohup ollama serve >/dev/null 2>&1 &); fi
    for _ in $(seq 1 45); do curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
  fi
  if curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    STEP="downloading the AI models"
    echo "  Downloading the models (a few GB, once). This is the slow part; it's fine to leave it."
    if retry 4 "$RSC" models --pull; then ok "Models are ready"
    else warn "Some models didn't finish. Run Install RSC again; it resumes where it stopped."; fi
  else
    warn "Ollama didn't start. Open the Ollama app once, then run Install RSC again."
  fi
else
  say "4. Local AI models: skipped (run  $RSC models --pull  later)"
fi

# ------------------------------------------------------------------ 5. Desktop icon
LAUNCHER=""
if [ "$NO_LAUNCHER" = 0 ]; then
  STEP="making the Desktop icon"
  say "5. Desktop icon"
  mkdir -p "$HOME/Desktop" 2>/dev/null || true
  LAUNCHER="$HOME/Desktop/RSC.command"
  {
    echo '#!/bin/bash'
    echo '# Double-click to open the RSC app. It starts anything that is not running.'
    echo "export RSC_HOME=\"$DATA_DIR\""
    echo "exec \"$RSC\" open"
  } > "$LAUNCHER" 2>/dev/null && chmod +x "$LAUNCHER" && ok "Created $LAUNCHER" \
    || warn "Couldn't write to the Desktop (macOS may have blocked it). Open http://localhost:$PORT in a browser instead."
else
  say "5. Desktop icon: skipped"
fi

# ------------------------------------------------------------------ 6. Background jobs
if [ "$NO_SCHEDULE" = 0 ] && [ "$(uname -s)" = "Darwin" ]; then
  STEP="setting up the background jobs"
  say "6. Keep it running (starts at login; checks email every 30 minutes; weekly report Monday 7 AM; crew work sheet weekdays 6 AM)"
  AGENTS="$HOME/Library/LaunchAgents"; mkdir -p "$AGENTS"
  agent() { # agent LABEL "<schedule xml>" arg...   (the program is always $RSC, or /usr/bin/open for ollama)
    local label="$1" sched="$2"; shift 2
    local plist="$AGENTS/com.reclaimedspacecrafters.$label.plist" args="" a
    xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
    for a in "$@"; do args="$args<string>$(xml "$a")</string>"; done
    local data_xml; data_xml="$(xml "$DATA_DIR")"
    cat > "$plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.reclaimedspacecrafters.$label</string>
  <key>ProgramArguments</key><array>$args</array>
  <key>EnvironmentVariables</key><dict><key>RSC_HOME</key><string>$data_xml</string></dict>
  $sched
  <key>StandardOutPath</key><string>$data_xml/$label.log</string>
  <key>StandardErrorPath</key><string>$data_xml/$label.log</string>
</dict>
</plist>
PLISTEOF
    [ "${NOBOOT:-0}" = 1 ] && return 0   # written for next login only (it is already running)
    launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null || warn "Couldn't start the $label job."
  }
  agent app '<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>' "$RSC" serve --no-browser
  agent checkmail '<key>StartInterval</key><integer>1800</integer>' "$RSC" check-mail
  agent weeklyreport '<key>StartCalendarInterval</key><dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>' "$RSC" weekly-report --send
  DAILY_SCHED=""; for wd in 1 2 3 4 5; do DAILY_SCHED="$DAILY_SCHED<dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>"; done
  agent dailysheet "<key>StartCalendarInterval</key><array>$DAILY_SCHED</array>" "$RSC" daily-sheet --send
  if [ "$OLLAMA_OURS" = 1 ] && [ -n "$OLLAMA_BIN" ]; then
    curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 && NOBOOT=1   # already running: avoid a second copy
    agent ollama '<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>' "$OLLAMA_BIN" serve; NOBOOT=0
  elif [ -n "${OLLAMA_APP:-}" ]; then agent ollama '<key>RunAtLoad</key><true/>' /usr/bin/open -ga "$OLLAMA_APP"; fi
  ok "Running in the background (logs in $DATA_DIR)"
else
  say "6. Background jobs: skipped"
fi

# ------------------------------------------------------------------ done
STEP="final check"
say "Done. Checking everything..."
if [ "$(uname -s)" = "Darwin" ]; then
  for _ in $(seq 1 30); do is_ours "$PORT" && break; sleep 1; done
  if ! is_ours "$PORT"; then   # the background job may not have started it: start it directly
    (cd "$APP_DIR" && RSC_HOME="$DATA_DIR" nohup "$RSC" serve --no-browser >/dev/null 2>&1 &)
    for _ in $(seq 1 20); do is_ours "$PORT" && break; sleep 1; done
  fi
fi
"$RSC" doctor || warn "Something above needs attention (see the lines marked FAIL or WARN)."
if [ "$(uname -s)" = "Darwin" ]; then
  if is_ours "$PORT"; then open "http://localhost:$PORT/setup"
  else warn "The app didn't start. Double-click RSC on the Desktop."; fi
fi
echo "  Next time: double-click RSC on the Desktop."
echo "  Your data:  $DATA_DIR  (back it up with Time Machine; daily copies are in $DATA_DIR/backups)"
echo "  To update:  unzip the new version over the old folder, then run Install RSC again."
trap - ERR
