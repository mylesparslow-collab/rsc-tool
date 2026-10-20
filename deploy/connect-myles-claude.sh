#!/bin/bash
# Lets Myles's Claude work in this folder on Nick's Mac, from Myles's Claude project (through Remote Control).
# Optional and separate from Install RSC: nothing here runs unless Myles sets it up. See docs/myles-claude-on-nicks-mac.md.
#
# Claude Code here signs in as MYLES, kept apart from Nick's own Claude in its own settings folder (~/.claude-myles).
# Threads from Myles's project then run in this folder and follow CLAUDE.md. Work counts against Myles's plan.
#
#   ./deploy/connect-myles-claude.sh --login      once: sign in as Myles (open the link on Myles's phone, paste the code)
#   ./deploy/connect-myles-claude.sh              connect now, in this Terminal window (close the window to stop)
#   ./deploy/connect-myles-claude.sh --keep-running   connect in the background, and again after every restart
#   ./deploy/connect-myles-claude.sh --off        stop the background connection
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${RSC_HOME:-$HOME/RSC}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude-myles}"
LABEL="com.reclaimedspacecrafters.claude-myles"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
MIN_VERSION="2.1.280"   # projects can run threads on a computer from this version on
NAME="Nick's Mac"

ok()   { printf '  \033[32mOK\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31mStopped:\033[0m %s\n' "$*" >&2; exit 1; }

MODE="now"
case "${1:-}" in
  "") ;;
  --login) MODE="login" ;;
  --keep-running) MODE="keep" ;;
  --off) MODE="off" ;;
  -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
esac

if [ "$MODE" = off ]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  ok "Myles's Claude is no longer connected to this Mac in the background."
  exit 0
fi

CLAUDE="$(command -v claude || true)"
[ -z "$CLAUDE" ] && [ -x "$HOME/.local/bin/claude" ] && CLAUDE="$HOME/.local/bin/claude"
[ -n "$CLAUDE" ] || die "Claude Code isn't installed. Run:  curl -fsSL https://claude.ai/install.sh | bash   then try again."
VERSION="$("$CLAUDE" --version 2>/dev/null | awk '{print $1}')"
if [ "$(printf '%s\n%s\n' "$MIN_VERSION" "$VERSION" | sort -V | head -1)" != "$MIN_VERSION" ]; then
  die "Claude Code $VERSION is too old (needs $MIN_VERSION or later). Run:  $CLAUDE update"
fi
ok "Claude Code $VERSION, settings in $CLAUDE_CONFIG_DIR"

if [ "$MODE" = login ]; then
  mkdir -p "$CLAUDE_CONFIG_DIR"
  echo "  Claude opens next. Type  /login  and sign in as MYLES (not Nick): open the link it shows on Myles's"
  echo "  phone, sign in there, and paste the code back here. Then type  /exit"
  echo "  Afterwards, open Nick's Claude app and check it still shows Nick's account."
  cd "$APP_DIR" && exec "$CLAUDE"
fi

# Each thread gets its own copy of the code (a git worktree), so a half-done fix never touches the running app.
# A folder that came from a zip has no git; then threads share the folder itself.
SPAWN="worktree"
if ! git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  SPAWN="same-dir"
  warn "This folder isn't a git checkout, so threads will work in it directly (see CLAUDE.md, Updating from GitHub)."
fi
ARGS=("$CLAUDE" remote-control --spawn "$SPAWN" --name "$NAME")

if [ "$MODE" = now ]; then
  echo "  Connecting. Leave this window open; close it to stop."
  cd "$APP_DIR" && exec "${ARGS[@]}"
fi

[ "$(uname -s)" = "Darwin" ] || die "--keep-running is for a Mac."
mkdir -p "$(dirname "$PLIST")" "$DATA_DIR"
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
args=""; for a in "${ARGS[@]}"; do args="$args<string>$(xml "$a")</string>"; done
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>$args</array>
  <key>WorkingDirectory</key><string>$(xml "$APP_DIR")</string>
  <key>EnvironmentVariables</key><dict>
    <key>CLAUDE_CONFIG_DIR</key><string>$(xml "$CLAUDE_CONFIG_DIR")</string>
    <key>RSC_HOME</key><string>$(xml "$DATA_DIR")</string>
    <key>PATH</key><string>$(xml "$(dirname "$CLAUDE"):$APP_DIR/.venv/bin:/usr/bin:/bin:/usr/sbin:/sbin")</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$(xml "$DATA_DIR")/claude-myles.log</string>
  <key>StandardErrorPath</key><string>$(xml "$DATA_DIR")/claude-myles.log</string>
</dict>
</plist>
PLISTEOF
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" || die "Couldn't start the background job. Run without --keep-running instead."
ok "Connected in the background, and again after every restart (log: $DATA_DIR/claude-myles.log)."
echo "  Keep this Mac from sleeping: System Settings > Energy > Prevent automatic sleeping."
