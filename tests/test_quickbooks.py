import csv
import io
import json
import re
import urllib.parse

import pytest

from rsc import books, models, qbo, quickbooks
from rsc.config import Config
from rsc.web import create_app

from .conftest import FakeModel


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_invoice_csv_uses_payment_id_as_invoice_number(conn, smith):
    out = rows(quickbooks.invoices_csv(conn))
    assert [r["InvoiceNo"] for r in out] == ["1001-SMI-1", "1001-SMI-2", "1001-SMI-3"]
    assert out[0]["Customer"] == "Jane Smith" and out[0]["ItemAmount"] == "5000.00"
    pid = conn.execute("SELECT id FROM payments WHERE seq = 1").fetchone()[0]
    conn.execute("UPDATE payments SET amount_paid = 5000, date_paid = '2026-10-01' WHERE id = ?", (pid,))
    assert len(rows(quickbooks.invoices_csv(conn))) == 2
    assert len(rows(quickbooks.invoices_csv(conn, open_only=False))) == 3


def test_expense_and_customer_csv(conn, smith):
    books.add_expense(conn, "2026-10-05", str(smith), 109.91, "Home Depot", "studs", "Materials", "", source="manual")
    e = rows(quickbooks.expenses_csv(conn))[0]
    assert e["Amount"] == "-109.91" and "Home Depot" in e["Description"] and "[1001]" in e["Description"]
    assert rows(quickbooks.customers_csv(conn))[0]["Customer"] == "Jane Smith"


def test_models_recommend_by_memory():
    assert models.recommend(8)["text"] == models.TEXT_SMALL and models.recommend(8)["vision"] == models.VISION_SMALL
    assert models.recommend(16)["text"] == models.TEXT_BIG and models.recommend(16)["vision"] == models.VISION_SMALL
    assert models.recommend(32)["vision"] == models.VISION_BIG


def test_models_status_when_ollama_is_off(cfg, monkeypatch):
    monkeypatch.setattr(models, "ollama_installed", lambda url: None)
    rows_ = models.status(cfg)
    assert [r["role"] for r in rows_] == ["text", "vision", "speech"] and not rows_[0]["ready"]
    assert models.ensure(cfg)[0].startswith("Ollama isn't running")


def test_models_ensure_pulls_only_what_is_missing(cfg, monkeypatch):
    cfg.model.vision = "qwen2.5vl:3b"
    pulled = []
    monkeypatch.setattr(models, "ollama_installed", lambda url: {cfg.model.name})
    monkeypatch.setattr(models, "pull_ollama", lambda url, name, say=print: pulled.append(name))
    from rsc import voice
    monkeypatch.setattr(voice, "available", lambda: False)   # on a Mac with voice installed this would download a real model
    models.ensure(cfg, say=lambda *_: None)
    assert pulled == ["qwen2.5vl:3b"]


class FakeQBO:
    """Stands in for Intuit: remembers what was created, answers the few queries the client makes."""

    def __init__(self):
        self.created, self.customers, self.invoices, self.estimates = [], {}, {}, {}

    def __call__(self, cfg, conn, method, path, body=None, query=None):
        if path == "query":
            sql = query["query"]
            if "from Customer" in sql:
                name = re.search(r"DisplayName = '(.*)'", sql).group(1)
                return {"QueryResponse": {"Customer": [{"Id": self.customers[name]}] if name in self.customers else []}}
            if "from Item" in sql:
                return {"QueryResponse": {"Item": [{"Id": "7"}]}}
            if "from Invoice" in sql:
                num = re.search(r"DocNumber = '(.*)'", sql).group(1)
                return {"QueryResponse": {"Invoice": [{"Id": self.invoices[num]}] if num in self.invoices else []}}
            if "from Estimate" in sql:
                num = re.search(r"DocNumber = '(.*)'", sql).group(1)
                return {"QueryResponse": {"Estimate": [{"Id": self.estimates[num]}] if num in self.estimates else []}}
        if path == "estimate":
            self.estimates[body["DocNumber"]] = str(300 + len(self.estimates))
            self.created.append(("estimate", body))
            return {"Estimate": {"Id": self.estimates[body["DocNumber"]]}}
        if path == "customer":
            self.customers[body["DisplayName"]] = str(100 + len(self.customers))
            return {"Customer": {"Id": self.customers[body["DisplayName"]]}}
        if path == "invoice":
            self.invoices[body["DocNumber"]] = str(500 + len(self.invoices))
            self.created.append(("invoice", body))
            return {"Invoice": {"Id": self.invoices[body["DocNumber"]]}}
        if path == "payment":
            self.created.append(("payment", body))
            return {"Payment": {"Id": "900"}}
        raise AssertionError(path)


def test_send_invoice_once_and_record_payment(cfg, conn, smith, monkeypatch):
    fake = FakeQBO()
    monkeypatch.setattr(qbo, "_call", fake)
    p = books.list_payments(conn)[0]
    first = qbo.send_invoice(cfg, conn, p, "Jane Smith")
    assert qbo.send_invoice(cfg, conn, p, "Jane Smith") == first
    assert [k for k, _ in fake.created] == ["invoice"]
    body = fake.created[0][1]
    assert body["DocNumber"] == "1001-SMI-1" and body["Line"][0]["Amount"] == 5000
    with pytest.raises(qbo.QBOError):
        qbo.record_payment(cfg, conn, p, "Jane Smith")  # nothing recorded here yet
    conn.execute("UPDATE payments SET amount_paid = 5000, date_paid = '2026-10-02' WHERE id = ?", (p["id"],))
    p = books.list_payments(conn)[0]
    assert qbo.record_payment(cfg, conn, p, "Jane Smith") == "900"
    assert fake.created[1][1]["Line"][0]["LinkedTxn"][0]["TxnId"] == first
    assert qbo.record_payment(cfg, conn, p, "Jane Smith") == "900" and len(fake.created) == 2


def test_existing_invoice_is_not_duplicated(cfg, conn, smith, monkeypatch):
    fake = FakeQBO()
    fake.invoices["1001-SMI-1"] = "42"
    monkeypatch.setattr(qbo, "_call", fake)
    assert qbo.send_invoice(cfg, conn, books.list_payments(conn)[0], "Jane Smith") == "42" and not fake.created


def test_send_estimate_one_line_per_payment_and_change_orders_apart(cfg, conn, smith, monkeypatch):
    fake = FakeQBO()
    monkeypatch.setattr(qbo, "_call", fake)
    job = books.get_job(conn, smith)
    assert qbo.send_estimates(cfg, conn, job, books.list_payments(conn, smith), "Jane Smith") == ["1001-SMI"]
    body = fake.created[0][1]
    assert body["DocNumber"] == "1001-SMI" and [ln["Amount"] for ln in body["Line"]] == [5000, 2500, 2500]
    assert body["Line"][1]["Description"] == "1001-SMI-2: Phase 1 (When Phase 1 is complete)"
    assert qbo.send_estimates(cfg, conn, job, books.list_payments(conn, smith), "Jane Smith") == []  # pressing twice
    books.add_payment(conn, smith, 800, "Change order 1: extra outlet", "With the next invoice", kind="change_order",
                      change_order_id=11)
    assert qbo.send_estimates(cfg, conn, job, books.list_payments(conn, smith), "Jane Smith") == ["1001-SMI-CO1"]
    co = fake.created[-1][1]
    assert [ln["Amount"] for ln in co["Line"]] == [800] and co["Line"][0]["Description"].startswith("1001-SMI-4:")
    assert [k for k, _ in fake.created] == ["estimate", "estimate"]
    assert qbo.estimates_synced(conn) == {smith: ["1001-SMI", "1001-SMI-CO1"]}


def test_existing_estimate_is_not_duplicated(cfg, conn, smith, monkeypatch):
    fake = FakeQBO()
    fake.estimates["1001-SMI"] = "77"
    monkeypatch.setattr(qbo, "_call", fake)
    job = books.get_job(conn, smith)
    assert qbo.send_estimates(cfg, conn, job, books.list_payments(conn, smith), "Jane Smith") == [] and not fake.created
    assert qbo.estimates_synced(conn) == {smith: ["1001-SMI"]}


def test_oauth_flow_and_pages(cfg, conn, smith, monkeypatch):
    cfg.quickbooks.client_id, cfg.quickbooks.client_secret = "id", "secret"
    app = create_app(cfg, model=FakeModel({}))
    app.testing = True
    c = app.test_client()
    html = c.get("/quickbooks").get_data(as_text=True)
    tok = re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)
    assert "Connect to QuickBooks" in html
    r = c.post("/quickbooks/connect", data={"csrf": tok})
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["Location"]).query)
    assert q["client_id"] == ["id"] and q["scope"] == [qbo.SCOPE]
    assert "Press Connect again" in c.get("/quickbooks/callback?code=x&state=wrong", follow_redirects=True).get_data(as_text=True)
    r = c.post("/quickbooks/connect", data={"csrf": tok})  # a bad attempt uses up the state; start again
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["Location"]).query)
    monkeypatch.setattr(qbo, "_token_request", lambda cfg, form: {"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    c.get(f"/quickbooks/callback?code=abc&realmId=123&state={q['state'][0]}")
    page = c.get("/quickbooks").get_data(as_text=True)
    assert "connected (sandbox)" in page and "1001-SMI-1" in page
    fake = FakeQBO()
    monkeypatch.setattr(qbo, "_call", fake)
    pk = books.list_payments(conn)[0]["id"]
    out = c.post(f"/quickbooks/send/{pk}", data={"csrf": tok}, follow_redirects=True).get_data(as_text=True)
    assert "1001-SMI-1 is in QuickBooks" in out and len(fake.created) == 1
    assert f"/quickbooks/estimate/{smith}" in out
    out = c.post(f"/quickbooks/estimate/{smith}", data={"csrf": tok}, follow_redirects=True).get_data(as_text=True)
    assert "Estimate 1001-SMI is in QuickBooks" in out and f"/quickbooks/estimate/{smith}" not in out
    assert c.post("/quickbooks/estimate/9999", data={"csrf": tok}).status_code == 404
    assert c.get("/quickbooks/invoices.csv").mimetype == "text/csv"


def test_bad_environment_rejected(tmp_path):
    from rsc import config
    (tmp_path / "config.toml").write_text('[quickbooks]\nenvironment = "prod"\n')
    with pytest.raises(ValueError):
        config.load(tmp_path)


def test_already_downloaded_models_are_kept():
    have = {"llama3.1:8b", "llama3.2-vision:latest"}
    pick = models.prefer_installed(models.recommend(8), have)
    assert pick["text"] == "llama3.1:8b" and pick["vision"] == "llama3.2-vision"
    assert models.prefer_installed(models.recommend(8), None) == models.recommend(8)
    assert models.prefer_installed(models.recommend(32), {"llama3.2:3b", "qwen2.5vl:3b"}) == models.recommend(32)
