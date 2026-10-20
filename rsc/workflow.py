"""Pages for the estimate / contract / change order / pricing workflow."""
import smtplib
from datetime import date

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for

from . import assist, books, changeorders, config, contract, estimate_mail, estimates, pricing, rates
from .llm import ModelUnavailable


def _num(value: str) -> float | None:
    value = (value or "").replace("$", "").replace(",", "").strip()
    return float(value) if value else None


def _pct(value: str) -> float | None:
    return _num((value or "").replace("%", ""))


def register(app, conn, get_model):
    """Add the pages to the app. `conn` is the app's per-request database getter; `get_model` returns the local model."""

    def job_or_404(number):
        job = books.get_job(conn(), number)
        if not job:
            abort(404)
        return job

    # ------------------------------------------------------------ estimate
    @app.get("/jobs/<int:number>/estimate")
    def estimate_edit(number):
        c = conn()
        job = job_or_404(number)
        est = estimates.get(c, number)
        ctx = {"job": job, "est": est, "templates": list(estimates.TEMPLATES)}
        if est:
            t = estimates.totals(est)
            ctx.update(totals=t, schedule=estimates.build_schedule(est) if t["total"] > 0 else [],
                       check=pricing.check_estimate(c, number), payments=books.list_payments(c, number),
                       ranges=estimates.step_ranges(est["phases"]))
        return render_template("estimate_edit.html", **ctx)

    @app.post("/jobs/<int:number>/estimate/draft")
    def estimate_draft(number):
        """The assistant writes (or rewrites) the whole estimate from what Nick typed."""
        job = job_or_404(number)
        description = request.form.get("description", "").strip()
        if not description:
            flash("Tell me a little about the job first.", "error")
            return redirect(url_for("estimate_edit", number=number))
        try:
            draft = assist.draft_estimate(get_model(), conn(), job, description)
            assist.apply_draft(conn(), number, draft)
            conn().execute("UPDATE jobs SET notes = CASE WHEN notes = '' THEN ? ELSE notes END WHERE number = ?",
                           (description[:300], number))
            conn().commit()
            flash("Estimate drafted. Check the numbers, then ask for any changes.")
        except (ModelUnavailable, ValueError, books.BooksError) as exc:
            flash(f"Couldn't draft it: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number))

    @app.post("/jobs/<int:number>/estimate/revise")
    def estimate_revise(number):
        """'Make labor $10,000 and add a bathroom fan': the assistant changes just that."""
        job = job_or_404(number)
        est = estimates.get(conn(), number)
        instruction = request.form.get("instruction", "").strip()
        if not est or not instruction:
            flash("Say what to change.", "error")
            return redirect(url_for("estimate_edit", number=number))
        try:
            draft = assist.draft_estimate(get_model(), conn(), job, job["notes"] or "", current=est, instruction=instruction)
            assist.apply_draft(conn(), number, draft)
            estimates.bump_version(conn(), number)
            flash(f"Changed. This is now version {estimates.get(conn(), number)['version']}. Check the numbers.")
        except (ModelUnavailable, ValueError, books.BooksError) as exc:
            flash(f"Couldn't change it: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number))

    @app.post("/jobs/<int:number>/estimate/new")
    def estimate_new(number):
        job_or_404(number)
        try:
            estimates.create(conn(), number, request.form.get("template", ""))
        except books.BooksError as exc:
            flash(f"Not started: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number))

    @app.post("/jobs/<int:number>/estimate")
    def estimate_save(number):
        job_or_404(number)
        f = request.form
        try:
            scalars = {k: _num(f.get(k, "")) for k in estimates.SCALARS}
            phases = [{"title": t, "steps": estimates.clean_steps(s), "inspection": i}
                      for t, s, i in zip(f.getlist("phase_title"), f.getlist("phase_steps"), f.getlist("phase_inspection"))]
            others = [{"label": label, "amount": _num(amount)}
                      for label, amount in zip(f.getlist("other_label"), f.getlist("other_amount"))]
            estimates.save(conn(), number, scalars, {k: f.get(k, "") for k in estimates.TEXTS}, phases, others)
            flash("Saved.")
        except (books.BooksError, ValueError) as exc:
            flash(f"Not saved: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number))

    @app.post("/jobs/<int:number>/estimate/schedule")
    def estimate_schedule(number):
        job_or_404(number)
        try:
            count = estimates.generate_schedule(conn(), number)
            flash(f"Payment schedule created: {count} payments. The contract total is set.")
        except books.BooksError as exc:
            flash(f"Not created: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number) + "#schedule")

    @app.post("/jobs/<int:number>/estimate/approve")
    def estimate_approve(number):
        job_or_404(number)
        try:
            count = estimates.approve(conn(), number, request.form.get("signed_on") or None)
            flash(f"Contract signed. Job marked Signed with {count} payments.")
        except books.BooksError as exc:
            flash(f"Not saved: {exc}", "error")
        return redirect(url_for("estimate_edit", number=number) + "#schedule")

    def _sow_context(number):
        job = job_or_404(number)
        est = estimates.get(conn(), number)
        if not est:
            abort(404)
        ranges = estimates.step_ranges(est["phases"])
        phases, n = [], 0
        for p, rng in zip(est["phases"], ranges):
            steps = []
            for text in p["steps"]:
                n += 1
                steps.append((n, text))
            phases.append({**p, "numbered": steps, "range": rng})
        return {"job": job, "est": est, "phases": phases, "totals": estimates.totals(est),
                "schedule": estimates.build_schedule(est), "payments": books.list_payments(conn(), number),
                "today": date.today().strftime("%B %-d, %Y"),
                "version_date": (date.fromisoformat(est["version_date"]) if est["version_date"] else date.today()).strftime("%-m/%-d/%y"),
                "lines": lambda text: [x.strip() for x in (text or "").splitlines() if x.strip()]}

    @app.get("/jobs/<int:number>/sow")
    def sow(number):
        return render_template("sow.html", **_sow_context(number))

    def _mail_ready():
        """(ok, why not): is Gmail set up well enough to send from?"""
        cfg = current_app.config["RSC"]
        if not cfg.mail.address:
            return False, "Add your Gmail address on the Setup page first."
        try:
            config.mail_password(cfg.mail.address)
        except RuntimeError:
            return False, "Save your Gmail app password on the Setup page first."
        return True, ""

    @app.get("/jobs/<int:number>/sow.pdf")
    def sow_pdf(number):
        ctx = _sow_context(number)
        return Response(estimate_mail.build_pdf(ctx), mimetype="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{estimate_mail.filename(ctx["job"])}"'})

    @app.get("/jobs/<int:number>/sow/send")
    def sow_send_page(number):
        ctx = _sow_context(number)
        job = ctx["job"]
        ready, why = _mail_ready()
        return render_template("estimate_send.html", job=job, ready=ready, why=why, to=job.get("email") or "",
                               subject=estimate_mail.default_subject(job),
                               body=estimate_mail.default_body(job, ctx["totals"]["total"]),
                               pdf_name=estimate_mail.filename(job), total=ctx["totals"]["total"],
                               sent=job.get("estimate_sent"),
                               rates=(pricing.check_estimate(conn(), number) or {}).get("rates"))

    @app.post("/jobs/<int:number>/sow/send")
    def sow_send(number):
        ctx = _sow_context(number)
        job, cfg = ctx["job"], current_app.config["RSC"]
        to = request.form.get("to", "").strip()
        subject = request.form.get("subject", "").strip() or estimate_mail.default_subject(job)
        body = request.form.get("body", "").strip()
        if "@" not in to or any(ch in to for ch in "\r\n,;<> "):
            flash("Type one email address for the client first.", "error")
            return redirect(url_for("sow_send_page", number=number))
        ready, why = _mail_ready()
        if not ready:
            flash(why, "error")
            return redirect(url_for("sow_send_page", number=number))
        try:
            estimate_mail.send(cfg.mail.address, config.mail_password(cfg.mail.address), to, subject, body,
                               estimate_mail.build_pdf(ctx), estimate_mail.filename(job))
        except (RuntimeError, ValueError, smtplib.SMTPException, OSError) as exc:
            flash(f"Not sent: {exc}. The job was not marked as sent.", "error")
            return redirect(url_for("sow_send_page", number=number))
        fields = {"estimate_sent": date.today().isoformat()}
        if not job.get("email"):
            fields["email"] = to   # remember the address for next time
        books.update_job(conn(), number, **fields)
        flash(f"Estimate sent to {to} (a copy went to you). The job now shows it as sent today.")
        return redirect(url_for("job_detail", number=number))

    @app.get("/jobs/<int:number>/contract")
    def contract_view(number):
        job_or_404(number)
        data = contract.build(conn(), number)
        ctx = {}
        if estimates.get(conn(), number):
            ctx = _sow_context(number)
        return render_template("contract.html", c=data, **{k: v for k, v in ctx.items() if k != "job"})

    # ------------------------------------------------------------ change orders
    @app.get("/jobs/<int:number>/change-orders")
    def change_orders(number):
        job = job_or_404(number)
        return render_template("change_orders.html", job=job, orders=changeorders.list_for_job(conn(), number))

    @app.post("/jobs/<int:number>/change-orders")
    def change_order_create(number):
        job_or_404(number)
        f = request.form
        text = f.get("description", "").strip()
        try:
            if f.get("amount", "").strip():  # typed by hand
                amount = _num(f["amount"])
                if amount is not None and f.get("direction") == "credit":
                    amount = -abs(amount)
                days = int(f.get("days_added") or 0)
            else:  # the assistant reads the amount from the sentence
                if not assist.has_amount(text):
                    raise books.BooksError("Include the price, like: add a second window on the east wall for $1,200")
                got = assist.parse_change(get_model(), text)
                text, amount, days = got["description"], got["amount"], got["days_added"]
            co_id = changeorders.create(conn(), number, text, amount or 0, days)
        except ModelUnavailable as exc:
            flash(f"The assistant isn't available ({exc}). Type the amount instead.", "error")
            return redirect(url_for("change_orders", number=number))
        except (books.BooksError, ValueError) as exc:
            flash(f"Not saved: {exc}", "error")
            return redirect(url_for("change_orders", number=number))
        return redirect(url_for("change_order_view", co_id=co_id))

    @app.get("/change-orders/<int:co_id>")
    def change_order_view(co_id):
        co = changeorders.get(conn(), co_id)
        if not co:
            abort(404)
        return render_template("change_order.html", co=co, job=co["job"],
                               new_total=(co["job"]["contract_total"] or 0) + co["amount"] if co["status"] == "draft"
                               else co["job"]["contract_total"])

    @app.get("/change-orders/<int:co_id>/print")
    def change_order_print(co_id):
        co = changeorders.get(conn(), co_id)
        if not co or co["status"] != "signed":
            abort(404)
        return render_template("change_order_print.html", co=co, job=co["job"])

    @app.post("/change-orders/<int:co_id>/sign")
    def change_order_sign(co_id):
        try:
            payment_id = changeorders.sign(conn(), co_id, request.form.get("signer_name", ""),
                                           request.form.get("signature", ""))
            flash(f"Signed. Contract total updated and payment {payment_id} added.")
        except books.BooksError as exc:
            flash(f"Not signed: {exc}", "error")
        return redirect(url_for("change_order_view", co_id=co_id))

    @app.post("/change-orders/<int:co_id>/<action>")
    def change_order_action(co_id, action):
        co = changeorders.get(conn(), co_id)
        if not co:
            abort(404)
        try:
            if action == "decline":
                changeorders.decline(conn(), co_id)
                flash("Marked declined.")
            elif action == "delete":
                changeorders.delete_draft(conn(), co_id)
                flash("Deleted.")
                return redirect(url_for("change_orders", number=co["job_number"]))
            else:
                abort(404)
        except books.BooksError as exc:
            flash(str(exc), "error")
        return redirect(url_for("change_order_view", co_id=co_id))

    # ------------------------------------------------------------ pricing
    @app.route("/pricing", methods=["GET", "POST"])
    def pricing_page():
        c = conn()
        if request.method == "POST" and request.form.get("which") == "rates":
            try:
                rates.save_settings(c, {k: request.form.get(k, "").replace("$", "").replace(",", "").strip() for k in rates.DEFAULTS})
                flash("Saved.")
            except ValueError as exc:
                flash(f"Not saved: {exc}", "error")
            return redirect(url_for("pricing_page"))
        if request.method == "POST":
            try:
                pricing.save_settings(c, _pct(request.form.get("target_margin", "")),
                                      _pct(request.form.get("overhead_override", "")))
                flash("Saved.")
            except (books.BooksError, ValueError) as exc:
                flash(f"Not saved: {exc}", "error")
            return redirect(url_for("pricing_page"))
        open_estimates = []
        for j in books.list_jobs(c, active_only=True):
            check = pricing.check_estimate(c, j["number"])
            if check:
                open_estimates.append({"job": j, "check": check})
        return render_template("pricing.html", rates=rates.get_settings(c), settings=pricing.get_settings(c), overhead=pricing.overhead(c),
                               accuracy=pricing.accuracy(c), open_estimates=open_estimates,
                               min_jobs=pricing.MIN_JOBS_FOR_HISTORY)
