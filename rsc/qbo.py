"""QuickBooks Online API: customers, invoices and payments, sent only when Nick presses a button.

Nothing here runs by itself. Setup (once, ~10 minutes): create an app at developer.intuit.com, put its Client ID and
Secret in config.toml under [quickbooks], add http://localhost:5151/quickbooks/callback (the port the app uses) as a Redirect URI, then press
"Connect" on the QuickBooks page. Start with environment = "sandbox" (a fake company) and switch to "production"
only after a test invoice looks right.

Sends are idempotent: an invoice is looked up by its number (the Payment ID) before it is created, and what was sent
is remembered, so pressing twice cannot make a duplicate.
"""
import base64
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API = {"sandbox": "https://sandbox-quickbooks.api.intuit.com", "production": "https://quickbooks.api.intuit.com"}
SCOPE = "com.intuit.quickbooks.accounting"
ITEM_NAME = "Remodeling Services"


class QBOError(Exception):
    pass


def configured(cfg) -> bool:
    return bool(cfg.quickbooks.client_id and cfg.quickbooks.client_secret)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS qb_sync (payment_pk INTEGER PRIMARY KEY, qb_invoice_id TEXT NOT NULL, "
                 "qb_payment_id TEXT, synced_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.execute("CREATE TABLE IF NOT EXISTS qb_estimates (doc_number TEXT PRIMARY KEY, job_number INTEGER NOT NULL, "
                 "qb_estimate_id TEXT NOT NULL, synced_at TEXT NOT NULL DEFAULT (datetime('now')))")


def _setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def _put(conn, key, value):
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))
    conn.commit()


def auth_url(cfg, state: str) -> str:
    q = cfg.quickbooks
    return AUTH_URL + "?" + urllib.parse.urlencode({"client_id": q.client_id, "response_type": "code", "scope": SCOPE,
                                                    "redirect_uri": cfg.qb_redirect_uri, "state": state})


def _token_request(cfg, form: dict) -> dict:
    q = cfg.quickbooks
    basic = base64.b64encode(f"{q.client_id}:{q.client_secret}".encode()).decode()
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), headers={
        "Authorization": f"Basic {basic}", "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise QBOError(f"QuickBooks refused the sign-in ({exc.code}). Connect again.") from exc
    except urllib.error.URLError as exc:
        raise QBOError(f"Couldn't reach QuickBooks ({exc.reason}).") from exc


def _store(conn, tok: dict) -> None:
    _put(conn, "qbo_access", tok["access_token"])
    _put(conn, "qbo_refresh", tok["refresh_token"])
    _put(conn, "qbo_expires", str(int(time.time()) + int(tok.get("expires_in", 3600)) - 60))


def connect(cfg, conn, code: str, realm: str) -> None:
    _store(conn, _token_request(cfg, {"grant_type": "authorization_code", "code": code,
                                      "redirect_uri": cfg.qb_redirect_uri}))
    _put(conn, "qbo_realm", realm)


def disconnect(conn) -> None:
    for k in ("qbo_access", "qbo_refresh", "qbo_expires", "qbo_realm"):
        conn.execute("DELETE FROM settings WHERE key = ?", (k,))
    conn.commit()


def connected(conn) -> bool:
    return bool(_setting(conn, "qbo_refresh") and _setting(conn, "qbo_realm"))


def _access(cfg, conn) -> str:
    if int(_setting(conn, "qbo_expires", "0") or 0) <= time.time():
        _store(conn, _token_request(cfg, {"grant_type": "refresh_token", "refresh_token": _setting(conn, "qbo_refresh")}))
    return _setting(conn, "qbo_access")


def _call(cfg, conn, method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
    url = f"{API[cfg.quickbooks.environment]}/v3/company/{_setting(conn, 'qbo_realm')}/{path}"
    url += "?" + urllib.parse.urlencode({**(query or {}), "minorversion": "70"})
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_access(cfg, conn)}", "Accept": "application/json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read())["Fault"]["Error"][0].get("Detail", "")
        except Exception:
            pass
        raise QBOError(f"QuickBooks said no ({exc.code}). {detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise QBOError(f"Couldn't reach QuickBooks ({exc.reason}).") from exc


def _query(cfg, conn, sql: str) -> list:
    out = _call(cfg, conn, "GET", "query", query={"query": sql}).get("QueryResponse", {})
    return next((v for v in out.values() if isinstance(v, list)), [])


def _q(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def customer_ref(cfg, conn, name: str, email: str = "") -> str:
    found = _query(cfg, conn, f"select Id from Customer where DisplayName = '{_q(name)}'")
    if found:
        return found[0]["Id"]
    body = {"DisplayName": name}
    if email:
        body["PrimaryEmailAddr"] = {"Address": email}
    return _call(cfg, conn, "POST", "customer", body)["Customer"]["Id"]


def item_ref(cfg, conn) -> str:
    found = _query(cfg, conn, f"select Id from Item where Name = '{ITEM_NAME}'")
    if found:
        return found[0]["Id"]
    income = _query(cfg, conn, "select Id from Account where AccountType = 'Income' maxresults 1")
    if not income:
        raise QBOError("QuickBooks has no income account to attach the service to. Add one there first.")
    return _call(cfg, conn, "POST", "item", {"Name": ITEM_NAME, "Type": "Service",
                                            "IncomeAccountRef": {"value": income[0]["Id"]}})["Item"]["Id"]


def send_invoice(cfg, conn, payment: dict, client_name: str, email: str = "") -> str:
    """Create the invoice for one payment on the schedule (or return the one already there). Returns QuickBooks' id."""
    ensure_tables(conn)
    done = conn.execute("SELECT qb_invoice_id FROM qb_sync WHERE payment_pk = ?", (payment["id"],)).fetchone()
    if done:
        return done[0]
    existing = _query(cfg, conn, f"select Id from Invoice where DocNumber = '{_q(payment['payment_id'])}'")
    if existing:
        inv = existing[0]["Id"]
    else:
        desc = f"{payment['description']} ({payment['due_when']})".strip(" ()")
        body = {"DocNumber": payment["payment_id"], "CustomerRef": {"value": customer_ref(cfg, conn, client_name, email)},
                "TxnDate": payment.get("invoice_sent") or time.strftime("%Y-%m-%d"),
                "Line": [{"Amount": round(payment["amount"], 2), "DetailType": "SalesItemLineDetail", "Description": desc,
                          "SalesItemLineDetail": {"ItemRef": {"value": item_ref(cfg, conn)}, "Qty": 1,
                                                  "UnitPrice": round(payment["amount"], 2)}}]}
        inv = _call(cfg, conn, "POST", "invoice", body)["Invoice"]["Id"]
    conn.execute("INSERT INTO qb_sync (payment_pk, qb_invoice_id) VALUES (?, ?)", (payment["id"], inv))
    conn.commit()
    return inv


def estimate_groups(payments: list[dict], job_id: str) -> list[tuple[str, list[dict]]]:
    """The job's estimates as QuickBooks will hold them: the signed schedule under the Job ID (1002-SMI), and each
    change order on its own (1002-SMI-CO1), so the original estimate stays as signed. One line per payment."""
    main = [p for p in payments if p["kind"] != "change_order"]
    groups = [(job_id, main)] if main else []
    cos = sorted({p["change_order_id"] for p in payments if p["kind"] == "change_order" and p["change_order_id"]})
    for i, co in enumerate(cos, start=1):
        groups.append((f"{job_id}-CO{i}", [p for p in payments if p["change_order_id"] == co]))
    return groups


def send_estimates(cfg, conn, job: dict, payments: list[dict], client_name: str, email: str = "") -> list[str]:
    """Create the job's estimate(s) in QuickBooks, one line per payment, each line naming its Payment ID so the
    invoices match. Ones already there are left alone, so pressing twice never duplicates. Returns the new numbers."""
    ensure_tables(conn)
    job_id = f"{job['number']}-{job['code']}"
    sent = []
    for doc, pays in estimate_groups(payments, job_id):
        if conn.execute("SELECT 1 FROM qb_estimates WHERE doc_number = ?", (doc,)).fetchone():
            continue
        existing = _query(cfg, conn, f"select Id from Estimate where DocNumber = '{_q(doc)}'")
        if existing:
            est = existing[0]["Id"]
        else:
            lines = []
            for p in pays:
                if not p["amount"]:
                    continue
                desc = f"{p['payment_id']}: {p['description']} ({p['due_when']})".replace(" ()", "")
                lines.append({"Amount": round(p["amount"], 2), "DetailType": "SalesItemLineDetail", "Description": desc,
                              "SalesItemLineDetail": {"ItemRef": {"value": item_ref(cfg, conn)}, "Qty": 1,
                                                      "UnitPrice": round(p["amount"], 2)}})
            if not lines:
                continue
            body = {"DocNumber": doc, "CustomerRef": {"value": customer_ref(cfg, conn, client_name, email)},
                    "TxnDate": time.strftime("%Y-%m-%d"), "Line": lines}
            if job.get("address"):
                body["CustomerMemo"] = {"value": job["address"]}
            est = _call(cfg, conn, "POST", "estimate", body)["Estimate"]["Id"]
            sent.append(doc)
        conn.execute("INSERT INTO qb_estimates (doc_number, job_number, qb_estimate_id) VALUES (?, ?, ?)",
                     (doc, job["number"], est))
        conn.commit()
    return sent


def estimates_synced(conn) -> dict:
    """Job number -> the estimate numbers already in QuickBooks."""
    ensure_tables(conn)
    out: dict = {}
    for doc, n in conn.execute("SELECT doc_number, job_number FROM qb_estimates ORDER BY doc_number"):
        out.setdefault(n, []).append(doc)
    return out


def record_payment(cfg, conn, payment: dict, client_name: str) -> str:
    """Mark a sent invoice as paid in QuickBooks, using the amount and date recorded in the tool."""
    ensure_tables(conn)
    row = conn.execute("SELECT qb_invoice_id, qb_payment_id FROM qb_sync WHERE payment_pk = ?", (payment["id"],)).fetchone()
    if not row:
        raise QBOError("Send the invoice to QuickBooks first.")
    if row[1]:
        return row[1]
    if not payment.get("amount_paid"):
        raise QBOError("Record the payment here first.")
    cust = customer_ref(cfg, conn, client_name)
    body = {"CustomerRef": {"value": cust}, "TotalAmt": round(payment["amount_paid"], 2),
            "TxnDate": payment.get("date_paid") or time.strftime("%Y-%m-%d"),
            "Line": [{"Amount": round(payment["amount_paid"], 2), "LinkedTxn": [{"TxnId": row[0], "TxnType": "Invoice"}]}]}
    pid = _call(cfg, conn, "POST", "payment", body)["Payment"]["Id"]
    conn.execute("UPDATE qb_sync SET qb_payment_id = ? WHERE payment_pk = ?", (pid, payment["id"]))
    conn.commit()
    return pid


def synced(conn) -> dict:
    ensure_tables(conn)
    return {r[0]: (r[1], r[2]) for r in conn.execute("SELECT payment_pk, qb_invoice_id, qb_payment_id FROM qb_sync")}
