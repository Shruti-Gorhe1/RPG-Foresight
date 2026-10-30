from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.graph import compiled_graph
from services.private_pipeline_signals import PrivateSignalRequest, evaluate_private_signal


NOW = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)


def _request() -> PrivateSignalRequest:
    return PrivateSignalRequest.model_validate(
        {
            "event": {
                "tenant_id": "kec-tenant",
                "event_id": "event-41",
                "sender_entity_id": "kec",
                "tender_ref": "tender-41",
                "project_name": "Illustrative transmission EPC package",
                "source_revision": "rev-3",
                "prior_stage": "bid_submitted",
                "stage": "preferred_bidder",
                "occurred_at": NOW - timedelta(minutes=5),
                "material_categories": ["HV cable", "cable accessories", "tyre components"],
                "expected_need_window": "next quarter",
                "existing_win_probability_percent": 82,
                "probability_updated_at": NOW - timedelta(minutes=5),
            },
            "rule": {
                "enabled": True,
                "tenant_id": "kec-tenant",
                "sender_entity_id": "kec",
                "trigger_stages": ["preferred_bidder"],
                "min_win_probability_percent": 80,
                "purpose": "Tender notification",
                "channel": "email",
                "routes": [
                    {
                        "subsidiary_entity_id": "",
                        "recipient_user_ids": ["buyer@example.test"],
                        "material_categories": ["HV cable", "cable accessories"],
                    },
                    {
                        "subsidiary_entity_id": "",
                        "recipient_user_ids": ["buyer@example.test"],
                        "material_categories": ["tyre components"],
                    },
                ],
            },
        }
    )


def test_matching_rule_creates_recipient_candidate_without_policy_gate() -> None:
    result = evaluate_private_signal(_request(), evaluated_at=NOW)

    assert result.status == "candidate_ready"
    assert result.dispatch_status == "not_implemented"
    assert len(result.recipient_decisions) == 1
    decision = result.recipient_decisions[0]
    assert decision.recipient_user_id == "buyer@example.test"
    assert decision.disposition == "candidate"
    assert decision.reason == "rule_matched"
    assert decision.payload == {
        "tender_ref": "tender-41",
        "project_name": "Illustrative transmission EPC package",
        "sender_entity_id": "kec",
        "stage": "preferred_bidder",
        "material_categories": ["HV cable", "cable accessories"],
        "existing_win_probability_percent": 82.0,
        "expected_need_window": "next quarter",
    }


def test_stage_and_material_matching_ignores_case_and_surrounding_whitespace() -> None:
    request = _request()
    event = request.event.model_copy(
        update={
            "stage": " PREFERRED_BIDDER ",
            "material_categories": [" HV CABLE ", "CABLE ACCESSORIES"],
        }
    )
    rule = request.rule.model_copy(
        update={
            "trigger_stages": ["preferred_bidder"],
            "routes": [
                request.rule.routes[0].model_copy(
                    update={"material_categories": ["hv cable", "Cable Accessories"]}
                )
            ],
        }
    )

    result = evaluate_private_signal(
        request.model_copy(update={"event": event, "rule": rule}),
        evaluated_at=NOW,
    )

    assert result.status == "candidate_ready"
    assert result.recipient_decisions[0].payload["material_categories"] == [
        "CABLE ACCESSORIES",
        "HV CABLE",
    ]


def test_configured_threshold_fails_closed_without_existing_probability() -> None:
    request = _request()
    event = request.event.model_copy(
        update={"existing_win_probability_percent": None, "probability_updated_at": None}
    )

    result = evaluate_private_signal(
        request.model_copy(update={"event": event}),
        evaluated_at=NOW,
    )

    assert result.status == "not_triggered"
    assert result.reason == "existing_probability_missing"
    assert result.recipient_decisions == []


def test_wrong_tenant_scope_suppresses_before_recipient_resolution() -> None:
    request = _request()
    rule = request.rule.model_copy(update={"tenant_id": "another-tenant"})

    result = evaluate_private_signal(
        request.model_copy(update={"rule": rule}),
        evaluated_at=NOW,
    )

    assert result.status == "suppressed"
    assert result.reason == "rule_scope_mismatch"
    assert result.recipient_decisions == []


def test_stale_pipeline_event_is_suppressed() -> None:
    request = _request()
    event = request.event.model_copy(update={"occurred_at": NOW - timedelta(days=2)})

    result = evaluate_private_signal(
        request.model_copy(update={"event": event}),
        evaluated_at=NOW,
    )

    assert result.status == "suppressed"
    assert result.reason == "event_stale"


def test_region_value_currency_and_closing_window_filters_explain_exclusions() -> None:
    request = _request()
    event = request.event.model_copy(
        update={
            "region": "South",
            "tender_value": 1_250_000,
            "currency": "INR",
            "closing_at": NOW + timedelta(days=12),
        }
    )
    rule = request.rule.model_copy(
        update={
            "regions": ["South"],
            "tender_currency": "INR",
            "minimum_tender_value": 1_000_000,
            "maximum_tender_value": 2_000_000,
            "minimum_days_to_close": 5,
            "maximum_days_to_close": 20,
        }
    )
    result = evaluate_private_signal(
        request.model_copy(update={"event": event, "rule": rule}),
        evaluated_at=NOW,
    )
    assert result.status == "candidate_ready"

    excluded = evaluate_private_signal(
        request.model_copy(update={
            "event": event.model_copy(update={"region": "North"}),
            "rule": rule,
        }),
        evaluated_at=NOW,
    )
    assert excluded.status == "not_triggered"
    assert excluded.reason == "region_not_matched"


def test_langgraph_routes_private_signal_input_to_specialist() -> None:
    request = _request()
    state = {
        "messages": [],
        "collected": {"private_pipeline_signal": request.model_dump()},
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
    }

    result = compiled_graph.invoke(state)

    assert result["current_step"] == "private_pipeline_signal_agent"
    assert result["step_status"] == "completed"
    assert result["collected"]["private_pipeline_signal_result"]["status"] == "candidate_ready"
    assert result["collected"]["private_pipeline_signal_result"]["dispatch_status"] == "not_implemented"
    assert result["messages"][-1]["agent"] == "private_pipeline_signal_agent"


def test_invalid_signal_fails_explicitly_and_graph_does_not_fall_through() -> None:
    state = {
        "messages": [],
        "collected": {"private_pipeline_signal": {"event": {"unexpected": "value"}}},
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
    }

    result = compiled_graph.invoke(state)

    assert result["current_step"] == "private_pipeline_signal_agent"
    assert result["step_status"] == "failed"
    assert result["collected"]["private_pipeline_signal_result"]["reason"] == (
        "private_pipeline_signal_input_invalid"
    )
