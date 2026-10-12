"""Weekly client update: draft, photos, open in Mail."""
from flask import Response, abort, flash, redirect, render_template, request, url_for

from . import books, client_update, receipts
from .llm import ModelUnavailable


def register(app, cfg, conn, get_model):
    def _job(number):
        job = books.get_job(conn(), number)
        if not job:
            abort(404)
        return job

    def _page(number, d):
        c = conn()
        job = _job(number)
        return render_template("client_update.html", job=job, d=d, photos=client_update.photos(c, number))

    @app.get("/jobs/<int:number>/update")
    def client_update_page(number):
        return _page(number, None)

    @app.post("/jobs/<int:number>/update/draft")
    def client_update_draft(number):
        job = _job(number)
        try:
            model = get_model()
        except ModelUnavailable:
            model = None
        d = client_update.draft(model, conn(), job, cfg.business_phone)
        if not d:
            flash("This job has no scope of work yet, so there is nothing to report.", "error")
            return redirect(url_for("client_update_page", number=number))
        return _page(number, d)

    @app.post("/jobs/<int:number>/update/photos")
    def client_update_photos(number):
        _job(number)
        n = 0
        for f in request.files.getlist("photos"):
            if not f or not f.filename:
                continue
            try:
                data = f.read()
                client_update.add_photo(conn(), number, receipts.check_photo(data), data)
                n += 1
            except receipts.NotAPhoto as exc:
                flash(str(exc), "error")
        flash(f"Added {n} photo(s)." if n else "Pick a photo first.")
        return redirect(url_for("client_update_page", number=number))

    @app.get("/jobs/<int:number>/update/photo/<int:photo_id>")
    def client_update_photo(number, photo_id):
        got = client_update.photo_file(conn(), number, photo_id)
        if not got:
            abort(404)
        return Response(got[1], mimetype=got[0], headers={"Content-Disposition": f'inline; filename="site-photo-{photo_id}.jpg"'})

    @app.post("/jobs/<int:number>/update/photo/<int:photo_id>/delete")
    def client_update_photo_delete(number, photo_id):
        _job(number)
        client_update.delete_photo(conn(), number, photo_id)
        return redirect(url_for("client_update_page", number=number))
