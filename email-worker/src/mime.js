// A small plain-text email in MIME form, for the lead summary. Kept here (not a library) so the Worker has one dependency.

function encodeWord(s) {
  return /^[\x20-\x7e]*$/.test(s) ? s : `=?UTF-8?B?${base64(s)}?=`;
}

function base64(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

export function plainEmail({ from, fromName, to, subject, text, date = new Date(), id = crypto.randomUUID() }) {
  const domain = from.split("@")[1];
  const body = base64(text).replace(/.{1,76}/g, "$&\r\n");
  return [
    `From: ${fromName ? `${encodeWord(fromName)} ` : ""}<${from}>`,
    `To: <${to}>`,
    `Subject: ${encodeWord(subject.replace(/[\r\n]+/g, " "))}`,
    `Date: ${date.toUTCString()}`,
    `Message-ID: <${id}@${domain}>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: base64",
    "",
    body,
  ].join("\r\n");
}
