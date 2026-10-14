# Changelog

Newest first. Each entry says what changed in plain words. Version numbers match `rsc/__init__.py` and `pyproject.toml`.

## 0.2.2 (unreleased)

- RSC.app checks your email by itself: once a few seconds after it opens and then every 30 minutes while it is open, only when Gmail is set up. Home shows when it last checked and what it found; a checkbox on Setup turns it off; it steps aside if the installer's background check is already on this Mac. New items still wait in To Review. When the window is closed the app quits and the checks stop. (The Monday report and daily crew sheet are not part of this; they still need the installer's background jobs.)
- AI status you can see: Home shows "AI ready · model", the footer says the same, and Setup says plainly whether your models are up and running, with a "Test it" button that asks the model one tiny question.
- No more warnings about a default model that isn't downloaded when another model on this Mac works. "Automatic" now means the config model if installed, else the best model you already have.
- One-click "Download" for the suggested models, with a progress bar. If this Mac has no usable text model at all, the suggested one downloads by itself (progress always shows; a checkbox on Setup turns this off).

## 0.2.1

- First release you can download from the Releases page. (An empty 0.2.0 release was made first; its build was not allowed to attach files. Ignore it.)
- Release builds can now attach files to the release (`contents: write`).

- Sidebar no longer jumps when you press an item: it keeps its scroll position from page to page, only scrolls if the current item is off screen, and is more compact so everything fits at normal window heights.
- New jobsite look: charcoal sidebar with icons, concrete-gray page, safety-yellow buttons, bold condensed headings, big tap targets. Home opens with five big buttons for the daily jobs (new estimate, add an expense, log hours, today's crew sheet, who owes us).
- Look panel (sidebar, "Look: text and colors"): four font packs (Jobsite, Plain, Easy read, Classic), three text sizes, light/dark/match the Mac, three highlight colors, and roomy spacing. Each choice applies at once and is saved in the database for everyone using the app on that computer. Fonts are bundled (open licences), so nothing is fetched. All colors and sizes are still only in `static/tokens.css`. Every page, button and number is where it was.
- RSC.app updates itself: it checks GitHub when it opens, shows an "Update now" banner when there is a newer release, and Install update downloads it, checks it, replaces itself in Applications and reopens. Never without a button press. Page menu, Check for updates; can be turned off. Needs a release made by pushing a tag like v0.2.1 (see docs/mac-app.md).
- RSC.app: the same app in its own window (`rsc desktop`), built into a downloadable `.dmg` by GitHub (`.github/workflows/mac-app.yml`). Not signed with an Apple Developer ID yet; see `docs/mac-app.md`. The existing installer and background jobs are unchanged.

- Setup page: choose which of the models already on this Mac reads email and photos (the list comes from Ollama). "Automatic" keeps the memory-based choice. Takes effect at once, including for the background email check.

## 0.1.0 (2026-10-12)

First version in GitHub. What the app does at this point:

- Jobs, phased payments and expenses (from the RSC Job Tracker), with job numbers, RSC codes and payment IDs.
- Email assistant: a local model reads Gmail (read-only) for receipts, payments and leads; everything waits in To Review.
- Estimates drafted from plain text, SOW, draft contract (needs NY attorney review), signed change orders, pricing check.
- Receipt photos, voice input, room modeler with client view and before/after photos.
- Crew hours, insurance certificates, payroll estimate, daily crew sheet, week plan.
- Owed (invoice aging and polite reminders), client updates, lead reply drafts, review and check-in follow-ups.
- Weekly Monday report, job margins, aging-in-place assessment, playbook and crew brief, "What's next" guide.
- QuickBooks CSV export and optional direct connection (mock-tested only).
- One-click Mac installer, launchd background jobs, `rsc doctor`, daily backups, uninstall.
- 207 tests pass.
