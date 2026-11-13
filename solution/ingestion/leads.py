
import csv
import json
from pathlib import Path

from core.security import encrypt_text, phone_fingerprint
from core.validation import validate_lead_row


def _is_blank_row(row):
    """Return True when every cell in a CSV row is empty."""
    return not row or all(
        not str(value).strip() for value in row
    )


def _apply_defaults(values, schema):
    """Apply schema defaults only to fields that remain null."""
    for field in schema["fields"]:
        name = field["name"]

        if values.get(name) is None and "default" in field:
            values[name] = field["default"]

    return values


def _merge_non_null(existing, incoming, schema):
    """
    Merge incoming values into an existing lead.

    Non-null incoming values overwrite existing values.
    Null incoming values never erase existing values.
    """
    merged = dict(existing)

    for field in schema["fields"]:
        name = field["name"]
        incoming_value = incoming.get(name)

        if incoming_value is not None:
            merged[name] = incoming_value

    return merged


def _load_existing_lead(connection, workflow_id, phone_hash):
    """Retrieve an existing lead using its keyed phone fingerprint."""
    row = connection.execute(
        """
        SELECT id, encrypted_data
        FROM leads
        WHERE workflow_id = ? AND phone_hash = ?
        """,
        (workflow_id, phone_hash),
    ).fetchone()

    if row is None:
        return None

    from core.security import decrypt_text

    values = json.loads(
        decrypt_text(bytes(row["encrypted_data"]))
    )

    return {
        "id": row["id"],
        "values": values,
    }


def ingest_leads_for_drop(connection, drop_path, drop_id, schemas):
    """
    Ingest every lead CSV file in one drop.

    Expected layout:
        drop_path/
            leads/
                workflow_id/
                    batch_id.csv

    The caller owns the database transaction and drop-level
    idempotency check.

    Returns per-drop ingestion metrics.
    """
    drop_path = Path(drop_path)
    leads_directory = drop_path / "leads"

    metrics = {
        "lead_rows_total": 0,
        "lead_rows_rejected": 0,
        "duplicate_lead_rows_merged": 0,
        "field_warnings": 0,
    }

    if not leads_directory.exists():
        return metrics

    csv_files = sorted(leads_directory.rglob("*.csv"))

    for csv_path in csv_files:
        workflow_id = csv_path.parent.name
        batch_id = csv_path.stem

        if workflow_id not in schemas:
            raise ValueError(
                f"No workflow schema found for: {workflow_id}"
            )

        schema = schemas[workflow_id]

        # A batch must exist before its leads because of the
        # composite foreign key in the leads table.
        connection.execute(
            """
            INSERT OR IGNORE INTO batches (
                workflow_id,
                batch_id,
                source_drop
            )
            VALUES (?, ?, ?)
            """,
            (workflow_id, batch_id, drop_id),
        )

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.reader(file)

            headers = next(reader, None)

            if headers is None:
                continue

            row_number = 0

            for raw_row in reader:
                if _is_blank_row(raw_row):
                    continue

                # Row numbers count nonblank data rows only.
                row_number += 1
                metrics["lead_rows_total"] += 1

                result = validate_lead_row(
                    raw_values=raw_row,
                    headers=headers,
                    schema=schema,
                )

                rejection_reason = result["rejection_reason"]

                if rejection_reason is not None:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO rejections (
                            workflow_id,
                            batch_id,
                            row_number,
                            reason
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            batch_id,
                            row_number,
                            rejection_reason,
                        ),
                    )

                    metrics["lead_rows_rejected"] += 1
                    continue

                incoming_values = result["values"]
                metrics["field_warnings"] += result[
                    "field_warnings"
                ]

                canonical_phone = incoming_values["phone"]
                phone_hash = phone_fingerprint(canonical_phone)

                existing = _load_existing_lead(
                    connection,
                    workflow_id,
                    phone_hash,
                )

                if existing is None:
                    merged_values = dict(incoming_values)

                    _apply_defaults(merged_values, schema)

                    encrypted_data = encrypt_text(
                        json.dumps(
                            merged_values,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )

                    connection.execute(
                        """
                        INSERT INTO leads (
                            workflow_id,
                            phone_hash,
                            encrypted_data,
                            batch_id
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            phone_hash,
                            encrypted_data,
                            batch_id,
                        ),
                    )

                else:
                    metrics["duplicate_lead_rows_merged"] += 1

                    merged_values = _merge_non_null(
                        existing["values"],
                        incoming_values,
                        schema,
                    )

                    _apply_defaults(merged_values, schema)

                    encrypted_data = encrypt_text(
                        json.dumps(
                            merged_values,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )

                    # Keep the original lead ID and batch ID.
                    connection.execute(
                        """
                        UPDATE leads
                        SET encrypted_data = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            encrypted_data,
                            existing["id"],
                        ),
                    )

    return metrics
