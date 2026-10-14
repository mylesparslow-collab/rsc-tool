# Changelog

Newest first. Each entry says what changed in plain words. Version numbers match `rsc/__init__.py` and `pyproject.toml`.

## Unreleased (2026-10-14): client funnel

- Website quote requests that give only a phone number now land in To Review as leads (before, a lead needed an email).
  A "Text the reply" button opens the drafted reply in Messages.
- Website leads show where the person found Nick (Google, Nextdoor, Facebook...). The site passes this along by itself.
- A quote sent from the person's own mail app replies to their address.
- An estimate with no answer after 7 days gets a polite follow-up note on the job page, ready to open in Mail or Messages.
  After 21 days the note becomes a last, no-pressure check-in. No prices, nothing sent automatically.
- 211 tests pass.

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
