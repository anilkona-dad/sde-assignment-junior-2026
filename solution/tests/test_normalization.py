
import pytest

from core.normalization import (
    normalize_header,
    normalize_phone,
    normalize_date,
    normalize_decimal,
    normalize_enum,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9876543210", "+919876543210"),
        ("+91 98765-43210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("(98765) 43210", "+919876543210"),
    ],
)
def test_phone_normalization(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1234567890",
        "5876543210",
        "987654321",
        "98765432101",
        "",
    ],
)
def test_invalid_phone(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-10-03", "2026-10-03"),
        ("03/10/2026", "2026-10-03"),
        ("03-10-2026", "2026-10-03"),
        ("03-Oct-2026", "2026-10-03"),
        ("03-oct-2026", "2026-10-03"),
    ],
)
def test_date_normalization(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "31/02/2026",
        "2026-13-01",
        "not-a-date",
        "",
    ],
)
def test_invalid_dates(raw):
    with pytest.raises(ValueError):
        normalize_date(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("₹12,500.50", "12500.50"),
        ("Rs. 1200", "1200.00"),
        ("INR 500", "500.00"),
        ("100.126", "100.13"),
        ("0", "0.00"),
    ],
)
def test_decimal_normalization(raw, expected):
    assert normalize_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["-10", "abc", "", "₹-50"])
def test_invalid_decimal(raw):
    with pytest.raises(ValueError):
        normalize_decimal(raw)


def test_enum_normalization():
    assert normalize_enum("HI", ["en", "hi", "ta"]) == "hi"


def test_invalid_enum():
    with pytest.raises(ValueError):
        normalize_enum("fr", ["en", "hi", "ta"])


def test_header_normalization():
    assert normalize_header("  Customer__NAME  ") == "customer name"
    assert normalize_header("Mobile   No") == "mobile no"
