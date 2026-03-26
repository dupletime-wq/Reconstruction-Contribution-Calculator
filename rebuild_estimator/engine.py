from __future__ import annotations

from dataclasses import replace
import statistics

from .data_sources import (
    build_complex_source_records,
    build_public_price_source_records,
    build_transaction_source_records,
)
from .models import (
    AllocationCandidate,
    AppContext,
    ExitOutcome,
    MemberPriceRecord,
    ParsedProjectNotice,
    ProjectFeasibilityResult,
    PropertyInput,
    ScenarioResult,
    SCENARIO_PRESETS,
    STAGE_BASE_MONTHS,
    SourceRecord,
    ValuationResult,
    now_timestamp,
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def build_context(
    property_input,
    project_input,
    tax_profile,
    parsed_notice: ParsedProjectNotice | None = None,
    applied_document_fields: set[str] | None = None,
    applied_document_price_table: bool = False,
    aggressive_upsize: bool = False,
) -> AppContext:
    return AppContext(
        property_input=property_input,
        project_input=project_input,
        tax_profile=tax_profile,
        parsed_notice=parsed_notice,
        applied_document_fields=applied_document_fields or set(),
        applied_document_price_table=applied_document_price_table,
        aggressive_upsize=aggressive_upsize,
    )


def _record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(
        key=key,
        value=value,
        source=source,
        retrieved_at=now_timestamp(),
        confidence=confidence,
        notes=notes,
    )


def _is_capital_area(address: str) -> bool:
    return any(token in address for token in ("Seoul", "Gyeonggi", "Incheon", "\uc11c\uc6b8", "\uacbd\uae30", "\uc778\ucc9c"))


def _floor_adjustment_factor(floor_no: int) -> float:
    if floor_no <= 3 and floor_no > 0:
        return 0.98
    if floor_no >= 13:
        return 1.02
    return 1.00


def _extract_formula_adjustment_factor(formula: str | None) -> float | None:
    if not formula:
        return None
    tail = formula.split("x")[-1] if "x" in formula.lower() else formula.split("\u00d7")[-1] if "\u00d7" in formula else formula
    digits = "".join(ch for ch in tail if ch.isdigit() or ch == ".")
    try:
        value = float(digits)
    except ValueError:
        return None
    return clamp(value, 1.05, 1.65)


def _estimate_adjustment_factor(context: AppContext) -> tuple[float, str, list[SourceRecord]]:
    property_input = context.property_input
    project_input = context.project_input
    parsed_notice = context.parsed_notice
    records: list[SourceRecord] = []

    if project_input.adjustment_factor_override:
        factor = clamp(project_input.adjustment_factor_override, 1.05, 1.65)
        records.append(_record("adjustment_factor", f"{factor:.3f}", "user_override", 0.92))
        return factor, "user_override", records

    if (
        parsed_notice
        and "old_asset_formula" in context.applied_document_fields
        and parsed_notice.old_asset_formula
    ):
        factor = _extract_formula_adjustment_factor(parsed_notice.old_asset_formula)
        if factor:
            records.append(_record("adjustment_factor", f"{factor:.3f}", f"document:{parsed_notice.source_url}", 0.84))
            return factor, "document_formula", records

    if property_input.public_price and property_input.recent_same_complex_trade_price:
        factor = clamp(property_input.recent_same_complex_trade_price / property_input.public_price, 1.05, 1.65)
        records.append(_record("adjustment_factor", f"{factor:.3f}", "trade_vs_public_price", 0.78))
        return factor, "trade_vs_public_price", records

    factor = 1.25 if _is_capital_area(property_input.address) else 1.18
    records.append(_record("adjustment_factor", f"{factor:.3f}", "heuristic_default", 0.44))
    return factor, "heuristic_default", records


def _pick_member_price_table(context: AppContext) -> tuple[list[MemberPriceRecord], list[SourceRecord]]:
    property_input = context.property_input
    project_input = context.project_input
    parsed_notice = context.parsed_notice
    if project_input.member_sale_price_table:
        return list(project_input.member_sale_price_table), [_record("member_price_table", str(len(project_input.member_sale_price_table)), "user_input", 0.95)]
    if parsed_notice and context.applied_document_price_table and parsed_notice.member_price_table:
        return list(parsed_notice.member_price_table), [_record("member_price_table", str(len(parsed_notice.member_price_table)), f"document:{parsed_notice.source_url}", 0.84)]

    base_market_price = property_input.comparison_new_apt_price or project_input.general_sale_price or property_input.purchase_price * 1.45
    base_exclusive = property_input.expected_new_exclusive_area or max(property_input.current_unit_exclusive_area, 59.0)
    candidate_sizes = sorted({59.0, 84.0, 101.0, round(base_exclusive)})
    price_table: list[MemberPriceRecord] = []
    for size in candidate_sizes:
        area_ratio = safe_div(size, base_exclusive, 1.0)
        general_price = base_market_price * (area_ratio ** 0.98)
        member_price = general_price * 0.85
        price_table.append(
            MemberPriceRecord(
                label=f"{int(size)}sqm",
                exclusive_area_sqm=float(size),
                supply_area_sqm=round(size / 0.78, 2),
                member_sale_price=float(member_price),
            )
        )
    return price_table, [_record("member_price_table", str(len(price_table)), "auto_generated", 0.40, "new build comparison based")]


def _stage_months(context: AppContext, scenario_name: str) -> float:
    base_months = STAGE_BASE_MONTHS.get(context.property_input.current_stage, 72)
    duration_multiplier = SCENARIO_PRESETS[scenario_name]["duration_multiplier"]
    months = base_months * duration_multiplier
    if context.project_input.delay_one_year:
        months += 12
    return months


def _valuation_source_confidence(old_asset_source: str, total_source: str, adjustment_source: str) -> float:
    weights = {
        "manual_appraisal": 0.96,
        "public_price_adjusted": 0.82,
        "trade_backsolve": 0.68,
        "purchase_price_heuristic": 0.36,
        "document_formula": 0.84,
        "trade_vs_public_price": 0.78,
        "heuristic_default": 0.44,
        "user_total_old_asset": 0.95,
        "document_total_old_asset": 0.88,
        "scaled_individual_old_asset": 0.54,
    }
    return statistics.mean([
        weights.get(old_asset_source, 0.50),
        weights.get(total_source, 0.54),
        weights.get(adjustment_source, 0.44),
    ])


def _estimate_old_asset_basics(context: AppContext) -> tuple[float, float, float, str, str, float, list[str], list[SourceRecord]]:
    property_input = context.property_input
    project_input = context.project_input
    parsed_notice = context.parsed_notice
    notes: list[str] = []
    source_records = (
        build_complex_source_records(property_input, project_input)
        + build_transaction_source_records(property_input)
        + build_public_price_source_records(property_input, project_input)
    )

    adjustment_factor, adjustment_source, adjustment_records = _estimate_adjustment_factor(context)
    source_records.extend(adjustment_records)
    floor_adjustment_factor = _floor_adjustment_factor(property_input.floor_no)

    if property_input.appraised_old_asset_value:
        old_asset_estimate = property_input.appraised_old_asset_value
        old_asset_source = "manual_appraisal"
    elif property_input.public_price:
        old_asset_estimate = property_input.public_price * adjustment_factor * floor_adjustment_factor
        old_asset_source = "public_price_adjusted"
    elif property_input.recent_same_complex_trade_price:
        old_asset_estimate = property_input.recent_same_complex_trade_price * floor_adjustment_factor
        old_asset_source = "trade_backsolve"
        notes.append("Public price missing; recent same-complex trade was used as the legacy asset anchor.")
    else:
        old_asset_estimate = property_input.purchase_price * 0.78 * floor_adjustment_factor
        old_asset_source = "purchase_price_heuristic"
        notes.append("Public price and same-complex trade were missing; purchase-price heuristic was used.")
    source_records.append(_record("old_asset_estimate", f"{old_asset_estimate:,.0f}", old_asset_source, 0.78))

    if (
        parsed_notice
        and "total_old_asset_value" in context.applied_document_fields
        and "total_old_asset_value" in parsed_notice.cost_items
    ):
        total_old_asset_value = parsed_notice.cost_items["total_old_asset_value"]
        total_old_asset_source = "document_total_old_asset"
    elif project_input.existing_total_old_asset_value:
        total_old_asset_value = project_input.existing_total_old_asset_value
        total_old_asset_source = "user_total_old_asset"
    else:
        member_count = max(int(round(project_input.current_households * (1 - project_input.cash_settlement_rate))), 1)
        market_cap = project_input.existing_total_market_value or property_input.recent_same_complex_trade_price
        market_cap_adjustment = 1.0
        if property_input.public_price and market_cap:
            market_cap_adjustment = clamp(market_cap / property_input.public_price, 0.85, 1.35)
        total_old_asset_value = old_asset_estimate * member_count * market_cap_adjustment
        total_old_asset_source = "scaled_individual_old_asset"
    source_records.append(_record("total_old_asset_value", f"{total_old_asset_value:,.0f}", total_old_asset_source, 0.68))

    confidence = _valuation_source_confidence(old_asset_source, total_old_asset_source, adjustment_source)
    return (
        old_asset_estimate,
        total_old_asset_value,
        floor_adjustment_factor,
        old_asset_source,
        total_old_asset_source,
        confidence,
        notes,
        source_records,
    )


def _estimate_gross_floor_area_pyeong(context: AppContext, price_table: list[MemberPriceRecord]) -> tuple[float, float]:
    property_input = context.property_input
    project_input = context.project_input
    if project_input.land_share and project_input.target_far:
        land_area_sqm = project_input.land_share * project_input.current_households
        gross_floor_area_sqm = land_area_sqm * (project_input.target_far / 100.0)
    elif project_input.current_far and project_input.target_far:
        current_gross_floor_area_sqm = project_input.current_households * property_input.current_unit_supply_area * 1.08
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(project_input.target_far, project_input.current_far, 1.0)
    else:
        average_supply_area = statistics.mean(item.supply_area_sqm for item in price_table) if price_table else property_input.current_unit_supply_area * 1.08
        gross_floor_area_sqm = project_input.planned_households * average_supply_area * 1.15
    current_gross_area_sqm = project_input.current_households * property_input.current_unit_supply_area * 1.08
    return gross_floor_area_sqm / 3.3058, current_gross_area_sqm / 3.3058


def _document_override_value(context: AppContext, key: str, default: float | None = None) -> float | None:
    parsed_notice = context.parsed_notice
    if not parsed_notice or key not in context.applied_document_fields:
        return default
    if key in parsed_notice.revenue_items:
        return parsed_notice.revenue_items[key]
    if key in parsed_notice.cost_items:
        return parsed_notice.cost_items[key]
    if key == "proportional_ratio" and parsed_notice.proportional_ratio is not None:
        return parsed_notice.proportional_ratio
    return default


def compute_project_feasibility(context: AppContext, scenario_name: str = "Base") -> ProjectFeasibilityResult:
    property_input = context.property_input
    base_project = context.project_input
    preset = SCENARIO_PRESETS[scenario_name]
    project_input = replace(
        base_project,
        construction_cost_per_pyeong=base_project.construction_cost_per_pyeong or preset["construction_cost_per_pyeong"],
        pf_rate=base_project.pf_rate or preset["pf_rate"],
        sale_rate=base_project.sale_rate or preset["sale_rate"],
        cash_settlement_rate=base_project.cash_settlement_rate or preset["cash_settlement_rate"],
    )
    old_asset_estimate, total_old_asset_value, _, _, _, valuation_confidence, _, source_records = _estimate_old_asset_basics(context)
    price_table, price_records = _pick_member_price_table(context)
    source_records.extend(price_records)
    gross_floor_area_pyeong, current_gross_area_pyeong = _estimate_gross_floor_area_pyeong(context, price_table)
    remaining_months = _stage_months(context, scenario_name)

    direct_construction_cost = gross_floor_area_pyeong * project_input.construction_cost_per_pyeong
    if project_input.delay_one_year and property_input.current_stage not in {"Construction", "Completion"}:
        direct_construction_cost *= 1.04
        source_records.append(_record("delay_markup", "4.0%", "delay_rule", 0.90))
    demolition_cost = current_gross_area_pyeong * project_input.construction_cost_per_pyeong * 0.06
    design_and_pm_cost = direct_construction_cost * 0.06
    reserve_cost = (direct_construction_cost + design_and_pm_cost + demolition_cost) * 0.05

    member_count = max(int(round(project_input.current_households * (1 - project_input.cash_settlement_rate))), 1)
    general_sale_households = max(project_input.planned_households - member_count, 0)
    if project_input.general_sale_ratio is not None:
        general_sale_households = max(int(round(project_input.planned_households * project_input.general_sale_ratio)), 0)
        member_count = max(project_input.planned_households - general_sale_households, 1)
    average_member_sale_price = statistics.mean(item.member_sale_price for item in price_table)
    benchmark_new_price = property_input.comparison_new_apt_price or project_input.general_sale_price or average_member_sale_price / 0.85
    member_sale_revenue = member_count * average_member_sale_price
    general_sale_unit_price = project_input.general_sale_price or benchmark_new_price
    general_sale_revenue = general_sale_households * general_sale_unit_price * project_input.sale_rate
    ancillary_revenue = project_input.ancillary_revenue or direct_construction_cost * 0.02
    other_disposal_revenue = project_input.other_disposal_revenue or direct_construction_cost * 0.01

    sales_expense = general_sale_revenue * 0.025
    settlement_and_litigation_cost = (
        project_input.liquidation_cost_override
        if project_input.liquidation_cost_override is not None
        else total_old_asset_value * (0.005 + project_input.cash_settlement_rate * 0.08)
    )
    base_non_finance_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + reserve_cost + sales_expense + settlement_and_litigation_cost
    tax_and_charge_cost = base_non_finance_cost * 0.03
    pf_principal = max((direct_construction_cost + demolition_cost + design_and_pm_cost + sales_expense + tax_and_charge_cost - reserve_cost) * 0.60, 0.0)
    financing_cost = pf_principal * project_input.pf_rate * 0.55 * (remaining_months / 12.0)
    move_loan_months = max(min(remaining_months, 30.0), 12.0)
    move_loan_interest_cost = member_count * (old_asset_estimate * 0.40) * project_input.move_loan_rate * (move_loan_months / 12.0)

    business_correction_before = 1.0
    business_correction_after = 1.0
    if project_input.apply_seoul_business_boost and ("Seoul" in property_input.address or "\uc11c\uc6b8" in property_input.address) and project_input.public_land_price_avg:
        business_correction_after = clamp(
            safe_div(project_input.seoul_average_public_land_price, project_input.public_land_price_avg, 1.0) + project_input.alpha + project_input.beta,
            1.0,
            2.0,
        )
        general_sale_revenue *= 1 + 0.06 * (business_correction_after - 1.0)
        source_records.append(_record("business_correction_factor", f"{business_correction_after:.3f}", "seoul_business_boost", 0.70))

    member_sale_revenue = _document_override_value(context, "member_sale_revenue", member_sale_revenue) or member_sale_revenue
    general_sale_revenue = _document_override_value(context, "general_sale_revenue", general_sale_revenue) or general_sale_revenue

    total_revenue = _document_override_value(context, "total_revenue") or (member_sale_revenue + general_sale_revenue + ancillary_revenue + other_disposal_revenue)
    total_cost = _document_override_value(context, "total_cost") or (
        direct_construction_cost
        + demolition_cost
        + design_and_pm_cost
        + reserve_cost
        + sales_expense
        + settlement_and_litigation_cost
        + tax_and_charge_cost
        + financing_cost
        + move_loan_interest_cost
        + project_input.reconstruction_levy
    )
    proportional_ratio = safe_div(total_revenue - total_cost, total_old_asset_value, 0.0) * 100.0
    document_ratio = _document_override_value(context, "proportional_ratio")
    if document_ratio is not None:
        proportional_ratio = document_ratio
        source_records.append(_record("proportional_ratio", f"{proportional_ratio:.2f}", "document_override", 0.88))

    average_contribution_per_member = max(average_member_sale_price - old_asset_estimate * (proportional_ratio / 100.0), 0.0)
    general_sale_capacity = safe_div(general_sale_households, project_input.planned_households, 0.0)

    source_records.extend(
        [
            _record("total_revenue", f"{total_revenue:,.0f}", "project_engine", 0.70),
            _record("total_cost", f"{total_cost:,.0f}", "project_engine", 0.70),
            _record("proportional_ratio", f"{proportional_ratio:.2f}", "project_engine", 0.70),
            _record("remaining_months", f"{remaining_months:.1f}", "stage_timeline", 0.76),
        ]
    )
    project_confidence = statistics.mean([
        valuation_confidence,
        0.82 if project_input.member_sale_price_table or context.applied_document_price_table else 0.44,
        0.82 if project_input.planned_households and project_input.current_households else 0.50,
        0.76 if property_input.current_stage in STAGE_BASE_MONTHS else 0.42,
    ])

    return ProjectFeasibilityResult(
        scenario_name=scenario_name,
        total_revenue=total_revenue,
        total_cost=total_cost,
        total_old_asset_value=total_old_asset_value,
        direct_construction_cost=direct_construction_cost,
        demolition_cost=demolition_cost,
        design_and_pm_cost=design_and_pm_cost,
        reserve_cost=reserve_cost,
        financing_cost=financing_cost,
        move_loan_interest_cost=move_loan_interest_cost,
        sales_expense=sales_expense,
        tax_and_charge_cost=tax_and_charge_cost,
        settlement_and_litigation_cost=settlement_and_litigation_cost,
        member_sale_revenue=member_sale_revenue,
        general_sale_revenue=general_sale_revenue,
        ancillary_revenue=ancillary_revenue,
        other_disposal_revenue=other_disposal_revenue,
        proportional_ratio=proportional_ratio,
        average_contribution_per_member=average_contribution_per_member,
        general_sale_capacity=general_sale_capacity,
        business_correction_before=business_correction_before,
        business_correction_after=business_correction_after,
        remaining_months=remaining_months,
        estimated_gross_floor_area_pyeong=gross_floor_area_pyeong,
        confidence=project_confidence,
        source_records=source_records,
    )


def estimate_valuation(context: AppContext, scenario_name: str = "Base", proportional_ratio: float | None = None) -> ValuationResult:
    old_asset_estimate, total_old_asset_value, floor_adjustment_factor, old_asset_source, total_old_asset_source, confidence, notes, source_records = _estimate_old_asset_basics(context)
    if proportional_ratio is None:
        proportional_ratio = compute_project_feasibility(context, scenario_name=scenario_name).proportional_ratio
    adjustment_factor, _, adjustment_records = _estimate_adjustment_factor(context)
    source_records.extend(adjustment_records)
    rights_value = old_asset_estimate * (proportional_ratio / 100.0)
    return ValuationResult(
        scenario_name=scenario_name,
        old_asset_estimate=old_asset_estimate,
        total_old_asset_value=total_old_asset_value,
        proportional_ratio=proportional_ratio,
        rights_value=rights_value,
        adjustment_factor=adjustment_factor,
        floor_adjustment_factor=floor_adjustment_factor,
        old_asset_source=old_asset_source,
        total_old_asset_source=total_old_asset_source,
        confidence=confidence,
        notes=notes,
        source_records=source_records,
    )


def estimate_allocation_candidates(context: AppContext, rights_value: float) -> list[AllocationCandidate]:
    property_input = context.property_input
    price_table, _ = _pick_member_price_table(context)
    candidates: list[AllocationCandidate] = []
    for item in price_table:
        additional_contribution = item.member_sale_price - rights_value
        cover_ratio = safe_div(rights_value, item.member_sale_price, 0.0)
        size_proximity = 1.0 - min(abs(item.exclusive_area_sqm - property_input.current_unit_exclusive_area) / max(property_input.current_unit_exclusive_area, 1.0), 1.0)
        burden_score = 1.0 - min(max(additional_contribution, 0.0) / max(property_input.purchase_price, 1.0), 1.0)
        score = 0.5 * size_proximity + 0.3 * min(cover_ratio, 1.0) + 0.2 * burden_score
        filtered = cover_ratio < 0.35 and not context.aggressive_upsize
        label = "High" if score >= 0.75 else "Medium" if score >= 0.55 else "Low"
        candidates.append(
            AllocationCandidate(
                label=item.label,
                exclusive_area_sqm=item.exclusive_area_sqm,
                supply_area_sqm=item.supply_area_sqm,
                member_sale_price=item.member_sale_price,
                additional_contribution=additional_contribution,
                cover_ratio=cover_ratio,
                score=score,
                feasibility_label=label,
                is_filtered=filtered,
            )
        )
    visible = [item for item in candidates if not item.is_filtered]
    visible.sort(key=lambda item: item.score, reverse=True)
    return visible[:3] if visible else sorted(candidates, key=lambda item: item.score, reverse=True)[:3]


def _pick_selected_candidate(context: AppContext, candidates: list[AllocationCandidate]) -> AllocationCandidate:
    target_area = context.property_input.expected_new_exclusive_area
    if target_area is None:
        return candidates[0]
    return min(candidates, key=lambda item: abs(item.exclusive_area_sqm - target_area))


def _exit_months(project_result: ProjectFeasibilityResult, exit_name: str) -> float:
    if exit_name == "Rights Sale":
        return max(project_result.remaining_months * 0.65, 6.0)
    if exit_name == "Sell at Completion":
        return project_result.remaining_months
    return project_result.remaining_months + 36.0


def _exit_realization_ratio(exit_name: str) -> float:
    if exit_name == "Rights Sale":
        return 0.80
    if exit_name == "Sell at Completion":
        return 0.95
    return 1.02**3


def _build_exit_outcome(context: AppContext, project_result: ProjectFeasibilityResult, selected_candidate: AllocationCandidate, exit_name: str) -> ExitOutcome:
    property_input = context.property_input
    tax_profile = context.tax_profile
    months = _exit_months(project_result, exit_name)
    years_to_exit = max(months / 12.0, 0.5)
    base_new_value = property_input.comparison_new_apt_price or selected_candidate.member_sale_price / 0.85
    gross_exit_value = base_new_value * _exit_realization_ratio(exit_name)
    acquisition_cost = property_input.purchase_price * tax_profile.acquisition_rate
    holding_cost = property_input.purchase_price * tax_profile.annual_holding_rate * years_to_exit
    capital_interest = max(selected_candidate.additional_contribution, 0.0) * max(context.project_input.pf_rate + 0.01, 0.04) * years_to_exit * 0.45
    disposal_cost = gross_exit_value * tax_profile.brokerage_rate
    pretax_profit = gross_exit_value - disposal_cost - (
        property_input.purchase_price + acquisition_cost + holding_cost + max(selected_candidate.additional_contribution, 0.0) + capital_interest
    )
    after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * tax_profile.capital_gains_effective_rate
    total_cash_outflow = property_input.purchase_price + acquisition_cost + holding_cost + max(selected_candidate.additional_contribution, 0.0) + capital_interest
    roi = safe_div(after_tax_profit, total_cash_outflow, 0.0)
    net_exit_inflow = gross_exit_value - disposal_cost - max(pretax_profit, 0.0) * tax_profile.capital_gains_effective_rate
    annualized_irr = None
    if total_cash_outflow > 0 and net_exit_inflow > 0:
        annualized_irr = (net_exit_inflow / total_cash_outflow) ** (1.0 / years_to_exit) - 1.0
    break_even_purchase_price = net_exit_inflow - (acquisition_cost + holding_cost + max(selected_candidate.additional_contribution, 0.0) + capital_interest)
    break_even_additional_contribution = net_exit_inflow - (property_input.purchase_price + acquisition_cost + holding_cost + capital_interest)
    exit_retention = max(1.0 - tax_profile.brokerage_rate - tax_profile.capital_gains_effective_rate * 0.80, 0.05)
    break_even_exit_value = total_cash_outflow / exit_retention
    return ExitOutcome(
        exit_name=exit_name,
        years_to_exit=years_to_exit,
        gross_exit_value=gross_exit_value,
        disposal_cost=disposal_cost,
        pretax_profit=pretax_profit,
        after_tax_profit=after_tax_profit,
        roi=roi,
        annualized_irr=annualized_irr,
        break_even_purchase_price=break_even_purchase_price,
        break_even_additional_contribution=break_even_additional_contribution,
        break_even_exit_value=break_even_exit_value,
    )


def calculate_confidence_score(context: AppContext, valuation_result: ValuationResult, project_result: ProjectFeasibilityResult) -> tuple[float, str]:
    property_input = context.property_input
    project_input = context.project_input
    tax_profile = context.tax_profile
    project_fields = [
        bool(project_input.current_households),
        bool(project_input.planned_households),
        project_input.land_share is not None,
        project_input.current_far is not None,
        project_input.target_far is not None,
        bool(project_input.general_sale_price or project_input.member_sale_price_table or context.applied_document_price_table),
    ]
    project_input_completion = (sum(project_fields) / len(project_fields)) * 100.0
    valuation_strength = valuation_result.confidence * 100.0
    stage_base = STAGE_BASE_MONTHS.get(property_input.current_stage, 72)
    schedule_certainty = clamp(100.0 - stage_base * 0.45 - (12.0 if project_input.delay_one_year else 0.0), 20.0, 100.0)
    tax_fields = [
        tax_profile.acquisition_rate > 0,
        tax_profile.annual_holding_rate >= 0,
        tax_profile.capital_gains_effective_rate >= 0,
        tax_profile.brokerage_rate > 0,
    ]
    tax_completion = (sum(tax_fields) / len(tax_fields)) * 100.0
    score = project_input_completion * 0.40 + valuation_strength * 0.30 + schedule_certainty * 0.20 + tax_completion * 0.10
    label = "High" if score >= 80 else "Medium" if score >= 60 else "Low"
    return score, label


def analyze_investment(context: AppContext) -> list[ScenarioResult]:
    scenario_results: list[ScenarioResult] = []
    for scenario_name in ("Optimistic", "Base", "Conservative"):
        project_result = compute_project_feasibility(context, scenario_name=scenario_name)
        valuation_result = estimate_valuation(context, scenario_name=scenario_name, proportional_ratio=project_result.proportional_ratio)
        allocation_candidates = estimate_allocation_candidates(context, valuation_result.rights_value)
        selected_candidate = _pick_selected_candidate(context, allocation_candidates)
        exit_outcomes = [
            _build_exit_outcome(context, project_result, selected_candidate, exit_name)
            for exit_name in ("Rights Sale", "Sell at Completion", "Hold 3Y After Completion")
        ]
        confidence_score, confidence_label = calculate_confidence_score(context, valuation_result, project_result)
        deduped = list({(record.key, record.value, record.source): record for record in (valuation_result.source_records + project_result.source_records)}.values())
        scenario_results.append(
            ScenarioResult(
                scenario_name=scenario_name,
                description=f"{scenario_name} scenario",
                valuation=valuation_result,
                project=project_result,
                allocation_candidates=allocation_candidates,
                selected_candidate=selected_candidate,
                exit_outcomes=exit_outcomes,
                confidence_score=confidence_score,
                confidence_label=confidence_label,
                source_records=deduped,
            )
        )
    return scenario_results
