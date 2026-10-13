# RSC.app (the Mac download)

RSC.app is the same app, in its own window instead of a browser tab. It stores everything in `~/RSC`, exactly like the
installer version, so the two share one set of jobs and one database. Nothing is sent over the internet.

## Get it

GitHub builds it (`.github/workflows/mac-app.yml`, an Apple-silicon Mac in GitHub's cloud).
- Any run: open the run on GitHub, then *Artifacts*, then **RSC-mac** (a zip holding `RSC-<version>.dmg`).
- A release: push a tag like `v0.2.0`; the `.dmg` is attached to the GitHub Release.
- Or on a Mac: `./packaging/build_mac.sh` makes `dist/RSC.app` and the `.dmg`.

It is built for Apple-silicon Macs (M1 and later), which includes Nick's iMac.

## Install and open (for Nick)

1. Double-click the `.dmg`, then drag **RSC** onto **Applications**.
2. The first time only: in Applications, **right-click RSC, choose Open, then Open again**.
   (The app isn't signed with an Apple Developer ID, so a plain double-click says it "can't be verified". This is expected.)
   If that is not offered: System Settings, Privacy & Security, scroll down, **Open Anyway**.
3. RSC opens. The first launch makes `~/RSC` and an empty database. The Home page then points to Setup (Gmail).

## What it does not do

- It does **not** install the local AI (Ollama and the models), the 30-minute email check, the Monday report or the weekday
  crew sheet. Those come from *Install RSC.command*, which is safe to run alongside the app. Without Ollama the app still works;
  drafts use plain templates.
- Mail drafts open in Mail, as before. Printing and "save as PDF" pages work better in a browser: use the menu
  **Page, Open this page in the browser**.
- If the background app from the installer is already running, the window just shows it.

## Status

Built and tested on Linux only (tests for the window's launch logic, the first-launch setup, and that the packaged app
serves its pages and fonts, which CI also checks on the Mac after building). **Not yet opened on a real Mac:** the window itself,
the unsigned-app prompt, and the `.dmg` layout. See the checklist in the pull request.

## For Myles later

Signing and notarizing needs a paid Apple Developer account ($99/year); then add the certificate to GitHub secrets and replace
the `codesign --sign -` line in `packaging/build_mac.sh`. An Intel build would need a second runner (`macos-13`).
