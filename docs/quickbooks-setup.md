# QuickBooks

Two ways to use it. The first needs no setup.

## 1. Files (works today)

Open **QuickBooks** in the app. The Payment ID is the invoice number (for example `1002-HAR-3`), so the files line up with no retyping:

| Download | QuickBooks Online screen |
|---|---|
| Invoices | Sales, then Invoices, then Import (or Import data, Invoices) |
| Expenses | Banking, then Upload from file (the job number is kept in the description in brackets) |
| Customers | Settings, then Import data, Customers |

The Excel export has the same Payment IDs and a QuickBooks account column on the RSC Codes sheet.

## 2. Direct connection (optional, one-time, about 10 minutes)

Nothing is sent automatically. The app only talks to QuickBooks when Nick presses **Send invoice** or **Record payment** next to a payment, and it checks the invoice number first so pressing twice never makes a duplicate.

1. Go to developer.intuit.com, sign in with the QuickBooks login, and create an app with the *Accounting* scope.
2. Under the app's Keys, copy the **Development** Client ID and Client Secret.
3. Add `http://localhost:5151/quickbooks/callback` as a Redirect URI.
4. In `~/RSC/config.toml` add:
   ```
   [quickbooks]
   client_id = "..."
   client_secret = "..."
   environment = "sandbox"
   ```
5. Restart the app, open QuickBooks, press **Connect**, and pick the sandbox company.
6. Send one test invoice and check it in the sandbox company.
7. For real books: create the Production keys in the same Intuit app (Intuit asks a few questions about the app), put them in `config.toml`, set `environment = "production"`, and Connect again.

What gets created: a customer (the client's name), an invoice whose number is the Payment ID with one line "Remodeling Services" (created if missing), and, for Record payment, a payment applied to that invoice.

**Not yet tested against a live QuickBooks account.** It is covered by tests that imitate QuickBooks' replies. Run step 6 on the sandbox first. Intuit's production keys use HTTPS redirects for apps that others will use; for one person on one Mac, `localhost` works in development and may need review for production.
