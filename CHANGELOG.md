# Changelog

Newest first. Each entry says what changed in plain words. Version numbers match `rsc/__init__.py` and `pyproject.toml`.

## 0.3.1 (2026-11-01)

New homeowners: the follow-through after the first letter.

- Each house now gets up to three cards by mail (greeting "Dear Smith family"): the welcome, a follow-up three weeks later, and a seasonal note about
  six weeks after that (its words follow the season it goes out in). All three can be edited on the page.
- Every card prints with its own short code and a QR code for the new page **rscrafters.com/welcome**, which offers a free
  walkthrough. A request from that page lands in To Review tagged "new homeowner mail" with the house's address filled
  in, and that house gets no more cards. A "Got in touch" button does the same for people who call or text.
- "This week's batch" puts due follow-ups first, then new welcome cards, up to 50. After the first batch, Home reminds
  Nick each week when cards are due. The CSV now has the card, code, link and words for a mailing service (Thanks.io).
- The county records are now checked every Monday morning instead of once a month, so new buyers show up as soon as
  the county map has them (re-run the installer to change the schedule).
- "No more mail": the welcome page has a stop form (card code or street address, nothing else). The email check marks
  that house "never mail" by itself, with no lead and nothing to approve, and it holds through later county checks.
  Requests that match no house are listed on the page. A "Never mail" button does the same for phone requests.
- Letters already marked mailed count as card 1, so their follow-up comes up on its own.
- New dependency: `segno` (draws the QR codes on the Mac, no network). The usual update step installs it.
- Website: new page `/welcome/` (not in the menu or sitemap, not indexed by search engines), using the same Formspree form.

## 0.3.0 (2026-11-01)

Everything from the open pull requests, merged together: website quote form, instant lead follow-up, pricing check, Google review reminders, rough range for new leads, Scorecard, QuickBooks Send estimate, email worker, Yelp/Houzz links, New homeowners, Leads page and Marketing page.

- Website quote requests that give only a phone number now land in To Review as leads (before, a lead needed an email).
  A "Text the reply" button opens the drafted reply in Messages.
- Website leads show where the person found Nick (Google, Nextdoor, Facebook...). The site passes this along by itself.
- A quote sent from the person's own mail app replies to their address.
- An estimate with no answer after 7 days gets a polite follow-up note on the job page, ready to open in Mail or Messages.
  After 21 days the note becomes a last, no-pressure check-in. No prices, nothing sent automatically.
- Website form through Formspree (2026-10-18): the tool now reads Formspree's notification emails whichever way they lay
  out the fields (value under its label, or in a table), and the reply goes to the person, not to Formspree. The Safe at
  Home list form sends one field per line like the quote form, and the site build wires every form, not only the quote
  form, when `FORMSPREE_URL` is set. Before Formspree is set up nothing changes: the form still opens an email.
- Faster lead replies (2026-10-20): email is checked every 10 minutes instead of 30 (re-run the installer to update the
  background check). A new Setup switch, *Thank new customers right away*, emails a short fixed thank-you to a website
  request with an email address within minutes, from Nick's Gmail with a copy to him. It is **off until he turns it on**.
  Nick's own reply with visit times still waits in To Review. A lead turned job with no estimate after 7 days gets a
  check-in note on the job page (Open in Mail / Text it), and a last one after 21 days.
- 330 tests pass.

- Pricing check before you send. The Send screen for an estimate now shows the labor rate per crew-hour (worked out from the Crew and Duration lines, nothing new to type) and any pricing warnings, with a "Change the price first" button. It never stops you sending.
- A suggested price. When labor is under the target rate (Pricing page, $72 a crew-hour by default) or the materials markup is under the industry-standard 43% (about a 30% gross margin; change it on the Pricing page), the estimate page and the Send screen say what the job would be at those numbers and how many dollars more that is.
- Materials with no markup at all are now a red flag, not a gentle note.

- Google reviews: after you mark a review request sent, a short, no-pressure reminder comes back to Follow-ups a week later. Press "They left a review" and it goes away. A job with a phone number gets a "Send as a text" button that opens Messages with the note already written.
- Until your Google review link is on the Setup page, Follow-ups and Setup say so plainly, and requests ask the client to reply with a few words. Add the link later and drafts already written pick it up.

- Rough range for new leads. Every new-lead card in To Review now has a yellow box, for you only: a rough price range ("$15,500 to $32,000"), what kind of job it looks like, and up to six things to ask or check at the visit. If they sent a photo, the photo program says what it shows. The range is worked out in plain code at your Pricing page rates ($65-72 a crew-hour and the materials markup); once you have two or more past estimates of the same kind with crew and days filled in, it uses those jobs' hours repriced at those rates. It is never put in the reply and never sent. After "Start estimate" it stays on the job page and the estimate page, and the job type is filled in. Works with the AI off (word matching and a standard question list). The starting hours and materials per kind of job are drafts in `rsc/ballpark.py` for Nick to adjust.

- New Scorecard page (Money, Scorecard): one screen that shows whether attention is turning into paid jobs. This week's new leads, estimates sent, jobs won, money in, the win rate over 90 days, and labor dollars per crew-hour against the $65 floor and $72 target, then the last 8 weeks side by side and which lead sources (Google, Nextdoor, TikTok, referrals...) turned into signed work. It counts only what's already in the app, so there's nothing new to type. The source is read from the job notes, which the website form fills in ("Found us: nextdoor"). Estimates priced under the floor are listed with links. Website visits, TikTok views, Google profile calls and ad spend are shown as "not connected yet" rather than guessed.
- The Monday report has a short "Leads and sales" section with the same numbers.

- QuickBooks: new **Send estimate** button on the QuickBooks page (direct connection only). It puts a job's estimate into QuickBooks with one line per payment on the schedule, each line starting with its Payment ID (for example "1002-SMI-3: Phase 3 (When Phase 3 is complete)"). The estimate number is the Job ID (1002-SMI). A signed change order goes in as its own estimate (1002-SMI-CO1), so the original stays as signed. Pressing twice never makes a second copy. Once the client signs, mark it Accepted in QuickBooks and make each phase's invoice from it, or keep using Send invoice. Nothing is sent until you press the button. Tested only against a stand-in for QuickBooks: try it on the sandbox company first.

- New page: **New homeowners** (under Jobs). Once a month it reads the public property records and lists people who just bought a house in your towns. In Saratoga County that's the county's parcel map (owner and deed year, no price); in Queensbury and Glens Falls it's Warren County's (with the sale price, a few months behind). The state's parcel data adds the year built, value and ZIP. Each house gets a grade (A best fit) from its age, value, how recently it sold and the town. Companies, banks and new builds are left out.
- Pick how many letters to send this time (best first), then "Print these letters" (one welcome letter per page, about the quality of the work, no prices), "Download the mailing list" (CSV for labels or a print shop) and "I mailed these", so nobody gets two letters. "Don't mail" takes one house off. The letter text can be changed on the same page.
- Mail only: no phone numbers, no calls or texts, nothing sent for you. The check runs in the background (5 to 10 minutes) and the installer adds a monthly check on the 2nd. Command line: `rsc new-owners --check --csv list.csv`.

- New **Leads** page (sidebar, under Jobs). Every open lead gets a grade, A, B, C or Pass, worked out in plain code from what the homeowner wrote: the kind of job (bathrooms, kitchens, porch enclosures, built-ins and restoration count most), any budget, how soon, the town, and whether they left a phone and an email. Each grade lists its reasons, and the best leads are at the top with the next thing to do ("Call today" for an A).
- The page knows when the crew is booked: you set how many jobs the crew can run at once (2 to start), and it counts the Signed and In Progress jobs. When booked, good leads are told to get a start date instead of being let go.

- New Marketing page (sidebar, under "Getting work").
  - **Post about a job.** Pick a finished or underway job (optional), type or speak one line about the work, and the assistant drafts a TikTok caption, a Facebook post and a Nextdoor post. The client's name becomes "the homeowners". Street addresses are removed, and so are whole sentences with a phone number, an email, a price, or a claim like "licensed", "insured" or "warranty". Only the town is kept. TikTok gets hashtags, and Facebook and Nextdoor get the website. If the assistant is off, plain wording is used. Each draft has Copy buttons and the job's site photos. Press "Posted" when it's up. Nothing is posted from the app.
  - **Posting schedule**, one line everyone can see (the TikTok ad times by default).
  - **Where you show up online:** website, Google, Yelp, Houzz, Nextdoor, TikTok, Facebook and business email. Each shows its link, whether it's Live, To fix or Not set up, and what still needs fixing, plus the exact name, phone and website every listing should match. The app never visits those sites.
- Monday report: a MARKETING section with drafts waiting, days since the last job post, jobs never posted about, and listings still to fix.
- (0.2.8 is used by other open changes; whichever merges last takes the next number.)

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
