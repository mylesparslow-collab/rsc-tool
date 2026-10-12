"""The Playbook (how RSC builds each kind of job) and the printable crew brief for one job."""
from flask import abort, render_template

from . import playbook


def register(app, conn):
    @app.get("/playbook")
    def playbook_page():
        return render_template("playbook.html", kinds=playbook.library(conn()))

    @app.get("/jobs/<int:number>/crew-brief")
    def crew_brief(number):
        b = playbook.job_brief(conn(), number)
        if not b:
            abort(404)
        return render_template("crew_brief.html", **b)
