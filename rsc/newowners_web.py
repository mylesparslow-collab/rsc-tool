"""New homeowners page: this month's buyers in our towns, a welcome letter for each, and a mailing list file."""
from datetime import date

from flask import Response, flash, redirect, render_template, request, url_for

from . import autocheck, newowners, prefs


def register(app, cfg, conn):
    def _filters():
        return request.values.get("grade", "B"), request.values.get("town", "")

    @app.get("/new-owners")
    def new_owners_page():
        c = conn()
        grade, town = _filters()
        rows = newowners.listing(c, "new", grade, town)
        last = prefs.get(c, newowners.LAST_KEY)
        return render_template("new_owners.html", rows=rows, grade=grade, town=town, towns=newowners.towns(c),
                               counts=newowners.counts(c), last_ago=autocheck.ago(last) if last else "",
                               last_message=prefs.get(c, newowners.LAST_MSG), due=newowners.due(c),
                               letter=newowners.letter_template(c), default_letter=newowners.DEFAULT_LETTER,
                               mailed=newowners.listing(c, "mailed")[:50])

    @app.post("/new-owners/refresh")
    def new_owners_refresh():
        try:
            msg = newowners.refresh(conn())
        except Exception as exc:      # the county server being down must never break the page
            msg = f"Couldn't check the county records right now ({exc}). Try again later."
        flash(msg)
        return redirect(url_for("new_owners_page"))

    @app.get("/new-owners/list.csv")
    def new_owners_csv():
        c = conn()
        grade, town = _filters()
        body = newowners.mailing_csv(c, newowners.listing(c, "new", grade, town))
        name = f"new-homeowners-{date.today().isoformat()}.csv"
        return Response(body, mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/new-owners/letters")
    def new_owners_letters():
        c = conn()
        grade, town = _filters()
        rows = newowners.listing(c, "new", grade, town)
        today_long = f"{date.today():%B} {date.today().day}, {date.today().year}"
        return render_template("new_owners_letters.html", items=[(r, newowners.letter(c, r)) for r in rows], today_long=today_long)

    @app.post("/new-owners/mark")
    def new_owners_mark():
        c = conn()
        status = request.form.get("status", "")
        keys = request.form.getlist("key")
        if request.form.get("all"):
            grade, town = _filters()
            keys = [r["key"] for r in newowners.listing(c, "new", grade, town)]
        try:
            n = newowners.set_status(c, keys, status)
        except ValueError:
            n = 0
        flash({"mailed": f"Marked {n} as mailed. They won't come up again.",
               "skip": f"Took {n} off the list.", "new": f"Put {n} back on the list."}.get(status, "Nothing changed."))
        return redirect(url_for("new_owners_page", grade=request.form.get("grade", "B"), town=request.form.get("town", "")))

    @app.post("/new-owners/letter")
    def new_owners_letter():
        c = conn()
        text = request.form.get("letter", "").strip()
        prefs.put(c, newowners.LETTER_KEY, "" if request.form.get("reset") or text == newowners.DEFAULT_LETTER.strip() else text)
        flash("Letter saved." if not request.form.get("reset") else "Letter set back to the original.")
        return redirect(url_for("new_owners_page") + "#letter")
