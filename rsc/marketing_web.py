"""Marketing page: social post drafts from real jobs, the posting schedule, and the online listings checklist."""
from flask import abort, flash, redirect, render_template, request, url_for

from . import client_update, marketing, prefs
from .llm import ModelUnavailable


def register(app, cfg, conn, get_model):
    @app.get("/marketing")
    def marketing_page():
        c = conn()
        ps = marketing.posts(c)
        for p in ps:
            p["photos"] = client_update.photos(c, p["job_number"]) if p["job_number"] else []
        return render_template("marketing.html", posts=ps, listings=marketing.listings(c),
                               schedule=marketing.schedule(c), website=marketing.website(c),
                               jobs=marketing.jobs_to_post(c), summary=marketing.summary(c),
                               pick=request.args.get("job", type=int))

    @app.post("/marketing/draft")
    def marketing_draft():
        note = request.form.get("note", "").strip()
        job = request.form.get("job_number", type=int)
        if not note:
            flash("Type or say a line about the work first.", "error")
            return redirect(url_for("marketing_page"))
        try:
            model = get_model()
        except ModelUnavailable:
            model = None
        marketing.draft(model, conn(), note, job)
        flash("Drafts ready below. Read them, change anything, then copy each one into the app you post from.")
        return redirect(url_for("marketing_page") + "#posts")

    @app.post("/marketing/post/<int:post_id>")
    def marketing_post(post_id):
        c = conn()
        if not marketing.get_post(c, post_id):
            abort(404)
        action = request.form.get("action", "save")
        if action == "delete":
            marketing.delete_post(c, post_id)
            flash("Draft removed.")
        else:
            marketing.update_post(c, post_id, **{k: request.form.get(k, "") for k in ("tiktok", "facebook", "nextdoor")
                                                 if k in request.form})
            if action == "posted":
                marketing.mark_posted(c, post_id)
                flash("Marked as posted.")
            else:
                flash("Saved.")
        return redirect(url_for("marketing_page") + "#posts")

    @app.post("/marketing/listing/<key>")
    def marketing_listing(key):
        if not marketing.save_listing(conn(), key, request.form.get("url", ""), request.form.get("todo", "")):
            abort(404)
        flash("Saved.")
        return redirect(url_for("marketing_page") + "#listings")

    @app.post("/marketing/schedule")
    def marketing_schedule():
        prefs.put(conn(), "social_schedule", request.form.get("schedule", ""))
        flash("Saved.")
        return redirect(url_for("marketing_page") + "#schedule")
