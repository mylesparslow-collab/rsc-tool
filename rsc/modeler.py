"""A room model for each job: wall sizes, windows and doors saved with the job, drawn as a plan and a 3D view
in the browser. Nothing here talks to the internet or to any AI service."""
import json
from datetime import date

from flask import Response, abort, jsonify, render_template, request

from . import books

MAX_BYTES = 80_000
MAX_ROOMS = 12
MAX_PHOTO = 4_000_000
KINDS = {"before", "after"}
WALLS = {"N", "E", "S", "W"}
TYPES = {"window", "door"}


def _num(value, name, low=0.0, high=100_000.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{name} is out of range")
    return float(value)


def _room(raw: dict) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("open"), list) or len(raw["open"]) > 100:
        raise ValueError("bad room")
    room = {k: _num(raw.get(k), k, low=1.0) for k in ("w", "d", "h", "t")}
    room.update(x=_num(raw.get("x", 0), "x", low=-100_000.0), y=_num(raw.get("y", 0), "y", low=-100_000.0),
                id=int(_num(raw.get("id", 1), "id", high=1_000_000)), name=str(raw.get("name", ""))[:40], open=[])
    for o in raw["open"]:
        if not isinstance(o, dict) or o.get("type") not in TYPES or o.get("wall") not in WALLS:
            raise ValueError("bad opening")
        item = {k: _num(o.get(k), k) for k in ("off", "w", "h", "sill")}
        item.update(id=int(_num(o.get("id"), "id", high=1_000_000)), type=o["type"], wall=o["wall"])
        room["open"].append(item)
    return room


def _fin(raw) -> dict:
    from .modeler_palette import PALETTE
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for key, names in PALETTE.items():
        cur = raw.get(key) if isinstance(raw.get(key), dict) else {}
        name = cur.get("name") if cur.get("name") in names else names[0]
        out[key] = {"name": name, "note": str(cur.get("note", ""))[:60]}
    return out


def clean(raw: str) -> dict:
    """Check and normalise a model sent by the browser. Raises ValueError if it is not a valid model.
    Version 1 (one room, fields at the top level) is converted to version 2 (a list of rooms)."""
    if len(raw.encode()) > MAX_BYTES:
        raise ValueError("model is too large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("not a room model")
    if isinstance(data.get("rooms"), list):
        if not 1 <= len(data["rooms"]) <= MAX_ROOMS:
            raise ValueError("wrong number of rooms")
        rooms = [_room(r) for r in data["rooms"]]
        ids = [r["id"] for r in rooms]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate room ids")
        sel = data.get("sel") if data.get("sel") in ids else ids[0]
        fin = _fin(data.get("fin"))
        next_open = int(_num(data.get("nextOpen", 1), "nextOpen", high=1_000_000))
        next_room = int(_num(data.get("nextRoom", 1), "nextRoom", high=1_000_000))
    else:
        data = dict(data, id=1, name="Room 1")
        rooms = [_room(data)]
        sel, fin = 1, _fin(None)
        next_open, next_room = int(_num(data.get("next", 1), "next", high=1_000_000)), 2
    return {"v": 2, "rooms": rooms, "sel": sel, "fin": fin, "nextOpen": next_open, "nextRoom": next_room}


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS job_models (
        job_number INTEGER PRIMARY KEY REFERENCES jobs(number),
        model      TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS job_photos (
        job_number INTEGER NOT NULL REFERENCES jobs(number),
        kind       TEXT NOT NULL,
        mime       TEXT NOT NULL,
        data       BLOB NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (job_number, kind))""")


def sniff(data: bytes):
    """The image type from its first bytes, or None. The browser's claim about the file is not trusted."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def register(app, conn):
    """Add the model pages to the app. `conn` is the app's per-request database getter."""

    def job_or_404(c, number):
        job = books.get_job(c, number)
        if not job:
            abort(404)
        ensure_table(c)
        return job

    @app.get("/models")
    def room_models():
        """Every job with its room model, so a model can be opened or started from the dashboard."""
        c = conn()
        ensure_table(c)
        saved = {r[0]: (json.loads(r[1]), r[2]) for r in c.execute("SELECT job_number, model, updated_at FROM job_models")}
        photos = {}
        for n, k in c.execute("SELECT job_number, COUNT(*) FROM job_photos GROUP BY job_number"):
            photos[n] = k
        rows = []
        for j in books.list_jobs(c):
            state, updated = saved.get(j["number"], (None, None))
            rows.append({"job": j, "rooms": len(state["rooms"]) if state else 0, "photos": photos.get(j["number"], 0),
                         "updated": (updated or "")[:10]})
        rows.sort(key=lambda r: (r["rooms"] == 0 and r["photos"] == 0, r["job"]["status"] not in books.ACTIVE, -r["job"]["number"]))
        return render_template("models.html", rows=rows)

    @app.get("/jobs/<int:number>/model")
    def job_model(number):
        c = conn()
        job = job_or_404(c, number)
        row = c.execute("SELECT model FROM job_models WHERE job_number = ?", (number,)).fetchone()
        photos = {r[0]: True for r in c.execute("SELECT kind FROM job_photos WHERE job_number = ?", (number,))}
        return render_template("job_model.html", job=job, state=json.loads(row[0]) if row else None,
                               photos={k: photos.get(k, False) for k in KINDS},
                               present=request.args.get("view") == "client", today=date.today().strftime("%B %-d, %Y"))

    @app.post("/jobs/<int:number>/model")
    def job_model_save(number):
        c = conn()
        job_or_404(c, number)
        try:
            model = clean(request.form.get("model", ""))
        except (ValueError, TypeError):
            return jsonify(ok=False, error="That model could not be read."), 400
        c.execute("""INSERT INTO job_models (job_number, model) VALUES (?, ?)
                     ON CONFLICT(job_number) DO UPDATE SET model = excluded.model, updated_at = datetime('now')""",
                  (number, json.dumps(model)))
        c.commit()
        return jsonify(ok=True)

    @app.get("/jobs/<int:number>/model/photo/<kind>")
    def job_photo(number, kind):
        if kind not in KINDS:
            abort(404)
        c = conn()
        job_or_404(c, number)
        row = c.execute("SELECT mime, data FROM job_photos WHERE job_number = ? AND kind = ?", (number, kind)).fetchone()
        if not row:
            abort(404)
        return Response(row[1], mimetype=row[0], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})

    @app.post("/jobs/<int:number>/model/photo/<kind>")
    def job_photo_save(number, kind):
        if kind not in KINDS:
            abort(404)
        c = conn()
        job_or_404(c, number)
        upload = request.files.get("file")
        data = upload.read(MAX_PHOTO + 1) if upload else b""
        mime = sniff(data)
        if not data or len(data) > MAX_PHOTO or not mime:
            return jsonify(ok=False, error="Use a JPEG, PNG or WebP picture under 4 MB."), 400
        c.execute("""INSERT INTO job_photos (job_number, kind, mime, data) VALUES (?, ?, ?, ?)
                     ON CONFLICT(job_number, kind) DO UPDATE SET mime = excluded.mime, data = excluded.data,
                     updated_at = datetime('now')""", (number, kind, mime, data))
        c.commit()
        return jsonify(ok=True)

    @app.post("/jobs/<int:number>/model/photo/<kind>/delete")
    def job_photo_delete(number, kind):
        if kind not in KINDS:
            abort(404)
        c = conn()
        job_or_404(c, number)
        c.execute("DELETE FROM job_photos WHERE job_number = ? AND kind = ?", (number, kind))
        c.commit()
        return jsonify(ok=True)
