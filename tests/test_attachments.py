import email.message

from rsc import books, pipeline
from rsc.mail import parse

from .conftest import FakeModel


def make_pdf(text: str) -> bytes:
    """A tiny one-page PDF with real, extractable text."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)


def two_pdf_mail(body="Here are the two estimates") -> bytes:
    msg = email.message.EmailMessage()
    msg["From"] = "Nick <nick@example.com>"
    msg["To"] = "nfparslow@gmail.com"
    msg["Subject"] = "Estimates for the Smith kitchen"
    msg["Message-ID"] = "<two@x>"
    msg["Date"] = "Wed, 08 Oct 2026 10:00:00 -0400"
    msg.set_content(body)
    msg.add_attachment(make_pdf("Estimate Alpha deck rebuild 4000"), maintype="application", subtype="pdf", filename="alpha.pdf")
    msg.add_attachment(make_pdf("Estimate Bravo bathroom tile 7000"), maintype="application", subtype="pdf", filename="bravo.pdf")
    return msg.as_bytes()


class PerPdfModel(FakeModel):
    """Answers with the amount of whichever estimate it was shown."""
    def extract(self, system, user, schema, images=None):
        self.calls.append(user)
        total = 7000 if "Bravo" in user else 4000 if "Alpha" in user else 0
        return {**self.BLANK, "kind": "expense_receipt", "vendor": "Sub", "date": "2026-10-08",
                "total": total, "description": "estimate", "job_clue": "Smith"}


def test_each_pdf_is_read_separately():
    mail = parse(two_pdf_mail())
    assert [n for n, _ in mail.documents] == ["alpha.pdf", "bravo.pdf"]
    parts = mail.split_documents()
    assert len(parts) == 2
    assert "Alpha" in parts[0].text_for_model() and "Bravo" not in parts[0].text_for_model()


def test_two_pdfs_give_two_review_items(conn, cfg):
    books.create_job(conn, "Smith")
    model = PerPdfModel({})
    report = pipeline.process(conn, cfg, [parse(two_pdf_mail())], model)
    assert len(model.calls) == 2
    assert report.suggestions == 2
    amounts = sorted(s["data"]["amount"] for s in pipeline.pending(conn))
    assert amounts == [4000, 7000]
    assert any("alpha.pdf" in s["match_note"] for s in pipeline.pending(conn))


def test_one_pdf_stays_one_item(conn, cfg):
    msg = email.message.EmailMessage()
    msg["From"] = "Sub <sub@x.com>"
    msg["Subject"] = "Bill for the Smith job"
    msg["Message-ID"] = "<one@x>"
    msg["Date"] = "Wed, 08 Oct 2026 10:00:00 -0400"
    msg.set_content("bill attached")
    msg.add_attachment(make_pdf("Estimate Alpha 4000"), maintype="application", subtype="pdf", filename="a.pdf")
    model = PerPdfModel({})
    pipeline.process(conn, cfg, [parse(msg.as_bytes())], model)
    assert len(model.calls) == 1


def test_pdf_text_counts_for_the_business_check(conn, cfg):
    """An email with a plain subject and body, whose PDF mentions an estimate, is not skipped."""
    from rsc import extract
    msg = email.message.EmailMessage()
    msg["From"] = "Sub <sub@x.com>"
    msg["Subject"] = "see attached"
    msg["Message-ID"] = "<kw@x>"
    msg.set_content("hi")
    msg.add_attachment(make_pdf("Invoice total due 400"), maintype="application", subtype="pdf", filename="scan.pdf")
    mail = parse(msg.as_bytes())
    assert extract.wants_model(mail, ["invoice"], [], "") is None
