# rscrafters.com email worker

A small Cloudflare program ("Email Worker") that runs on every email sent to the rscrafters.com addresses it is
attached to (nick@, and ideally inquiries@ and info@). For each email it:

1. **Forwards it to Nick's Gmail** (`FORWARD_TO`, nfparslow@gmail.com), the inbox the RSC tool reads. This always
   happens first; if it fails, Cloudflare reports the email as undelivered rather than losing it.
2. **Sends a copy to Myles** (`COPY_TO`, mzpprojects1@gmail.com). Every email, not just leads.
3. **If it is a lead, sends a short summary** to `LEAD_SUMMARY_TO` (also mzpprojects1@gmail.com) from
   leads@rscrafters.com, with subject like `New lead: Kitchen - Jane Smith (Wilton)` and one line each for name,
   phone, email, town, job type, source and the message.
4. **Marks leads** on both forwarded copies with an `X-RSC-Lead: yes; Kitchen; Jane Smith; (518) 555-0142; Wilton`
   header (and `X-RSC-Lead-Source`), so the RSC tool or a later filter can spot them. Cloudflare can't change the
   email itself, only add `X-` headers.

What counts as a lead (plain rules in `src/lead.js`, no AI): the website quote form (from Formspree, or subject
"Quote request from the website"), or a person writing directly about a job (deck, kitchen, bathroom, estimate, ...).
Newsletters, receipts, no-reply senders and mail from rscrafters.com itself are never leads. If the rules miss
something, nothing is lost: Nick and the copy still get the full email; only the summary is skipped.

Big emails (over 256 KB, usually photos or PDFs) are forwarded and copied without being read, to stay within the
free plan's limits.

It only sees mail coming **in**. Nick's replies go out through Gmail and are not copied.

## Set it up (Myles, in the Cloudflare dashboard)

Do these in order. The worker can only send to addresses verified in Email Routing.

1. **Email Routing must be on**, with nfparslow@gmail.com verified (Nick clicks the Cloudflare verify email; see
   `/mnt/project-files/email/business-email-plan.md`). Until then forwarding to Nick fails.
2. **Verify the copy address.** Cloudflare > rscrafters.com > Email > Email Routing > **Destination addresses** >
   **Add destination address** > `mzpprojects1@gmail.com` > Save. Open the "Verify email address" email Cloudflare
   sends to mzpprojects1@gmail.com and click the link. The list should show it as **Verified**.
3. **Publish the worker** (pick one):
   - **From GitHub (no Mac needed):** Cloudflare > My Profile > **API Tokens** > the token used for the website >
     Edit > **Add more** > Account | **Workers Scripts** | **Edit** > Continue > Update token. (The value of the
     token doesn't change, so the GitHub secret stays as it is.) Then merge the PR, or GitHub > Actions >
     **Email worker** > Run workflow.
   - **From the Mac:** `cd rsc-tool/email-worker && npm ci && npx wrangler deploy` (wrangler is already logged in).
4. **Point the addresses at it.** Cloudflare > rscrafters.com > Email > Email Routing > **Routing rules** >
   nick@rscrafters.com > **Edit** > Action: **Send to a Worker** > Destination: **rscrafters-email** > Save.
   Do the same for inquiries@ and info@ so their mail is copied and checked for leads too.
5. **Website form:** in Formspree (form `xzedwyge` > Settings) set the target email to `inquiries@rscrafters.com`.
   Form leads then pass through the worker: Nick and the RSC tool get them, and the summary comes to Myles.
6. **Test:** from any other account, email nick@rscrafters.com "Could you quote a bathroom in Malta? 518-555-0142".
   Within a minute: the email in Nick's Gmail, a copy in mzpprojects1@gmail.com, and a "New lead: Bathroom" summary.
   Then send something ordinary ("lunch Sunday?"): it should arrive in both inboxes with no summary.
   Problems show in Cloudflare > Workers & Pages > rscrafters-email > **Logs**.

**To undo:** change each routing rule back to Action **Send to an email** > nfparslow@gmail.com. Nothing else changes.
**To stop the copies:** set `COPY_TO = ""` in `wrangler.toml` and publish again (same for `LEAD_SUMMARY_TO`).
Changing an address means editing `wrangler.toml` (and `allowed_destination_addresses` for the summary), verifying
the new address in Destination addresses, and publishing again.

## Develop

```
cd email-worker
npm ci
npm test                       # node's built-in test runner, no Cloudflare account needed
npx wrangler deploy --dry-run  # checks it bundles
```

`src/index.js` wires Cloudflare's pieces to `src/handler.js` (what happens to each email); `src/lead.js` finds the
lead; `src/mime.js` builds the summary email. The GitHub Action `.github/workflows/email-worker.yml` runs the tests on
every PR and publishes on merge.
