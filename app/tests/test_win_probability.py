from __future__ import annotations

from services.win_probability import estimate_win_probability


def _snapshot(event_id: str, stage: str, outcome: str) -> dict:
    return {
        "source_event_id": event_id,
        "stage": stage,
        "material_categories": ["Power cables"],
        "region": "West",
        "tender_value": 1_000_000,
        "currency": "INR",
        "outcome": outcome,
        "is_demo": True,
    }


def test_probability_is_learned_from_historical_stage_outcomes_not_source_value():
    history = [
        _snapshot(f"early-win-{index}", "Bid preparation", "won")
        for index in range(7)
    ] + [
        _snapshot(f"early-loss-{index}", "Bid preparation", "lost")
        for index in range(3)
    ] + [
        _snapshot(f"late-win-{index}", "Technical evaluation", "won")
        for index in range(2)
    ] + [
        _snapshot(f"late-loss-{index}", "Technical evaluation", "lost")
        for index in range(8)
    ]

    early = estimate_win_probability(
        {
            "stage": "Bid preparation",
            "material_categories": ["Power cables"],
            "region": "West",
            "tender_value": 1_000_000,
            "currency": "INR",
            "existing_win_probability_percent": 99,
        },
        history,
    )
    late = estimate_win_probability(
        {
            "stage": "Technical evaluation",
            "material_categories": ["Power cables"],
            "region": "West",
            "tender_value": 1_000_000,
            "currency": "INR",
        },
        history,
    )

    assert early is not None
    assert late is not None
    assert early["probability_percent"] > late["probability_percent"]
    assert early["probability_percent"] != 99
    assert early["training_tender_count"] == 10
    assert early["training_snapshot_count"] == 10
    assert early["training_wins"] == 7
    assert early["training_losses"] == 3
    assert early["dataset_label"] == "Synthetic iTrack demo history"


def test_probability_is_unavailable_without_both_historical_outcome_classes():
    assert estimate_win_probability(
        {"stage": "Qualification"},
        [_snapshot("only-win", "Qualification", "won")],
    ) is None
