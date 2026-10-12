"""Money owed: invoices waiting for payment, by age, with a reminder drafted for the ones that are late."""
from flask import abort, flash, redirect, render_template, request, url_for

from . import receivables
from .llm import ModelUnavailable


def register(app, cfg, conn, get_model):
    @app.get("/owed")
    def owed_page():
        c = conn()
        rows = receivables.outstanding(c)
        return render_template("owed.html", buckets=receivables.buckets(rows), rows=rows, total=round(sum(r["owed"] for r in rows), 2),
                               terms=receivables.terms(c), drafts={})

    @app.post("/owed/<int:payment_pk>/draft")
    def owed_draft(payment_pk):
        c = conn()
        try:
            model = get_model()
        except ModelUnavailable:
            model = None
        d = receivables.draft(model, c, payment_pk, cfg.business_phone)
        if not d:
            abort(404)
        rows = receivables.outstanding(c)
        return render_template("owed.html", buckets=receivables.buckets(rows), rows=rows, total=round(sum(r["owed"] for r in rows), 2),
                               terms=receivables.terms(c), drafts={payment_pk: d})

    @app.post("/owed/<int:payment_pk>/sent")
    def owed_sent(payment_pk):
        receivables.mark_reminded(conn(), payment_pk, request.form.get("text", ""))
        flash("Marked as reminded. I won't suggest another for a week.")
        return redirect(url_for("owed_page"))
