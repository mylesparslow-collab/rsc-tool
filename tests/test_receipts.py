import email.message

from rsc import books, pipeline, receipts
from rsc.mail import parse

from .conftest import FakeModel
from .test_assist import web

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 6000


class Vision:
    def __init__(self, **fields):
        self.fields = {"is_receipt": True, "vendor": "Lowe's", "date": "2026-10-08", "total": 87.45,
                       "description": "deck screws", "category": "Materials", "job_clue": "", **fields}
        self.images = []

    def extract(self, system, user, schema, images=None):
        self.images.append(images)
        return self.fields


def test_photo_is_read_and_adds_nothing_until_confirmed(cfg, conn):
    books.create_job(conn, "Smith")
    vision = Vision(job_clue="Smith")
    c, tok = web(cfg, FakeModel({}))
    c.application.view_functions  # app built
    from rsc.web import create_app
    app = create_app(cfg, model=FakeModel({}), vision=vision)
    app.testing = True
    c = app.test_client()
    import re
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', c.get("/expenses").get_data(as_text=True)).group(1)
    page = c.post("/expenses/photo", data={"csrf": tok, "photo": (__import__("io").BytesIO(JPEG), "r.jpg"), "typed": "for Smith"},
                  content_type="multipart/form-data").get_data(as_text=True)
    assert 'value="87.45"' in page and "photo_token" in page and vision.images[0] == [JPEG]
    assert books.list_expenses(conn) == []
    token = re.search(r'name="photo_token" value="([0-9a-f]+)"', page).group(1)
    c.post("/expenses", data={"csrf": tok, "charge_to": "1001", "date": "2026-10-08", "amount": "87.45",
                              "vendor": "Lowe's", "description": "screws", "category": "", "paid_with": "", "notes": "",
                              "photo_token": token})
    e = books.list_expenses(conn)[0]
    assert receipts.photo_for(conn, e["id"])[1] == JPEG
    assert c.get(f"/expenses/{e['id']}/photo").data == JPEG
    assert c.get("/expenses/9999/photo").status_code == 404


def test_non_photo_is_refused(cfg, conn):
    assert not _ok(receipts.check_photo, b"not an image")


def _ok(fn, *a):
    try:
        fn(*a)
        return True
    except receipts.NotAPhoto:
        return False


def test_not_a_receipt_gives_nothing(conn):
    assert receipts.read_photo(Vision(is_receipt=False), conn, JPEG) == {}


def test_emailed_photo_becomes_a_suggestion_with_the_photo_kept(conn, cfg):
    books.create_job(conn, "Smith")
    msg = email.message.EmailMessage()
    msg["From"] = "Nick <nfparslow@gmail.com>"
    msg["To"] = "nfparslow@gmail.com"
    msg["Subject"] = "receipt for Smith"
    msg["Message-ID"] = "<photo1@x>"
    msg["Date"] = "Wed, 08 Oct 2026 10:00:00 -0400"
    msg.set_content("here")
    msg.add_attachment(JPEG, maintype="image", subtype="jpeg", filename="r.jpg")
    mail = parse(msg.as_bytes())
    assert mail.attachment_images == [JPEG]
    report = pipeline.process(conn, cfg, [mail], FakeModel({}), Vision())
    assert report.suggestions == 1
    s = pipeline.pending(conn)[0]
    assert s["kind"] == "expense" and s["data"]["amount"] == 87.45
    pipeline.approve(conn, s["id"], {"charge_to": "1001"})
    assert receipts.photo_for(conn, books.list_expenses(conn)[0]["id"]) is not None
