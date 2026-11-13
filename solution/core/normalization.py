
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def normalize_header(value: str) -> str:
    """
    Normalize CSV headers:
    - lowercase
    - trim whitespace
    - replace runs of underscores/whitespace with one space
    """
    if value is None:
        return ""

    return re.sub(r"[_\s]+", " ", str(value).strip().lower())


def normalize_phone(value: str) -> str:
    """
    Normalize an Indian mobile number to +91XXXXXXXXXX.

    Accepted transformations:
    - Strip all non-digits.
    - Remove 91 from a 12-digit number starting with 91.
    - Remove 0 from an 11-digit number starting with 0.
    - Require exactly 10 digits starting with 6, 7, 8 or 9.
    """
    if value is None:
        raise ValueError("Phone number is missing")

    digits = re.sub(r"\D", "", str(value))

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("invalid_phone")

    return "+91" + digits



def normalize_date(value: str) -> str:
    """
    Parse supported date formats and return YYYY-MM-DD.
    Month abbreviations are case-insensitive.
    """
    if value is None or not str(value).strip():
        raise ValueError("Date is missing")

    value = str(value).strip()

    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt).date()
            return parsed.isoformat()
        except ValueError:
            continue

    raise ValueError(f"Invalid date: {value}")


def normalize_decimal(value: str) -> str:
    """
    Parse a non-negative amount with an optional INR prefix.
    Supports Western and Indian comma grouping.
    Returns exactly two decimal places.
    """
    if value is None or not str(value).strip():
        raise ValueError("Amount is missing")

    amount = str(value).strip()

    # Remove one optional currency prefix.
    amount = re.sub(
        r"^(?:\u20B9|INR|Rs\.?)\s*",
        "",
        amount,
        flags=re.IGNORECASE,
    ).strip()

    # Accept ungrouped, Western grouping, or Indian grouping.
    number_pattern = (
        r"(?:"
        r"\d+"
        r"|\d{1,3}(?:,\d{3})+"
        r"|\d{1,2}(?:,\d{2})+,\d{3}"
        r")(?:\.\d+)?"
    )

    if not re.fullmatch(number_pattern, amount):
        raise ValueError(f"Invalid decimal: {value}")

    amount = amount.replace(",", "")

    try:
        number = Decimal(amount)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal: {value}") from exc

    if not number.is_finite() or number < 0:
        raise ValueError(f"Invalid non-negative amount: {value}")

    rounded = number.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return format(rounded, ".2f")


def normalize_enum(value: str, allowed_values: list[str]) -> str:
    """Match an enum value case-insensitively."""
    if value is None:
        raise ValueError("Enum value is missing")

    candidate = str(value).strip().lower()
    allowed = {str(item).strip().lower() for item in allowed_values}

    if candidate not in allowed:
        raise ValueError(f"Invalid enum value: {value}")

    return candidate
