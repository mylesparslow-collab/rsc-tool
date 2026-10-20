import { test } from "node:test";
import assert from "node:assert/strict";
import PostalMime from "postal-mime";
import { findLead, formFields, leadHeader, summarySubject, summaryText } from "../src/lead.js";
import { handleEmail, PARSE_LIMIT } from "../src/handler.js";
import { plainEmail } from "../src/mime.js";

const none = { get: () => null };
const site = "Hello, this is Jane Smith. I’m planning a kitchen remodel in Wilton, as soon as possible. Old cabinets. Found you through Facebook.";

test("website form, labels and values on one line", () => {
  const lead = findLead({
    from: { name: "Formspree", address: "noreply@formspree.io" }, to: "nick@rscrafters.com",
    subject: "Quote request from the website", headers: none,
    text: `Name: Jane Smith\nPhone: 518 555 0142\nTown: Wilton\nSource: Facebook\nMessage: ${site}\n\nSubmitted at 3:02pm\nUnsubscribe from Formspree emails`,
  });
  assert.equal(lead.name, "Jane Smith");
  assert.equal(lead.phone, "(518) 555-0142");
  assert.equal(lead.town, "Wilton");
  assert.equal(lead.job, "Kitchen");
  assert.equal(lead.message, site);
  assert.equal(lead.source, "Website quote form (found us through Facebook)");
});

test("website form, each value on the line after its label (and an email instead of a phone)", () => {
  const lead = findLead({
    from: { address: "submissions@formspree.io" }, subject: "New submission", headers: none,
    text: "name:\nBob Jones\n\nemail:\nbob@example.com\n\ntown:\n\nsource:\nwebsite\n\nmessage:\nHello, this is Bob. I’m planning a deck or stairs project, next season.\nThe old one is rotting.\n\n---\nformspree.io",
  });
  assert.equal(lead.name, "Bob Jones");
  assert.equal(lead.email, "bob@example.com");
  assert.equal(lead.phone, "");
  assert.equal(lead.town, "");
  assert.equal(lead.job, "Deck / stairs");
  assert.match(lead.message, /The old one is rotting\.$/);
  assert.equal(lead.source, "Website quote form");
});

test("website form sent as HTML only", () => {
  const lead = findLead({
    from: { address: "noreply@formspree.io" }, subject: "Quote request from the website", headers: none, text: "",
    html: "<table><tr><td><b>name</b></td><td>Ann Lee</td></tr><tr><td>phone</td><td>(518) 555-0199</td></tr>" +
      "<tr><td>message</td><td>Hello, this is Ann. I&rsquo;m planning a bathroom remodel in Malta.</td></tr></table>",
  });
  assert.equal(lead.name, "Ann Lee");
  assert.equal(lead.phone, "(518) 555-0199");
  assert.equal(lead.town, "Malta");
  assert.equal(lead.job, "Bathroom");
});

test("a person writing directly about a job", () => {
  const lead = findLead({
    from: { name: "Pat Okafor", address: "Pat.Okafor@example.com" }, to: "inquiries@rscrafters.com",
    subject: "Kitchen remodel estimate?", headers: none,
    text: "Hi Nick, a neighbor recommended you. We'd like an estimate to redo our kitchen at 12 Maple Ave, Wilton.\nCall me at 518-555-0142. Thanks, Pat\n\n-- \nPat Okafor\n555 999 1234",
  });
  assert.equal(lead.name, "Pat Okafor");
  assert.equal(lead.email, "pat.okafor@example.com");
  assert.equal(lead.phone, "(518) 555-0142");
  assert.equal(lead.town, "Wilton");
  assert.equal(lead.job, "Kitchen");
  assert.equal(lead.source, "Email to inquiries@rscrafters.com");
  assert.doesNotMatch(lead.message, /999/);
});

test("newsletters, receipts and plain chat are not leads", () => {
  const list = { get: (n) => (n === "list-unsubscribe" ? "<mailto:x@y.com>" : null) };
  assert.equal(findLead({ from: { address: "deals@homedepot.com" }, subject: "Kitchen cabinets on sale", text: "Save on cabinets", headers: list }), null);
  assert.equal(findLead({ from: { address: "no-reply@lowes.com" }, subject: "Your receipt", text: "Deck screws $12", headers: none }), null);
  assert.equal(findLead({ from: { address: "friend@example.com" }, subject: "dinner sunday?", text: "Are you free?", headers: none }), null);
  assert.equal(findLead({ from: { address: "nick@rscrafters.com" }, subject: "deck", text: "deck", headers: none }), null);
});

test("summary and header", () => {
  const lead = { name: "José Ruiz", phone: "(518) 555-0142", email: "", town: "Malta", job: "Bathroom", message: "Tub to shower", source: "Website quote form" };
  assert.equal(summarySubject(lead), "New lead: Bathroom - José Ruiz (Malta)");
  const body = summaryText(lead, { subject: "Quote request from the website", to: "nick@rscrafters.com" });
  assert.match(body, /Phone: +\(518\) 555-0142/);
  assert.match(body, /Email: +\(not given\)/);
  assert.equal(leadHeader(lead), "yes; Bathroom; Jose Ruiz; (518) 555-0142; Malta");
});

test("summary email is valid MIME that reads back the same", async () => {
  const raw = plainEmail({ from: "leads@rscrafters.com", fromName: "RSC lead alert", to: "me@example.com", subject: "New lead: Deck – Zoë", text: "Línea 1\nLine 2" });
  const back = await PostalMime.parse(raw);
  assert.equal(back.subject, "New lead: Deck – Zoë");
  assert.equal(back.text.trim(), "Línea 1\nLine 2");
  assert.equal(back.from.address, "leads@rscrafters.com");
  assert.match(raw, /^Message-ID: <[\w-]+@rscrafters\.com>$/m);
});

function fakeMessage(raw, { failForwardTo = null } = {}) {
  const forwarded = [];
  const headerLines = raw.split("\r\n\r\n")[0].split("\r\n");
  const headers = new Headers(headerLines.map((l) => [l.slice(0, l.indexOf(":")), l.slice(l.indexOf(":") + 1).trim()]));
  return {
    from: "sender@example.com", to: "nick@rscrafters.com", rawSize: raw.length, headers, forwarded,
    raw: new Response(raw).body,
    async forward(to, h) {
      if (to === failForwardTo) throw new Error("not verified");
      forwarded.push({ to, lead: h.get("X-RSC-Lead") });
    },
  };
}
const env = { FORWARD_TO: "nick@example.com", COPY_TO: "copy@example.com", LEAD_SUMMARY_FROM: "leads@rscrafters.com", LEAD_SUMMARY_TO: "copy@example.com" };
const quiet = { error: () => {} };
class FakeEmailMessage { constructor(from, to, raw) { Object.assign(this, { from, to, raw }); } }
const deps = (extra = {}) => ({ parse: (r) => PostalMime.parse(r), EmailMessage: FakeEmailMessage, log: quiet, ...extra });

test("worker: a lead goes to Nick and the copy with X-RSC-Lead, plus one summary", async () => {
  const sent = [];
  const raw = "From: Pat <pat@example.com>\r\nTo: nick@rscrafters.com\r\nSubject: Bathroom quote\r\nContent-Type: text/plain\r\n\r\nCould you quote a new bathroom in Malta? 518-555-0142\r\n";
  const msg = fakeMessage(raw);
  await handleEmail(msg, { ...env, LEADS: { send: async (m) => sent.push(m) } }, deps());
  assert.deepEqual(msg.forwarded.map((f) => f.to), ["nick@example.com", "copy@example.com"]);
  assert.ok(msg.forwarded.every((f) => f.lead.startsWith("yes; Bathroom; Pat")));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].to, "copy@example.com");
  assert.match((await PostalMime.parse(sent[0].raw)).subject, /^New lead: Bathroom - Pat \(Malta\)$/);
});

test("worker: ordinary mail is forwarded and copied, with no summary", async () => {
  const sent = [];
  const raw = "From: Friend <f@example.com>\r\nTo: nick@rscrafters.com\r\nSubject: hi\r\n\r\nSee you Sunday\r\n";
  const msg = fakeMessage(raw);
  await handleEmail(msg, { ...env, LEADS: { send: async (m) => sent.push(m) } }, deps());
  assert.deepEqual(msg.forwarded, [{ to: "nick@example.com", lead: null }, { to: "copy@example.com", lead: null }]);
  assert.equal(sent.length, 0);
});

test("worker: Nick still gets the email when reading it, the copy or the summary fails", async () => {
  const raw = "From: Pat <pat@example.com>\r\nSubject: deck\r\n\r\nNew deck please\r\n";
  const msg = fakeMessage(raw, { failForwardTo: "copy@example.com" });
  const out = await handleEmail(msg, { ...env, LEADS: { send: async () => { throw new Error("nope"); } } }, deps());
  assert.deepEqual(msg.forwarded.map((f) => f.to), ["nick@example.com"]);
  assert.deepEqual(out.sent, [["copy", "rejected"], ["lead summary", "rejected"]]);

  const msg2 = fakeMessage(raw);
  await handleEmail(msg2, env, deps({ parse: async () => { throw new Error("bad mime"); } }));
  assert.deepEqual(msg2.forwarded, [{ to: "nick@example.com", lead: null }, { to: "copy@example.com", lead: null }]);
});

test("worker: big emails are passed on without being read", async () => {
  let read = false;
  const msg = fakeMessage("From: a@example.com\r\nSubject: photos of my deck\r\n\r\nx\r\n");
  msg.rawSize = PARSE_LIMIT + 1;
  await handleEmail(msg, env, deps({ parse: async () => { read = true; return {}; } }));
  assert.equal(read, false);
  assert.equal(msg.forwarded.length, 2);
});

test("worker: if Nick's forward fails, the error is not swallowed", async () => {
  const msg = fakeMessage("From: a@example.com\r\nSubject: hi\r\n\r\nx\r\n", { failForwardTo: "nick@example.com" });
  await assert.rejects(handleEmail(msg, env, deps()), /not verified/);
});
