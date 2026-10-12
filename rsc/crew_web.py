"""The Crew page: log hours in plain words, see who's insured, and price out payroll."""
import math
from datetime import date

from flask import abort, flash, redirect, render_template, request, send_file, url_for
import io

from . import books, crew, receipts
from .llm import ModelUnavailable


def _num(text, default=0.0):
    try:
        v = float(str(text).replace("$", "").replace(",", "").strip() or default)
    except ValueError:
        return default
    return v if math.isfinite(v) else default


def register(app, cfg, conn, get_model, get_vision_model):
    app.jinja_env.globals["crew_alerts"] = lambda: crew.alerts(conn())

    @app.get("/crew")
    def crew_page():
        c = conn()
        calc = None
        if request.args.get("workers"):
            wage = min(max(_num(request.args.get("wage"), 28), 0), 500)
            calc = crew.payroll_cost(min(max(int(_num(request.args.get("workers"), 0)), 0), 100), wage,
                                     min(max(_num(request.args.get("hours"), 1800), 0), 4000), min(max(_num(request.args.get("wc"), 8), 0), 100))
            calc["wage"] = wage
        return render_template("crew.html", people=crew.people(c), hours=crew.recent_hours(c, 25), certs=crew.certificates(c),
                               alerts=crew.alerts(c), roles=crew.ROLE_LABEL, cert_kinds=crew.CERT_KINDS, calc=calc,
                               calc_args={"workers": request.args.get("workers", "3"), "wage": request.args.get("wage", "28"),
                                          "hours": request.args.get("hours", "1800"), "wc": request.args.get("wc", "8")},
                               jobs=books.list_jobs(c, active_only=True), today=date.today().isoformat())

    @app.post("/crew/hours")
    def crew_hours_add():
        c = conn()
        default = request.form.get("job", type=int)
        back = request.form.get("back") or url_for("crew_page")
        if not back.startswith("/") or back.startswith("//") or "\\" in back or any(ord(ch) < 32 for ch in back):
            back = url_for("crew_page")
        try:
            model = None
            try:
                model = get_model()
            except ModelUnavailable:
                model = None
            res = crew.log_hours(c, model, request.form.get("text", ""), default)
        except crew.CrewError as exc:
            flash(str(exc), "error")
            return redirect(back)
        if res["saved"]:
            total = sum(s["hours"] for s in res["saved"])
            flash("Logged " + "; ".join(f"{s['name']} {s['hours']:g}h on {s['job']} ({s['date']})" for s in res["saved"][:6])
                  + (f" and {len(res['saved']) - 6} more" if len(res["saved"]) > 6 else "") + f". {total:g} hours in all.")
        if res["new_people"]:
            flash("New on the crew: " + ", ".join(res["new_people"]) + ". Set their pay on the Crew page so job costs include them.")
        for p in res["problems"]:
            flash(p, "error")
        if not res["saved"] and not res["problems"]:
            flash("I couldn't find any names and hours in that. Try: Tue Mike 8, Dave 6 on Delano", "error")
        return redirect(back)

    @app.post("/crew/hours/<int:hours_id>/delete")
    def crew_hours_delete(hours_id):
        crew.delete_hours(conn(), hours_id)
        flash("Removed.")
        return redirect(url_for("crew_page"))

    @app.post("/crew/person")
    def crew_person_add():
        try:
            crew.add_person(conn(), request.form.get("name", ""), request.form.get("role", "helper"), _num(request.form.get("wage")),
                            email=request.form.get("email", ""))
            flash("Added.")
        except crew.CrewError as exc:
            flash(str(exc), "error")
        return redirect(url_for("crew_page"))

    @app.post("/crew/person/<int:crew_id>")
    def crew_person_update(crew_id):
        try:
            crew.update_person(conn(), crew_id, request.form.get("name", ""), request.form.get("role", "helper"),
                               _num(request.form.get("wage")), bool(request.form.get("active")), request.form.get("email", ""))
            flash("Saved.")
        except crew.CrewError as exc:
            flash(str(exc), "error")
        return redirect(url_for("crew_page"))

    @app.post("/crew/certificate")
    def crew_cert_add():
        c = conn()
        holder = request.form.get("holder", "")
        crew_id = int(holder) if holder.isdigit() else None
        kind, insurer, policy, expires = (request.form.get(k, "").strip() for k in ("kind", "insurer", "policy_no", "expires"))
        mime, data, read = "", None, None
        shot = request.files.get("file")
        if shot and shot.filename:
            raw = shot.read()
            try:
                mime = receipts.check_photo(raw)
                data = raw
            except receipts.NotAPhoto as exc:
                if raw[:4] == b"%PDF" and len(raw) <= receipts.MAX_PHOTO_BYTES:
                    mime, data = "application/pdf", raw
                else:
                    flash(str(exc), "error")
                    return redirect(url_for("crew_page"))
            if mime.startswith("image/"):
                try:
                    read = crew.read_certificate(get_vision_model(), data)
                except (ModelUnavailable, Exception):
                    read = None
        if read:
            kind = kind or read.get("kind", "")
            insurer = insurer or read.get("insurer", "")
            policy = policy or read.get("policy_no", "")
            expires = expires or read.get("expires", "")
        try:
            crew.add_certificate(c, crew_id, kind or "General liability", insurer, policy, expires, mime, data)
        except crew.CrewError as exc:
            flash(str(exc), "error")
            return redirect(url_for("crew_page"))
        if crew.clean_date(expires):
            flash(f"Saved. Expires {crew.clean_date(expires)}" + (" (read from the photo, please check it)." if read else "."))
        else:
            flash("Saved, but there's no expiry date yet. Type it in below so I can warn you before it runs out.", "error")
        return redirect(url_for("crew_page"))

    @app.get("/crew/certificate/<int:cert_id>")
    def crew_cert_file(cert_id):
        got = crew.certificate_file(conn(), cert_id)
        if not got:
            abort(404)
        return send_file(io.BytesIO(got[1]), mimetype=got[0])

    @app.post("/crew/certificate/<int:cert_id>")
    def crew_cert_update(cert_id):
        c = conn()
        c.execute("UPDATE certificates SET expires = ?, insurer = CASE WHEN ? != '' THEN ? ELSE insurer END WHERE id = ?",
                  (crew.clean_date(request.form.get("expires", "")), request.form.get("insurer", "").strip(),
                   request.form.get("insurer", "").strip(), cert_id))
        c.commit()
        flash("Saved.")
        return redirect(url_for("crew_page"))

    @app.post("/crew/certificate/<int:cert_id>/delete")
    def crew_cert_delete(cert_id):
        crew.delete_certificate(conn(), cert_id)
        flash("Removed.")
        return redirect(url_for("crew_page"))
