from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


SCENARIO_PRESETS: dict[str, dict[str, float]] = {
    "Optimistic": {
        "sale_rate": 1.00,
        "cash_settlement_rate": 0.00,
        "construction_cost_per_pyeong": 8_500_000.0,
        "pf_rate": 0.07,
        "duration_multiplier": 0.80,
    },
    "Base": {
        "sale_rate": 0.97,
        "cash_settlement_rate": 0.03,
        "construction_cost_per_pyeong": 9_000_000.0,
        "pf_rate": 0.085,
        "duration_multiplier": 1.00,
    },
    "Conservative": {
        "sale_rate": 0.92,
        "cash_settlement_rate": 0.07,
        "construction_cost_per_pyeong": 10_000_000.0,
        "pf_rate": 0.10,
        "duration_multiplier": 1.35,
    },
}

STAGE_BASE_MONTHS: dict[str, int] = {
    "Rebuild Diagnostic": 120,
    "District Designation": 96,
    "Promotion Committee": 84,
    "Association Approval": 72,
    "Project Approval": 48,
    "Disposition Approval": 36,
    "Relocation/Demolition": 24,
    "Construction": 18,
    "Completion": 0,
}

STAGE_OPTIONS: tuple[str, ...] = tuple(STAGE_BASE_MONTHS.keys())
EXIT_SCENARIOS: tuple[str, ...] = ("Rights Sale", "Sell at Completion", "Hold 3Y After Completion")


@dataclass(slots=True)
class SourceRecord:
    key: str
    value: str
    source: str
    retrieved_at: str
    confidence: float
    notes: str = ""


@dataclass(slots=True)
class MemberPriceRecord:
    label: str
    exclusive_area_sqm: float
    supply_area_sqm: float
    member_sale_price: float


@dataclass(slots=True)
class ParsedProjectNotice:
    proportional_ratio: float | None = None
    old_asset_formula: str | None = None
    member_price_table: list[MemberPriceRecord] = field(default_factory=list)
    revenue_items: dict[str, float] = field(default_factory=dict)
    cost_items: dict[str, float] = field(default_factory=dict)
    source_url: str | None = None
    extracted_records: list[SourceRecord] = field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class PropertyInput:
    complex_name: str
    address: str
    current_stage: str
    purchase_price: float
    purchase_date: date
    current_unit_supply_area: float
    current_unit_exclusive_area: float
    building_no: str = ""
    floor_no: int = 0
    expected_new_exclusive_area: float | None = None
    comparison_new_apt_price: float | None = None
    recent_same_complex_trade_price: float | None = None
    public_price: float | None = None
    appraised_old_asset_value: float | None = None
    manual_overrides: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ProjectInput:
    land_share: float | None = None
    current_households: int = 100
    planned_households: int = 120
    current_far: float | None = None
    target_far: float | None = None
    construction_cost_per_pyeong: float = 9_000_000.0
    pf_rate: float = 0.085
    move_loan_rate: float = 0.05
    general_sale_price: float | None = None
    general_sale_ratio: float | None = None
    member_sale_price_table: list[MemberPriceRecord] = field(default_factory=list)
    sale_rate: float = 0.97
    cash_settlement_rate: float = 0.03
    delay_one_year: bool = False
    apply_seoul_business_boost: bool = False
    public_land_price_avg: float | None = None
    seoul_average_public_land_price: float = 43_000_000.0
    alpha: float = 0.0
    beta: float = 0.0
    reconstruction_levy: float = 0.0
    ancillary_revenue: float = 0.0
    other_disposal_revenue: float = 0.0
    existing_total_old_asset_value: float | None = None
    existing_total_market_value: float | None = None
    adjustment_factor_override: float | None = None
    liquidation_cost_override: float | None = None
    parsed_notice: ParsedProjectNotice | None = None


@dataclass(slots=True)
class TaxProfile:
    label: str
    acquisition_rate: float = 0.015
    annual_holding_rate: float = 0.003
    capital_gains_effective_rate: float = 0.20
    brokerage_rate: float = 0.004


@dataclass(slots=True)
class ValuationResult:
    scenario_name: str
    old_asset_estimate: float
    total_old_asset_value: float
    proportional_ratio: float
    rights_value: float
    adjustment_factor: float
    floor_adjustment_factor: float
    old_asset_source: str
    total_old_asset_source: str
    confidence: float
    notes: list[str] = field(default_factory=list)
    source_records: list[SourceRecord] = field(default_factory=list)


@dataclass(slots=True)
class ProjectFeasibilityResult:
    scenario_name: str
    total_revenue: float
    total_cost: float
    total_old_asset_value: float
    direct_construction_cost: float
    demolition_cost: float
    design_and_pm_cost: float
    reserve_cost: float
    financing_cost: float
    move_loan_interest_cost: float
    sales_expense: float
    tax_and_charge_cost: float
    settlement_and_litigation_cost: float
    member_sale_revenue: float
    general_sale_revenue: float
    ancillary_revenue: float
    other_disposal_revenue: float
    proportional_ratio: float
    average_contribution_per_member: float
    general_sale_capacity: float
    business_correction_before: float
    business_correction_after: float
    remaining_months: float
    estimated_gross_floor_area_pyeong: float
    confidence: float
    source_records: list[SourceRecord] = field(default_factory=list)


@dataclass(slots=True)
class AllocationCandidate:
    label: str
    exclusive_area_sqm: float
    supply_area_sqm: float
    member_sale_price: float
    additional_contribution: float
    cover_ratio: float
    score: float
    feasibility_label: str
    is_filtered: bool = False


@dataclass(slots=True)
class ExitOutcome:
    exit_name: str
    years_to_exit: float
    gross_exit_value: float
    disposal_cost: float
    pretax_profit: float
    after_tax_profit: float
    roi: float
    annualized_irr: float | None
    break_even_purchase_price: float
    break_even_additional_contribution: float
    break_even_exit_value: float


@dataclass(slots=True)
class ScenarioResult:
    scenario_name: str
    description: str
    valuation: ValuationResult
    project: ProjectFeasibilityResult
    allocation_candidates: list[AllocationCandidate]
    selected_candidate: AllocationCandidate
    exit_outcomes: list[ExitOutcome]
    confidence_score: float
    confidence_label: str
    source_records: list[SourceRecord] = field(default_factory=list)


@dataclass(slots=True)
class AppContext:
    property_input: PropertyInput
    project_input: ProjectInput
    tax_profile: TaxProfile
    parsed_notice: ParsedProjectNotice | None
    applied_document_fields: set[str] = field(default_factory=set)
    applied_document_price_table: bool = False
    aggressive_upsize: bool = False


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
