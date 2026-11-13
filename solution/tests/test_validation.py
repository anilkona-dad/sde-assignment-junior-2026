
from core.validation import (
    build_header_mapping,
    validate_lead_row,
)


SCHEMA = {
    "workflow_id": "motor_renewal",
    "fields": [
        {
            "name": "customer_name",
            "type": "string",
            "required": True,
            "pii": True,
            "aliases": ["name", "customer name"],
        },
        {
            "name": "phone",
            "type": "phone",
            "required": True,
            "pii": True,
            "aliases": ["mobile", "mobile no"],
        },
        {
            "name": "policy_number",
            "type": "string",
            "required": True,
            "reference": True,
            "aliases": ["policy no"],
        },
        {
            "name": "policy_expiry",
            "type": "date",
            "required": False,
            "aliases": ["expiry date"],
        },
        {
            "name": "preferred_language",
            "type": "enum",
            "required": False,
            "values": ["en", "hi", "ta"],
            "default": "en",
            "aliases": ["language"],
        },
    ],
}


def test_header_alias_mapping():
    headers = [
        "Customer_Name",
        "Mobile No",
        "Policy No",
        "Expiry Date",
        "Extra Column",
    ]

    mapping = build_header_mapping(headers, SCHEMA)

    assert mapping == {
        0: "customer_name",
        1: "phone",
        2: "policy_number",
        3: "policy_expiry",
    }


def test_valid_row():
    headers = [
        "Name",
        "Mobile",
        "Policy No",
        "Expiry Date",
        "Language",
    ]

    row = [
        " Meghana ",
        "9876543210",
        "POL-100",
        "03/10/2026",
        "HI",
    ]

    result = validate_lead_row(row, headers, SCHEMA)

    assert result["rejection_reason"] is None
    assert result["field_warnings"] == 0
    assert result["values"]["customer_name"] == "Meghana"
    assert result["values"]["phone"] == "+919876543210"
    assert result["values"]["policy_expiry"] == "2026-10-03"
    assert result["values"]["preferred_language"] == "hi"


def test_missing_required_field():
    headers = ["Name", "Mobile", "Policy No"]
    row = ["Meghana", "9876543210", ""]

    result = validate_lead_row(row, headers, SCHEMA)

    assert result["rejection_reason"] == "missing_required:policy_number"


def test_invalid_phone_rejected():
    headers = ["Name", "Mobile", "Policy No"]
    row = ["Meghana", "1234567890", "POL-100"]

    result = validate_lead_row(row, headers, SCHEMA)

    assert result["rejection_reason"] == "invalid_phone"


def test_invalid_optional_date_becomes_null_and_warning():
    headers = ["Name", "Mobile", "Policy No", "Expiry Date"]
    row = ["Meghana", "9876543210", "POL-100", "31/02/2026"]

    result = validate_lead_row(row, headers, SCHEMA)

    assert result["rejection_reason"] is None
    assert result["values"]["policy_expiry"] is None
    assert result["field_warnings"] == 1


def test_optional_default_is_not_applied_during_validation():
    headers = ["Name", "Mobile", "Policy No"]
    row = ["Meghana", "9876543210", "POL-100"]

    result = validate_lead_row(row, headers, SCHEMA)

    assert result["values"]["preferred_language"] is None
