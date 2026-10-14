"""Setup, follow-ups and the weekly report: the pages that keep the business running between jobs."""
import imaplib
import smtplib

from flask import flash, jsonify, redirect, render_template, request, url_for

from . import brand, config, doctor, followups, leads, margins, models, prefs, report
from .llm import ModelUnavailable
from .mail import GmailReader


def register(app, cfg, conn, get_model):
    def _password_ok():
        try:
            config.mail_password(cfg.mail.address)
            return True
        except RuntimeError:
            return False

    def setup_state(c):
        return {"email": bool(cfg.mail.address), "password": bool(cfg.mail.address) and _password_ok(),
                "recipients": bool(prefs.report_recipients(c))}

    app.jinja_env.globals["setup_state"] = lambda: setup_state(conn())
    app.jinja_env.globals["followups_due"] = lambda: len(followups.due(conn()))

    @app.route("/setup", methods=["GET", "POST"])
    def setup_page():
        c = conn()
        if request.method == "POST":
            f = request.form
            address = f.get("address", "").strip()
            password = f.get("password", "").replace(" ", "")
            if address and address != cfg.mail.address:
                config.update_config(cfg.home, address)
                cfg.mail.address = address
            if "brand_name" in f:
                brand.save(c, {k: f.get("brand_" + k, "") for k, _ in brand.LABELS})
                brand.use(c, cfg)
            for key in ("report_to", "daily_to", "review_url", "visit_when", "owner_name"):
                if key in f:
                    prefs.put(c, key, f[key])
            if password and cfg.mail.address:
                try:
                    config.save_mail_password(cfg.mail.address, password)
                except RuntimeError as exc:
                    flash(f"Couldn't save the password: {exc}", "error")
                    return redirect(url_for("setup_page"))
            if cfg.mail.address and _password_ok():
                try:
                    GmailReader(cfg.mail.address, config.mail_password(cfg.mail.address), cfg.mail.host).check()
                    flash("Saved. Gmail is connected.")
                except (imaplib.IMAP4.error, OSError):
                    flash("Saved, but Gmail said no. Check the address and make a fresh app password "
                          "(myaccount.google.com/apppasswords).", "error")
            else:
                flash("Saved.")
            return redirect(url_for("setup_page"))
        models.apply_choice(cfg)
        return render_template("setup.html", address=cfg.mail.address, model_choices=models.choices(cfg), state=setup_state(c), ai=models.health(cfg),
                               auto_models=prefs.get(c, "auto_models") != "off", download=models.downloading(),
                               vals={k: prefs.get(c, k) for k in ("report_to", "daily_to", "review_url", "visit_when", "owner_name")},
                               slots=leads.visit_slots(prefs.get(c, "visit_when")),
                               health=doctor.run(cfg, include_app=False),
                               brand_fields=[(k, label, brand.current()[k]) for k, label in brand.LABELS])

    @app.post("/look")
    def save_look():
        """The Look panel saves each choice as it is made. The page already changed itself; this makes it stick."""
        c = conn()
        for key, allowed in prefs.LOOK.items():
            v = request.form.get(key)
            if v in allowed:
                prefs.put(c, "look_" + key, v)
        return ("", 204)

    @app.post("/setup/models")
    def setup_models():
        """Pick which of the models already on this Mac does each job. Blank means automatic. Takes effect at once."""
        c = conn()
        have = models.ollama_installed(cfg.model.url)
        if have is None:
            flash("Ollama isn't running, so I can't see your models. Open the Ollama app and try again.", "error")
            return redirect(url_for("setup_page") + "#ai")
        for key, field_name in (("model_text", "text_model"), ("model_vision", "vision_model")):
            pick = request.form.get(field_name, "").strip()
            if pick and not models._has(have, pick):
                flash(f"{pick} isn't one of the models on this Mac.", "error")
                return redirect(url_for("setup_page") + "#ai")
            prefs.put(c, key, pick)
        models.apply_choice(cfg)
        flash(f"Saved. Reading and writing now uses {cfg.model.name}.")
        return redirect(url_for("setup_page") + "#ai")

    @app.post("/setup/models/download")
    def setup_models_download():
        """One-click download of a suggested model, in the background; the page shows progress."""
        name = request.form.get("model", "")
        if name not in models.allowed_downloads():
            flash("That isn't one of the suggested models.", "error")
        elif models.ollama_installed(cfg.model.url) is None:
            flash("Ollama isn't running. Open the Ollama app, then press Download again.", "error")
        else:
            models.start_download(cfg.model.url, name)
            flash(f"Downloading {name}. You can keep working; progress shows at the top of the page.")
        return redirect(url_for("setup_page") + "#ai")

    @app.get("/setup/models/progress")
    def setup_models_progress():
        d = models.downloads()
        running = next(({"model": k, "pct": v["pct"]} for k, v in d.items() if v["state"] == "running"), None)
        done = [k for k, v in d.items() if v["state"] == "done"]
        failed = {k: v["error"] for k, v in d.items() if v["state"] == "error"}
        return jsonify(running=running, done=done, failed=failed)

    @app.post("/setup/models/test")
    def setup_models_test():
        """A tiny real question to the text model, so 'working' means it actually answered."""
        models.apply_choice(cfg)
        return jsonify(models.test_text(cfg))

    @app.post("/setup/models/auto")
    def setup_models_auto():
        prefs.put(conn(), "auto_models", "on" if request.form.get("auto") else "off")
        flash("Saved.")
        return redirect(url_for("setup_page") + "#ai")

    @app.before_request
    def _auto_download_when_nothing_usable():
        """Home and Setup only: if this Mac has no usable text model at all, start fetching the suggested one."""
        if request.endpoint in ("home", "setup_page") and request.method == "GET":
            try:
                models.auto_download(cfg, prefs.get(conn(), "auto_models") != "off")
            except Exception:
                pass   # never let the AI setup break a page

    # ------------------------------------------------------------ follow-ups
    @app.get("/followups")
    def followups_page():
        c = conn()
        items = followups.upcoming(c)
        return render_template("followups.html", items=items, today=__import__("datetime").date.today().isoformat(),
                               review_url=prefs.get(c, "review_url"))

    @app.post("/followups/<int:fid>/draft")
    def followup_draft(fid):
        c = conn()
        try:
            followups.draft(get_model(), c, fid, cfg.business_phone)
        except ModelUnavailable:
            followups.draft(None, c, fid, cfg.business_phone)  # falls back to the plain template
        return redirect(url_for("followups_page") + f"#f{fid}")

    @app.post("/followups/<int:fid>/<status>")
    def followup_mark(fid, status):
        if status in ("sent", "skipped"):
            followups.mark(conn(), fid, status)
            flash("Marked " + status + ".")
        return redirect(url_for("followups_page"))

    # ------------------------------------------------------------ weekly report
    def _report(c, with_model):
        r = report.build(c)
        model = None
        if with_model:
            try:
                model = get_model()
            except ModelUnavailable:
                model = None
        text = report.render_text(r, report.opening(model, r))
        return r, text

    @app.get("/report")
    def report_page():
        c = conn()
        r, text = _report(c, with_model=False)
        return render_template("report.html", text=text, recipients=prefs.report_recipients(c), subject=report.subject(r))

    @app.post("/report/send")
    def report_send():
        c = conn()
        r, text = _report(c, with_model=True)
        try:
            to = report.send(c, cfg.mail.address, config.mail_password(cfg.mail.address), text, report.subject(r))
            flash("Sent to " + ", ".join(to) + ".")
        except (ValueError, RuntimeError, smtplib.SMTPException, OSError) as exc:
            flash(f"Not sent: {exc}", "error")
        return redirect(url_for("report_page"))

    @app.get("/margins")
    def margins_page():
        return render_template("margins.html", rows=margins.all_margins(conn()))
