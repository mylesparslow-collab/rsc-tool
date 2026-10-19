# Letting Myles's Claude work on Nick's Mac

Checked 2026-10-18 against the Claude Code docs ("Projects" and "Remote Control" on code.claude.com).

## What can and can't happen

- Two Claudes on two accounts **can't message each other**, and a Claude project **can't be shared** with another
  person ("A project belongs to one user"). A Team plan doesn't change that.
- A project **can** run a thread on a computer through Remote Control. If Claude Code on Nick's Mac is signed in as
  Myles, Nick's Mac shows up in Myles's project, and threads there can work in this folder: `rsc doctor`, read the
  logs, fix code, run tests.
- Nick's own Claude keeps working on his account. The two leave each other notes in `~/RSC/HANDOFF.md`
  (rules in CLAUDE.md, "Two Claudes on this Mac") and in `LOCAL-FIXES.md`.

## Agree with Nick first

- Myles's Claude can read Nick's client data in `~/RSC`. It goes to Anthropic under Myles's account.
- Work on Nick's Mac counts against Myles's plan limits, not Nick's.
- To stop it: `./deploy/connect-myles-claude.sh --off`, or Myles signs out of that device in his Claude settings.

## Setup (Myles, by screen share or in person)

1. On Myles's account, **Require trusted devices** must be off (claude.ai, Settings > Account). Projects can't run a
   thread on a computer while it's on.
2. On Nick's Mac, in Terminal: `curl -fsSL https://claude.ai/install.sh | bash`
3. `cd ~/rsc-tool` (or wherever the folder is), then `./deploy/connect-myles-claude.sh --login`. Type `/login`, open
   the link on Myles's phone, sign in as Myles there, paste the code back, then `/exit`. Myles's password is never
   typed on Nick's Mac.
4. **Check Nick's Claude app still shows Nick's account.** The script keeps Myles's login in its own settings folder
   (`~/.claude-myles`), but reports differ on whether macOS keeps two Claude Code logins apart. If Nick got signed
   out, sign him back in and stop here.
5. `./deploy/connect-myles-claude.sh` connects in that Terminal window. In Myles's project, ask for something on
   Nick's Mac ("run rsc doctor on Nick's Mac"); an **Allow Claude to work in a folder on your device** card appears.
   Pick Nick's Mac and this folder, click Allow once.
6. Once that works, close the window and run `./deploy/connect-myles-claude.sh --keep-running` so it reconnects after
   every restart (log: `~/RSC/claude-myles.log`).
7. System Settings > Energy: turn on **Prevent automatic sleeping**. A sleeping Mac pauses the thread.

Nick clicks nothing day to day.

## How a fix reaches the running app

Threads from Myles's project work in a git worktree (their own copy of the code), so nothing they change touches the
running app. A fix is committed to a `nick-mac-fixes-YYYY-MM-DD` branch and pushed; Myles merges it, and Nick's app
gets it with the next update. Reading logs and data, running `rsc doctor` and restarting the app work directly.
