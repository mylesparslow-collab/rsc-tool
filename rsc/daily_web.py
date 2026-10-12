"""Today page: the daily work sheet, with steps the crew can tick off, and the full progress page for a job."""
import smtplib
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

from . import books, config, daily, estimates


def _ints(values):
    out = []
    for v in values:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return out


def register(app, cfg, conn):
    @app.get("/today")
    def today_page():
        c = conn()
        d = daily.build(c)
        return render_template("today.html", d=d, today=date.today().isoformat(), recipients=daily.recipients(c))

    @app.post("/today/job/<int:number>")
    def today_job(number):
        c = conn()
        if not books.get_job(c, number):
            abort(404)
        daily.set_steps(c, number, _ints(request.form.getlist("shown")), _ints(request.form.getlist("done")))
        if "note" in request.form:
            daily.set_note(c, number, date.today().isoformat(), request.form.get("note", ""))
        flash("Saved.")
        back = request.form.get("back") or ""
        ok = back.startswith("/") and not back.startswith("//") and "\\" not in back and all(ord(ch) >= 32 for ch in back)
        return redirect(back if ok else url_for("today_page"))

    @app.post("/today/send")
    def today_send():
        c = conn()
        try:
            to = daily.send(c, cfg.mail.address, config.mail_password(cfg.mail.address), daily.build(c))
            flash("Sent to " + ", ".join(to) + ".")
        except (ValueError, RuntimeError, smtplib.SMTPException, OSError) as exc:
            flash(f"Not sent: {exc}", "error")
        return redirect(url_for("today_page"))

    @app.get("/jobs/<int:number>/progress")
    def job_progress(number):
        c = conn()
        job = books.get_job(c, number)
        est = estimates.get(c, number)
        if not job or not est:
            abort(404)
        done = daily.done_steps(c, number)
        phases, n = [], 0
        for p in est["phases"]:
            steps = []
            for text in p["steps"]:
                n += 1
                steps.append((n, text, n in done))
            phases.append({"title": p["title"], "steps": steps})
        return render_template("progress.html", job=job, phases=phases, total=n, done=len(done))
