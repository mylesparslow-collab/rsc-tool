"""Read-only Gmail access over IMAP.

The mailbox is opened read-only and messages are fetched with BODY.PEEK, so the
tool never marks anything read, moves, labels, deletes or sends mail.
"""
import email
import html
import imaplib
import io
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime, parseaddr

MAX_BODY_CHARS = 8000
MAX_PDF_PAGES = 5
MAX_PHOTOS = 6


@dataclass
class Mail:
    message_id: str
    mailbox: str
    sender: str
    sender_name: str
    subject: str
    received_at: str | None
    body: str
    attachment_text: str = ""
    attachment_names: list[str] = field(default_factory=list)
    attachment_images: list[bytes] = field(default_factory=list)   # photos (receipts) attached to the email
    documents: list[tuple[str, str]] = field(default_factory=list)  # (file name, text) for each PDF with readable text

    def text_for_model(self) -> str:
        parts = [f"From: {self.sender_name} <{self.sender}>", f"Date: {self.received_at or 'unknown'}",
                 f"Subject: {self.subject}", "", self.body.strip()]
        if self.attachment_text:
            parts += ["", "--- Attached PDF text ---", self.attachment_text.strip()]
        return "\n".join(parts)[:MAX_BODY_CHARS]

    def split_documents(self) -> list["Mail"]:
        """One copy of this email per PDF when it carries two or more, so each is read (and reviewed) on its own."""
        if len(self.documents) < 2:
            return [self]
        short_body = self.body.strip()[:1500]
        return [replace(self, body=short_body, attachment_text=text, documents=[(name, text)])
                for name, text in self.documents]


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", markup)
    markup = re.sub(r"(?i)</t[dh]>", "\t", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"[ \xa0]+", " ", text)
    text = re.sub(r" ?\t[ \t]*", "  ", text)  # table cells stay two spaces apart, so "name  Jane" reads as a form field
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
    except Exception:
        return ""


def parse(raw: bytes, mailbox: str = "INBOX") -> Mail:
    msg: EmailMessage = email.message_from_bytes(raw, policy=default_policy)  # type: ignore[assignment]
    name, addr = parseaddr(str(msg.get("From", "")))
    try:
        received = parsedate_to_datetime(str(msg["Date"])).date().isoformat() if msg["Date"] else None
    except (TypeError, ValueError):
        received = None

    plain, markup, pdf_text, names, images, docs = "", "", [], [], [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        filename = part.get_filename()
        if filename:
            names.append(filename)
            if ctype == "application/pdf" or filename.lower().endswith(".pdf"):
                text = _pdf_text(part.get_payload(decode=True) or b"")
                pdf_text.append(text)
                if text.strip():
                    docs.append((filename, text))
            elif ctype.startswith("image/") and len(images) < MAX_PHOTOS:
                blob = part.get_payload(decode=True) or b""
                if 5_000 < len(blob) <= 8 * 1024 * 1024:  # skip tiny logos and tracking pixels
                    images.append(blob)
            continue
        if ctype == "text/plain" and not plain:
            plain = part.get_content()
        elif ctype == "text/html" and not markup:
            markup = part.get_content()

    body = plain if plain.strip() else _html_to_text(markup)
    message_id = str(msg.get("Message-ID", "")).strip() or f"<no-id:{addr}:{msg.get('Date')}:{msg.get('Subject')}>"
    return Mail(message_id=message_id, mailbox=mailbox, sender=addr.lower(), sender_name=name,
                subject=str(msg.get("Subject", "")), received_at=received, body=body,
                attachment_text="\n".join(t for t in pdf_text if t), attachment_names=names,
                attachment_images=images, documents=docs)


class GmailReader:
    def __init__(self, address: str, password: str, host: str = "imap.gmail.com"):
        self.address, self.password, self.host = address, password, host

    def check(self) -> None:
        """Log in and out, to find out whether the address and app password work."""
        with imaplib.IMAP4_SSL(self.host) as imap:
            imap.login(self.address, self.password)

    def fetch_since(self, mailbox: str, since: date, limit: int) -> list[Mail]:
        with imaplib.IMAP4_SSL(self.host) as imap:
            imap.login(self.address, self.password)
            status, _ = imap.select(f'"{mailbox}"', readonly=True)
            if status != "OK":
                raise RuntimeError(f"Could not open mailbox {mailbox}")
            _, data = imap.uid("SEARCH", None, "SINCE", since.strftime("%d-%b-%Y"))
            uids = data[0].split()[-limit:] if data and data[0] else []
            mails = []
            for uid in uids:
                _, msg_data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
                if raw:
                    mails.append(parse(raw, mailbox))
            return mails


def lookback_start(last_run: str | None, first_run_days: int) -> date:
    """IMAP SINCE is day-granular; re-reading a day is harmless because emails are de-duplicated."""
    if last_run:
        return date.fromisoformat(last_run[:10]) - timedelta(days=1)
    return date.today() - timedelta(days=first_run_days)
