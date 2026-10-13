# Changelog

Newest first. Each entry says what changed in plain words. Version numbers match `rsc/__init__.py` and `pyproject.toml`.

## Unreleased

- New look, borrowed from the Conflara app: warm paper background, serif headings, a sidebar instead of the top menu, soft shadows, a dark mode that follows the Mac's setting, and gentle motion. Fonts are bundled, so nothing is fetched from the internet. All colors and sizes are still only in `static/tokens.css`. Every page, button and number is where it was.
- RSC.app: the same app in its own window (`rsc desktop`), built into a downloadable `.dmg` by GitHub (`.github/workflows/mac-app.yml`). Not signed with an Apple Developer ID yet; see `docs/mac-app.md`. The existing installer and background jobs are unchanged.

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
