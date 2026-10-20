# CLAUDE.md: the RSC tool

Read this first. You are probably running on Nick Parslow's Mac, helping him (or Myles, his son) fix or adjust the
RSC tool. The app is small and local, and it handles real client money, so change little and check everything.

## Who and what

- **Business:** Reclaimed Space Crafters (RSC), a design-build remodeling business in Saratoga Springs, NY. Owner:
  Nick Parslow. Myles (Nick's son) built this tool and is the person to ask about design intent.
- **Nick is not a programmer.** Explain changes in plain words, one step at a time. Never ask him to edit a file by
  hand if you can do it for him. He is 66 and wants the business to run with less paperwork.
- **Not confirmed (don't state these as fact in the app or in documents):** how the crew is paid (payroll, Zelle,
  insurance), Nick's real markup practice, and whether the contract text is legally sound.
- **Goal of the tool:** less typing and less forgetting. Jobs, estimates, contracts, change orders, expenses,
  payments, crew hours, daily crew sheet, invoice reminders, and a weekly report, all on his own computer.

## Principles (do not break these)

1. **Minimal fields.** Prefer a text box where Nick types or speaks plainly and the local model fills things in.
   Don't add dropdowns or required fields if notes can do the job. "People are lazy."
2. **The model only reads and drafts; code decides.** Prices, totals, job matching, dates and payment IDs are
   computed or validated in code. A model answer that drops a required fact (invoice number, amount) falls back to a
   plain template. Keep it that way.
3. **Every suggestion needs Nick's approval.** Email-derived expenses, payments and leads wait in *To Review*.
   Nothing touches the books until he presses the button.
4. **Nothing is sent for him.** Emails open in Mail (`mailto:`) for him to read and send. The only things the app
   emails by itself are the Monday report and the weekday crew sheet, both to people he listed on the Setup page. One more, only when he presses it (Myles approved 2026-10-15): the **Send** button on the estimate preview emails the estimate PDF to the client from his Gmail, with a copy to him.
   Do not add automatic sending to clients, QuickBooks writes, or anything else that leaves the Mac without asking Myles.
5. **Local first.** The AI runs in Ollama on this Mac. Nothing is sent to a cloud model. Don't add network calls.
6. **Professional wording.** Client-facing text is plain, polite, and never threatens (no fees or lawyers in
   payment reminders).

## What it does (pages)

Home (today's cards, What's next), To Review (email suggestions), Jobs, job page (estimate, SOW, contract, change
orders, hours, safety assessment, crew brief, progress, client update, room model), Expenses, Codes (RSC-100..900),
Pricing, Crew (people, hours, insurance certificates, payroll cost), Today (daily crew sheet), Week (who is where),
Owed (invoice aging and reminders), Playbook, QuickBooks (CSV downloads; optional direct connection), Setup.

Longer descriptions: `README.md`, `docs/how-it-works.md`, `docs/crew-pricing-aging.md`, `docs/nick-quick-start.md`,
`docs/launch-checklist.md`, `docs/quickbooks-setup.md`.

## Architecture

Python 3.11+ Flask app with Jinja templates, SQLite (WAL) for data, Ollama for models. No JavaScript build step.

```
rsc/web.py            create_app(): routes for home, jobs, review, expenses, estimates; registers the *_web.py modules
rsc/*_web.py          crew_web, daily_web, aging_web, playbook_web, receivables_web, client_update_web, schedule_web, qb_web, ops_web (Setup), next_web (job tracker, glow, Next task)
rsc/db.py             schema (CREATE TABLE IF NOT EXISTS) and _migrate() for added columns. Add tables here.
rsc/books.py          jobs, payments, expenses, change orders' money effects. IDs: job number + code + payment seq (ids.py)
rsc/estimates.py      estimate model, templates, SOW. assist.py = model drafts estimates/scopes. pricing.py, rates.py = price checks
rsc/contract.py       contract text (DRAFT, see Safe-change rules). changeorders.py = signed change orders
rsc/pipeline.py       email -> model -> suggestions -> approve/dismiss. extract.py = prompts and parsing. mail.py = IMAP (read-only)
rsc/intake.py         website-form and job-application emails (plain code, no model needed)
rsc/leads.py, followups.py  reply drafts for new leads; review/check-in follow-ups
rsc/receivables.py    invoice aging and polite reminder drafts. client_update.py = weekly note to the homeowner
rsc/crew.py           people, hours, certificates, payroll cost. schedule.py = week plan. daily.py = daily crew sheet
rsc/aging.py          aging-in-place assessment, dimension checks. playbook.py, guide.py = crew brief and What's next
rsc/margins.py, report.py  job margins, weekly report. doctor.py = health check. backup.py = daily DB copies
rsc/brand.py          business name/owner/address/phone in ONE place (Setup page). Use `brand.current()`, never hard-code names
rsc/llm.py, models.py Ollama client; which model does which job; download/pull
rsc/qbo.py, quickbooks.py  optional QuickBooks Online link; CSV export
rsc/config.py         config.toml loading; Keychain access for the Gmail app password
rsc/cli.py            the `rsc` command
rsc/templates, static HTML and CSS. Design tokens (colors, type sizes, 8px spacing) are ONLY in static/tokens.css; style.css uses them. To restyle, change tokens first. tests/ = pytest. deploy/ = install.sh, uninstall.sh
```

Conventions: small modules, plain functions taking `conn` (sqlite connection); web modules expose
`register(app, cfg, conn[, get_model])`; money is stored as floats rounded to cents; all POST forms carry a `csrf`
field; redirects that take a `back` parameter must validate it is a local path. Match the surrounding style.

## Where things live

- **Code:** the `rsc-tool` folder (this one), with its own `.venv`. Don't move it.
- **Website:** `website/` is the public site at rscrafters.com (pages, blog posts, photos, build scripts). A GitHub
  Action builds it and uploads it to Cloudflare Pages: merging to the default branch makes it live, PRs get preview links. Read
  `website/CLAUDE.md` before changing it. It is separate from the app: no tests, no version bump, no `rsc` restart.
- **Email worker:** `email-worker/` is a small Cloudflare program on the rscrafters.com addresses: it forwards each email to
  Nick's Gmail, copies it to Myles, and sends Myles a summary of each lead. Read `email-worker/README.md` before changing it.
  Separate from the app: no Python tests, no version bump, no `rsc` restart.
- **Data:** `~/RSC` (or whatever `RSC_HOME` says): `rsc.db` (everything), `config.toml`, `backups/rsc-YYYY-MM-DD.db`
  (daily, 30 kept), `install.log`, and one log per background job: `app.log`, `checkmail.log`, `weeklyreport.log`,
  `dailysheet.log`.
- **Secrets:** the Gmail app password is in the macOS **Keychain** (service `rsc-tool-gmail`). Never write it to a
  file, a log, a commit, or this document. QuickBooks keys are in `config.toml`; QuickBooks tokens are in the database.
  Treat `config.toml` and `rsc.db` as private: don't paste their contents anywhere.
- **Models:** managed by Ollama (`~/.ollama`). Which model does which job is in `config.toml` `[model]`; see `rsc models`.

## Run, check, restart

Use the venv: `cd ~/rsc-tool` (or wherever the folder is) then `.venv/bin/rsc <command>`; set `RSC_HOME` if the data
is not in `~/RSC`.

| Do this | Command |
|---|---|
| Health check (start here for any problem) | `.venv/bin/rsc doctor` |
| Open the app (starts it if needed) | `.venv/bin/rsc open` |
| Run the app in a terminal | `.venv/bin/rsc serve --no-browser` (port is in `config.toml`, default 5151) |
| Back up the database now | `.venv/bin/rsc backup` |
| Which models, download missing | `.venv/bin/rsc models` / `rsc models --pull` |
| Check email once | `.venv/bin/rsc check-mail` |
| Show reports without sending | `.venv/bin/rsc weekly-report`, `.venv/bin/rsc daily-sheet` |
| Re-run installer after an update | double-click *Install RSC.command* (safe to repeat) |

Background jobs (launchd, labels `com.reclaimedspacecrafters.<name>` for app, checkmail, weeklyreport, dailysheet,
ollama): `launchctl list | grep reclaimed`. Plists are in `~/Library/LaunchAgents`. Restart the app after a code change:
`launchctl kickstart -k gui/$(id -u)/com.reclaimedspacecrafters.app`. (If it isn't loaded, `rsc open` starts it.)
Port in use: `lsof -nP -iTCP:5151 -sTCP:LISTEN`. A phone on the same Wi-Fi needs `access_pin` in `config.toml`
(6+ characters) and `rsc serve --lan`; otherwise the app listens on this Mac only.

## Config and the Setup page

`config.toml` holds: `port`, `access_pin`, `first_job_number`, `[mail]` (Gmail address, keywords, ignore_senders),
`[model]` (url, name, vision), `[voice]`, `[quickbooks]`, `[business]`. See `config.example.toml`. Most things Nick
changes (Gmail address, report recipients, daily sheet recipients, visit availability, review link, business
details, rates) are on the **Setup** and **Pricing** pages, not in the file. Prefer adding a Setup field over asking
him to edit TOML.

## Models and routing

- Text model (`llama3.1:8b` on 16 GB+ Macs, else `llama3.2:3b`): reads email, drafts estimates and scopes, fills forms
  from notes, writes reply and reminder drafts. Vision model (`qwen2.5vl:3b` on smaller Macs; the installer picks a
  larger one on 24 GB+): reads receipt and certificate photos. Speech model (`base.en`): microphone buttons.
- All calls go through `model.extract(system, user, schema, images=None)` which returns JSON matching the schema.
  Wrap model calls in try/except and keep a plain-code fallback; the model can be off (Ollama closed) and the app must still work.
- `rsc doctor` reports which models are missing. `rsc models --pull` downloads them.

## Tests and safe changes

Run `.venv/bin/python -m pytest -q` before and after every change (about 200 tests, under 15 seconds).
If pytest is missing: `.venv/bin/pip install pytest` (or `uv pip install --python .venv/bin/python pytest`).

**Rules**

1. **Back up first:** `.venv/bin/rsc backup`, and note the file name in `backups/`.
2. **Smallest change that fixes it.** Hotfix means one bug, one commit-sized edit, one new test when practical.
   Don't refactor, rename, or reformat unrelated code.
3. **Database changes are additive only:** new tables/columns in `db.py` (`CREATE TABLE IF NOT EXISTS`, and an
   `ALTER TABLE ... ADD COLUMN` in `_migrate`). Never drop, rename, or rewrite existing data. Check table names
   don't already exist (`grep -rn "CREATE TABLE" rsc/`); for example `job_photos` already belongs to the room modeler.
4. **Contract text is not yours to change.** `rsc/contract.py` is a draft awaiting New York attorney review. If a fix
   touches wording, flag it to Nick/Myles as needing attorney review, don't "improve" legal language, and keep the
   `OPEN_ITEMS` list accurate. Don't claim the contract is legally sufficient.
5. **No automatic sending or outside writes.** No new code that emails clients (beyond that one Send button), posts to QuickBooks, or calls the
   internet without Myles's say-so. Email drafts open in Mail.
6. **Secrets stay in the Keychain.** Never log, print, commit, or paste passwords, app passwords, PINs, or QuickBooks keys.
7. **Don't edit live data with raw SQL** unless Nick asks and you've backed up. Prefer the app's own pages.
8. **Test against a copy** when trying something risky: `RSC_HOME=/tmp/rsc-try .venv/bin/rsc serve --port 5199 --no-browser`
   (`rsc load-example examples/*.json` loads sample jobs). Never test on port 5151 with real data open.
9. **After a change:** run the tests, run `rsc doctor`, restart the app, and open the page you changed.
10. **Tell Nick what you changed** in plain words and where the backup is. If it goes wrong, restore by quitting the
    app and copying the newest good file from `backups/` over `rsc.db` (keep the broken one with a new name).

## Updating from GitHub

The code lives in a public GitHub repo (no client data in it): `https://github.com/mylesparslow-collab/rsc-tool`. Myles pushes changes
there and lists them in `CHANGELOG.md`. Data never goes in the repo (`~/RSC`, `config.toml`, `.venv` are ignored).
When Nick or Myles asks you to update the app:

1. **Check access.** This Mac needs to reach the repo (public, so normally nothing to set up; if Myles ever makes it private, `gh auth login`
   or a read-only token). If `git fetch` asks for a password or says "not found", stop and tell Nick to ask Myles.
2. **Back up first:** `.venv/bin/rsc backup`, and also copy the whole data folder:
   `cp -R ~/RSC ~/RSC-before-update-$(date +%Y-%m-%d)`. Tell Nick where the copy is.
3. **First time only (folder came from a zip, no `.git`):** `git init`, `git remote add origin <repo URL>`,
   `git fetch origin`, then `git reset origin/HEAD` (keeps the files on disk) and `git branch -u origin/HEAD` if needed.
   `git status` now shows any local edits. If there are some, write them up in `LOCAL-FIXES.md` (step 7) before
   `git checkout -- .` replaces them with the repo version.
4. **Pull:** commit any local fixes first (step 7), then `git pull --ff-only`. If it refuses or conflicts, don't force
   it: stop, leave things as they are, and tell Nick to ask Myles.
5. **Install and test:** `.venv/bin/pip install -e '.[dev]'` (picks up new dependencies), then
   `.venv/bin/python -m pytest -q`. All tests must pass. If any fail, roll back (`git reset --hard <previous commit>`,
   noted before pulling) and tell Myles which test failed.
6. **Check and restart:** `.venv/bin/rsc doctor`, then
   `launchctl kickstart -k gui/$(id -u)/com.reclaimedspacecrafters.app` (or `rsc open`). Open the app and the pages
   the CHANGELOG says changed. Tell Nick in one or two plain sentences what's new.
7. **Leave notes for Myles.** Any fix or change you make on this Mac (not ones pulled from GitHub) goes in
   `LOCAL-FIXES.md` at the top of this folder, newest first, a few lines each: date, what was wrong, what you changed
   (files), whether tests passed, and anything Myles should check. Commit it with the fix (`git commit -am "..."`).
   If this Mac can push, push to a new branch named `nick-mac-fixes-YYYY-MM-DD`, never to the main branch;
   otherwise leave the commit local and tell Nick to let Myles know there are notes in `LOCAL-FIXES.md`.

## Known gaps and open items

- **Contract needs a New York attorney** (attorneys' fees, permits, termination days, license/insurance wording,
  deposits/cancellation/lien section 18 which cites NY GBL §771 as a placeholder). Not legal advice.
- **Default markup is 43%** (`rates.py`), but Nick's own practice has been closer to 20%. Myles has not decided.
  Don't change it without asking.
- **Hours vs expense double counting:** crew hours logged on the Crew page and labor entered as expenses can both
  count toward a job's cost. The Crew page notes this. Logged hours replace the estimate's guess only when higher.
- **Crew pay setup is unconfirmed** (payroll, workers' comp, insurance). The Crew page payroll calculator is an estimate.
- **Not yet tested on a real first install with model downloads:** the installer was run end-to-end on Myles's Mac
  with models skipped; the model download step (several GB) and Nick's M1 iMac are untested.
- **QuickBooks direct connection** has only run against mocks; CSV export is the reliable path.
- Estimate template steps are drafts; Nick's real step lists (Whitcomb has 58) should replace them over time.
- The payment-1 amount on the Hartwell example reads "$1,957" and looks like a typo to check with Nick.
- The business name is a question in Myles's mind ("REFINED" vs "Reclaimed"); use `brand.current()` and the Setup page.

## Troubleshooting

- **Page won't load / "can't connect":** `rsc doctor`; check the port in `config.toml`; `launchctl list | grep reclaimed`;
  read `~/RSC/app.log` (last 50 lines). Try `rsc open`.
- **Another RSC already on the port:** the installer picks the next free port for a fresh install; an existing install
  keeps the port in `config.toml`. Two copies cannot share a port.
- **"Assistant isn't available" / model errors:** Ollama isn't running. Open the Ollama app, then `rsc models`.
  Without it the app still works; drafts use plain templates.
- **Model missing:** `rsc models --pull` (large downloads: use fast Wi-Fi; they resume).
- **No email arriving in To Review:** Gmail address not set (Setup), app password not stored (`rsc set-password`),
  or emails skipped by keywords (see `[mail] keywords`; add words rather than disabling the filter). Check `checkmail.log`.
- **Gmail login fails:** needs 2-Step Verification and an *App password*, not the normal password.
- **Weekly report or crew sheet didn't arrive:** recipients on Setup; `weeklyreport.log` / `dailysheet.log`; try
  `rsc weekly-report --send` or `rsc daily-sheet --send` once by hand.
- **Phone can't reach the app:** needs `access_pin` and `rsc serve --lan`, same Wi-Fi; or see `docs/share-with-nick-tailscale.md`.
- **Mac asks to allow the installer / "unidentified developer":** right-click *Install RSC.command* > Open once.
- **A number looks wrong:** check `rates.py` and `pricing.py` first, then the job's estimate on the job page; compare with the
  Pricing page rates. Add a test with the numbers before fixing.
- **Test fails only on this Mac:** often a real service (Ollama, voice model, network) leaking into a test. Stub it in the test; don't skip the test.

## When unsure

Stop and ask Nick or Myles. A short question costs less than a wrong change to a client's job record.
