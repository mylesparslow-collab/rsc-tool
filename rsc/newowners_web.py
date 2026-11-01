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
        """This week's mail: follow-up cards that are due, then new welcome cards up to the batch size."""
        grade, town, n = _filters()
        return newowners.this_weeks_mail(c, n or None, grade, town)

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
                               letters={k: newowners.letter_template(c, k) for k in (1, 2, 3)},
                               default_letters=newowners.DEFAULT_CARDS, card_names=newowners.CARD_NAMES,
                               next_card=newowners.next_card, seq=newowners.sequence_counts(c),
                               mailed=newowners.in_the_mail(c), short_link=newowners.SHORT_LINK)

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
        rows = _batch(c)
        newowners.ensure_codes(c, [r["key"] for r in rows])     # each card carries its own code for the welcome page
        rows = [c.execute("SELECT * FROM new_owners WHERE key = ?", (r["key"],)).fetchone() for r in rows]
        items = [(r, newowners.letter(c, r), newowners.next_card(r), newowners.qr_svg(newowners.card_link(r))) for r in rows]
        return render_template("new_owners_letters.html", items=items, today_long=today_long,
                               card_names=newowners.CARD_NAMES, short_link=newowners.SHORT_LINK)

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
        flash({"mailed": f"Marked {n} as mailed. Each one's next card comes up here on its own when it's due.",
               "replied": f"Marked {n} as got in touch. No more cards go to them.",
               "skip": f"Took {n} off the list.", "new": f"Put {n} back on the list."}.get(status, "Nothing changed."))
        grade, town, n_ = _filters()
        return redirect(url_for("new_owners_page", grade=grade, town=town, n=n_))

    @app.post("/new-owners/letter")
    def new_owners_letter():
        c = conn()
        try:
            card = int(request.form.get("card", 1))
        except ValueError:
            card = 1
        card = card if card in newowners.DEFAULT_CARDS else 1
        text = request.form.get("letter", "").strip()
        prefs.put(c, newowners.card_key(card),
                  "" if request.form.get("reset") or text == newowners.DEFAULT_CARDS[card].strip() else text)
        flash(f"{newowners.CARD_NAMES[card]} card saved." if not request.form.get("reset") else "Card set back to the original.")
        return redirect(url_for("new_owners_page") + "#letter")
