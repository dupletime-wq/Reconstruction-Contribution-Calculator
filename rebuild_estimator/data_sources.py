from __future__ import annotations

from .models import ProjectInput, PropertyInput, SourceRecord, now_timestamp


def _record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(
        key=key,
        value=value,
        source=source,
        retrieved_at=now_timestamp(),
        confidence=confidence,
        notes=notes,
    )


def build_complex_source_records(property_input: PropertyInput, project_input: ProjectInput) -> list[SourceRecord]:
    return [
        _record("complex_name", property_input.complex_name or "-", "user_input", 0.98),
        _record("address", property_input.address or "-", "user_input", 0.98),
        _record("current_stage", property_input.current_stage, "user_input", 0.98),
        _record("current_households", f"{project_input.current_households:,}", "user_input", 0.92),
        _record("planned_households", f"{project_input.planned_households:,}", "user_input", 0.92),
    ]


def build_transaction_source_records(property_input: PropertyInput) -> list[SourceRecord]:
    records: list[SourceRecord] = [
        _record("purchase_price", f"{property_input.purchase_price:,.0f}", "user_input", 0.98),
    ]
    if property_input.recent_same_complex_trade_price:
        records.append(
            _record(
                "recent_same_complex_trade_price",
                f"{property_input.recent_same_complex_trade_price:,.0f}",
                "manual_market_comp",
                0.72,
                "same complex recent median trade",
            )
        )
    if property_input.comparison_new_apt_price:
        records.append(
            _record(
                "comparison_new_apt_price",
                f"{property_input.comparison_new_apt_price:,.0f}",
                "manual_new_build_comp",
                0.68,
                "new-build comparison benchmark",
            )
        )
    return records


def build_public_price_source_records(property_input: PropertyInput, project_input: ProjectInput) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    if property_input.public_price:
        records.append(
            _record(
                "public_price",
                f"{property_input.public_price:,.0f}",
                "manual_public_price",
                0.82,
            )
        )
    if project_input.adjustment_factor_override:
        records.append(
            _record(
                "adjustment_factor_override",
                f"{project_input.adjustment_factor_override:.3f}",
                "user_input",
                0.92,
            )
        )
    if project_input.public_land_price_avg:
        records.append(
            _record(
                "public_land_price_avg",
                f"{project_input.public_land_price_avg:,.0f}",
                "user_input",
                0.72,
            )
        )
    return records
