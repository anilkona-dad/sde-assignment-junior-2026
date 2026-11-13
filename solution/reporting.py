
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import (
    DATABASE_PATH,
    REPORTS_DIR,
    load_workflow_schemas,
    load_dispositions,
)
from database import get_connection
from core.security import decrypt_text


IST = timezone(timedelta(hours=5, minutes=30))

BUCKETS = [
    "yet_to_reach_out",
    "in_progress_telephony_failed",
    "in_progress_dialed",
    "completed",
]


def _parse_timestamp(value):
    timestamp = datetime.fromisoformat(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def _to_ist(value):
    return _parse_timestamp(value).astimezone(IST)


def _write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _load_leads(connection, schemas):
    reference_fields = {}

    for workflow_id, schema in schemas.items():
        reference_fields[workflow_id] = next(
            (
                field["name"]
                for field in schema["fields"]
                if field.get("reference") is True
            ),
            None,
        )

    leads = {}

    rows = connection.execute(
        """
        SELECT id, workflow_id, batch_id, encrypted_data
        FROM leads
        ORDER BY workflow_id, batch_id, id
        """
    ).fetchall()

    for row in rows:
        values = json.loads(
            decrypt_text(bytes(row["encrypted_data"]))
        )

        workflow_id = row["workflow_id"]
        reference_field = reference_fields.get(workflow_id)

        leads[row["id"]] = {
            "id": row["id"],
            "workflow_id": workflow_id,
            "batch_id": row["batch_id"],
            "values": values,
            "external_ref": (
                values.get(reference_field)
                if reference_field else ""
            ) or "",
            "phone": values.get("phone") or "",
        }

    return leads


def _load_calls(connection, dispositions):
    rows = connection.execute(
        """
        SELECT
            e.event_id,
            e.workflow_id,
            e.event_type,
            e.occurred_at,
            e.call_id,
            e.disposition_code,
            l.lead_id
        FROM interaction_events AS e
        JOIN event_lead_links AS l
            ON l.event_id = e.event_id
        ORDER BY e.occurred_at, e.event_id
        """
    ).fetchall()

    events_by_call = defaultdict(list)

    for row in rows:
        # Avoid grouping unrelated events if a call ID is missing.
        call_key = row["call_id"]

        if call_key is None:
            call_key = f"__missing_call_id__{row['event_id']}"

        key = (row["lead_id"], call_key)
        events_by_call[key].append(dict(row))

    calls_by_lead = defaultdict(list)

    for (lead_id, call_id), events in events_by_call.items():
        initiated = [
            event for event in events
            if event["event_type"] == "call.initiated"
        ]

        # A call is counted only if it has a linked initiated event.
        if not initiated:
            continue

        initiated_event = min(
            initiated,
            key=lambda event: _parse_timestamp(event["occurred_at"]),
        )

        workflow_id = initiated_event["workflow_id"]

        overrides = [
            event for event in events
            if event["event_type"] == "disposition.override"
            and event["disposition_code"]
        ]

        disposition_sets = [
            event for event in events
            if event["event_type"] == "disposition.set"
            and event["disposition_code"]
        ]

        # An override takes precedence over every disposition.set.
        if overrides:
            effective_event = max(
                overrides,
                key=lambda event: _parse_timestamp(event["occurred_at"]),
            )
        elif disposition_sets:
            effective_event = max(
                disposition_sets,
                key=lambda event: _parse_timestamp(event["occurred_at"]),
            )
        else:
            effective_event = None

        disposition_code = (
            effective_event["disposition_code"]
            if effective_event else None
        )

        disposition = (
            dispositions.get(workflow_id, {}).get(disposition_code, {})
            if disposition_code else {}
        )

        call = {
            "lead_id": lead_id,
            "workflow_id": workflow_id,
            "call_id": call_id,
            "initiated_at": initiated_event["occurred_at"],
            "initiated_utc": _parse_timestamp(
                initiated_event["occurred_at"]
            ),
            "call_date": _to_ist(
                initiated_event["occurred_at"]
            ).date().isoformat(),
            "connected": any(
                event["event_type"] == "call.connected"
                for event in events
            ),
            "telephony_failed": any(
                event["event_type"] == "call.telephony_failed"
                for event in events
            ),
            "disposition_code": disposition_code,
            "is_terminal": disposition.get("is_terminal", False),
            "is_success": disposition.get("is_success", False),
        }

        calls_by_lead[lead_id].append(call)

    return calls_by_lead


def _get_bucket(calls):
    if not calls:
        return "yet_to_reach_out"

    if any(call["is_terminal"] for call in calls):
        return "completed"

    if all(call["telephony_failed"] for call in calls):
        return "in_progress_telephony_failed"

    return "in_progress_dialed"


def _build_batch_summary(leads, calls_by_lead):
    grouped = defaultdict(list)

    for lead_id, lead in leads.items():
        key = (lead["workflow_id"], lead["batch_id"])
        grouped[key].append(lead_id)

    rows = []

    for (workflow_id, batch_id), lead_ids in sorted(grouped.items()):
        counts = {bucket: 0 for bucket in BUCKETS}

        for lead_id in lead_ids:
            bucket = _get_bucket(calls_by_lead.get(lead_id, []))
            counts[bucket] += 1

        rows.append({
            "workflow_id": workflow_id,
            "batch_id": batch_id,
            "total_leads": len(lead_ids),
            **counts,
        })

    return rows


def _build_daily_overview(calls_by_lead):
    daily = defaultdict(lambda: {
        "total_calls": 0,
        "connected_calls": 0,
        "success_leads": set(),
    })

    for lead_id, calls in calls_by_lead.items():
        for call in calls:
            key = (call["workflow_id"], call["call_date"])
            entry = daily[key]

            entry["total_calls"] += 1

            if call["connected"]:
                entry["connected_calls"] += 1

            if call["is_success"]:
                entry["success_leads"].add(lead_id)

    rows = []

    for (workflow_id, date), values in sorted(daily.items()):
        total = values["total_calls"]
        connected = values["connected_calls"]

        rows.append({
            "workflow_id": workflow_id,
            "date": date,
            "total_calls": total,
            "connected_calls": connected,
            "connectivity_rate": f"{connected / total:.4f}",
            "success_leads": len(values["success_leads"]),
        })

    return rows


def _build_lead_report(leads, calls_by_lead):
    rows = []

    for lead_id, lead in leads.items():
        calls = sorted(
            calls_by_lead.get(lead_id, []),
            key=lambda call: call["initiated_utc"],
            reverse=True,
        )

        total_calls = len(calls)
        connected_calls = sum(
            1 for call in calls if call["connected"]
        )

        latest_call_with_disposition = next(
            (
                call for call in calls
                if call["disposition_code"] is not None
            ),
            None,
        )

        last_call_at = ""

        if calls:
            last_call_at = (
                _to_ist(calls[0]["initiated_at"])
                .isoformat(timespec="seconds")
            )

        phone = lead["phone"]
        phone_masked = ""

        if phone:
            phone_masked = "+91******" + phone[-4:]

        rows.append({
            "workflow_id": lead["workflow_id"],
            "external_ref": lead["external_ref"],
            "batch_id": lead["batch_id"],
            "phone_masked": phone_masked,
            "bucket": _get_bucket(calls),
            "total_calls": total_calls,
            "connected_calls": connected_calls,
            "last_call_at": last_call_at,
            "current_disposition": (
                latest_call_with_disposition["disposition_code"]
                if latest_call_with_disposition else ""
            ),
            "ever_success": str(
                any(call["is_success"] for call in calls)
            ).lower(),
        })

    return sorted(
        rows,
        key=lambda row: (
            row["workflow_id"],
            row["external_ref"],
        ),
    )


def _build_rejections(connection):
    rows = connection.execute(
        """
        SELECT workflow_id, batch_id, row_number, reason
        FROM rejections
        ORDER BY workflow_id, batch_id, row_number
        """
    ).fetchall()

    return [dict(row) for row in rows]


def _build_data_quality(connection):
    metric_rows = connection.execute(
        """
        SELECT metric_name, SUM(metric_value) AS total
        FROM drop_metrics
        GROUP BY metric_name
        """
    ).fetchall()

    metrics = {
        row["metric_name"]: row["total"]
        for row in metric_rows
    }

    rejection_rows = connection.execute(
        """
        SELECT reason, COUNT(*) AS total
        FROM rejections
        GROUP BY reason
        ORDER BY reason
        """
    ).fetchall()

    rejections_by_reason = {
        row["reason"]: row["total"]
        for row in rejection_rows
    }

    orphan_events = connection.execute(
        """
        SELECT COUNT(*)
        FROM interaction_events AS e
        LEFT JOIN event_lead_links AS l
            ON l.event_id = e.event_id
        WHERE l.event_id IS NULL
        """
    ).fetchone()[0]

    return {
        "lead_rows_total": metrics.get("lead_rows_total", 0),
        "lead_rows_rejected": metrics.get("lead_rows_rejected", 0),
        "rejections_by_reason": rejections_by_reason,
        "duplicate_lead_rows_merged": metrics.get(
            "duplicate_lead_rows_merged", 0
        ),
        "field_warnings": metrics.get("field_warnings", 0),
        "events_total": metrics.get("events_total", 0),
        "malformed_events": metrics.get("malformed_events", 0),
        "duplicate_events_dropped": metrics.get(
            "duplicate_events_dropped", 0
        ),
        "orphan_events": orphan_events,
        "unknown_disposition_events": metrics.get(
            "unknown_disposition_events", 0
        ),
    }


def generate_reports(database_path=None, reports_dir=None):
    schemas = load_workflow_schemas()
    dispositions = load_dispositions()

    output_directory = Path(reports_dir or REPORTS_DIR)
    output_directory.mkdir(parents=True, exist_ok=True)

    connection = get_connection(database_path)

    try:
        leads = _load_leads(connection, schemas)
        calls_by_lead = _load_calls(connection, dispositions)

        batch_rows = _build_batch_summary(leads, calls_by_lead)
        daily_rows = _build_daily_overview(calls_by_lead)
        lead_rows = _build_lead_report(leads, calls_by_lead)
        rejection_rows = _build_rejections(connection)
        quality = _build_data_quality(connection)

        _write_csv(
            output_directory / "batch_summary.csv",
            [
                "workflow_id",
                "batch_id",
                "total_leads",
                "yet_to_reach_out",
                "in_progress_telephony_failed",
                "in_progress_dialed",
                "completed",
            ],
            batch_rows,
        )

        _write_csv(
            output_directory / "daily_overview.csv",
            [
                "workflow_id",
                "date",
                "total_calls",
                "connected_calls",
                "connectivity_rate",
                "success_leads",
            ],
            daily_rows,
        )

        _write_csv(
            output_directory / "lead_report.csv",
            [
                "workflow_id",
                "external_ref",
                "batch_id",
                "phone_masked",
                "bucket",
                "total_calls",
                "connected_calls",
                "last_call_at",
                "current_disposition",
                "ever_success",
            ],
            lead_rows,
        )

        _write_csv(
            output_directory / "rejections.csv",
            [
                "workflow_id",
                "batch_id",
                "row_number",
                "reason",
            ],
            rejection_rows,
        )

        with (
            output_directory / "data_quality.json"
        ).open("w", encoding="utf-8") as file:
            json.dump(quality, file, indent=2, ensure_ascii=False)

        return {
            "status": "success",
            "output_directory": str(output_directory.resolve()),
            "files_generated": [
                "batch_summary.csv",
                "daily_overview.csv",
                "lead_report.csv",
                "rejections.csv",
                "data_quality.json",
            ],
            "lead_count": len(leads),
            "daily_rows": len(daily_rows),
            "rejection_count": len(rejection_rows),
            "orphan_events": quality["orphan_events"],
        }

    finally:
        connection.close()


if __name__ == "__main__":
    result = generate_reports()
    print(json.dumps(result, indent=2))
