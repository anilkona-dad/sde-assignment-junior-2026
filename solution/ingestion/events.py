
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.normalization import normalize_phone
from core.security import encrypt_text, phone_fingerprint

IST = timezone(timedelta(hours=5, minutes=30))


def _normalize_timestamp(value):
    """Convert UTC, offset-aware, or naive IST timestamps to UTC ISO format."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing event timestamp")

    timestamp = value.strip()

    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    parsed = datetime.fromisoformat(timestamp)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _get_phone_hash(event):
    """Return a keyed fingerprint, or None if the phone is absent/invalid."""
    phone = event.get("phone")

    if phone is None or not str(phone).strip():
        return None

    try:
        canonical_phone = normalize_phone(phone)
        return phone_fingerprint(canonical_phone)
    except ValueError:
        return None


def _is_unknown_disposition(event, dispositions):
    event_type = event.get("event_type", "")

    if not event_type.startswith("disposition."):
        return False

    payload = event.get("payload")
    if not isinstance(payload, dict):
        return True

    code = payload.get("disposition_code")
    workflow_id = event.get("workflow_id")

    return (
        not code
        or code not in dispositions.get(workflow_id, {})
    )


def _resolve_event_links(connection):
    """
    Resolve every currently linkable event.

    Phone-bearing events use workflow_id + phone_hash.
    Phone-less events, particularly disposition.override, use
    another already-linked event with the same workflow_id + call_id.

    An event is linked only when the call identifies exactly one lead.
    """
    unresolved = connection.execute(
        """
        SELECT
            e.event_id,
            e.workflow_id,
            e.event_type,
            e.call_id,
            e.phone_hash
        FROM interaction_events AS e
        LEFT JOIN event_lead_links AS l
            ON l.event_id = e.event_id
        WHERE l.event_id IS NULL
        ORDER BY e.occurred_at, e.event_id
        """
    ).fetchall()

    for event in unresolved:
        lead_ids = set()

        if event["phone_hash"]:
            rows = connection.execute(
                """
                SELECT id
                FROM leads
                WHERE workflow_id = ?
                  AND phone_hash = ?
                """,
                (event["workflow_id"], event["phone_hash"]),
            ).fetchall()

            lead_ids.update(row["id"] for row in rows)

        elif event["event_type"] == "disposition.override" and event["call_id"]:
            rows = connection.execute(
                """
                SELECT DISTINCT l.lead_id
                FROM interaction_events AS peer
                JOIN event_lead_links AS l
                    ON l.event_id = peer.event_id
                WHERE peer.workflow_id = ?
                  AND peer.call_id = ?
                """,
                (event["workflow_id"], event["call_id"]),
            ).fetchall()

            lead_ids.update(row["lead_id"] for row in rows)

        # Never guess if a call unexpectedly points to multiple leads.
        if len(lead_ids) == 1:
            lead_id = next(iter(lead_ids))

            connection.execute(
                """
                INSERT OR IGNORE INTO event_lead_links (
                    event_id, lead_id
                )
                VALUES (?, ?)
                """,
                (event["event_id"], lead_id),
            )


def count_orphan_events(connection):
    """Return the current number of accepted events without a lead link."""
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM interaction_events AS e
        LEFT JOIN event_lead_links AS l
            ON l.event_id = e.event_id
        WHERE l.event_id IS NULL
        """
    ).fetchone()

    return row[0]


def ingest_events_for_drop(
    connection,
    drop_path,
    drop_id,
    dispositions,
):
    """
    Ingest JSONL events for one drop.

    The caller owns the transaction. Events are globally deduplicated,
    encrypted at rest, and retained even when they are initially orphaned.
    """
    drop_path = Path(drop_path)
    events_directory = drop_path / "events"

    metrics = {
        "events_total": 0,
        "malformed_events": 0,
        "duplicate_events_dropped": 0,
        "unknown_disposition_events": 0,
    }

    if not events_directory.exists():
        _resolve_event_links(connection)
        metrics["orphan_events"] = count_orphan_events(connection)
        return metrics

    jsonl_files = sorted(events_directory.rglob("*.jsonl"))

    for jsonl_path in jsonl_files:
        with jsonl_path.open(
            "r",
            encoding="utf-8-sig",
        ) as file:
            for line in file:
                if not line.strip():
                    continue

                metrics["events_total"] += 1

                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    metrics["malformed_events"] += 1
                    continue

                if not isinstance(event, dict):
                    metrics["malformed_events"] += 1
                    continue

                event_id = event.get("event_id")

                if not isinstance(event_id, str) or not event_id.strip():
                    metrics["malformed_events"] += 1
                    continue

                event_id = event_id.strip()

                # Check global event ID uniqueness before any other processing.
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO seen_event_ids (
                        event_id,
                        first_seen_drop,
                        outcome
                    )
                    VALUES (?, ?, ?)
                    """,
                    (event_id, drop_id, "pending"),
                )

                if cursor.rowcount == 0:
                    metrics["duplicate_events_dropped"] += 1
                    continue

                workflow_id = event.get("workflow_id")
                event_type = event.get("event_type")
                occurred_at = event.get("occurred_at")

                if not all(
                    isinstance(value, str) and value.strip()
                    for value in (workflow_id, event_type, occurred_at)
                ):
                    metrics["malformed_events"] += 1

                    connection.execute(
                        """
                        UPDATE seen_event_ids
                        SET outcome = ?
                        WHERE event_id = ?
                        """,
                        ("malformed", event_id),
                    )
                    continue

                try:
                    normalized_timestamp = _normalize_timestamp(
                        occurred_at
                    )
                except (TypeError, ValueError, OverflowError):
                    metrics["malformed_events"] += 1

                    connection.execute(
                        """
                        UPDATE seen_event_ids
                        SET outcome = ?
                        WHERE event_id = ?
                        """,
                        ("malformed", event_id),
                    )
                    continue

                if _is_unknown_disposition(event, dispositions):
                    metrics["unknown_disposition_events"] += 1

                    connection.execute(
                        """
                        UPDATE seen_event_ids
                        SET outcome = ?
                        WHERE event_id = ?
                        """,
                        ("unknown_disposition", event_id),
                    )
                    continue

                payload = event.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {"original_payload": payload}

                disposition_code = None
                if event_type.startswith("disposition."):
                    disposition_code = payload.get("disposition_code")

                call_id = event.get("call_id")
                if call_id is not None:
                    call_id = str(call_id)

                phone_hash = _get_phone_hash(event)

                # Encrypt the entire event so phone and extra payload fields
                # are never stored in plaintext.
                encrypted_payload = encrypt_text(
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )

                connection.execute(
                    """
                    INSERT INTO interaction_events (
                        event_id,
                        workflow_id,
                        event_type,
                        occurred_at,
                        call_id,
                        phone_hash,
                        disposition_code,
                        encrypted_payload,
                        source_drop
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        workflow_id,
                        event_type,
                        normalized_timestamp,
                        call_id,
                        phone_hash,
                        disposition_code,
                        encrypted_payload,
                        drop_id,
                    ),
                )

                connection.execute(
                    """
                    UPDATE seen_event_ids
                    SET outcome = ?
                    WHERE event_id = ?
                    """,
                    ("stored", event_id),
                )

    # Resolve both newly inserted events and older orphans.
    _resolve_event_links(connection)

    metrics["orphan_events"] = count_orphan_events(connection)

    return metrics
