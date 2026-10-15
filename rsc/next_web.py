"""Never lost: the step tracker at the top of every job page, the one glowing thing to press, and the Next task button.

All of it reads guide.py, so there is one idea of "what's next" in the app. The Next task button goes through /next, which
works out the task, remembers which field to light up, and sends you to that page; the page scrolls to it and glows.
"""
import sqlite3

from flask import flash, g, redirect, request, session, url_for

from . import books, guide


def register(app, cfg, conn) -> None:
    def _setup_ok() -> bool:
        st = app.jinja_env.globals.get("setup_state")
        try:
            s = st() if st else {"email": True, "password": True}
        except Exception:
            return True
        return bool(s.get("email") and s.get("password"))

    def _page_job() -> dict | None:
        number = (request.view_args or {}).get("number")
        if not isinstance(number, int):
            return None
        return books.get_job(conn(), number)

    def _here(step: dict | None) -> bool:
        return bool(step) and step["endpoint"] == request.endpoint and step.get("args", {}) == (request.view_args or {})

    def job_tracker() -> dict | None:
        """The job this page belongs to, its stage, and its next step. Cached for the request."""
        if "tracker" not in g:
            g.tracker = None
            try:
                job = _page_job()
                if job:
                    st = guide.stage(conn(), job)
                    nxt = st["next"]
                    g.tracker = {**st, "job": job, "here": _here(nxt) and not (nxt or {}).get("wait") and bool(nxt.get("target"))}
            except sqlite3.Error:
                g.tracker = None
        return g.tracker

    def glow_here() -> dict | None:
        """What to light up on this page: the field the Next task button sent you to (scrolled into view), or else this
        job's next field when it is on this page (lit, not scrolled). Nothing for steps that are waiting on someone."""
        want = session.pop("glow", None) if "glow" in session else None  # used once: on the page Next task sent you to, or dropped
        if want and want.get("ep") == request.endpoint and want.get("args") == (request.view_args or {}):
            return {"target": want.get("target") or [], "scroll": True}
        t = job_tracker()
        if t and t["here"]:
            return {"target": t["next"]["target"], "scroll": False}
        return None

    def next_task_now() -> dict | None:
        return guide.next_task(conn(), _setup_ok())

    app.jinja_env.globals.update(job_tracker=job_tracker, glow_here=glow_here, next_task_now=next_task_now)

    @app.get("/next")
    def next_task():
        """Go to the next thing to do. From a job page, that job's next step first (unless it's only waiting)."""
        c = conn()
        task = None
        job = books.get_job(c, request.args.get("job", type=int)) if request.args.get("job", type=int) else None
        if job:
            step = guide.next_step(c, job)
            if step and not step.get("wait"):
                task = step
        task = task or guide.next_task(c, _setup_ok())
        if not task:
            flash("You're all caught up. Nothing needs you right now.")
            return redirect(url_for("home"))
        session["glow"] = {"ep": task["endpoint"], "args": task.get("args", {}), "target": task.get("target") or []}
        if "number" not in task.get("args", {}):  # job pages say it in the tracker already
            flash(f"Next: {task['title']}. {task['why']}", "next")
        return redirect(url_for(task["endpoint"], **task.get("args", {})))
