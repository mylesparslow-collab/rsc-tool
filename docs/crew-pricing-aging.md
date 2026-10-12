# Pricing checks, crew, and aging-in-place

All of this is built from the market, crew and aging-in-place research reports. Every number is a starting point Nick can change.

## Pricing (Pricing page, and a card on every estimate)
- Labor per crew-hour = labor price / (people x 8 hours x days). People and days are read from the estimate's own "crew" and "duration" lines ("1 general contractor, 1 skilled laborer", "9-11 days on-site"), so nobody types anything new. Part-time counts as half.
- Warns when labor is under **$65** a crew-hour (never go below), notes when under **$72** (the target). Delano worked out to about $31 and Hartwell about $53 in the research.
- Estimated gross margin counts crew time at **$43** an hour (a carpenter's wage plus taxes and insurance). Goal **30%**.
- New estimates start with a **43%** markup on materials (cost x 1.43) instead of 20%. Existing estimates are not changed.
- Warns on jobs under **$500**.
- The same warnings appear under "Please check these" when the assistant drafts an estimate, on the Pricing page, and in the Monday report ("Priced too low").
- Once logged crew hours pass the guess, the real hours are used.

## Contract
Section 18 is a **placeholder** for the New York GBL section 771 notices: how advance payments are held (escrow or bond), the 3-business-day right to cancel, and a mechanic's lien notice. It is flagged in the contract's open items. A New York attorney must supply the exact wording before a client sees it. This is not legal advice.

## Crew page
- **Log hours** by typing or speaking: "Tue Mike 8, Dave 6 on Delano". The local model reads it; the app checks names, dates, jobs and hours (0-16) before saving, and a plain pattern reader works if the model is off. Unknown people are added as helpers; set their pay afterwards.
- Hours x pay (plus 18% payroll cost for employees) count as labor cost in **Job margins**. **Log either a payment as an expense or the hours, not both**, or the cost counts twice.
- **Insurance certificates**: photo or PDF of the certificate; the vision model reads the insurer and expiry. Warnings 30 days before expiry, when expired, and when a subcontractor has hours logged but no current certificate. They show on Home, the Crew tab badge and the Monday report.
- **What would payroll cost?** A planning calculator (FICA, workers comp about $8 per $100, NY unemployment, federal unemployment, disability/PFL, payroll service). 3 workers at $28 x 1,800 hours comes out near $26,600 a year, about $4.93 on top of every worked hour. Not a quote.
- Before putting anyone on payroll, ask what Nick does now. Whether workers are paid by hand is not confirmed.

## Aging in place
- Job type "Aging in place" and four estimate templates: safety fixes, ramp and entry, accessible bathroom, first-floor suite. Measurements in the steps (grab bars 33-36 in, door 32 in clear, ramp 1:12 with 5x5 ft landings, rails 34-38 in) are the common ADA / ANSI figures; confirm with the town and the client's therapist.
- **Safety assessment** (button on every job): say what you saw on the walk-through; the model picks fixes from the price list, the code adds the price ranges (national ranges from the report), and you can print a client sheet. Suggested fee $150-250, credited toward jobs over $2,500.
- Nick has no accessibility experience yet. The report's advice: take the CAPS classes, start with grab bars, rails, levers, a wider door and a wood ramp, and do the first curbless shower with training or an experienced tile sub.

## Health, backups and updates
- Setup page has a **Health check**; in Terminal run `rsc doctor`.
- A copy of the database is saved every day the app runs (last 30 kept) in `~/RSC/backups`.
- Update: unzip the new version over the old folder, then double-click Install RSC again. The installer keeps data, settings and the Gmail password.
- If the installer stops, send Myles `~/RSC/install.log`.
- `Uninstall RSC.command` stops the background jobs and removes the Desktop icon; it never touches your data.

## What's next, crew brief and playbook
- **What's next** (Home, and at the top of every job): one plain next step per job: write the estimate, check the labor price, send it, follow up after 7 days, set up payments, invoice payment 1, log receipts and hours, next invoice, mark Complete, ask for the review. A new install with no jobs shows a short welcome with the first steps.
- **Crew brief** (button on every job with an estimate): a one-page printable checklist for the lead carpenter. Before-you-start items, every step as a checkbox, inspections, materials, what is not included (anything else is a change order), what the client still has to decide, and when to tell Nick to invoice.
- **Playbook** (Jobs page, "Playbook" button): how RSC builds each kind of job, assembled from Nick's own estimates and scope-of-work steps (usual crew, labor, phases and steps, how many jobs used each step). It improves with every estimate.
- **Safety assessment** is now a room-by-room checklist (entry, stairs and halls, bathroom, bedroom and kitchen) with photos per room. Ticks become priced items; "anything else" can still be typed or spoken.

## Daily work sheet for the crew
- Every weekday at 6 AM the app emails a short sheet: for each job In Progress, the rest of the current phase (up to 8 steps), who has worked on it lately, the client's address and phone, what to call in for inspection, materials to have on site before a job starts, and a note from Nick for the day. Jobs that are Signed but not started show under "Coming up". Nothing is sent when no job is in progress.
- It goes to everyone in "Also send the daily sheet to" on the Setup page plus every active crew member who has an email on the Crew page.
- The **Today** tab shows the same sheet. Tick a step when it's done and the next sheet moves on; add a note for the crew ("Homeowner home until noon"). "All steps" on a job (the Progress button) lets you fix any step. "Email this sheet now" sends it on demand. Terminal: `rsc daily-sheet` (shows it), `rsc daily-sheet --send`.
- To let laborers tick steps from a phone they need the app on the home Wi-Fi with a PIN (`access_pin` in config.toml); otherwise the email is read-only.
- The 6 AM job is installed by the installer (Install RSC again after updating).

## Round 3: money owed, client updates, the week, website leads, branding

**Money owed** (the *Owed* tab). Every invoice marked sent and not yet paid, grouped by age (under 14 days, 14–29, 30–59, 60+). An invoice past the payment terms (14 days) gets a *Write a reminder* button. The note is friendly under 30 days, firm to 60, direct after that; it always states the invoice number, amount and date and never mentions fees or lawyers. It opens in Mail (or copy it). *I sent it* hides that invoice for a week. Home shows a card when something is late and the weekly report has a "Late" line.

**Client update** (job page, *Client update*). Add site photos, press *Write this week's update*. It lists the steps finished in the last 7 days, what is next and the percent done, then opens in Mail for the client. Photos can't be attached by a mail link, so drag them from the page into the message. Works without the model.

**The week** (*Week* tab). Type who is where in your own words: `Mon-Wed Delano Mike Dave; Thu Hartwell Mike`. Names are matched to the Crew page and jobs by last name or address; anything unclear is reported, not guessed. Someone on two jobs the same day is flagged as double-booked. Logged hours show beside the plan, and today's planned people lead each job on the daily sheet.

**Website and job-application emails.** A contact-form notification (`Name:`, `Email:`, `Phone:`, `Message:` lines) lands in To Review as a lead with a reply already drafted, even if Ollama is off. If the message is about working for you (resume, apply, years of experience…) it becomes a *Job applicant* instead; approving it saves a not-yet-active person on the Crew page, and no job is started. Ordinary emails from applicants are recognised after the model reads them.

**Branding.** Setup → *Your business* holds the name, short name, owner, legal name, address, phone, email, region, county and tagline. Every page, the estimate/contract/safety-assessment headers, email drafts and model prompts use these. `[business]` in `config.toml` can pre-fill them for a new install.
