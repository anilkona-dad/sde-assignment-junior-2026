
from core.normalization import (
    normalize_header,
    normalize_phone,
    normalize_date,
    normalize_decimal,
    normalize_enum,
)



def build_header_mapping(headers, schema):
    """
    Map CSV column indexes to schema field names.

    Header names and aliases use the same normalization rules.
    Unrecognized columns are ignored.
    Duplicate mappings are rejected.
    """
    aliases = {}

    for field in schema["fields"]:
        canonical = field["name"]
        candidates = [canonical] + field.get("aliases", [])

        for candidate in candidates:
            normalized = normalize_header(candidate)
            aliases.setdefault(normalized, canonical)

    mapping = {}

    for index, header in enumerate(headers):
        normalized = normalize_header(header)
        field_name = aliases.get(normalized)

        if field_name is not None:
            if field_name in mapping.values():
                raise ValueError(
                    f"Multiple CSV columns map to the same field: {field_name}"
                )

            mapping[index] = field_name

    return mapping



def _normalize_field(value, field):
    """Normalize one non-empty field according to its schema type."""
    field_type = field["type"]

    if field_type == "string":
        return str(value).strip()

    if field_type == "phone":
        return normalize_phone(value)

    if field_type == "date":
        return normalize_date(value)

    if field_type == "decimal":
        return normalize_decimal(value)

    if field_type == "enum":
        return normalize_enum(value, field.get("values", []))

    raise ValueError(f"Unsupported field type: {field_type}")


def validate_lead_row(raw_values, headers, schema):
    """
    Validate and normalize one nonblank CSV data row.

    Returns:
        {
            "values": normalized field dictionary,
            "rejection_reason": string or None,
            "field_warnings": integer
        }

    The first required-field failure rejects the row.
    Invalid optional fields become None and generate one warning each.
    """
    mapping = build_header_mapping(headers, schema)

    raw_by_field = {}

    for index, field_name in mapping.items():
        if index < len(raw_values):
            raw_by_field[field_name] = raw_values[index]

    normalized = {}
    warnings = 0

    for field in schema["fields"]:
        name = field["name"]
        raw_value = raw_by_field.get(name)

        # All incoming CSV values are trimmed.
        value = "" if raw_value is None else str(raw_value).strip()

        if value == "":
            normalized[name] = None

            if field.get("required", False):
                return {
                    "values": normalized,
                    "rejection_reason": f"missing_required:{name}",
                    "field_warnings": 0,
                }

            continue

        try:
            normalized[name] = _normalize_field(value, field)

        except ValueError:
            if field.get("required", False):
                reason = (
                    "invalid_phone"
                    if field["type"] == "phone"
                    else f"invalid_required:{name}"
                )

                return {
                    "values": normalized,
                    "rejection_reason": reason,
                    "field_warnings": 0,
                }

            normalized[name] = None
            warnings += 1

    return {
        "values": normalized,
        "rejection_reason": None,
        "field_warnings": warnings,
    }
