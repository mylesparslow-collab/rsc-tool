"""Week page: the plan for jobs and crew, typed in plain words."""
from datetime import date

from flask import flash, redirect, render_template, request, url_for

from . import schedule


def _start(text):
    try:
        return schedule.week_start(date.fromisoformat(text))
    except (TypeError, ValueError):
        return schedule.week_start(date.today())


def register(app, cfg, conn):
    @app.get("/week")
    def week_page():
        c = conn()
        return render_template("week.html", w=schedule.week(c, _start(request.args.get("start"))), today=date.today().isoformat())

    @app.post("/week/plan")
    def week_plan():
        start = _start(request.form.get("start"))
        res = schedule.add(conn(), request.form.get("plan", ""), start)
        if res["saved"]:
            flash(f"Planned {res['saved']} spot(s).")
        for p in res["problems"]:
            flash(p, "error")
        if not res["saved"] and not res["problems"]:
            flash("Type who is where, like: Mon-Wed Delano Mike Dave.", "error")
        return redirect(url_for("week_page", start=start.isoformat()))

    @app.post("/week/remove/<int:entry_id>")
    def week_remove(entry_id):
        schedule.remove(conn(), entry_id)
        return redirect(url_for("week_page", start=_start(request.form.get("start")).isoformat()))
