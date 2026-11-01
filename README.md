# RSC Tool

A small app for Reclaimed Space Crafters that runs entirely on one Mac. It keeps the jobs, phased payments and expenses from the RSC Job Tracker, and a local AI model reads Nick's Gmail to find receipts, client payments and new leads. Everything it finds waits in a **To Review** list until Nick approves it.

> **Quick install on a Mac:** double-click `Install RSC.command` (or run `./deploy/install.sh`); it does every setup step below, including downloading the models. See docs/launch-checklist.md and docs/nick-quick-start.md.

> **Code and updates:** this folder is the GitHub repo `mylesparslow-collab/rsc-tool`. Myles pushes changes
> there; on Nick's Mac, Claude pulls them in following "Updating from GitHub" in `CLAUDE.md`. Real data (`~/RSC`),
> `config.toml`, passwords, the website and the social videos are never in the repo. Changes are listed in `CHANGELOG.md`.

## Typing instead of forms

The local model fills in forms from plain text, so Nick types a sentence instead of choosing from dropdowns: a pasted client email makes the job and drafts the estimate (`rsc/assist.py`), "Home Depot 109.91 studs for Smith" fills in an expense, and "second window east wall $1,200" writes a change order. The model only drafts. Prices it guesses are listed under "Please check these", nothing is billed or signed without Nick, and every page keeps a by-hand form behind "Or fill it in by hand" for when the model is off. Small models (3B) draft rougher prices than 8B; the installer picks 8B on Macs with 16 GB or more.

## Models, photos and QuickBooks

Three local models, chosen from the computer's memory by `rsc setup` and downloaded by `rsc models --pull`: text (`llama3.2:3b` or `llama3.1:8b`) for email, estimates and forms; vision (`qwen2.5vl:3b`, or `llama3.2-vision` with 24 GB or more) for receipt photos; speech (`base.en`) for the microphone. `rsc models` shows what is ready.

Receipt photos: Expenses > "snap a photo" (on a phone the camera opens), or attach the photo to an email to the business address. The vision model reads vendor, date and total; the job comes from the same rules as email and a few typed words. Nothing is added until it is checked, and the photo is kept with the expense.

QuickBooks: the QuickBooks page downloads invoices (invoice number = Payment ID), expenses and customers as CSV for QuickBooks Online's importers. An optional direct connection sends one invoice at a time when a button is pressed (docs/quickbooks-setup.md).

## Keeping the business moving

- **Weekly report:** Monday 7 AM the app emails a one-page report (collected, owed, jobs underway, margin warnings, estimates waiting, follow-ups due) from the business Gmail to the addresses on the Setup page. Preview or send now at `/report`; from Terminal `rsc weekly-report [--send]`. The numbers come from the books; the model only writes the opening sentence.
- **Lead replies:** a new inquiry in To Review comes with a reply already written that offers the next real visit times (set in plain words on Setup, like "Tuesdays and Thursdays at 4pm"). The reply is never sent for him: Open in Mail, or Copy.
- **Follow-ups:** marking a job Complete queues a review request (3 days) and a one-year check-in. Each is drafted on demand, opens in Mail, and is marked sent by hand.
- **Job margins:** `/margins` compares spent with the estimate's direct-cost budget and projects the margin; warnings appear on Home. Set the target on the Pricing page.
- **One-click install:** `Install RSC.command` asks nothing, then opens the Setup page. The app runs as a login item (launchd), so the Desktop icon just opens it.

## Voice input

The big text boxes have a microphone button. The browser records a short clip, the app sends it to itself (`/voice`), and a local speech model (faster-whisper, `base.en`, about 150 MB) turns it into text. Nothing leaves the computer after the one-time model download. The installer adds it (`--no-voice` skips it); by hand: `pip install -e '.[voice]'` then `rsc voice-setup`. The mic works on `localhost`; a phone over Wi-Fi needs HTTPS for the browser to allow the microphone, so phone voice typing isn't supported yet.

## What it does

| Area | What Nick sees |
|---|---|
| **Home** | Count of items to review, open jobs with paid / still owed / expenses / profit, and payments not yet received. |
| **To Review** | Cards built from emails: *Receipt* (vendor, amount, which job), *Client payment* (which Payment ID it pays), *New lead* (name, phone, address, project). He can fix a field, then press **Add expense / Mark paid / Start estimate**, or **Skip**. |
| **Jobs** | New estimate gets the next number automatically (1003-OKA). Each job page has the payment schedule with Payment IDs to use as QuickBooks invoice numbers. |
| **Expenses** | Every cost is charged to a job number or an RSC code (RSC-100 truck, RSC-120 insurance...). |
| **Estimate & contract** | On a job: pick a job type and it drafts the phases, numbered steps, inspections and "not included" lists in Nick's Whitcomb format. He enters prices; it builds the payment schedule (Whitcomb's comes out to $17,618, 8 x $1,690, $1,965), prints the Estimate / SOW, and drafts the contract with his 5-year warranty and change-order terms. **Contract signed** creates the payments and marks the job Signed. |
| **Change orders** | Write the change, hand over the screen, the client signs with a finger; the contract total and payment schedule update together (1002-SMI-CO1 adds payment 1002-SMI-4). Printable. |
| **Pricing** | Estimate vs. what the job really cost, and a floor price from his own overhead (RSC-coded costs) and target margin. Shows nothing it can't back up: it asks for his margin instead of assuming one. |
| **Room model** | Per job (linked from the Jobs list and each job page): wall sizes, windows and doors drawn as a dimensioned plan and a 3D view, saved with the job. Works offline. |
| **Export** | One click downloads everything as Excel for QuickBooks or the accountant. |

## How the email part works

1. Every 10 minutes (and when Nick presses **Check email now**) the app opens his Gmail **read-only** over IMAP. It never marks mail read, moves, deletes or sends anything. (One exception, off by default: the Setup switch *Thank new customers right away* sends a fixed thank-you to a new website request, over Gmail SMTP.)
2. A keyword filter drops obvious non-business mail before the model sees it.
3. The local model ([Ollama](https://ollama.com), default `llama3.1:8b`) classifies each remaining email and pulls out the fields, using a fixed JSON schema at temperature 0.
4. Plain rules, not the model, decide which job something belongs to: a Job ID or Payment ID written in the email first (a Home Depot PO of `1002-SMI`, an invoice number `1002-SMI-2`), then a unique job address, then a unique client last name. Anything unclear is left for Nick to pick.
5. Every email is recorded by Message-ID, so nothing is suggested twice.

**Tip for Nick:** give the Job ID as the PO / job name at the register (Home Depot, Lowe's and most lumber yards print it on the receipt). That makes receipts match their job automatically.

## Contract text

The contract is a **draft, not legal advice**, built from the terms Nick settled on for Whitcomb (5-year workmanship warranty with written notice, written change orders, up-front schedule-hold payment, right to stop work for late payment, mutual indemnity capped at sums paid, NY law, arbitration in Saratoga County, non-disparagement). It carries a banner and a list of open items: mutual attorneys' fees wording, permits, termination notice days, license/insurance details, and three plain-language sections (schedule, client responsibilities, materials) that weren't in those terms. A New York attorney should review it before it goes to a client. The phase steps in the estimate templates are starting drafts (only Whitcomb's eight phase names come from a real SOW).

## Using it from a phone (optional)

Change orders are easiest on a phone or tablet at the job. Add `access_pin = "six-or-more-characters"` to `~/RSC/config.toml`, then start the app with `rsc serve --lan`. It prints an address like `http://192.168.1.20:5151`; open that on a phone on the same Wi-Fi and enter the PIN. Everything then requires the PIN (guessing is throttled). It is plain HTTP on the home network, so use it on home Wi-Fi only and never forward the port to the internet. Without `--lan` the app stays reachable only from the computer itself.

## Privacy and safety

- Email text goes only to the model on the same computer (`localhost:11434`). Nothing goes to OpenAI, Anthropic or any other service.
- The app only listens on `127.0.0.1`, so other devices on the network can't reach it. Forms carry a CSRF token.
- Gmail access uses an **app password** stored in the macOS Keychain. It can be revoked any time at https://myaccount.google.com/apppasswords without changing Nick's real password.
- Nothing touches the books until a person approves it.
- Data lives in `~/RSC/rsc.db` (SQLite). Back it up with Time Machine, or copy the file.

## Setup (on Nick's Mac, about 20 minutes)

You need macOS with Python 3.11+ (`brew install python` if `python3 --version` is older) and the Ollama app.

```bash
# 1. Local model
brew install --cask ollama        # or download from ollama.com; open it once
ollama pull llama3.1:8b           # ~4.7 GB. On an 8 GB Mac: llama3.2:3b, and set it in config.toml

# 2. The app
cp -R rsc-tool ~/rsc-tool && cd ~/rsc-tool
python3 -m venv .venv && .venv/bin/pip install -e .

# 3. Settings, database, and the existing tracker
.venv/bin/rsc setup --tracker "/path/to/RSC Job Tracker.xlsx"

# 4. Gmail app password (Nick's Google account needs 2-Step Verification on)
#    Create one at https://myaccount.google.com/apppasswords, name it "RSC Tool"
.venv/bin/rsc set-password

# 5. Try it
.venv/bin/rsc check-mail          # reads the last 30 days
.venv/bin/rsc serve               # opens http://localhost:5151
```

Then make it Nick-proof:

```bash
cp deploy/RSC.command ~/Desktop/                     # double-click to open the app
sed "s/USERNAME/$USER/g" deploy/com.reclaimedspacecrafters.checkmail.plist \
  > ~/Library/LaunchAgents/com.reclaimedspacecrafters.checkmail.plist
launchctl load ~/Library/LaunchAgents/com.reclaimedspacecrafters.checkmail.plist   # checks mail every 10 min
```

Settings are in `~/RSC/config.toml` (see `config.example.toml`): starting job number, mailboxes, senders to ignore, and the model.

## Commands

| Command | Does |
|---|---|
| `rsc setup [--tracker file.xlsx]` | Writes config, creates the database, imports the spreadsheet, checks the model |
| `rsc set-password` | Saves the Gmail app password to the Keychain |
| `rsc serve` | Opens the app in the browser |
| `rsc check-mail` | One email check (what the schedule runs) |
| `rsc import file.xlsx` / `rsc export file.xlsx` | Spreadsheet in / out |

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests cover the Whitcomb schedule to the cent, change-order signing, floor-price math, the PIN gate, upgrading an older database, the numbering rules, money totals, the email-to-suggestion pipeline with a stand-in model (receipt, client payment, lead, newsletter), the Ollama request format against a fake server, every page of the app, and import/export of the tracker workbook.

| File | Role |
|---|---|
| `rsc/ids.py` | Job ID / Payment ID / RSC code rules |
| `rsc/books.py` | Jobs, payments, expenses, totals |
| `rsc/mail.py` | Read-only Gmail (IMAP), email parsing, PDF receipt text |
| `rsc/llm.py` | Ollama client |
| `rsc/extract.py` | Prompt, schema, and job matching rules |
| `rsc/pipeline.py` | Check mail → suggestions → approve / skip |
| `rsc/web.py`, `rsc/templates/` | The app |
| `rsc/sheets.py` | Excel import / export |
| `rsc/estimates.py`, `rsc/contract.py` | Estimate templates, payment schedule rules, draft contract text |
| `rsc/changeorders.py` | Change orders and signatures |
| `rsc/pricing.py` | Floor price, overhead, estimate accuracy |
| `rsc/workflow.py` | Pages for the above |
| `rsc/modeler.py`, `rsc/static/modeler.js` | Room model page (three.js bundled in `static/vendor/`) |

## Not built yet

- QuickBooks direct connection is written and tested against imitated replies only; try it in the sandbox first (docs/quickbooks-setup.md).
- Receipt photos need a vision model; the first real receipts should be checked, especially crumpled or faint ones.
- Tested against a stand-in model and sample emails only. The first run on Nick's real inbox should be watched to tune the keyword filter and the model choice.


## Pricing, crew and aging in place
See [docs/crew-pricing-aging.md](docs/crew-pricing-aging.md): labor-rate and margin warnings, crew hours and insurance certificates, the payroll calculator, aging-in-place templates and the safety assessment, plus health checks, backups and updating.
