"""Leads page: every open lead with its grade and what to do next, plus the crew's capacity."""
from flask import flash, redirect, render_template, request, url_for

from . import funnel, prefs


def register(app, cfg, conn):
    @app.get("/leads")
    def leads_page():
        c = conn()
        return render_template("leads.html", leads=funnel.leads(c), s=funnel.summary(c))

    @app.post("/leads/slots")
    def leads_slots():
        raw = request.form.get("crew_slots", "").strip()
        if not raw.isdigit() or not 1 <= int(raw) <= 20:
            flash("Put in how many jobs the crew can run at once, like 2.", "error")
        else:
            prefs.put(conn(), "crew_slots", raw)
            flash(f"Saved: the crew can run {raw} job{'s' if raw != '1' else ''} at once.")
        return redirect(url_for("leads_page"))
