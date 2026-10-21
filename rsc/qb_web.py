"""The QuickBooks page: CSV downloads that work today, and the optional direct connection."""
import secrets

from flask import Response, abort, flash, redirect, render_template, request, session, url_for

from . import books, qbo, quickbooks


def register(app, cfg, conn):
    def _csv(text, name):
        return Response(text, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/quickbooks")
    def quickbooks_page():
        c = conn()
        on = qbo.connected(c)
        return render_template("quickbooks.html", configured=qbo.configured(cfg), connected=on,
                               env=cfg.quickbooks.environment, redirect_uri=cfg.qb_redirect_uri,
                               payments=books.list_payments(c) if on else [], synced=qbo.synced(c) if on else {},
                               estimate_jobs=_estimate_jobs(c) if on else [])

    def _estimate_jobs(c):
        """Jobs with a payment schedule, each with what is already in QuickBooks and whether anything is left to send."""
        pays = books.list_payments(c)
        done = qbo.estimates_synced(c)
        out = []
        for j in books.list_jobs(c):
            mine = [p for p in pays if p["job_number"] == j["number"]]
            if not mine:
                continue
            docs = [d for d, _ in qbo.estimate_groups(mine, f"{j['number']}-{j['code']}")]
            sent = done.get(j["number"], [])
            out.append({**j, "job_id": f"{j['number']}-{j['code']}", "scheduled_total": sum(p["amount"] for p in mine),
                        "sent": sent, "unsent": [d for d in docs if d not in sent]})
        return out

    @app.get("/quickbooks/invoices.csv")
    def qb_invoices():
        return _csv(quickbooks.invoices_csv(conn(), open_only=request.args.get("all") != "1"), "RSC invoices for QuickBooks.csv")

    @app.get("/quickbooks/expenses.csv")
    def qb_expenses():
        return _csv(quickbooks.expenses_csv(conn()), "RSC expenses for QuickBooks.csv")

    @app.get("/quickbooks/customers.csv")
    def qb_customers():
        return _csv(quickbooks.customers_csv(conn()), "RSC customers for QuickBooks.csv")

    @app.post("/quickbooks/connect")
    def qb_connect():
        if not qbo.configured(cfg):
            flash("Add the QuickBooks Client ID and Secret to config.toml first (see the steps on this page).", "error")
            return redirect(url_for("quickbooks_page"))
        session["qb_state"] = secrets.token_urlsafe(16)
        return redirect(qbo.auth_url(cfg, session["qb_state"]))

    @app.get("/quickbooks/callback")
    def qb_callback():
        if not request.args.get("code") or request.args.get("state") != session.pop("qb_state", None):
            flash("The QuickBooks sign-in didn't match. Press Connect again.", "error")
            return redirect(url_for("quickbooks_page"))
        try:
            qbo.connect(cfg, conn(), request.args["code"], request.args.get("realmId", ""))
            flash(f"Connected to QuickBooks ({cfg.quickbooks.environment}).")
        except qbo.QBOError as exc:
            flash(str(exc), "error")
        return redirect(url_for("quickbooks_page"))

    @app.post("/quickbooks/disconnect")
    def qb_disconnect():
        qbo.disconnect(conn())
        flash("Disconnected from QuickBooks.")
        return redirect(url_for("quickbooks_page"))

    def _payment(c, pk):
        match = [p for p in books.list_payments(c) if p["id"] == pk]
        if not match:
            abort(404)
        j = books.get_job(c, match[0]["job_number"])
        name = f"{j['first_name']} {j['last_name']}".strip()
        return match[0], name, j["email"]

    @app.post("/quickbooks/send/<int:pk>")
    def qb_send(pk):
        c = conn()
        p, name, email = _payment(c, pk)
        try:
            qbo.send_invoice(cfg, c, p, name, email)
            flash(f"Invoice {p['payment_id']} is in QuickBooks.")
        except qbo.QBOError as exc:
            flash(str(exc), "error")
        return redirect(url_for("quickbooks_page"))

    @app.post("/quickbooks/estimate/<int:number>")
    def qb_estimate(number):
        c = conn()
        j = books.get_job(c, number)
        if not j:
            abort(404)
        name = f"{j['first_name']} {j['last_name']}".strip()
        try:
            made = qbo.send_estimates(cfg, c, j, books.list_payments(c, number), name, j["email"])
            flash(f"Estimate {', '.join(made)} is in QuickBooks." if made else "That estimate is already in QuickBooks.")
        except qbo.QBOError as exc:
            flash(str(exc), "error")
        return redirect(url_for("quickbooks_page"))

    @app.post("/quickbooks/paid/<int:pk>")
    def qb_paid(pk):
        c = conn()
        p, name, _ = _payment(c, pk)
        try:
            qbo.record_payment(cfg, c, p, name)
            flash(f"Payment on {p['payment_id']} recorded in QuickBooks.")
        except qbo.QBOError as exc:
            flash(str(exc), "error")
        return redirect(url_for("quickbooks_page"))
