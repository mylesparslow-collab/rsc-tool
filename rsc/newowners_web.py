"""New homeowners page: this month's buyers in our towns, a welcome letter for each, and a mailing list file."""
import threading
from datetime import date

from flask import Response, flash, redirect, render_template, request, url_for

from . import autocheck, db, newowners, prefs

BATCHES = (25, 50, 100, 250, 0)    # letters per mailing; 0 = all
_running = threading.Lock()


def register(app, cfg, conn):
    def _filters():
        try:
            n = int(request.values.get("n", 50))
        except ValueError:
            n = 50
        return request.values.get("grade", "A"), request.values.get("town", ""), (n if n in BATCHES else 50)

    def _batch(c):
        grade, town, n = _filters()
        return newowners.listing(c, "new", grade, town, mailable=True, limit=n or None)

    def _check_in_background():
        try:
            c = db.connect(cfg.db_path)
            try:
                newowners.refresh(c)
            finally:
                c.close()
        except Exception as exc:      # the county server being down must never break the app
            c = db.connect(cfg.db_path)
            prefs.put(c, newowners.LAST_MSG, f"Couldn't check the county records ({exc}). Try again later.")
            c.close()
        finally:
            _running.release()

    @app.get("/new-owners")
    def new_owners_page():
        c = conn()
        grade, town, n = _filters()
        last = prefs.get(c, newowners.LAST_KEY)
        return render_template("new_owners.html", rows=_batch(c), grade=grade, town=town, n=n, batches=BATCHES,
                               towns=newowners.towns(c), counts=newowners.counts(c), no_zip=newowners.no_zip(c),
                               matching=len(newowners.listing(c, "new", grade, town, mailable=True)),
                               last_ago=autocheck.ago(last) if last else "", last_message=prefs.get(c, newowners.LAST_MSG),
                               due=newowners.due(c), checking=_running.locked(),
                               letter=newowners.letter_template(c), default_letter=newowners.DEFAULT_LETTER,
                               mailed=newowners.listing(c, "mailed", limit=50))

    @app.post("/new-owners/refresh")
    def new_owners_refresh():
        if _running.acquire(blocking=False):
            threading.Thread(target=_check_in_background, daemon=True, name="rsc-new-owners").start()
            flash("Reading the county records. This takes about 5 to 10 minutes; you can keep using the app.")
        else:
            flash("Already checking. This page shows the result when it's done.")
        return redirect(url_for("new_owners_page"))

    @app.get("/new-owners/list.csv")
    def new_owners_csv():
        c = conn()
        body = newowners.mailing_csv(c, _batch(c))
        name = f"new-homeowners-{date.today().isoformat()}.csv"
        return Response(body, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/new-owners/letters")
    def new_owners_letters():
        c = conn()
        today_long = f"{date.today():%B} {date.today().day}, {date.today().year}"
        return render_template("new_owners_letters.html", items=[(r, newowners.letter(c, r)) for r in _batch(c)], today_long=today_long)

    @app.post("/new-owners/mark")
    def new_owners_mark():
        c = conn()
        status = request.form.get("status", "")
        keys = request.form.getlist("key")
        if request.form.get("all"):
            keys = [r["key"] for r in _batch(c)]
        try:
            n = newowners.set_status(c, keys, status)
        except ValueError:
            n = 0
        flash({"mailed": f"Marked {n} as mailed. They won't come up again.",
               "skip": f"Took {n} off the list.", "new": f"Put {n} back on the list."}.get(status, "Nothing changed."))
        grade, town, n_ = _filters()
        return redirect(url_for("new_owners_page", grade=grade, town=town, n=n_))

    @app.post("/new-owners/letter")
    def new_owners_letter():
        c = conn()
        text = request.form.get("letter", "").strip()
        prefs.put(c, newowners.LETTER_KEY, "" if request.form.get("reset") or text == newowners.DEFAULT_LETTER.strip() else text)
        flash("Letter saved." if not request.form.get("reset") else "Letter set back to the original.")
        return redirect(url_for("new_owners_page") + "#letter")
