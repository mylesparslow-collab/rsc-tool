# Launch checklist: Reclaimed Space Crafters tool

## Install on Nick's Mac (about 30 minutes, with Nick)
1. Unzip `rsc-tool.zip` in the home folder and double-click **Install RSC.command** (right-click > Open the first time; that is the only extra step). It asks nothing and needs no Homebrew or administrator password.
   It fetches Python (uv), builds the app, installs Ollama if missing, downloads the three local models sized to the Mac's memory (reusing any already pulled), keeps the app running in the background (starts at login), checks mail every 30 minutes, emails the weekly report Monday 7 AM, adds an RSC icon to the Desktop, and opens the app. Allow 15 to 30 minutes for the downloads.
   To import the tracker too: `./deploy/install.sh --tracker "RSC Job Tracker.xlsx"`.
2. In the app's **Setup** page (it opens there): Gmail address, app password (Google Account > Security > 2-Step Verification on > App passwords > "RSC Tool"), who gets the Monday report, visit availability, Google review link.
3. Optional later: QuickBooks direct connection, docs/quickbooks-setup.md. The CSV downloads on the QuickBooks page need no setup.
4. Press "Check email now" on the Home page and review what appears in To Review.
5. Turn on Time Machine (or any backup) for the `~/RSC` folder.

## Before real clients see anything
- [ ] New York attorney reviews the contract draft and its open items (attorneys' fees, permits, termination days, license and insurance wording, sections 5, 8 and 9).
- [ ] Nick replaces the draft template steps with his real scope-of-work steps (the Whitcomb job has 58).
- [ ] Nick confirms RSC-100 to RSC-900 codes match QuickBooks accounts (ask the accountant).
- [ ] Nick sets his target margin on the Pricing page.
- [ ] Run against the real inbox for a week; tune the keyword list and check the model's suggestions.

## Known gaps
- No QuickBooks sync (Payment IDs are the invoice numbers; entry is manual).
- Photo-only receipts are not read.
- Room model and photos are not in the Excel export.
- Phone access is off by default; `rsc serve --lan` needs `access_pin` in config.toml.
