// What happens to each email that reaches the Worker. index.js wires in Cloudflare's EmailMessage and the
// postal-mime parser; the tests pass fakes, so this file runs in plain Node too.
import { findLead, leadHeader, summarySubject, summaryText } from "./lead.js";
import { plainEmail } from "./mime.js";

// Lead emails are a few KB. Bigger mail (photos, PDFs) is passed on without being read, to stay inside the
// free plan's CPU limit.
export const PARSE_LIMIT = 256 * 1024;

export async function handleEmail(message, env, { parse, EmailMessage, log = console }) {
  let lead = null;
  let mail = null;
  if (message.rawSize <= PARSE_LIMIT) {
    try {
      const parsed = await parse(message.raw);
      mail = {
        from: parsed.from || { address: message.from },
        to: message.to,
        subject: parsed.subject || message.headers.get("subject") || "",
        text: parsed.text || "",
        html: parsed.html || "",
        replyTo: parsed.replyTo?.[0]?.address || "",
        headers: message.headers,
      };
      lead = findLead(mail);
    } catch (err) {
      log.error("could not read the email for lead details:", err?.message || err);
    }
  }

  const headers = new Headers();
  headers.set("X-RSC-Worker", "rscrafters-email");
  if (lead) {
    headers.set("X-RSC-Lead", leadHeader(lead));
    headers.set("X-RSC-Lead-Source", lead.source.replace(/[^\x20-\x7e]/g, "").slice(0, 120));
  }

  // Nick's copy comes first and must not fail quietly: if it throws, Cloudflare reports the email as not delivered.
  await message.forward(env.FORWARD_TO, headers);

  const extras = [];
  if (env.COPY_TO) extras.push(["copy", () => message.forward(env.COPY_TO, headers)]);
  if (lead && env.LEADS && env.LEAD_SUMMARY_TO) {
    extras.push(["lead summary", () => {
      const raw = plainEmail({
        from: env.LEAD_SUMMARY_FROM,
        fromName: "RSC lead alert",
        to: env.LEAD_SUMMARY_TO,
        subject: summarySubject(lead),
        text: summaryText(lead, mail),
      });
      return env.LEADS.send(new EmailMessage(env.LEAD_SUMMARY_FROM, env.LEAD_SUMMARY_TO, raw));
    }]);
  }
  const results = await Promise.allSettled(extras.map(([, run]) => run()));
  results.forEach((r, i) => {
    if (r.status === "rejected") log.error(`${extras[i][0]} failed:`, r.reason?.message || r.reason);
  });
  return { lead, sent: extras.map(([name], i) => [name, results[i].status]) };
}
