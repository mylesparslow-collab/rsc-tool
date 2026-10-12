"""Draft contract text built from a job's estimate and payment schedule.

The terms follow what Nick settled on for the Whitcomb contract (Feb 2025): a 5-year workmanship warranty with
written notice, written change orders, an up-front schedule-hold and materials payment, the right to stop work
for late payment, mutual indemnification with liability capped at sums paid, New York law, binding arbitration
in Saratoga County, mutual non-disparagement and electronic signatures.

This is a draft for Nick's convenience, not legal advice. Bracketed items are open and need a decision, and a
New York attorney should review the whole thing before it is used with a client.
"""
import sqlite3

from . import books, brand, estimates

DISCLAIMER = ("DRAFT. This is not legal advice. Have a New York attorney review this contract, and settle every "
              "[bracketed] item, before using it with a client.")

CONTRACTOR = "Nicholas F. Parslow d/b/a Reclaimed Space Crafters"
CONTRACTOR_ADDRESS = "4 Briar Lane, Saratoga Springs, NY 12866"

OPEN_ITEMS = [
    "Attorneys' fees (section 14): the Whitcomb template only made the client pay. Nick agreed it should be mutual "
    "but wasn't sure of the wording.",
    "Permits (section 6): the Whitcomb template had the client obtain permits. Confirm that is still what Nick wants.",
    "Termination notice period (section 16): an AI review of the Whitcomb template suggested adding one. The number of days is blank.",
    "Licensing and insurance (section 15): Nick's license and insurance details aren't recorded anywhere yet.",
    "Deposits, cancellation and lien notice (section 18): the market research says New York GBL \u00a7 771 requires a "
    "notice about how advance payments are held (escrow or bond), a three-business-day right to cancel, and a mechanic's "
    "lien notice. The text here is a placeholder with brackets; a New York attorney must supply the exact wording and "
    "choose escrow or bond before this goes to a client.",
    "Sections 5, 8 and 9 (schedule, Client's responsibilities, materials) are plain-language additions. They were not "
    "among the Whitcomb terms this draft was built from.",
]


def _money(v: float) -> str:
    return f"${v:,.2f}"


def build(conn: sqlite3.Connection, job_number: int) -> dict | None:
    CONTRACTOR, CONTRACTOR_ADDRESS = brand.current()["legal"], brand.address_line()
    job = books.get_job(conn, job_number)
    if not job:
        return None
    est = estimates.get(conn, job_number)
    payments = books.list_payments(conn, job_number)
    total = job["contract_total"]
    if total is None and est:
        total = estimates.totals(est)["total"]
    client = f"{job['first_name']} {job['last_name']}".strip()
    address = job["address"] or "[job address]"
    duration = (est or {}).get("duration") or "[estimated duration]"

    schedule_text = ("The Payment Schedule below is part of this contract." if payments
                     else "[The payment schedule has not been created yet. Create it on the estimate page before printing.]")

    sections = [
        ("1. Parties and project", [
            f"This Contract is between {CONTRACTOR} of {CONTRACTOR_ADDRESS} (\"Contractor\") and {client or '[client name]'} "
            f"(\"Client\") for work at {address} (the \"Project\"). Job ID: {job['job_id']}.",
        ]),
        ("2. Scope of work", [
            "Contractor will perform the work described in the attached Scope of Work (Exhibit A) and nothing else. Anything "
            "listed as not included, or not listed, is outside this Contract unless added by a Change Order under section 7.",
        ]),
        ("3. Contract price", [
            f"The Client will pay Contractor {_money(total) if total is not None else '[contract price]'} for the work, "
            "paid under the Payment Schedule (Exhibit B). " + schedule_text,
            "The first payment holds the Client's place on Contractor's schedule and covers materials and other items bought "
            "up front. It is due when this Contract is signed. Later payments are due as shown in the Payment Schedule.",
        ]),
        ("4. Late payment", [
            "If a payment is late, Contractor may stop work until it is paid. Contractor will give written notice before "
            "stopping. Time lost to a stoppage for late payment is added to the schedule.",
        ]),
        ("5. Schedule", [
            f"Estimated duration: {duration}. Dates are estimates. Weather, material delivery, inspections, hidden conditions "
            "and Client decisions can change them.",
        ]),
        ("6. Permits and inspections", [
            "[Unless Exhibit A says otherwise, the Client obtains required permits.] Contractor will schedule the inspections "
            "listed in Exhibit A and make any corrections the inspector requires for work Contractor performed.",
        ]),
        ("7. Changes", [
            "Any change to the scope, the price or the schedule must be written and signed by both Client and Contractor "
            "(a \"Change Order\") before the changed work starts. This includes hidden conditions found during the job, such "
            "as rot or code problems behind walls. A Change Order states the work, the price change and the schedule change. "
            "Contractor is not required to do changed work, and the Client is not required to pay for it, without one.",
        ]),
        ("8. Client's responsibilities", [
            "The Client will give Contractor access to the work area, make decisions promptly, and keep people and pets out "
            "of the work area.",
        ]),
        ("9. Materials", [
            "Contractor buys materials when Exhibit A says it will. Substitutions of equal quality may be made when an "
            "item is unavailable.",
        ]),
        ("10. Workmanship warranty", [
            "Contractor warrants the labor and workmanship on this Project for five (5) years from completion. To use the "
            "warranty, the Client must give Contractor written notice of the defect. Contractor will repair defective "
            "workmanship at no charge.",
            "The warranty does not cover third-party materials or products (which carry their manufacturer's warranty), "
            "ordinary wear and tear, misuse or neglect, or changes made by anyone other than Contractor.",
        ]),
        ("11. Indemnification", [
            "Each party will indemnify the other against third-party claims caused by its own negligence or breach of this Contract.",
        ]),
        ("12. Limits on liability", [
            "Contractor's total liability under this Contract is limited to the amount the Client has paid under it. Neither "
            "party is liable to the other for indirect or consequential damages.",
        ]),
        ("13. Disputes", [
            "New York law governs this Contract. Any dispute will be settled by binding arbitration, and any court action "
            f"needed to enforce an award will be brought in {brand.current()['county']}.",
        ]),
        ("14. Attorneys' fees", [
            "[OPEN: mutual attorneys' fees wording to be written with a New York attorney.]",
        ]),
        ("15. Licenses and insurance", [
            "[OPEN: Contractor's license and insurance details.]",
        ]),
        ("16. Ending the Contract", [
            "[OPEN: number of days] days' written notice is required to end this Contract early. The Client will pay for work "
            "done and materials bought up to that date.",
        ]),
        ("17. Respect", [
            "Neither party will make false or disparaging public statements about the other.",
        ]),
        ("18. Deposits, cancellation and liens", [
            "[ATTORNEY TO CONFIRM THE EXACT WORDING REQUIRED BY NEW YORK GENERAL BUSINESS LAW \u00a7 771.] "
            "Payments made before the work is finished are an advance on the price. Contractor will hold advance payments "
            "that are not yet used for materials and labor for this job in [a separate escrow account / a bond: attorney to choose], "
            "and will tell the Client in writing where they are held.",
            "The Client may cancel this Contract by written notice until midnight of the third business day after signing it. "
            "[Attorney to supply the required notice form and where to send it.]",
            "Mechanic's lien notice: a contractor, subcontractor or supplier who is not paid for work or materials on this "
            "property may be able to file a lien against it under New York Lien Law. Contractor will pay its subcontractors and "
            "suppliers for this job and will give the Client lien waivers on request. "
            "[Attorney to supply the required notice wording.]",
        ]),
        ("19. Whole agreement and signatures", [
            "This Contract, with Exhibits A and B and any signed Change Orders, is the whole agreement. It can be changed only "
            "in writing signed by both parties. Electronic signatures are valid.",
        ]),
    ]
    return {"job": job, "estimate": est, "payments": payments, "sections": sections, "client": client,
            "total": total, "disclaimer": DISCLAIMER, "open_items": OPEN_ITEMS, "contractor": CONTRACTOR,
            "contractor_address": CONTRACTOR_ADDRESS, "change_orders": _signed_change_orders(conn, job_number)}


def _signed_change_orders(conn: sqlite3.Connection, job_number: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM change_orders WHERE job_number = ? AND status = 'signed' ORDER BY seq",
                        (job_number,)).fetchall()
    return [dict(r) for r in rows]
