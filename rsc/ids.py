"""Job and payment numbering, per Nick's scheme.

Job ID     = <job number>-<first 3 letters of client last name>   e.g. 1002-SMI
Payment ID = <job ID>-<payment number>                           e.g. 1002-SMI-3
Operations expenses use RSC codes (RSC-100 ...) and never look like a job number.
"""
import re

JOB_ID_RE = re.compile(r"\b(\d{4,5})-([A-Z]{2,3})\b")
PAYMENT_ID_RE = re.compile(r"\b(\d{4,5})-([A-Z]{2,3})-(\d{1,2})\b")
JOB_REF_RE = re.compile(r"\bjob\s*(?:#|no\.?|number)?\s*(\d{4,5})\b", re.IGNORECASE)
RSC_CODE_RE = re.compile(r"^RSC-\d{3}$")


def client_code(last_name: str) -> str:
    letters = re.sub(r"[^A-Za-z]", "", last_name or "")
    if not letters:
        raise ValueError("Client last name needs at least one letter")
    return letters[:3].upper()


def job_id(job_number: int, last_name: str) -> str:
    return f"{job_number}-{client_code(last_name)}"


def payment_id(job_number: int, last_name: str, payment_number: int) -> str:
    return f"{job_id(job_number, last_name)}-{payment_number}"


def is_rsc_code(value: str) -> bool:
    return bool(RSC_CODE_RE.match((value or "").strip().upper()))


def find_payment_ids(text: str) -> list[tuple[int, str, int]]:
    return [(int(n), c, int(p)) for n, c, p in PAYMENT_ID_RE.findall(text or "")]


def find_job_numbers(text: str) -> list[int]:
    """Job numbers written as a Job ID (1002-SMI) or as 'job 1002' / 'job #1002'.

    A bare 4-digit number is not trusted: it is too often a year, a street
    number or an order number.
    """
    text = text or ""
    found = [int(n) for n, _ in JOB_ID_RE.findall(text)]
    found += [int(n) for n in JOB_REF_RE.findall(text)]
    return list(dict.fromkeys(found))
