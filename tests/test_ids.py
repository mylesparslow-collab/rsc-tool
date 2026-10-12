import pytest

from rsc import ids


def test_ids_follow_nicks_example():
    assert ids.job_id(1234, "Smith") == "1234-SMI"
    assert ids.payment_id(1234, "Smith", 1) == "1234-SMI-1"


@pytest.mark.parametrize("name,code", [("O'Brien", "OBR"), ("Ng", "NG"), ("van der Berg", "VAN"), ("de-Leon", "DEL")])
def test_client_code_handles_odd_names(name, code):
    assert ids.client_code(name) == code


def test_client_code_rejects_empty():
    with pytest.raises(ValueError):
        ids.client_code("  ")


def test_rsc_codes_are_never_job_numbers():
    assert ids.is_rsc_code("RSC-100") and ids.is_rsc_code("rsc-900")
    assert not ids.is_rsc_code("1001")


def test_job_numbers_only_trusted_in_context():
    assert ids.find_job_numbers("PO/JOB NAME: 1002-SMI") == [1002]
    assert ids.find_job_numbers("for job #1003 lumber") == [1003]
    assert ids.find_job_numbers("Order 2025 shipped to 1450 Broadway") == []


def test_payment_ids_found():
    assert ids.find_payment_ids("Invoice 1002-SMI-2 paid") == [(1002, "SMI", 2)]
