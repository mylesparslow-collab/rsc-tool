"""Scorecard page: leads, estimates sent, jobs won, win rate, money in and dollars per crew-hour, week by week."""
from datetime import date

from flask import render_template, request

from . import scorecard


def register(app, cfg, conn):
    @app.get("/scorecard")
    def scorecard_page():
        try:
            today = date.fromisoformat(request.args.get("date", ""))
        except ValueError:
            today = date.today()
        card = scorecard.build(conn(), today)
        return render_template("scorecard.html", card=card, level=scorecard.level)
