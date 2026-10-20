# Changelog

Newest first. Each entry says what changed in plain words. Version numbers match `rsc/__init__.py` and `pyproject.toml`.

## Unreleased

- Pricing check before you send. The Send screen for an estimate now shows the labor rate per crew-hour (worked out from the Crew and Duration lines, nothing new to type) and any pricing warnings, with a "Change the price first" button. It never stops you sending.
- A suggested price. When labor is under the target rate (Pricing page, $72 a crew-hour by default) or the materials markup is under your usual one, the estimate page and the Send screen say what the job would be at those numbers and how many dollars more that is.
- Materials with no markup at all are now a red flag, not a gentle note.

## 0.2.7

- Harder to get lost. Every job page now starts with a tracker: the job's five stages (Write the estimate, Send it, Get it signed, Do the work and get paid, Wrap up) with a check on the finished ones, "Stage 3 of 5" in words, and the one next thing to do with a big button.
- The next thing to press glows. When you're on the page where the next step happens, that field or button pulses with a "Do this next" tag. Only one thing glows per page, and nothing glows while a job is only waiting on the client or a payment.
- New "Next task" button at the top of the sidebar (in the top bar on a phone). Press it from anywhere and it takes you to the next thing that needs doing, scrolls to it and lights it up. On a job page it means that job's next step; elsewhere it goes in the same order as Home: setup, email to review, late invoices, follow-ups, then each job. Home shows "Your next task" at the top.

## 0.2.6

- Fixes from a full test job, first email to review request (invented client):
  - Expenses: after "Read it" or "Read the photo", pressing "Add expense" saved nothing. It now saves.
  - To Review: "Start estimate" on a new lead now opens that job's estimate instead of staying on To Review.
  - With the AI program closed, the email check no longer stops: website-form leads still come in (with the plain reply), and the rest waits for the next check.
  - The plain lead reply says "about your deck project" instead of pasting the customer's whole sentence.
  - Estimates: a "Walk-through" step no longer gets a "Rough-in inspection" (the last phase gets the final inspection again). A subcontractor price the assistant puts under hired labor is now flagged: it is your cost, not added to the client's price.
  - Job page: a date paid with the amount left blank counts as paid in full. When the crew ticks off every step of a phase, "What's next" says to invoice that payment now. A job marked Complete with the final payment not yet invoiced says so first (before the review), and stays on Home until it is paid.
  - QuickBooks invoices file: the description no longer loses its closing parenthesis.

## 0.2.5 (unreleased)

- Payments: each unpaid row on the job page has one-click "Invoiced today" and "Paid in full today" buttons, so a client who paid outside the app (or a test job) clears the "Invoice payment 1" card without typing dates and amounts.

## 0.2.4 (unreleased)

- One-click Send for estimates. The estimate preview now has "Send to <client>". It opens a short screen with the client's address, a subject and a friendly message already filled in, and the estimate attached as a PDF (Estimate-<job>.pdf). Press "Send to the client" and it goes from your Gmail, with a copy to you; only then is the job marked "Estimate sent" today. If the email fails, nothing is marked. If Gmail isn't set up, the screen says so with a "Set up email first" link. Nothing is ever sent without that press.
- New: the estimate PDF is made inside the app (adds the small `reportlab` library). The same PDF opens at /jobs/<number>/sow.pdf.
- "What's next" now says "Preview and send" for an unsent estimate.

## 0.2.3

- Fixed: an email with two or more PDF attachments (for example two estimates) now puts each one in To Review as its own item, labeled with the file name. Before, they were read together and only one came through. Several receipt photos in one email are each read too (up to 6), and PDFs are read up to 5 pages.
- A PDF that says "invoice" or "estimate" inside, with a plain subject and body, is no longer skipped as "not business".
- Not changed: scanned (picture-only) PDFs still can't be read; that needs a PDF-to-image step.

## 0.2.2

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
