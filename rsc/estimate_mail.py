"""The estimate as a PDF, plus the plain-code wording of the email that goes with it.

The PDF is drawn from the same numbers as the printable scope of work (`sow.html`). The message is plain code,
not a model. Nothing here sends anything by itself.
"""
import io
import smtplib
from email.message import EmailMessage
from xml.sax.saxutils import escape

from . import brand

GREEN = "#2F5D46"


def money(x) -> str:
    return f"${float(x or 0):,.2f}"


def filename(job: dict) -> str:
    return f"Estimate-{job['job_id']}.pdf"


def default_subject(job: dict) -> str:
    return f"Your estimate from {brand.current()['name']} ({job['job_id']})"


def default_body(job: dict, total: float) -> str:
    b = brand.current()
    first = (job.get("first_name") or job.get("last_name") or "").strip()
    return (f"Hi {first},\n\n"
            f"Thank you for the chance to work on your project. Attached is the scope of work and estimate "
            f"for {job.get('address') or 'your project'}. The total is {money(total)}, and the payment schedule is at the end.\n\n"
            f"Please read it over and let me know if you have any questions or want anything changed. "
            f"I'm happy to walk through it with you.\n\n"
            f"{b['owner']}\n{b['name']}\n{b['phone']}")


def _clean(text) -> str:
    """The built-in PDF fonts know Windows Latin-1 only; anything else becomes a plain stand-in."""
    return str(text or "").encode("cp1252", "replace").decode("cp1252")


def build_pdf(ctx: dict) -> bytes:
    """ctx is the printable scope of work's data (see workflow._sow_context)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    b, job, est, totals = brand.current(), ctx["job"], ctx["est"], ctx["totals"]
    green = colors.HexColor(GREEN)
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=13.5)
    muted = ParagraphStyle("muted", parent=base, textColor=colors.HexColor("#555555"), fontSize=9)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=12, spaceAfter=3, textColor=green)
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10, spaceBefore=8, spaceAfter=2)
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19, alignment=1, textColor=green)
    heading = ParagraphStyle("heading", parent=title, alignment=0, fontSize=13)
    center = ParagraphStyle("center", parent=muted, alignment=1)
    step = ParagraphStyle("step", parent=base, leftIndent=22, firstLineIndent=-22)
    bullet = ParagraphStyle("bullet", parent=base, leftIndent=14, firstLineIndent=-10)
    cell = ParagraphStyle("cell", parent=base, fontSize=9.5, leading=12)
    right = ParagraphStyle("right", parent=cell, alignment=2)
    cell_bold = ParagraphStyle("cell_bold", parent=cell, fontName="Helvetica-Bold")
    right_bold = ParagraphStyle("right_bold", parent=right, fontName="Helvetica-Bold")

    def P(text, style=base):
        return Paragraph(escape(_clean(text)), style)

    def table(rows, widths, header=False, bold_last=False):
        t = Table(rows, colWidths=widths)
        style = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")))
        if bold_last:
            style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEEEEE")))
        t.setStyle(TableStyle(style))
        return t

    def lines(text):
        return [x.strip() for x in (text or "").splitlines() if x.strip()]

    client = f"{job.get('first_name') or ''} {job.get('last_name') or ''}".strip()
    out = [P(b["name"].upper(), title),
           P(f"{b['address']}, {b['city']}  |  {b['email']}  |  {b['phone']}", center),
           HRFlowable(width="100%", thickness=1.5, color=green, spaceBefore=4, spaceAfter=8),
           Paragraph(f"<b>{escape(_clean(client))}</b><br/>{escape(_clean(job.get('address') or ''))}", base),
           Spacer(1, 6), P("SCOPE OF WORK / ESTIMATE", heading),
           P(f"Version {est['version']} - {ctx['version_date']}  |  Job {job['job_id']}", muted)]

    if est.get("project"):
        out.append(P("PROJECT", h2))
        out += [P(x) for x in lines(est["project"])]
    out.append(P("LABOR", h2))
    for i, p in enumerate(ctx["phases"], 1):
        out.append(P(f"PHASE {i} - {p['title'].upper()}", h3))
        out += [P(f"{n}.  {text}", step) for n, text in p["numbered"]]
        if p.get("inspection"):
            out.append(P(f"Inspection: {p['inspection']}", muted))
    if lines(est.get("materials_list")):
        out.append(P(f"MATERIALS - {b['short']}", h2))
        out += [P("- " + x, bullet) for x in lines(est["materials_list"])]
    if est.get("duration") or est.get("crew"):
        out.append(P("SCHEDULE / CREW", h2))
        if est.get("duration"):
            out.append(P(f"Business days on site: {est['duration']}"))
        if est.get("crew"):
            out.append(P(f"Crew: {est['crew']}"))

    fees = [[P("LABOR" + (f" ({est['labor_note']})" if est.get("labor_note") else ""), cell), P(money(est.get("labor")), right)]]
    if est.get("materials"):
        fees.append([P("MATERIALS", cell), P(money(totals["materials_price"]), right)])
    if est.get("windows_doors"):
        fees.append([P("WINDOWS & DOORS", cell), P(money(est["windows_doors"]), right)])
    fees += [[P(o["label"].upper(), cell), P(money(o["amount"]), right)] for o in est.get("others") or []]
    if est.get("debris"):
        fees.append([P("DEBRIS DISPOSAL / DUMP FEES", cell), P(money(est["debris"]), right)])
    fees.append([P("TOTAL FEES", cell_bold), P(money(totals["total"]), right_bold)])
    out.append(KeepTogether([P("FEES", h2), table(fees, [5.2 * inch, 1.8 * inch], bold_last=True)]))

    if ctx.get("payments"):
        rows = [(p["payment_id"], p["description"], p["due_when"], p["amount"]) for p in ctx["payments"]]
    else:
        rows = [(f"{job['job_id']}-{i}", s["description"], s["due_when"], s["amount"]) for i, s in enumerate(ctx["schedule"], 1)]
    pay = [[P("Payment", cell_bold), P("For", cell_bold), P("Due", cell_bold), P("Amount", right_bold)]]
    pay += [[P(a, cell), P(what, cell), P(due, cell), P(money(amount), right)] for a, what, due, amount in rows]
    out.append(KeepTogether([P("PAYMENT SCHEDULE", h2), table(pay, [1.1 * inch, 3.0 * inch, 1.7 * inch, 1.2 * inch], header=True)]))

    for title_, key in (("Labor not included", "labor_not_included"), ("Materials not included", "materials_not_included"),
                        ("Open decisions for the client", "open_decisions")):
        if lines(est.get(key)):
            out.append(P(title_, h2))
            out += [P("- " + x, bullet) for x in lines(est[key])]
    out += [Spacer(1, 10), P("Changes to this scope or price require a written, signed Change Order.", muted)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.7 * inch,
                      bottomMargin=0.7 * inch, title=_clean(f"Estimate {job['job_id']}"), author=_clean(b["name"])).build(out)
    return buf.getvalue()


def send(address: str, password: str, to: str, subject: str, body: str, pdf: bytes, name: str,
         host: str = "smtp.gmail.com") -> None:
    """Send from Nick's Gmail with the PDF attached, only ever called when he presses Send. A copy goes to him."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = address, to, subject
    msg["Bcc"] = address
    msg.set_content(body)
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=name)
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(address, password)
        s.send_message(msg)


def selftest() -> bool:
    """Used when building RSC.app: can the PDF library draw a page from inside the packaged app?"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(72, 720, "RSC")
        c.save()
        return buf.getvalue().startswith(b"%PDF")
    except Exception:
        return False
