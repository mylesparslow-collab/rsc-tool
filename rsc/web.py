"""The app Nick uses, in his browser at http://localhost:5151. Only reachable from his own computer."""
import fcntl
import hmac
import secrets
import sqlite3
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for

from . import receivables, receivables_web, client_update_web, schedule_web, brand, daily_web, guide, playbook_web, aging_web, assist, backup, books, crew, crew_web, db, estimates, followups, margins, modeler, models, ops_web, pipeline, qb_web, receipts, sheets, voice, workflow
from .config import Config, mail_password
from .llm import ModelUnavailable, OllamaModel
from .mail import GmailReader


def run_mail_check(cfg: Config) -> pipeline.RunReport:
    """Used by the button and by the scheduled `rsc check-mail`. One run at a time, across processes."""
    lock = open(cfg.home / ".mail-check.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError("Already checking email")
    try:
        conn = db.connect(cfg.db_path)
        try:
            models.apply_choice(cfg)
            model = OllamaModel(cfg.model.url, cfg.model.name, cfg.model.timeout_seconds)
            model.check()
            vision = None
            if cfg.model.vision:  # photos attached to emails; without this model they are simply skipped
                vision = OllamaModel(cfg.model.url, cfg.model.vision, cfg.model.timeout_seconds)
                try:
                    vision.check()
                except ModelUnavailable:
                    vision = None
            reader = GmailReader(cfg.mail.address, mail_password(cfg.mail.address), cfg.mail.host)
            return pipeline.check_mail(conn, cfg, reader, model, vision)
        finally:
            conn.close()
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


_LOGIN_FAILS: dict[str, list[float]] = {}
LOGIN_MAX_FAILS, LOGIN_WINDOW = 5, 300


def create_app(cfg: Config, lan: bool = False, model=None, vision=None) -> Flask:
    """`lan=True` is for opening the app from a phone on the same Wi-Fi: everything then needs the access PIN."""
    if lan and len(cfg.access_pin) < 6:
        raise ValueError("Phone access needs access_pin (6 or more characters) in config.toml")
    if cfg.access_pin and len(cfg.access_pin) < 6:
        raise ValueError("access_pin in config.toml needs 6 or more characters")
    lan = lan or bool(cfg.access_pin)  # a PIN in config.toml always turns the PIN gate on (Tailscale, phone, anything)
    app = Flask(__name__)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # photo uploads are capped at 4 MB each by the modeler
    conn0 = db.connect(cfg.db_path)
    db.init(conn0, cfg.first_job_number)
    brand.use(conn0, cfg)
    try:
        backup.run(cfg.db_path, cfg.home)  # one safe copy a day, keeps 30
    except (OSError, sqlite3.Error):
        pass
    row = conn0.execute("SELECT value FROM settings WHERE key = 'secret_key'").fetchone()
    if not row:
        conn0.execute("INSERT INTO settings VALUES ('secret_key', ?)", (secrets.token_hex(32),))
        conn0.commit()
        row = conn0.execute("SELECT value FROM settings WHERE key = 'secret_key'").fetchone()
    app.secret_key = row[0]
    conn0.close()
    app.config["RSC"] = cfg
    app.config["MAIL_STATUS"] = {"running": False, "message": ""}

    def conn():
        if "db" not in g:
            g.db = db.connect(cfg.db_path)
        return g.db

    @app.teardown_appcontext
    def _close(_exc):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    @app.before_request
    def _csrf():
        session.setdefault("csrf", secrets.token_hex(16))
        if request.method == "POST" and request.form.get("csrf") != session["csrf"]:
            abort(400, "Form expired. Go back, reload the page and try again.")

    @app.before_request
    def _pin_gate():
        if not lan or request.endpoint in ("login", "static") or session.get("auth"):
            return None
        if request.method == "POST":
            abort(403)
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not lan:
            return redirect(url_for("home"))
        if request.method == "POST":
            who = request.remote_addr or "?"
            now = time.time()
            recent = [t for t in _LOGIN_FAILS.get(who, []) if now - t < LOGIN_WINDOW]
            if len(recent) >= LOGIN_MAX_FAILS:
                return render_template("login.html", error="Too many tries. Wait a few minutes."), 429
            if hmac.compare_digest(request.form.get("pin", "").encode(), cfg.access_pin.encode()):
                _LOGIN_FAILS.pop(who, None)
                session["auth"] = True
                return redirect(url_for("home"))
            _LOGIN_FAILS[who] = recent + [now]
            return render_template("login.html", error="That PIN isn't right."), 401
        return render_template("login.html", error="")

    @app.context_processor
    def _globals():
        return {"csrf": session.get("csrf", ""), "review_count": len(pipeline.pending(conn())),
                "mail_status": app.config["MAIL_STATUS"], "voice_ready": voice.available(),
                "biz": brand.current(), "address_line": brand.address_line(), "today": date.today().isoformat(),
                "money": lambda v: "" if v is None else (f"-${-v:,.2f}" if v < 0 else f"${v:,.2f}")}

    modeler.register(app, conn)
    def get_model():
        """The local model for typed-in text. `model` lets tests pass a stand-in."""
        if model is not None:
            return model
        models.apply_choice(cfg)
        m = OllamaModel(cfg.model.url, cfg.model.name, cfg.model.timeout_seconds)
        m.check()
        return m

    def get_vision_model():
        """The local model that reads photos. `vision` lets tests pass a stand-in."""
        if vision is not None:
            return vision
        models.apply_choice(cfg)
        if not cfg.model.vision:
            raise ModelUnavailable("No photo-reading model is set up. Run: rsc models --pull")
        m = OllamaModel(cfg.model.url, cfg.model.vision, cfg.model.timeout_seconds)
        m.check()
        return m

    workflow.register(app, conn, get_model)
    qb_web.register(app, cfg, conn)
    ops_web.register(app, cfg, conn, get_model)
    aging_web.register(app, conn, get_model)
    playbook_web.register(app, conn)
    daily_web.register(app, cfg, conn)
    receivables_web.register(app, cfg, conn, get_model)
    client_update_web.register(app, cfg, conn, get_model)
    schedule_web.register(app, cfg, conn)
    crew_web.register(app, cfg, conn, get_model, get_vision_model)

    def _form(*names):
        return {n: request.form.get(n, "").strip() for n in names}

    def _num(value):
        return float(value.replace("$", "").replace(",", "")) if value else None

    # ------------------------------------------------------------ home
    @app.get("/")
    def home():
        c = conn()
        last = c.execute("SELECT value FROM settings WHERE key = 'last_mail_report'").fetchone()
        return render_template("home.html", jobs=books.list_jobs(c, active_only=True),
                               open_payments=books.list_payments(c, open_only=True)[:15],
                               last_report=last[0] if last else "", next_number=books.next_job_number(c),
                               watch=[m for m in margins.all_margins(c) if m["status"] != "ok" and m["job"]["status"] != "Complete"],
                               due_followups=followups.due(c), late_invoices=[r for r in receivables.outstanding(c) if r["needs_reminder"]],
                               next_steps=[{"job": j, "step": guide.next_step(c, j)} for j in books.list_jobs(c, active_only=True)[:6]
                                           if guide.next_step(c, j)][:4],
                               all_jobs_count=len(books.list_jobs(c)))

    @app.post("/check-mail")
    def check_mail():
        status = app.config["MAIL_STATUS"]
        if status["running"]:
            flash("Already checking email.")
            return redirect(url_for("home"))

        def work():
            status.update(running=True, message="Checking email...")
            try:
                status["message"] = run_mail_check(cfg).summary()
            except Exception as exc:
                status["message"] = f"Email check failed: {exc}"
            finally:
                status["running"] = False

        threading.Thread(target=work, daemon=True).start()
        flash("Checking email now. New items will show up under To Review.")
        return redirect(url_for("home"))

    # ------------------------------------------------------------ review
    @app.get("/review")
    def review():
        c = conn()
        return render_template("review.html", items=pipeline.pending(c), jobs=books.list_jobs(c),
                               codes=books.list_rsc_codes(c), payments=books.list_payments(c, open_only=True),
                               categories=books.EXPENSE_CATEGORIES, paid_with=books.PAID_WITH)

    @app.post("/review/<int:sid>")
    def review_decide(sid):
        c = conn()
        try:
            if request.form.get("action") == "dismiss":
                pipeline.dismiss(c, sid)
                flash("Skipped.")
            else:
                edits = {k: v.strip() for k, v in request.form.items() if k not in ("csrf", "action")}
                if "amount" in edits:
                    edits["amount"] = _num(edits["amount"])
                flash(pipeline.approve(c, sid, edits))
        except (books.BooksError, ValueError) as exc:
            flash(f"Not saved: {exc}", "error")
        return redirect(url_for("review"))

    # ------------------------------------------------------------ jobs
    @app.get("/jobs")
    def jobs():
        return render_template("jobs.html", jobs=books.list_jobs(conn()))

    @app.route("/jobs/new", methods=["GET", "POST"])
    def job_new():
        c = conn()
        if request.method == "POST":
            about = request.form.get("about", "").strip()
            if about:  # the easy way: the model reads it, makes the job, and drafts the estimate
                try:
                    f = assist.parse_job(get_model(), about)
                except (ModelUnavailable, ValueError) as exc:
                    flash(f"The assistant isn't available ({exc}). Fill in the form below instead.", "error")
                    return redirect(url_for("job_new"))
                if not f["last_name"]:
                    flash("I couldn't find the client's name. Add it to what you typed, or fill in the form below.", "error")
                    return redirect(url_for("job_new"))
                notes = f.pop("notes")
            else:
                f, notes = _form("last_name", "first_name", "phone", "email", "address", "job_type"), request.form.get("notes", "").strip()
            try:
                number = books.create_job(c, f.pop("last_name"), status="Estimate", estimate_sent=None, notes=notes, **f)
            except (books.BooksError, ValueError) as exc:
                flash(f"Not saved: {exc}", "error")
                return redirect(url_for("job_new"))
            job = books.get_job(c, number)
            if about:
                try:
                    assist.apply_draft(c, number, assist.draft_estimate(get_model(), c, job, about))
                    flash(f"Job {job['job_id']} started and the estimate is drafted. Check the numbers below.")
                except (ModelUnavailable, ValueError, books.BooksError) as exc:
                    flash(f"Job {job['job_id']} started, but the estimate draft failed ({exc}). Try again here.", "error")
                return redirect(url_for("estimate_edit", number=number))
            flash(f"Job {job['job_id']} started.")
            return redirect(url_for("job_detail", number=number))
        return render_template("job_new.html", next_number=books.next_job_number(c), job_types=books.JOB_TYPES)

    @app.route("/jobs/<int:number>", methods=["GET", "POST"])
    def job_detail(number):
        c = conn()
        job = books.get_job(c, number)
        if not job:
            abort(404)
        if request.method == "POST":
            f = _form("first_name", "phone", "email", "address", "job_type", "status", "estimate_sent",
                      "contract_signed", "contract_total", "notes")
            try:
                f["contract_total"] = _num(f["contract_total"])
                books.update_job(c, number, **f)
                flash("Saved.")
            except ValueError as exc:
                flash(f"Not saved: {exc}", "error")
            return redirect(url_for("job_detail", number=number))
        return render_template("job_detail.html", job=job, payments=books.list_payments(c, number),
                               expenses=books.list_expenses(c, number), statuses=books.STATUSES,
                               job_types=books.JOB_TYPES, job_hours=crew.recent_hours(c, 8, number), guide_steps=guide.steps(c, job), guide_next=guide.next_step(c, job),
                               job_hours_total=crew.hours_for_job(c, number), job_labor_cost=crew.labor_cost_for_job(c, number))

    @app.post("/jobs/<int:number>/payments")
    def payment_add(number):
        f = _form("description", "due_when", "amount")
        try:
            seq = books.add_payment(conn(), number, _num(f["amount"]) or 0, f["description"], f["due_when"])
            flash(f"Payment {seq} added.")
        except (books.BooksError, ValueError) as exc:
            flash(f"Not saved: {exc}", "error")
        return redirect(url_for("job_detail", number=number) + "#payments")

    @app.post("/payments/<int:pk>")
    def payment_update(pk):
        c = conn()
        row = c.execute("SELECT job_number FROM payments WHERE id = ?", (pk,)).fetchone()
        if not row:
            abort(404)
        f = _form("invoice_sent", "date_paid", "amount_paid")
        try:
            f["amount_paid"] = _num(f["amount_paid"]) if f["amount_paid"] else ""
            books.update_payment(c, pk, **f)
            flash("Payment updated.")
        except ValueError as exc:
            flash(f"Not saved: {exc}", "error")
        return redirect(url_for("job_detail", number=row[0]) + "#payments")

    # ------------------------------------------------------------ expenses
    def _expenses_page(prefill=None, note="", typed=""):
        c = conn()
        return render_template("expenses.html", expenses=books.list_expenses(c), jobs=books.list_jobs(c),
                               codes=books.list_rsc_codes(c), categories=books.EXPENSE_CATEGORIES,
                               paid_with=books.PAID_WITH, prefill=prefill, prefill_note=note, typed=typed,
                               photos=receipts.expenses_with_photos(c))

    @app.route("/expenses", methods=["GET", "POST"])
    def expenses():
        c = conn()
        if request.method == "POST":
            f = _form("date", "charge_to", "vendor", "description", "category", "amount", "paid_with", "notes")
            try:
                expense_id = books.add_expense(c, f["date"], f["charge_to"], _num(f["amount"]) or 0, f["vendor"],
                                               f["description"], f["category"], f["paid_with"], f["notes"])
                token = request.form.get("photo_token", "")
                if token:
                    receipts.attach(c, token, expense_id)
                flash("Expense added.")
            except (books.BooksError, ValueError) as exc:
                flash(f"Not saved: {exc}", "error")
            return redirect(url_for("expenses"))
        return _expenses_page()

    @app.post("/expenses/read")
    def expenses_read():
        typed = request.form.get("typed", "").strip()
        if not typed:
            return redirect(url_for("expenses"))
        try:
            found = assist.parse_expense(get_model(), conn(), typed)
        except (ModelUnavailable, ValueError) as exc:
            flash(f"The assistant isn't available ({exc}). Use the form instead.", "error")
            return _expenses_page(typed=typed)
        if not found:
            flash("I couldn't find an amount in that. Include the total, like: Home Depot 109.91 studs for Smith.", "error")
            return _expenses_page(typed=typed)
        return _expenses_page(prefill=found, note=found.pop("note", ""))

    @app.post("/expenses/photo")
    def expenses_photo():
        """A photo of a receipt, snapped or saved from a text message. Read by the local vision model."""
        shot = request.files.get("photo")
        hint = request.form.get("typed", "").strip()
        try:
            data = shot.read() if shot else b""
            mime = receipts.check_photo(data)
            found = receipts.read_photo(get_vision_model(), conn(), data, hint)
        except receipts.NotAPhoto as exc:
            flash(str(exc), "error")
            return _expenses_page(typed=hint)
        except (ModelUnavailable, ValueError) as exc:
            flash(f"The photo reader isn't available ({exc}). Type the receipt instead.", "error")
            return _expenses_page(typed=hint)
        if not found:
            flash("I couldn't read a total on that photo. Try a closer, flatter shot, or type the receipt.", "error")
            return _expenses_page(typed=hint)
        found["photo_token"] = receipts.save_photo(conn(), data, mime)
        return _expenses_page(prefill=found, note=found.pop("note", ""))

    @app.get("/expenses/<int:expense_id>/photo")
    def expense_photo(expense_id):
        got = receipts.photo_for(conn(), expense_id)
        if not got:
            abort(404)
        resp = send_file(__import__("io").BytesIO(got[1]), mimetype=got[0])
        resp.headers["Content-Security-Policy"] = "default-src 'none'"
        return resp

    @app.post("/voice")
    def voice_text():
        """A short recording in, the words out. The browser puts them in the box the person was talking to."""
        clip = request.files.get("audio")
        if not clip:
            return jsonify(error="No recording came through."), 400
        suffix = ".mp4" if "mp4" in (clip.mimetype or "") else ".ogg" if "ogg" in (clip.mimetype or "") else ".webm"
        try:
            text = voice.transcribe(clip.read(), cfg.voice.model, cfg.voice_cache, suffix)
        except voice.VoiceUnavailable as exc:
            return jsonify(error=str(exc)), 503
        except Exception as exc:  # a bad clip or a failed first download should not take the page down
            return jsonify(error=f"Couldn't understand the recording ({exc}). Try again, or type it."), 500
        return jsonify(text=text)

    @app.get("/codes")
    def codes():
        return render_template("codes.html", codes=books.list_rsc_codes(conn()))

    @app.get("/export")
    def export():
        out = Path(tempfile.mkdtemp()) / f"RSC Books {date.today().isoformat()}.xlsx"
        sheets.export(conn(), out)
        return send_file(out, as_attachment=True, download_name=out.name)

    return app
