# RSC.app (the Mac download)

RSC.app is the same app, in its own window instead of a browser tab. It stores everything in `~/RSC`, exactly like the
installer version, so the two share one set of jobs and one database. Nothing is sent over the internet.

## Get it

GitHub builds it (`.github/workflows/mac-app.yml`, an Apple-silicon Mac in GitHub's cloud).
- Any run: open the run on GitHub, then *Artifacts*, then **RSC-mac** (a zip holding `RSC-<version>.dmg`).
- A release: push a tag like `v0.2.1`; the `.dmg` is attached to the GitHub Release.
- Or on a Mac: `./packaging/build_mac.sh` makes `dist/RSC.app` and the `.dmg`.

It is built for Apple-silicon Macs (M1 and later), which includes Nick's iMac.

## Install and open (for Nick)

1. Double-click the `.dmg`, then drag **RSC** onto **Applications**.
2. The first time only: in Applications, **right-click RSC, choose Open, then Open again**.
   (The app isn't signed with an Apple Developer ID, so a plain double-click says it "can't be verified". This is expected.)
   If that is not offered: System Settings, Privacy & Security, scroll down, **Open Anyway**.
3. RSC opens. The first launch makes `~/RSC` and an empty database. The Home page then points to Setup (Gmail).

## Updates (no re-downloading)

The app checks GitHub when it opens. If a newer release exists, a yellow **Update now** banner shows on every page; the
**Page** menu also has **Check for updates**. **Install update** downloads the new app, checks it against its fingerprint, replaces
itself in Applications and reopens. Jobs and settings are not touched. It never installs without a button press, and the check can be
turned off on the Updates page. The first copy still has to be downloaded by hand, and it must be in Applications (not run from the `.dmg`).

To publish an update (Myles): bump `version` in `pyproject.toml` and `rsc/__init__.py`, add a line to `CHANGELOG.md`, merge, then
`git tag v0.2.1 && git push origin v0.2.1`. The "Mac app" workflow builds it and attaches `RSC-mac.zip`, its `.sha256` and the `.dmg` to a
GitHub Release (it refuses a tag that doesn't match the version). Installed apps pick it up the next time they open.
The updater reads the Releases page without logging in, so the repository (or at least its releases) must be readable without an account.
Updates need no Apple signature because the app downloads the file itself, so macOS doesn't flag it.

## What it does not do

- It does **not** install the local AI (Ollama and the models), the 30-minute email check, the Monday report or the weekday
  crew sheet. Those come from *Install RSC.command*, which is safe to run alongside the app. Without Ollama the app still works;
  drafts use plain templates.
- Mail drafts open in Mail, as before. Printing and "save as PDF" pages work better in a browser: use the menu
  **Page, Open this page in the browser**.
- The window runs its own copy of the app on this Mac only, even if the installer's background app is running (they share the same data). The window never asks for the phone PIN.

## Status

Built and tested on Linux only (tests for the window's launch logic, the first-launch setup, and that the packaged app
serves its pages and fonts, which CI also checks on the Mac after building). **Not yet opened on a real Mac:** the window itself,
the unsigned-app prompt, and the `.dmg` layout. See the checklist in the pull request.

## For Myles later

Signing and notarizing needs a paid Apple Developer account ($99/year); then add the certificate to GitHub secrets and replace
the `codesign --sign -` line in `packaging/build_mac.sh`. An Intel build would need a second runner (`macos-13`).
