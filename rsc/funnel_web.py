"""Leads page (grades, crew capacity, pass along) and Partners page (who Nick trusts with overflow, and the fee ledger)."""
from urllib.parse import quote

from flask import abort, flash, redirect, render_template, request, url_for

from . import books, brand, funnel, prefs


def register(app, cfg, conn):
    @app.get("/leads")
    def leads_page():
        c = conn()
        partners = funnel.list_partners(c)
        ls = funnel.leads(c)
        for j in ls:
            j["partners"] = funnel.matches(partners, j, j["score"])
        return render_template("leads.html", leads=ls, s=funnel.summary(c), partners=partners)

    @app.post("/leads/slots")
    def leads_slots():
        raw = request.form.get("crew_slots", "").strip()
        if not raw.isdigit() or not 1 <= int(raw) <= 20:
            flash("Put in how many jobs the crew can run at once, like 2.", "error")
        else:
            prefs.put(conn(), "crew_slots", raw)
            flash(f"Saved: the crew can run {raw} job{'s' if raw != '1' else ''} at once.")
        return redirect(url_for("leads_page"))

    @app.post("/leads/<int:number>/consent")
    def lead_consent(number):
        c = conn()
        if not books.get_job(c, number):
            abort(404)
        try:
            funnel.record_consent(c, number, request.form.get("how", ""), request.form.get("note", ""))
            flash("Saved their OK to be passed to a partner.")
        except books.BooksError as exc:
            flash(str(exc), "error")
        return redirect(url_for("leads_page") + f"#lead{number}")

    @app.get("/leads/<int:number>/pass/<int:partner_id>")
    def lead_pass(number, partner_id):
        c = conn()
        try:
            job, partner, ok = funnel.can_pass(c, number, partner_id)
        except books.BooksError as exc:
            flash(str(exc), "error")
            return redirect(url_for("leads_page") + f"#lead{number}")
        owner = prefs.get(c, "owner_name") or brand.current()["owner"]
        d = funnel.handoff_drafts(job, partner, owner)
        mail = {k: f"mailto:{quote(v['to'])}?subject={quote(v['subject'])}&body={quote(v['text'])}" for k, v in d.items()}
        return render_template("lead_pass.html", job=job, partner=partner, consent=ok, drafts=d, mail=mail)

    @app.post("/leads/<int:number>/pass/<int:partner_id>")
    def lead_passed(number, partner_id):
        try:
            funnel.mark_passed(conn(), number, partner_id)
            flash("Logged. The job is marked Passed on and shows in the partner ledger.")
        except books.BooksError as exc:
            flash(str(exc), "error")
        return redirect(url_for("partners_page") + "#ledger")

    @app.get("/partners")
    def partners_page():
        c = conn()
        edit = request.args.get("edit", type=int)
        partners = funnel.list_partners(c)
        current = next((p for p in partners if p["id"] == edit), None)
        return render_template("partners.html", partners=partners, current=current, ledger=funnel.ledger(c))

    @app.post("/partners")
    def partner_save():
        c = conn()
        pid = request.form.get("id", type=int)
        try:
            funnel.save_partner(c, request.form, pid)
            flash("Partner saved.")
        except books.BooksError as exc:
            flash(str(exc), "error")
            return redirect(url_for("partners_page", edit=pid) if pid else url_for("partners_page"))
        return redirect(url_for("partners_page"))

    @app.post("/partners/referral/<int:referral_id>")
    def referral_update(referral_id):
        try:
            funnel.referral_outcome(conn(), referral_id, request.form.get("status", ""), request.form.get("amount", ""))
            flash("Referral updated.")
        except books.BooksError as exc:
            flash(str(exc), "error")
        return redirect(url_for("partners_page") + "#ledger")
