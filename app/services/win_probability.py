"""Outcome-based, explainable tender win-probability estimation."""
from __future__ import annotations

import math
from typing import Any


MODEL_VERSION = "categorical-naive-bayes-v1"
MIN_TENDERS_PER_STAGE = 10
_FEATURES = ("stage", "material", "region", "currency", "value_band")


def _normalized(value: Any) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).strip().casefold().split())
    return result or None


def _value_band(value: float | None, currency_values: list[float]) -> str | None:
    if value is None or not currency_values:
        return None
    ordered = sorted(currency_values)
    lower = ordered[(len(ordered) - 1) // 3]
    upper = ordered[(2 * (len(ordered) - 1)) // 3]
    if value <= lower:
        return "lower"
    if value <= upper:
        return "middle"
    return "upper"


def _feature_values(
    record: Any,
    currency_values: dict[str, list[float]],
) -> dict[str, str]:
    categories = (
        record.get("material_categories", [])
        if isinstance(record, dict)
        else getattr(record, "material_categories", [])
    )
    tender_value = (
        record.get("tender_value")
        if isinstance(record, dict)
        else getattr(record, "tender_value", None)
    )
    currency = (
        record.get("currency")
        if isinstance(record, dict)
        else getattr(record, "currency", None)
    )
    stage = record.get("stage") if isinstance(record, dict) else getattr(record, "stage", None)
    region = record.get("region") if isinstance(record, dict) else getattr(record, "region", None)

    features: dict[str, str] = {}
    for name, value in (
        ("stage", stage),
        ("material", categories[0] if categories else None),
        ("region", region),
        ("currency", currency),
    ):
        normalized = _normalized(value)
        if normalized:
            features[name] = normalized
    normalized_currency = _normalized(currency)
    if tender_value is not None and normalized_currency:
        band = _value_band(
            float(tender_value),
            currency_values.get(normalized_currency, []),
        )
        if band:
            features["value_band"] = band
    return features


def estimate_win_probability(
    tender: dict[str, Any],
    outcome_snapshots: list[Any],
) -> dict[str, Any] | None:
    """Estimate win probability from tenant-scoped, labeled stage snapshots.

    Categorical naive Bayes with Laplace smoothing uses only features available
    at the tender's current stage. The source's probability field is never used.
    """
    target_stage = _normalized(tender.get("stage"))
    if not target_stage:
        return None
    samples = [
        sample for sample in outcome_snapshots
        if _normalized(
            sample.get("outcome")
            if isinstance(sample, dict)
            else getattr(sample, "outcome", None)
        ) in {"won", "lost"}
        and _normalized(
            sample.get("stage")
            if isinstance(sample, dict)
            else getattr(sample, "stage", None)
        ) == target_stage
    ]
    if not samples:
        return None

    distinct_tenders = {
        (
            sample.get("source_event_id")
            if isinstance(sample, dict)
            else getattr(sample, "source_event_id", None)
        )
        for sample in samples
    }
    distinct_tenders.discard(None)
    if len(distinct_tenders) < MIN_TENDERS_PER_STAGE:
        return None

    values_by_currency: dict[str, list[float]] = {}
    for sample in samples:
        sample_currency = _normalized(
            sample.get("currency")
            if isinstance(sample, dict)
            else getattr(sample, "currency", None)
        )
        sample_value = (
            sample.get("tender_value")
            if isinstance(sample, dict)
            else getattr(sample, "tender_value", None)
        )
        if sample_currency and sample_value is not None:
            values_by_currency.setdefault(sample_currency, []).append(float(sample_value))

    feature_rows = [_feature_values(sample, values_by_currency) for sample in samples]
    outcomes = [
        _normalized(sample.get("outcome") if isinstance(sample, dict) else sample.outcome)
        for sample in samples
    ]
    wins = sum(outcome == "won" for outcome in outcomes)
    losses = len(outcomes) - wins
    if not wins or not losses:
        return None

    alpha = 1.0
    log_odds = math.log((wins + alpha) / (losses + alpha))
    features = _feature_values(tender, values_by_currency)
    contributions = []
    for feature in _FEATURES:
        value = features.get(feature)
        if value is None:
            continue
        observed_values = {
            row[feature] for row in feature_rows if feature in row
        }
        category_count = max(1, len(observed_values))
        win_count = sum(
            row.get(feature) == value and outcome == "won"
            for row, outcome in zip(feature_rows, outcomes)
        )
        loss_count = sum(
            row.get(feature) == value and outcome == "lost"
            for row, outcome in zip(feature_rows, outcomes)
        )
        win_likelihood = (win_count + alpha) / (wins + alpha * category_count)
        loss_likelihood = (loss_count + alpha) / (losses + alpha * category_count)
        effect = math.log(win_likelihood / loss_likelihood)
        log_odds += effect
        contributions.append({
            "feature": feature,
            "value": value,
            "direction": "positive" if effect > 0 else "negative" if effect < 0 else "neutral",
        })

    probability = 1 / (1 + math.exp(-max(-30, min(30, log_odds))))
    tender_outcomes: dict[Any, str] = {}
    for sample, outcome in zip(samples, outcomes):
        source_event_id = (
            sample.get("source_event_id")
            if isinstance(sample, dict)
            else getattr(sample, "source_event_id", None)
        )
        if source_event_id is not None:
            tender_outcomes[source_event_id] = outcome or ""
    is_demo = any(
        bool(sample.get("is_demo")) if isinstance(sample, dict) else bool(sample.is_demo)
        for sample in samples
    )
    return {
        "probability_percent": round(probability * 100, 1),
        "model_version": MODEL_VERSION,
        "method": "Laplace-smoothed categorical naive Bayes trained on historical outcomes.",
        "training_snapshot_count": len(samples),
        "training_tender_count": len(distinct_tenders),
        "training_wins": sum(outcome == "won" for outcome in tender_outcomes.values()),
        "training_losses": sum(outcome == "lost" for outcome in tender_outcomes.values()),
        "dataset_label": (
            "Synthetic iTrack demo history"
            if is_demo
            else "Historical tender outcomes"
        ),
        "confidence": "low" if len(distinct_tenders) < 100 else "provisional",
        "features_used": contributions,
        "limitations": (
            "Demo estimate trained on synthetic iTrack records; not calibrated for real bids."
            if is_demo
            else "Historical estimate; validate calibration on held-out, time-separated tender outcomes."
        ),
    }


def _tender_features(tender: Any) -> dict[str, Any]:
    return {
        "stage": tender.stage,
        "material_categories": tender.material_categories or [],
        "region": tender.region,
        "tender_value": tender.tender_value,
        "currency": tender.currency,
    }


def apply_win_probability(
    tender: Any,
    outcome_snapshots: list[Any],
) -> dict[str, Any] | None:
    """Set a tender's persisted estimate from the matching labeled dataset."""
    is_demo = (getattr(tender, "data_provenance", "") or "").startswith("Demo data:")
    matching_snapshots = [
        snapshot for snapshot in outcome_snapshots
        if bool(
            snapshot.get("is_demo")
            if isinstance(snapshot, dict)
            else getattr(snapshot, "is_demo", False)
        ) == is_demo
    ]
    estimate = estimate_win_probability(
        _tender_features(tender),
        matching_snapshots,
    )
    tender.existing_win_probability_percent = (
        estimate["probability_percent"] if estimate else None
    )
    from datetime import datetime, timezone

    tender.probability_updated_at = datetime.now(timezone.utc) if estimate else None
    return estimate


async def refresh_tender_win_probability(db: Any, tender: Any) -> dict[str, Any] | None:
    """Load tenant-scoped outcome history and refresh a tender's estimate."""
    from sqlalchemy import select

    from db.models import TenderOutcomeSnapshot

    is_demo = (getattr(tender, "data_provenance", "") or "").startswith("Demo data:")
    result = await db.execute(
        select(TenderOutcomeSnapshot).where(
            TenderOutcomeSnapshot.tenant_id == tender.tenant_id,
            TenderOutcomeSnapshot.is_demo.is_(is_demo),
        )
    )
    return apply_win_probability(tender, list(result.scalars().all()))
