// Lead details from an incoming email, by plain rules (no model). Two kinds of lead:
//  - the website quote form (Formspree sends "Name: ...", "Phone: ...", "Town: ...", "Source: ...", "Message: ...")
//  - a person writing straight to nick@ / inquiries@ / info@ about a job
// Anything automated (newsletters, receipts, no-reply senders) is not a lead. When unsure, it is not a lead:
// the email still reaches Nick and the copy still reaches Myles, only the summary is skipped.

const TOWNS = [
  "Saratoga Springs", "Ballston Spa", "Malta", "Wilton", "Greenfield", "Milton", "Gansevoort", "Stillwater",
  "Mechanicville", "Schuylerville", "Corinth", "Clifton Park", "Halfmoon", "Round Lake", "Glens Falls", "Queensbury",
  "Saratoga", "Ballston Lake", "Burnt Hills", "Galway", "Lake George", "Albany", "Schenectady", "Troy", "Niskayuna",
];

// first match wins, so the more specific words come first
const JOBS = [
  ["Porch enclosure / four-season room", /\b(four[- ]season|sun ?room|three[- ]season|porch enclosure|enclos(e|ing) (the |our |a )?porch|screen(ed)? porch)\b/i],
  ["Safety / accessibility", /\b(accessib\w*|aging in place|grab bars?|ramp|walk-?in shower|curbless|wider door\w*|widen\w* door\w*|safe at home|wheelchair|walker)\b/i],
  ["Bathroom", /\b(bath(room)?s?|shower|tub|vanity|tile)\b/i],
  ["Kitchen", /\b(kitchens?|cabinets?|counter ?tops?|backsplash)\b/i],
  ["Deck / stairs", /\b(decks?|decking|stairs?|steps|railings?|porch)\b/i],
  ["Built-ins", /\b(built[- ]?ins?|bookcases?|shelving|mudroom|window seat)\b/i],
  ["Restoration / repair", /\b(restor\w*|rot(ted|ten)?|repair\w*|trim|old house|historic|siding|windows?)\b/i],
  ["Remodel (type not clear)", /\b(remodel\w*|renovat\w*|estimate|quote|contractor|addition|basement)\b/i],
];

const LABELS = {
  name: ["name", "full name", "your name", "pname"],
  email: ["email", "e-mail", "email address", "your email"],
  phone: ["phone", "phone number", "telephone", "mobile", "cell"],
  town: ["town", "city", "ptown", "location"],
  source: ["source", "found us", "how did you hear about us", "referral"],
  message: ["message", "pmsg", "details", "project", "project details", "comments"],
  contact: ["contact", "pcontact", "phone or email"],
};
const LABEL_OF = new Map(Object.entries(LABELS).flatMap(([k, names]) => names.map((n) => [n, k])));
const LINE = /^\s*\**\s*([A-Za-z][A-Za-z _-]{0,40}?)\s*\**\s*:\s*(.*?)\s*$/;
const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/;
const PHONE = /(?:\+?1[\s.-]?)?\(?\b([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})\b/;
const AUTOMATED_FROM = /(no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|bounce|newsletter|marketing@|news@|billing@|receipts?@)/i;
const FORMSPREE = /formspree/i;
const FOOTER = /formspree|unsubscribe|^-{2,}|^_{3,}|^submitted (at|on)\b/i;

/** Text of an HTML part, with table cells turned into "label: value" lines. */
export function htmlToText(html) {
  return (html || "")
    .replace(/<(style|script)[\s\S]*?<\/\1>/gi, "")
    .replace(/<\/t[dh]>\s*<t[dh][^>]*>/gi, ": ")
    .replace(/<br\s*\/?>|<\/(p|div|tr|li|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&#39;|&rsquo;|&#8217;/g, "’").replace(/&quot;/g, '"')
    .replace(/[ \t]+/g, " ");
}

/** "Label: value" fields, where the value may sit on the same line or the next one(s). */
export function formFields(text) {
  const found = {};
  let current = null;
  for (const raw of (text || "").split(/\r?\n/)) {
    const line = raw.trim();
    const m = LINE.exec(line);
    const key = m && LABEL_OF.get(m[1].trim().toLowerCase().replace(/_/g, " "));
    if (key) {
      current = key in found ? null : key;
      if (current) found[key] = m[2];
      continue;
    }
    if (FOOTER.test(line)) current = null;
    if (!line || !current) continue;
    // a value on the line(s) after its label; only the message runs on over several lines
    if (current === "message" || !found[current]) found[current] = found[current] ? `${found[current]} ${line}` : line;
    else current = null;
  }
  for (const k of Object.keys(found)) found[k] = found[k].trim();
  return found;
}

function first(...values) {
  return values.map((v) => (v || "").trim()).find(Boolean) || "";
}

function findTown(text) {
  for (const t of TOWNS) if (new RegExp(`\\b${t.replace(/ /g, "\\s+")}\\b`, "i").test(text)) return t;
  return "";
}

function findJob(text) {
  for (const [label, re] of JOBS) if (re.test(text)) return label;
  return "";
}

function formatPhone(text) {
  const m = PHONE.exec(text || "");
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : "";
}

/** The person's own words from a direct email: drop quoted replies and signatures, keep it short. */
function ownWords(text) {
  const kept = [];
  for (const line of (text || "").split(/\r?\n/)) {
    if (/^\s*>/.test(line)) continue;
    if (/^\s*(--\s*$|On .+wrote:\s*$|Sent from my )/.test(line)) break;
    kept.push(line.trim());
  }
  return kept.join(" ").replace(/\s+/g, " ").trim().slice(0, 600);
}

/**
 * The lead in an email, or null when it isn't one.
 * mail: { from: {name, address}, to, subject, text, html, replyTo, headers: {get(name)} }
 */
export function findLead(mail) {
  const fromAddr = (mail.from?.address || "").toLowerCase();
  const subject = mail.subject || "";
  const text = mail.text || htmlToText(mail.html);
  const header = (n) => (mail.headers?.get?.(n) || "");
  const isForm = FORMSPREE.test(fromAddr) || /^quote request from the website/i.test(subject);

  if (isForm) {
    const f = formFields(text.includes(":") ? text : htmlToText(mail.html));
    const contact = f.contact || "";
    const email = first(EMAIL.exec(f.email || "")?.[0], EMAIL.exec(contact)?.[0], mail.replyTo);
    const phone = formatPhone(first(f.phone, contact));
    const message = first(f.message);
    if (!email && !phone && !message) return null;
    return {
      name: first(f.name),
      email,
      phone,
      town: first(f.town, findTown(message)),
      job: findJob(message) || "Not given",
      message: message.slice(0, 1200),
      source: `Website quote form${f.source && !/^website$/i.test(f.source) ? ` (found us through ${f.source})` : ""}`,
    };
  }

  if (!fromAddr || AUTOMATED_FROM.test(fromAddr) || fromAddr.endsWith("@rscrafters.com")) return null;
  if (header("list-unsubscribe") || header("list-id") || /^(bulk|list|junk|auto_reply)$/i.test(header("precedence"))) return null;
  if (/^auto-(generated|replied)/i.test(header("auto-submitted"))) return null;

  const words = ownWords(text);
  const job = findJob(`${subject} ${words}`);
  if (!job) return null;
  return {
    name: first(mail.from?.name),
    email: fromAddr,
    phone: formatPhone(words),
    town: findTown(`${subject} ${words}`),
    job,
    message: first(words, subject),
    source: `Email to ${(mail.to || "").toLowerCase() || "rscrafters.com"}`,
  };
}

/** The plain-text lead summary, one fact per line. */
export function summaryText(lead, mail) {
  const lines = [
    "New lead from rscrafters.com email",
    "",
    `Name:    ${lead.name || "(not given)"}`,
    `Phone:   ${lead.phone || "(not given)"}`,
    `Email:   ${lead.email || "(not given)"}`,
    `Town:    ${lead.town || "(not given)"}`,
    `Job:     ${lead.job}`,
    `Source:  ${lead.source}`,
    "",
    "Message:",
    lead.message || "(none)",
    "",
    "----",
    `Original subject: ${mail.subject || "(none)"}`,
    `Sent to: ${mail.to || ""}`,
    "The full email went to Nick's Gmail, and a copy came to this inbox.",
    "Found by the rscrafters.com email worker by simple rules, so check the original if something looks off.",
  ];
  return lines.join("\n");
}

export function summarySubject(lead) {
  const who = lead.name || lead.phone || lead.email || "someone";
  return `New lead: ${lead.job} - ${who}${lead.town ? ` (${lead.town})` : ""}`;
}

/** Value for the X-RSC-Lead header on the forwarded email: short and plain ASCII. */
export function leadHeader(lead) {
  const parts = [lead.job, lead.name, lead.phone, lead.town].filter(Boolean).join("; ");
  return `yes; ${parts}`.normalize("NFKD").replace(/[^\x20-\x7e]/g, "").slice(0, 200);
}
