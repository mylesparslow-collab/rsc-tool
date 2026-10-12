"""Home safety assessment pages (aging in place): a room-by-room checklist, photos, and notes in plain words."""
import io

from flask import abort, flash, redirect, render_template, request, send_file, url_for

from . import aging, books, receipts


def register(app, conn, get_model):
    def _job(number):
        job = books.get_job(conn(), number)
        if not job:
            abort(404)
        return job

    @app.get("/jobs/<int:number>/assessment")
    def assessment(number):
        c = conn()
        job = _job(number)
        return render_template("assessment.html", job=job, a=aging.latest(c, number), fee=aging.FEE_RANGE,
                               credit_over=aging.FEE_CREDIT_OVER, dimensions=aging.DIMENSIONS.splitlines()[1:],
                               checklist=aging.CHECKLIST, rooms=aging.ROOMS, photos=aging.photos(c, number))

    @app.get("/jobs/<int:number>/assessment/print")
    def assessment_print(number):
        c = conn()
        job, a = _job(number), aging.latest(c, number)
        if not a:
            abort(404)
        return render_template("assessment_print.html", job=job, a=a, credit_over=aging.FEE_CREDIT_OVER, photos=aging.photos(c, number))

    @app.get("/jobs/<int:number>/assessment/photo/<int:photo_id>")
    def assessment_photo(number, photo_id):
        got = aging.photo_file(conn(), number, photo_id)
        if not got:
            abort(404)
        return send_file(io.BytesIO(got[1]), mimetype=got[0])

    @app.post("/jobs/<int:number>/assessment/photo/<int:photo_id>/delete")
    def assessment_photo_delete(number, photo_id):
        _job(number)
        aging.delete_photo(conn(), number, photo_id)
        return redirect(url_for("assessment", number=number) + "#photos")

    @app.post("/jobs/<int:number>/assessment")
    def assessment_save(number):
        c = conn()
        _job(number)
        saved_photos = 0
        for f in request.files.getlist("photos"):
            if not f or not f.filename:
                continue
            try:
                data = f.read()
                mime = receipts.check_photo(data)
            except receipts.NotAPhoto as exc:
                flash(str(exc), "error")
                continue
            aging.add_photo(c, number, request.form.get("photo_room", "Other"), mime, data)
            saved_photos += 1
        if request.form.get("action") == "photos":
            flash(f"Added {saved_photos} photo(s)." if saved_photos else "Pick a photo first.")
            return redirect(url_for("assessment", number=number) + "#photos")
        checked = aging.from_checks(request.form.getlist("check"))
        notes = request.form.get("notes", "").strip()[:4000]
        if not checked and not notes:
            flash("Tick what you saw, or type or say it.", "error")
            return redirect(url_for("assessment", number=number))
        parsed = {"items": [], "concerns": []}
        if notes:
            try:
                model = get_model()
            except Exception:
                model = None
            parsed = aging.read_notes(model, notes)
        items = aging.merge(checked, parsed["items"])
        if not items and not parsed["concerns"]:
            flash("I couldn't match that to any fixes. Try: two grab bars at the tub, railing on the front steps.", "error")
            return redirect(url_for("assessment", number=number))
        label = "Checklist: " + ", ".join(aging.CHECK_INDEX[i][1] for i in request.form.getlist("check") if i in aging.CHECK_INDEX)
        aging.save(c, number, (label + "\n" + notes).strip(), {"items": items, "concerns": parsed["concerns"]})
        flash("Assessment written. Check the quantities, then print it for the client.")
        return redirect(url_for("assessment", number=number))
