
import pytest

from reporting import (
    _get_bucket,
    _build_batch_summary,
    _build_daily_overview,
    _build_lead_report,
)


def make_call(
    call_id,
    initiated_at,
    *,
    connected=False,
    telephony_failed=False,
    disposition_code=None,
    is_terminal=False,
    is_success=False,
):
    from datetime import datetime

    return {
        "lead_id": 1,
        "workflow_id": "motor_renewal",
        "call_id": call_id,
        "initiated_at": initiated_at,
        "initiated_utc": datetime.fromisoformat(
            initiated_at
        ),
        "call_date": initiated_at[:10],
        "connected": connected,
        "telephony_failed": telephony_failed,
        "disposition_code": disposition_code,
        "is_terminal": is_terminal,
        "is_success": is_success,
    }


def test_no_calls_means_yet_to_reach_out():
    assert _get_bucket([]) == "yet_to_reach_out"


def test_all_telephony_failed_calls_get_failed_bucket():
    calls = [
        make_call(
            "call1",
            "2026-10-01T10:00:00+00:00",
            telephony_failed=True,
        ),
        make_call(
            "call2",
            "2026-10-02T10:00:00+00:00",
            telephony_failed=True,
        ),
    ]

    assert _get_bucket(calls) == "in_progress_telephony_failed"


def test_terminal_disposition_has_priority_over_telephony_failure():
    calls = [
        make_call(
            "call1",
            "2026-10-01T10:00:00+00:00",
            telephony_failed=True,
            disposition_code="not_interested",
            is_terminal=True,
        ),
    ]

    assert _get_bucket(calls) == "completed"


def test_non_terminal_disposition_is_not_completed():
    calls = [
        make_call(
            "call1",
            "2026-10-01T10:00:00+00:00",
            disposition_code="callback_requested",
        ),
    ]

    assert _get_bucket(calls) == "in_progress_dialed"


def test_batch_summary_counts_each_lead_once():
    leads = {
        1: {
            "id": 1,
            "workflow_id": "motor_renewal",
            "batch_id": "batch_001",
        },
        2: {
            "id": 2,
            "workflow_id": "motor_renewal",
            "batch_id": "batch_001",
        },
        3: {
            "id": 3,
            "workflow_id": "motor_renewal",
            "batch_id": "batch_001",
        },
    }

    calls = {
        1: [
            make_call(
                "call1",
                "2026-10-01T10:00:00+00:00",
                telephony_failed=True,
            )
        ],
        2: [
            make_call(
                "call2",
                "2026-10-01T11:00:00+00:00",
                disposition_code="renewed",
                is_terminal=True,
                is_success=True,
            )
        ],
    }

    result = _build_batch_summary(leads, calls)

    assert len(result) == 1
    assert result[0]["total_leads"] == 3
    assert result[0]["in_progress_telephony_failed"] == 1
    assert result[0]["completed"] == 1
    assert result[0]["yet_to_reach_out"] == 1


def test_daily_overview_counts_distinct_successful_leads():
    calls = {
        1: [
            make_call(
                "call1",
                "2026-10-01T10:00:00+00:00",
                connected=True,
                is_success=True,
            ),
            make_call(
                "call2",
                "2026-10-01T11:00:00+00:00",
                connected=True,
                is_success=True,
            ),
        ],
        2: [
            make_call(
                "call3",
                "2026-10-01T12:00:00+00:00",
                connected=False,
            ),
        ],
    }

    result = _build_daily_overview(calls)

    assert len(result) == 1
    assert result[0]["total_calls"] == 3
    assert result[0]["connected_calls"] == 2
    assert result[0]["connectivity_rate"] == "0.6667"
    assert result[0]["success_leads"] == 1


def test_lead_report_uses_latest_call_with_disposition():
    lead = {
        1: {
            "id": 1,
            "workflow_id": "motor_renewal",
            "external_ref": "MOT/TEST/001",
            "batch_id": "batch_001",
            "phone": "+919876543210",
        }
    }

    calls = {
        1: [
            make_call(
                "older",
                "2026-10-01T10:00:00+00:00",
                disposition_code="renewed",
                is_terminal=True,
                is_success=True,
            ),
            make_call(
                "newer",
                "2026-10-02T10:00:00+00:00",
            ),
        ]
    }

    result = _build_lead_report(lead, calls)

    assert len(result) == 1
    assert result[0]["current_disposition"] == "renewed"
    assert result[0]["total_calls"] == 2
    assert result[0]["ever_success"] == "true"
    assert result[0]["phone_masked"] == "+91******3210"
    assert result[0]["bucket"] == "completed"
