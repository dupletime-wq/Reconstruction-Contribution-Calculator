from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProjectKind(str, Enum):
    RECONSTRUCTION = "재건축"
    REDEVELOPMENT = "재개발"
    REMODELING = "리모델링"


class ReconstructionStyle(str, Enum):
    APARTMENT = "공동주택"
    DETACHED_CLUSTER = "단독주택 묶음"


class ProjectRoute(str, Enum):
    AUTO = "auto"
    SEOUL_PRIVATE_RECONSTRUCTION = "seoul_private_reconstruction"
    SEOUL_PRIVATE_REDEVELOPMENT = "seoul_private_redevelopment"
    SEOUL_PUBLIC_REDEVELOPMENT = "seoul_public_redevelopment"
    SEOUL_CONTRIBUTION_RELAXED = "seoul_contribution_relaxed"


class MarketReferenceMode(str, Enum):
    OFFICIAL_PLUS_MARKET = "official_plus_market"
    MANUAL_ONLY = "manual_only"


DEFAULT_POLICY_PROFILE_VERSION = "seoul-v1"
DEFAULT_MARKET_REFERENCE_MODE = MarketReferenceMode.OFFICIAL_PLUS_MARKET.value

STAGE_BASE_MONTHS: dict[str, int] = {
    "안전진단": 156,
    "정비구역지정": 132,
    "추진위승인": 108,
    "조합설립인가": 96,
    "사업시행인가": 72,
    "관리처분인가": 48,
    "이주/철거": 30,
    "착공": 24,
    "준공/입주": 0,
}

SEOUL_AVG_OFFICIAL_PRICE_PER_SQM: dict[ProjectKind, float] = {
    ProjectKind.RECONSTRUCTION: 7_192_258.0,
    ProjectKind.REDEVELOPMENT: 5_861_129.0,
}

RECONSTRUCTION_LEVY_BRACKETS: tuple[tuple[float, float | None, float, float], ...] = (
    (80_000_000.0, 130_000_000.0, 0.10, 0.0),
    (130_000_000.0, 180_000_000.0, 0.20, 5_000_000.0),
    (180_000_000.0, 230_000_000.0, 0.30, 15_000_000.0),
    (230_000_000.0, 280_000_000.0, 0.40, 30_000_000.0),
    (280_000_000.0, None, 0.50, 50_000_000.0),
)

RECONSTRUCTION_LEVY_HOLDING_RELIEF: tuple[tuple[float, float | None, float], ...] = (
    (6.0, 7.0, 0.10),
    (7.0, 8.0, 0.20),
    (8.0, 9.0, 0.30),
    (9.0, 10.0, 0.40),
    (10.0, 15.0, 0.50),
    (15.0, 20.0, 0.60),
    (20.0, None, 0.70),
)

SOURCE_LABELS: dict[str, str] = {
    "official_cleanup": "서울 정비몽땅",
    "manual": "직접 입력",
    "manual_override": "직접 보정",
    "manual_adjusted": "직접 입력 후 자동 상향",
    "heuristic": "휴리스틱",
    "simulation": "자동 시뮬레이션",
    "policy": "서울 정책 기준",
    "policy_profile": "법정/정책 프로필",
    "general_sale_price": "일반분양 평균가",
    "general_sale_ppy": "일반분양 평당가",
    "comparison_new_price": "비교 신축 시세",
    "fallback": "매수가 기반 보정",
    "trade_vs_public": "실거래-공시 비교",
    "heuristic_default": "공시가격 보정 기본값",
    "recent_trade": "최근 실거래",
}

REFERENCE_URLS: dict[str, str] = {
    "cleanup": "https://cleanup.seoul.go.kr/",
    "seoul_ordinance": "https://law.go.kr/ordinInfoP.do%3FordinSeq%3D1736907",
    "molit_rental_notice": "https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?gubun=&idx=18076&lcmspage=6&old_search_dept_nm=&psize=10&search=%EC%A3%BC%ED%83%9D&search_dept_id=&search_dept_nm=&search_regdate_e=&search_regdate_s=&srch_usr_ctnt=&srch_usr_nm=&srch_usr_num=&srch_usr_titl=Y&srch_usr_year=",
    "seoul_public_contribution": "https://mediahub.seoul.go.kr/archives/2015170",
    "applyhome": "https://static.applyhome.co.kr/co/coa/selectMainView.do",
}


@dataclass
class SourceRecord:
    key: str
    value: str
    source: str
    note: str = ""


@dataclass
class WarningMessage:
    level: str
    category: str
    message: str


@dataclass
class UnitMixRow:
    label: str
    households: int
    exclusive_area_sqm: float
    supply_area_sqm: float


@dataclass
class SeoulProjectData:
    project_name: str
    district: str
    business_type: str
    project_kind: ProjectKind | None
    progress_stage: str | None
    representative_lot: str = ""
    project_slug: str = ""
    cafe_id: str = ""
    source_url: str = ""
    official_area_sqm: float | None = None
    site_area_sqm: float | None = None
    gross_floor_area_sqm: float | None = None
    target_building_coverage_ratio_pct: float | None = None
    target_far_pct: float | None = None
    current_households: int | None = None
    owner_count: int | None = None
    tenant_count: int | None = None
    planned_households: int | None = None
    sale_households_total: int | None = None
    sale_households: int | None = None
    rental_households: int | None = None
    public_facility_area_sqm: float | None = None
    donation_area_sqm: float | None = None
    average_current_floors: float | None = None
    current_building_count: int | None = None
    schedule_text: str | None = None
    official_planned_households: int | None = None
    official_general_sale_households: int | None = None
    official_rental_households: int | None = None
    official_public_facility_area_sqm: float | None = None
    official_donation_area_sqm: float | None = None
    official_target_far_pct: float | None = None
    official_target_bcr_pct: float | None = None
    project_route_hint: str | None = None
    source_reference_date: str = "2024-01-19"
    existing_unit_mix_rows: list[UnitMixRow] = field(default_factory=list)
    source_records: list[SourceRecord] = field(default_factory=list)


@dataclass
class PolicyAdjustment:
    active: bool
    coefficient: float = 1.0
    price_factor: float = 1.0
    area_factor: float = 0.0
    density_factor: float = 0.0
    recognized_far_pct: float | None = None
    estimated_target_far_pct: float | None = None
    note: str = ""


@dataclass
class SiteResolution:
    selected_total_site_area_sqm: float | None
    source: str
    official_site_area_sqm: float | None = None
    manual_site_area_sqm: float | None = None
    implied_site_area_sqm: float | None = None
    average_site_area_per_member_sqm: float | None = None


@dataclass
class ReconstructionLevyResult:
    total_levy: float
    levy_per_member: float
    average_profit_per_member: float
    relief_ratio: float
    bracket_label: str


@dataclass(frozen=True)
class RegulatoryConstraintSet:
    profile_id: str
    project_route: str
    project_kind: ProjectKind
    policy_profile_version: str
    legal_min_rental_ratio: float
    target_rental_ratio: float
    legal_min_public_contribution_ratio: float
    target_public_contribution_ratio: float
    rental_source_url: str
    public_contribution_source_url: str
    basis_date: str
    note: str


@dataclass
class ConstraintResolution:
    profile_id: str
    project_route: str
    policy_profile_version: str
    planned_households: int
    planned_households_source: str
    resolved_rental_households: int
    resolved_rental_ratio: float
    resolved_public_contribution_area_sqm: float
    resolved_public_contribution_ratio: float
    resolved_general_sale_households: int
    resolved_general_sale_ratio: float
    legal_min_rental_households: int
    legal_min_public_contribution_area_sqm: float
    rental_source: str
    public_contribution_source: str
    general_sale_source: str
    override_notes: list[str] = field(default_factory=list)


@dataclass
class PlanAreaLedger:
    gross_floor_area_sqm: float
    gross_usable_area_sqm: float
    public_contribution_area_sqm: float
    saleable_residential_area_sqm: float
    rental_area_sqm: float
    member_area_sqm: float
    general_sale_area_sqm: float
    residual_saleable_area_sqm: float
    average_supply_area_sqm: float
    rental_reference_supply_area_sqm: float
    capacity_households: int
    mix_demand_area_sqm: float
    capacity_gap_sqm: float


@dataclass
class QaOutcome:
    regulatory_strength: float
    official_alignment_strength: float
    conservation_ok: bool
    monotonic_ok: bool
    confidence_cap: float
    rows: list[dict[str, str]] = field(default_factory=list)
    warnings: list[WarningMessage] = field(default_factory=list)


@dataclass
class UnionProjectInputs:
    project_kind: ProjectKind
    reconstruction_style: ReconstructionStyle
    region_is_seoul: bool
    seoul_project: SeoulProjectData | None
    purchase_price: float
    current_stage: str
    current_households: int
    current_unit_exclusive_area: float
    current_unit_supply_area: float
    expected_new_exclusive_area: float
    comparison_new_price: float | None
    general_sale_price: float | None
    general_sale_price_basis_exclusive_area: float | None
    general_sale_price_per_pyeong_manwon: float | None
    construction_cost_per_pyeong: float
    current_far_pct: float | None
    target_far_pct: float | None
    total_site_area_sqm: float | None
    land_share_sqm: float | None
    current_building_coverage_ratio_pct: float | None
    target_building_coverage_ratio_pct: float | None
    average_current_floors: float | None
    floor_no: int
    recent_same_complex_trade_price: float | None
    adjustment_factor_override: float | None
    existing_unit_mix_rows: list[UnitMixRow]
    planned_unit_mix_rows: list[UnitMixRow]
    official_price_reference: float | None
    appraised_old_asset_value: float | None
    total_old_asset_value: float | None
    avg_official_land_price_per_sqm: float | None
    target_households_override: int | None
    general_sale_ratio_override: float | None
    rental_ratio_override: float | None
    donation_ratio_override: float | None
    member_sale_price_ratio_override: float | None
    sale_rate: float
    cash_settlement_rate: float
    pf_rate: float
    move_loan_rate: float
    pf_financing_ratio: float
    pf_interest_months: float
    average_move_loan_amount: float
    move_loan_duration_months: float
    include_reconstruction_levy: bool
    manual_reconstruction_levy_total: float | None
    is_one_homeowner: bool
    holding_years: float
    project_route: str = ProjectRoute.AUTO.value
    policy_profile_version: str = DEFAULT_POLICY_PROFILE_VERSION
    market_reference_mode: str = DEFAULT_MARKET_REFERENCE_MODE


@dataclass
class CalculationResult:
    mode: ProjectKind
    top_cards: list[tuple[str, str, str]]
    summary_lines: list[str]
    warnings: list[WarningMessage]
    why_rows: list[dict[str, str]]
    business_rows: list[dict[str, str]]
    settlement_rows: list[dict[str, str]]
    sensitivity_rows: list[dict[str, str]]
    policy_rows: list[dict[str, str]]
    source_rows: list[dict[str, str]]
    allocation_rows: list[dict[str, str]] = field(default_factory=list)
    planned_mix_rows: list[dict[str, str]] = field(default_factory=list)
    qa_rows: list[dict[str, str]] = field(default_factory=list)
    debug_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class UnionPlanPreview:
    remaining_months: float
    duration_source: str
    site_resolution: SiteResolution
    site_warnings: list[WarningMessage]
    target_far_pct: float
    target_bcr_pct: float | None
    target_bcr_source: str
    required_avg_floors: float | None
    current_gross_floor_area_sqm: float
    gross_floor_area_sqm: float
    average_supply_area_sqm: float
    average_exclusive_area_sqm: float
    residential_efficiency: float
    residential_efficiency_source: str
    planned_households: int
    planned_households_source: str
    simulated_total_households: int
    member_households: int
    general_sale_households: int
    general_sale_source: str
    rental_households: int
    donation_ratio: float
    donation_source: str
    rental_ratio: float
    rental_source: str
    general_sale_ratio: float
    planned_mix_rows: list[UnitMixRow]
    planned_mix_source: str
    constraint_resolution: ConstraintResolution
    plan_area_ledger: PlanAreaLedger
    qa_outcome: QaOutcome
    resolved_public_contribution_area_sqm: float
    resolved_public_contribution_ratio: float
    resolved_rental_households: int
    resolved_general_sale_households: int


@dataclass(frozen=True)
class PolicyProfile:
    profile_id: str
    project_route: str
    project_kind: ProjectKind
    legal_min_rental_ratio: float
    target_rental_ratio: float
    legal_min_public_contribution_ratio: float
    target_public_contribution_ratio: float
    note: str


POLICY_PROFILES: dict[str, PolicyProfile] = {
    ProjectRoute.SEOUL_PRIVATE_RECONSTRUCTION.value: PolicyProfile(
        profile_id="seoul_private_reconstruction_general",
        project_route=ProjectRoute.SEOUL_PRIVATE_RECONSTRUCTION.value,
        project_kind=ProjectKind.RECONSTRUCTION,
        legal_min_rental_ratio=0.03,
        target_rental_ratio=0.05,
        legal_min_public_contribution_ratio=0.05,
        target_public_contribution_ratio=0.08,
        note="서울 민간 재건축 일반 프로필. 정비몽땅 공식 계획이 있으면 그 값을 우선 적용합니다.",
    ),
    ProjectRoute.SEOUL_PRIVATE_REDEVELOPMENT.value: PolicyProfile(
        profile_id="seoul_private_redevelopment_general",
        project_route=ProjectRoute.SEOUL_PRIVATE_REDEVELOPMENT.value,
        project_kind=ProjectKind.REDEVELOPMENT,
        legal_min_rental_ratio=0.10,
        target_rental_ratio=0.15,
        legal_min_public_contribution_ratio=0.08,
        target_public_contribution_ratio=0.12,
        note="서울 민간 재개발 일반 프로필. 임대주택과 공공기여를 공식값/법정 하한 중 더 보수적으로 반영합니다.",
    ),
    ProjectRoute.SEOUL_PUBLIC_REDEVELOPMENT.value: PolicyProfile(
        profile_id="seoul_public_redevelopment_special",
        project_route=ProjectRoute.SEOUL_PUBLIC_REDEVELOPMENT.value,
        project_kind=ProjectKind.REDEVELOPMENT,
        legal_min_rental_ratio=0.15,
        target_rental_ratio=0.20,
        legal_min_public_contribution_ratio=0.10,
        target_public_contribution_ratio=0.15,
        note="서울 공공재개발/특례형 프로필. 민간형보다 보수적인 임대·공공기여 목표를 사용합니다.",
    ),
    ProjectRoute.SEOUL_CONTRIBUTION_RELAXED.value: PolicyProfile(
        profile_id="seoul_public_contribution_relaxed",
        project_route=ProjectRoute.SEOUL_CONTRIBUTION_RELAXED.value,
        project_kind=ProjectKind.REDEVELOPMENT,
        legal_min_rental_ratio=0.10,
        target_rental_ratio=0.12,
        legal_min_public_contribution_ratio=0.02,
        target_public_contribution_ratio=0.04,
        note="서울 공공기여 완화 대상지 가정 프로필. 일반형보다 공공기여율을 완화해 시뮬레이션합니다.",
    ),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0:
        return default
    return num / den


def fmt_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) / 100_000_000.0:,.2f}억"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"


def fmt_plain_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def settlement_label(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"추가분담금 {fmt_money(value)}"
    if value < 0:
        return f"환급금 {fmt_money(abs(value))}"
    return "정산 없음"


def humanize_source(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def record(key: str, value: str, source: str, note: str = "") -> SourceRecord:
    return SourceRecord(key=key, value=value, source=source, note=note)


def warning(level: str, category: str, message: str) -> WarningMessage:
    return WarningMessage(level=level, category=category, message=message)


def dedupe_warning_messages(items: list[WarningMessage]) -> list[WarningMessage]:
    deduped: list[WarningMessage] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (item.level, item.category, item.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def uses_land_based_flow(project_kind: ProjectKind, reconstruction_style: ReconstructionStyle) -> bool:
    return project_kind == ProjectKind.REDEVELOPMENT or reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER


def uses_apartment_reconstruction_flow(project_kind: ProjectKind, reconstruction_style: ReconstructionStyle) -> bool:
    return project_kind == ProjectKind.RECONSTRUCTION and reconstruction_style == ReconstructionStyle.APARTMENT


def scale_price_by_area(anchor_price: float, anchor_exclusive_area: float | None, target_exclusive_area: float | None) -> float:
    base_area = max(float(anchor_exclusive_area or 0.0), 1.0)
    target_area = max(float(target_exclusive_area or base_area), 1.0)
    return float(anchor_price) * ((target_area / base_area) ** 0.98)


def price_from_supply_pyeong(price_per_pyeong_manwon: float | None, target_supply_area_sqm: float | None) -> float | None:
    if price_per_pyeong_manwon is None or target_supply_area_sqm is None:
        return None
    return float(price_per_pyeong_manwon) * 10_000.0 * (float(target_supply_area_sqm) / 3.3058)


def estimate_supply_area_from_exclusive_area(exclusive_area_sqm: float, project_kind: ProjectKind) -> float:
    area = max(float(exclusive_area_sqm), 1.0)
    if project_kind == ProjectKind.REDEVELOPMENT:
        ratio = 1.27 if area <= 59 else 1.25 if area <= 84 else 1.22
    else:
        if area <= 59:
            ratio = 1.30
        elif area <= 74:
            ratio = 1.28
        elif area <= 84:
            ratio = 1.27
        elif area <= 101:
            ratio = 1.25
        else:
            ratio = 1.23
    return round(area * ratio, 2)


def estimate_exclusive_area_from_supply_area(supply_area_sqm: float, project_kind: ProjectKind) -> float:
    supply = max(float(supply_area_sqm), 1.0)
    ratios = (1.27, 1.25) if project_kind == ProjectKind.REDEVELOPMENT else (1.30, 1.27, 1.23)
    return round(sum(supply / ratio for ratio in ratios) / len(ratios), 2)


def infer_unit_mix_label(exclusive_area_sqm: float) -> str:
    return f"{int(round(exclusive_area_sqm))}㎡"


def weighted_average_exclusive_area(rows: list[UnitMixRow], default_exclusive_area: float) -> float:
    if not rows:
        return default_exclusive_area
    weighted_area = sum(item.households * item.exclusive_area_sqm for item in rows)
    total_households = sum(item.households for item in rows)
    return safe_div(weighted_area, total_households, default_exclusive_area)


def weighted_average_supply_area(rows: list[UnitMixRow], default_supply_area: float) -> float:
    if not rows:
        return default_supply_area
    weighted_area = sum(item.households * item.supply_area_sqm for item in rows)
    total_households = sum(item.households for item in rows)
    return safe_div(weighted_area, total_households, default_supply_area)


def nearest_standard_size(target_size: float, sizes: list[float] | tuple[float, ...]) -> float:
    if not sizes:
        return float(target_size)
    return float(min(sizes, key=lambda size: (abs(size - target_size), size)))


def candidate_planned_sizes(
    *,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
    average_exclusive: float,
    expected_new_exclusive_area: float,
) -> list[float]:
    if uses_land_based_flow(project_kind, reconstruction_style):
        return [59.0, 74.0, 84.0]
    if average_exclusive >= 100.0 or expected_new_exclusive_area >= 101.0:
        return [59.0, 84.0, 101.0, 114.0]
    if average_exclusive >= 84.0 or expected_new_exclusive_area >= 84.0:
        return [59.0, 74.0, 84.0, 101.0]
    return [59.0, 74.0, 84.0]


def project_member_target_size(existing_exclusive_area: float, expected_new_exclusive_area: float, sizes: list[float]) -> float:
    growth_target = (float(existing_exclusive_area) * 1.18) + 6.0
    minimum_target = max(59.0, min(float(expected_new_exclusive_area), max(sizes)) * 0.72)
    projected_size = max(growth_target, minimum_target)
    return nearest_standard_size(projected_size, sizes)


def extra_sale_weights_from_member_mix(member_counts: list[int], sizes: list[float], expected_new_exclusive_area: float) -> list[float]:
    total_members = max(sum(member_counts), 1)
    sale_anchor = nearest_standard_size(max(float(expected_new_exclusive_area), min(sizes)), sizes)
    smallest_size = min(sizes)
    weights: list[float] = []
    for size, count in zip(sizes, member_counts):
        inherited_share = safe_div(count, total_members, 0.0)
        bias = 0.10
        if size == sale_anchor:
            bias += 0.12
        elif size < sale_anchor:
            bias += 0.08
        else:
            bias += 0.04
        if size == smallest_size:
            bias += 0.02
        weights.append((inherited_share * 0.55) + bias)
    return weights


def estimate_residential_efficiency(
    *,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
    required_avg_floors: float | None,
    target_bcr_pct: float | None,
    current_far_pct: float | None,
    target_far_pct: float,
    average_exclusive_area_sqm: float,
) -> tuple[float, str]:
    if project_kind == ProjectKind.REDEVELOPMENT:
        base_efficiency = 0.72
    elif reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        base_efficiency = 0.69
    else:
        base_efficiency = 0.76
    if average_exclusive_area_sqm <= 59:
        base_efficiency += 0.02
    elif average_exclusive_area_sqm >= 101:
        base_efficiency -= 0.02
    if required_avg_floors is not None:
        if required_avg_floors >= 35:
            base_efficiency -= 0.06
        elif required_avg_floors >= 25:
            base_efficiency -= 0.03
    elif current_far_pct is not None and target_far_pct - current_far_pct >= 120:
        base_efficiency -= 0.03
    if target_bcr_pct is not None and target_bcr_pct <= 18:
        base_efficiency -= 0.02
    return clamp(base_efficiency, 0.60, 0.82), "heuristic"


def allocate_counts_by_weights(total_count: int, weights: list[float]) -> list[int]:
    if total_count <= 0 or not weights:
        return [0 for _ in weights]
    cleaned = [max(float(weight), 0.0) for weight in weights]
    total_weight = sum(cleaned)
    if total_weight <= 0:
        even = total_count // len(weights)
        counts = [even for _ in weights]
        for index in range(total_count - sum(counts)):
            counts[index] += 1
        return counts
    raw = [total_count * weight / total_weight for weight in cleaned]
    counts = [int(value) for value in raw]
    remainder = total_count - sum(counts)
    ranked_indices = sorted(range(len(weights)), key=lambda idx: (raw[idx] - counts[idx], cleaned[idx]), reverse=True)
    for index in ranked_indices[:remainder]:
        counts[index] += 1
    return counts


def allocation_from_capacities(capacities: list[int], target_count: int) -> list[int]:
    if target_count <= 0 or not capacities:
        return [0 for _ in capacities]
    remaining = target_count
    allocations = [0 for _ in capacities]
    ranked_indices = sorted(range(len(capacities)), key=lambda idx: capacities[idx], reverse=True)
    while remaining > 0:
        progressed = False
        for index in ranked_indices:
            available = capacities[index] - allocations[index]
            if available <= 0:
                continue
            allocations[index] += 1
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break
    return allocations


def floor_factor(floor_no: int) -> float:
    if floor_no <= 2:
        return 0.96
    if floor_no >= 20:
        return 1.04
    return 1.00 + clamp((floor_no - 10) * 0.004, -0.04, 0.04)


def adjustment_factor(
    *,
    public_price: float,
    recent_trade: float | None,
    override_value: float | None,
    region_is_seoul: bool,
) -> tuple[float, str]:
    if override_value is not None:
        return clamp(override_value, 0.80, 1.80), "manual_override"
    if recent_trade is not None and public_price > 0:
        ratio = clamp(recent_trade / public_price, 0.85, 1.65)
        return ratio, "trade_vs_public"
    return (1.25 if region_is_seoul else 1.18), "heuristic_default"


def auto_planned_unit_mix_rows(inputs: UnionProjectInputs, planned_households: int) -> tuple[list[UnitMixRow], str]:
    if planned_households <= 0:
        return [], "simulation"
    if inputs.planned_unit_mix_rows:
        return inputs.planned_unit_mix_rows, "manual_override"
    average_exclusive = weighted_average_exclusive_area(inputs.existing_unit_mix_rows, inputs.current_unit_exclusive_area)
    sizes = candidate_planned_sizes(
        project_kind=inputs.project_kind,
        reconstruction_style=inputs.reconstruction_style,
        average_exclusive=average_exclusive,
        expected_new_exclusive_area=inputs.expected_new_exclusive_area,
    )
    if inputs.existing_unit_mix_rows:
        source_total = sum(max(row.households, 0) for row in inputs.existing_unit_mix_rows)
        if source_total > 0:
            member_counts = allocate_counts_by_weights(
                inputs.current_households,
                [
                    sum(row.households for row in inputs.existing_unit_mix_rows if nearest_standard_size(row.exclusive_area_sqm, sizes) == size)
                    for size in sizes
                ],
            )
            if planned_households <= sum(member_counts):
                counts = allocate_counts_by_weights(planned_households, [float(count) for count in member_counts])
            else:
                extra_weights = extra_sale_weights_from_member_mix(member_counts, sizes, inputs.expected_new_exclusive_area)
                extra_counts = allocate_counts_by_weights(planned_households - sum(member_counts), extra_weights)
                counts = [member + extra for member, extra in zip(member_counts, extra_counts)]
        else:
            counts = allocate_counts_by_weights(planned_households, [0.35, 0.35, 0.30][: len(sizes)])
    else:
        counts = allocate_counts_by_weights(planned_households, [0.30, 0.30, 0.40][: len(sizes)])
    rows: list[UnitMixRow] = []
    for size, households in zip(sizes, counts):
        if households <= 0:
            continue
        rows.append(
            UnitMixRow(
                label=infer_unit_mix_label(size),
                households=households,
                exclusive_area_sqm=float(size),
                supply_area_sqm=estimate_supply_area_from_exclusive_area(size, inputs.project_kind),
            )
        )
    return rows, "simulation"


def resolve_business_unit_price(
    *,
    general_sale_price: float | None,
    general_sale_basis_area: float | None,
    general_sale_price_per_pyeong_manwon: float | None,
    comparison_new_price: float | None,
    purchase_price: float,
    target_exclusive_area: float,
    target_supply_area_sqm: float,
) -> tuple[float, str]:
    per_pyeong_price = price_from_supply_pyeong(general_sale_price_per_pyeong_manwon, target_supply_area_sqm)
    if per_pyeong_price is not None:
        return per_pyeong_price, "general_sale_ppy"
    if general_sale_price is not None:
        return scale_price_by_area(general_sale_price, general_sale_basis_area or 84.0, target_exclusive_area), "general_sale_price"
    if comparison_new_price is not None:
        return scale_price_by_area(comparison_new_price * 0.92, general_sale_basis_area or target_exclusive_area, target_exclusive_area), "comparison_new_price"
    return scale_price_by_area(purchase_price * 1.35, general_sale_basis_area or 84.0, target_exclusive_area), "fallback"


def resolve_exit_unit_price(
    *,
    comparison_new_price: float | None,
    general_sale_price: float | None,
    general_sale_basis_area: float | None,
    purchase_price: float,
    target_exclusive_area: float,
) -> tuple[float, str]:
    if comparison_new_price is not None:
        return scale_price_by_area(comparison_new_price, general_sale_basis_area or target_exclusive_area, target_exclusive_area), "comparison_new_price"
    if general_sale_price is not None:
        return scale_price_by_area(general_sale_price, general_sale_basis_area or target_exclusive_area, target_exclusive_area), "general_sale_price"
    return scale_price_by_area(purchase_price * 1.45, general_sale_basis_area or 84.0, target_exclusive_area), "fallback"


def default_member_sale_price_ratio(project_kind: ProjectKind, current_stage: str, override_value: float | None) -> tuple[float, str]:
    if override_value is not None:
        return clamp(override_value, 0.55, 0.95), "manual_override"
    base_ratio = 0.70 if project_kind == ProjectKind.REDEVELOPMENT else 0.75
    if current_stage in {"관리처분인가", "이주/철거", "착공", "준공/입주"}:
        base_ratio += 0.02
    return clamp(base_ratio, 0.60, 0.90), "heuristic"


def seoul_policy_adjustment(
    *,
    project_kind: ProjectKind,
    region_is_seoul: bool,
    current_far_pct: float | None,
    target_far_pct: float | None,
    total_site_area_sqm: float | None,
    current_households: int,
    current_unit_supply_area: float,
    avg_official_land_price_per_sqm: float | None,
) -> PolicyAdjustment:
    if not region_is_seoul or project_kind == ProjectKind.REMODELING:
        return PolicyAdjustment(active=False, note="서울 전용 제도는 비서울/리모델링에는 자동 적용하지 않습니다.")
    seoul_avg_price = SEOUL_AVG_OFFICIAL_PRICE_PER_SQM.get(project_kind)
    if seoul_avg_price is None:
        return PolicyAdjustment(active=False, note="서울 전용 제도 대상이 아닌 유형입니다.")
    if avg_official_land_price_per_sqm is not None:
        price_factor = clamp(seoul_avg_price / max(avg_official_land_price_per_sqm, 1.0), 1.0, 2.0)
        price_note = "평균 공시지가 입력값 기준"
    else:
        price_factor = 1.0
        price_note = "평균 공시지가가 없어 가격 보정계수는 1.0으로 유지"
    area_factor = 0.0
    density_factor = 0.0
    if project_kind == ProjectKind.RECONSTRUCTION and total_site_area_sqm is not None and total_site_area_sqm < 20_000:
        area_factor = 0.20 if total_site_area_sqm <= 10_000 else clamp(0.20 - ((total_site_area_sqm - 10_000) / 10_000.0) * 0.10, 0.10, 0.20)
    if project_kind == ProjectKind.RECONSTRUCTION:
        avg_supply_per_household = safe_div(total_site_area_sqm or (current_households * current_unit_supply_area), current_households, current_unit_supply_area)
        density_factor = 0.20 if avg_supply_per_household <= 80 else 0.10 if avg_supply_per_household <= 110 else 0.0
    coefficient = clamp(price_factor + area_factor + density_factor, 1.0, 2.0)
    baseline_far = 230.0 if project_kind == ProjectKind.RECONSTRUCTION else 190.0
    recognized_far_pct = current_far_pct if current_far_pct is not None and current_far_pct > baseline_far else None
    effective_seed = target_far_pct if target_far_pct is not None else recognized_far_pct or baseline_far
    incentive_far = 20.0 if project_kind == ProjectKind.RECONSTRUCTION else 30.0
    estimated_target_far_pct = effective_seed if target_far_pct is not None else effective_seed + incentive_far * coefficient
    return PolicyAdjustment(
        active=True,
        coefficient=coefficient,
        price_factor=price_factor,
        area_factor=area_factor,
        density_factor=density_factor,
        recognized_far_pct=recognized_far_pct,
        estimated_target_far_pct=estimated_target_far_pct,
        note=price_note,
    )


def estimate_remaining_months(stage: str, seoul_project: SeoulProjectData | None, project_kind: ProjectKind) -> tuple[float, str]:
    if project_kind == ProjectKind.REMODELING:
        return 48.0, "heuristic"
    base = float(STAGE_BASE_MONTHS.get(stage, 72))
    if seoul_project and seoul_project.schedule_text:
        return max(base - 6.0, 6.0), "official_cleanup"
    return base, "heuristic"


def estimate_current_gross_floor_area_sqm(
    inputs: UnionProjectInputs,
    official_site_area_sqm: float | None,
    official_gross_floor_area_sqm: float | None,
) -> float:
    if official_gross_floor_area_sqm is not None:
        return official_gross_floor_area_sqm
    if official_site_area_sqm is not None and inputs.current_far_pct is not None:
        return official_site_area_sqm * (inputs.current_far_pct / 100.0)
    return inputs.current_households * max(inputs.current_unit_supply_area, 1.0) * 1.05


def resolve_site_area(
    *,
    manual_total_site_area_sqm: float | None,
    official_site_area_sqm: float | None,
    land_share_sqm: float | None,
    current_households: int,
    current_far_pct: float | None,
    current_gross_floor_area_sqm: float,
    current_building_coverage_ratio_pct: float | None,
    average_current_floors: float | None,
) -> tuple[SiteResolution, list[WarningMessage]]:
    warnings: list[WarningMessage] = []
    source = "heuristic"
    implied_site_area_sqm = None
    avg_site_area = None
    selected = None
    if manual_total_site_area_sqm is not None:
        selected = manual_total_site_area_sqm
        source = "manual"
    elif official_site_area_sqm is not None:
        selected = official_site_area_sqm
        source = "official_cleanup"
    elif current_far_pct is not None and current_far_pct > 0:
        implied_site_area_sqm = current_gross_floor_area_sqm / (current_far_pct / 100.0)
        selected = implied_site_area_sqm
    elif current_building_coverage_ratio_pct is not None and average_current_floors:
        implied_far = current_building_coverage_ratio_pct * average_current_floors
        if implied_far > 0:
            implied_site_area_sqm = current_gross_floor_area_sqm / (implied_far / 100.0)
            selected = implied_site_area_sqm
    if selected is not None:
        avg_site_area = safe_div(selected, current_households, 0.0)
    else:
        warnings.append(warning("risk", "입력 부족", "전체 대지면적을 확정하기 어려워 용적률과 평형 기준 휴리스틱으로 계산했습니다."))
    return (
        SiteResolution(
            selected_total_site_area_sqm=selected,
            source=source,
            official_site_area_sqm=official_site_area_sqm,
            manual_site_area_sqm=manual_total_site_area_sqm,
            implied_site_area_sqm=implied_site_area_sqm,
            average_site_area_per_member_sqm=avg_site_area,
        ),
        warnings,
    )


def estimate_old_asset_value(
    *,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
    purchase_price: float,
    appraised_old_asset_value: float | None,
    official_price_reference: float | None,
    recent_same_complex_trade_price: float | None,
    adjustment_factor_override: float | None,
    region_is_seoul: bool,
    floor_no: int,
) -> tuple[float, str]:
    if appraised_old_asset_value is not None:
        return appraised_old_asset_value, "manual"
    if official_price_reference is not None:
        multiplier, source = adjustment_factor(
            public_price=official_price_reference,
            recent_trade=recent_same_complex_trade_price,
            override_value=adjustment_factor_override,
            region_is_seoul=region_is_seoul,
        )
        floor_adj = floor_factor(floor_no) if uses_apartment_reconstruction_flow(project_kind, reconstruction_style) else 1.0
        return official_price_reference * multiplier * floor_adj, source
    if recent_same_complex_trade_price is not None and uses_apartment_reconstruction_flow(project_kind, reconstruction_style):
        return recent_same_complex_trade_price * floor_factor(floor_no), "recent_trade"
    fallback_multiplier = 0.78 if project_kind == ProjectKind.RECONSTRUCTION else 0.74
    floor_adj = floor_factor(floor_no) if uses_apartment_reconstruction_flow(project_kind, reconstruction_style) else 1.0
    return purchase_price * fallback_multiplier * floor_adj, "heuristic"


def estimate_total_old_asset_value(
    *,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
    explicit_total_old_asset_value: float | None,
    old_asset_estimate: float,
    member_households: int,
    land_share_sqm: float | None,
    site_resolution: SiteResolution,
) -> tuple[float, str]:
    if explicit_total_old_asset_value is not None:
        return explicit_total_old_asset_value, "manual"
    if uses_land_based_flow(project_kind, reconstruction_style) and land_share_sqm is not None and site_resolution.selected_total_site_area_sqm is not None and member_households > 0:
        avg_share = safe_div(site_resolution.selected_total_site_area_sqm, member_households, 0.0)
        share_ratio = clamp(safe_div(land_share_sqm, max(avg_share, 1.0), 1.0), 0.35, 2.50)
        return old_asset_estimate * member_households / share_ratio, "heuristic"
    return old_asset_estimate * member_households, "heuristic"


def calculate_reconstruction_levy(
    *,
    total_reconstruction_profit: float,
    member_households: int,
    is_one_homeowner: bool,
    holding_years: float,
) -> ReconstructionLevyResult:
    if member_households <= 0:
        return ReconstructionLevyResult(0.0, 0.0, 0.0, 0.0, "미적용")
    average_profit = safe_div(total_reconstruction_profit, member_households, 0.0)
    levy_total = 0.0
    levy_per_member = 0.0
    bracket_label = "면제"
    for lower, upper, rate, base_amount in RECONSTRUCTION_LEVY_BRACKETS:
        if average_profit < lower:
            continue
        if upper is None or average_profit < upper:
            levy_per_member = base_amount + (average_profit - lower) * rate
            levy_total = levy_per_member * member_households
            bracket_label = f"{fmt_money(lower)} 이상"
            break
    relief_ratio = 0.0
    if is_one_homeowner:
        for lower, upper, relief in RECONSTRUCTION_LEVY_HOLDING_RELIEF:
            if holding_years < lower:
                continue
            if upper is None or holding_years < upper:
                relief_ratio = relief
                break
    if relief_ratio > 0:
        levy_total *= (1.0 - relief_ratio)
    return ReconstructionLevyResult(
        total_levy=levy_total,
        levy_per_member=safe_div(levy_total, member_households, 0.0),
        average_profit_per_member=average_profit,
        relief_ratio=relief_ratio,
        bracket_label=bracket_label,
    )


def official_value(project: SeoulProjectData | None, official_attr: str, legacy_attr: str) -> int | float | None:
    if project is None:
        return None
    value = getattr(project, official_attr, None)
    if value is not None:
        return value
    return getattr(project, legacy_attr, None)


def derive_project_route(inputs: UnionProjectInputs) -> str:
    if inputs.project_route and inputs.project_route != ProjectRoute.AUTO.value:
        return inputs.project_route
    project = inputs.seoul_project
    business_text = " ".join(
        [
            project.business_type if project else "",
            project.project_name if project else "",
            project.schedule_text if project and project.schedule_text else "",
        ]
    )
    if "\uacf5\uacf5\uc7ac\uac1c\ubc1c" in business_text:
        return ProjectRoute.SEOUL_PUBLIC_REDEVELOPMENT.value
    has_public_contribution = "\uacf5\uacf5\uae30\uc5ec" in business_text
    has_relaxation = "\uc644\ud654" in business_text or "\uc885\uc0c1\ud5a5" in business_text
    if has_public_contribution and has_relaxation:
        return ProjectRoute.SEOUL_CONTRIBUTION_RELAXED.value
    if project and project.project_route_hint:
        return project.project_route_hint
    business_text = " ".join([project.business_type if project else "", project.project_name if project else ""])
    if "공공재개발" in business_text:
        return ProjectRoute.SEOUL_PUBLIC_REDEVELOPMENT.value
    if "역세권 활성화" in business_text or "공공기여 완화" in business_text:
        return ProjectRoute.SEOUL_CONTRIBUTION_RELAXED.value
    if inputs.project_kind == ProjectKind.RECONSTRUCTION:
        return ProjectRoute.SEOUL_PRIVATE_RECONSTRUCTION.value
    return ProjectRoute.SEOUL_PRIVATE_REDEVELOPMENT.value


def resolve_regulatory_constraint_set(inputs: UnionProjectInputs) -> RegulatoryConstraintSet:
    route = derive_project_route(inputs)
    profile = POLICY_PROFILES.get(route)
    if profile is None:
        fallback_route = ProjectRoute.SEOUL_PRIVATE_RECONSTRUCTION.value if inputs.project_kind == ProjectKind.RECONSTRUCTION else ProjectRoute.SEOUL_PRIVATE_REDEVELOPMENT.value
        profile = POLICY_PROFILES[fallback_route]
        route = fallback_route
    return RegulatoryConstraintSet(
        profile_id=profile.profile_id,
        project_route=route,
        project_kind=profile.project_kind,
        policy_profile_version=inputs.policy_profile_version or DEFAULT_POLICY_PROFILE_VERSION,
        legal_min_rental_ratio=profile.legal_min_rental_ratio,
        target_rental_ratio=profile.target_rental_ratio,
        legal_min_public_contribution_ratio=profile.legal_min_public_contribution_ratio,
        target_public_contribution_ratio=profile.target_public_contribution_ratio,
        rental_source_url=REFERENCE_URLS["molit_rental_notice"],
        public_contribution_source_url=REFERENCE_URLS["seoul_public_contribution"] if route == ProjectRoute.SEOUL_CONTRIBUTION_RELAXED.value else REFERENCE_URLS["seoul_ordinance"],
        basis_date="2024-01-19",
        note=profile.note,
    )


def resolve_regulatory_constraints(
    *,
    inputs: UnionProjectInputs,
    constraint_set: RegulatoryConstraintSet,
    planned_households_candidate: int,
    member_households: int,
    gross_floor_area_sqm: float,
    gross_usable_area_sqm: float,
) -> ConstraintResolution:
    project = inputs.seoul_project
    official_planned = official_value(project, "official_planned_households", "planned_households")
    official_rental = official_value(project, "official_rental_households", "rental_households")
    official_general_sale = official_value(project, "official_general_sale_households", "sale_households")
    official_public_area = official_value(project, "official_public_facility_area_sqm", "public_facility_area_sqm")
    official_donation_area = official_value(project, "official_donation_area_sqm", "donation_area_sqm")
    official_public_reference_area = max([value for value in (official_public_area, official_donation_area) if value is not None], default=0.0)

    if inputs.target_households_override is not None:
        planned_households = inputs.target_households_override
        planned_source = "manual_override"
    elif inputs.planned_unit_mix_rows:
        planned_households = sum(item.households for item in inputs.planned_unit_mix_rows)
        planned_source = "manual_override"
    elif official_planned is not None:
        planned_households = int(official_planned)
        planned_source = "official_cleanup"
    else:
        planned_households = int(planned_households_candidate)
        planned_source = "simulation"

    legal_min_rental_households = int(round(planned_households * constraint_set.legal_min_rental_ratio))
    target_rental_households = int(round(planned_households * constraint_set.target_rental_ratio))
    legal_min_public_contribution_area_sqm = gross_floor_area_sqm * constraint_set.legal_min_public_contribution_ratio
    target_public_contribution_area_sqm = gross_floor_area_sqm * constraint_set.target_public_contribution_ratio
    rental_floor = max(legal_min_rental_households, int(official_rental or 0))
    public_floor_area = max(legal_min_public_contribution_area_sqm, float(official_public_reference_area or 0.0))
    override_notes: list[str] = []

    if inputs.rental_ratio_override is not None:
        requested_rental = int(round(planned_households * inputs.rental_ratio_override))
        if requested_rental < rental_floor:
            override_notes.append(f"임대 비율 직접입력 {fmt_pct(inputs.rental_ratio_override)}은 공식/법정 하한 {rental_floor:,}세대보다 낮아 자동 상향했습니다.")
            rental_households = rental_floor
            rental_source = "manual_adjusted"
        else:
            rental_households = requested_rental
            rental_source = "manual_override"
    elif official_rental is not None:
        rental_households = int(official_rental)
        rental_source = "official_cleanup"
    else:
        rental_households = max(target_rental_households, rental_floor)
        rental_source = "policy_profile"

    if inputs.donation_ratio_override is not None:
        requested_public_area = gross_floor_area_sqm * inputs.donation_ratio_override
        if requested_public_area < public_floor_area:
            override_notes.append(f"기부채납 비율 직접입력 {fmt_pct(inputs.donation_ratio_override)}은 공식/법정 하한 {public_floor_area:,.0f}㎡보다 낮아 자동 상향했습니다.")
            public_contribution_area = public_floor_area
            public_source = "manual_adjusted"
        else:
            public_contribution_area = requested_public_area
            public_source = "manual_override"
    elif official_public_reference_area > 0:
        public_contribution_area = official_public_reference_area
        public_source = "official_cleanup"
    else:
        public_contribution_area = max(target_public_contribution_area_sqm, public_floor_area)
        public_source = "policy_profile"

    public_contribution_area = clamp(public_contribution_area, 0.0, gross_floor_area_sqm * 0.95)
    available_general_sale = max(planned_households - member_households - rental_households, 0)
    if inputs.general_sale_ratio_override is not None:
        requested_general_sale = int(round(max(planned_households - rental_households, 0) * inputs.general_sale_ratio_override))
        general_sale_households = min(requested_general_sale, available_general_sale)
        general_sale_source = "manual_override"
    elif official_general_sale is not None:
        general_sale_households = min(int(official_general_sale), available_general_sale)
        general_sale_source = "official_cleanup"
    else:
        general_sale_households = available_general_sale
        general_sale_source = "policy_profile"

    rental_ratio = safe_div(rental_households, max(planned_households, 1), 0.0)
    public_ratio = safe_div(public_contribution_area, max(gross_floor_area_sqm, 1.0), 0.0)
    general_sale_ratio = safe_div(general_sale_households, max(planned_households - rental_households, 1), 0.0)
    return ConstraintResolution(
        profile_id=constraint_set.profile_id,
        project_route=constraint_set.project_route,
        policy_profile_version=constraint_set.policy_profile_version,
        planned_households=planned_households,
        planned_households_source=planned_source,
        resolved_rental_households=rental_households,
        resolved_rental_ratio=rental_ratio,
        resolved_public_contribution_area_sqm=public_contribution_area,
        resolved_public_contribution_ratio=public_ratio,
        resolved_general_sale_households=general_sale_households,
        resolved_general_sale_ratio=general_sale_ratio,
        legal_min_rental_households=legal_min_rental_households,
        legal_min_public_contribution_area_sqm=legal_min_public_contribution_area_sqm,
        rental_source=rental_source,
        public_contribution_source=public_source,
        general_sale_source=general_sale_source,
        override_notes=override_notes,
    )


def compute_plan_area_ledger(
    *,
    gross_floor_area_sqm: float,
    residential_efficiency: float,
    average_supply_area_sqm: float,
    planned_mix_rows: list[UnitMixRow],
    public_contribution_area_sqm: float,
    rental_allocations: list[int],
    member_allocations: list[int],
    general_allocations: list[int],
) -> PlanAreaLedger:
    gross_usable_area_sqm = gross_floor_area_sqm * residential_efficiency
    saleable_residential_area_sqm = max(gross_usable_area_sqm - public_contribution_area_sqm, average_supply_area_sqm)
    rental_area_sqm = sum(row.supply_area_sqm * count for row, count in zip(planned_mix_rows, rental_allocations))
    member_area_sqm = sum(row.supply_area_sqm * count for row, count in zip(planned_mix_rows, member_allocations))
    general_sale_area_sqm = sum(row.supply_area_sqm * count for row, count in zip(planned_mix_rows, general_allocations))
    mix_demand_area_sqm = sum(row.households * row.supply_area_sqm for row in planned_mix_rows)
    used_area_sqm = rental_area_sqm + member_area_sqm + general_sale_area_sqm
    residual_saleable_area_sqm = saleable_residential_area_sqm - used_area_sqm
    rental_reference_supply_area_sqm = min((row.supply_area_sqm for row in planned_mix_rows), default=average_supply_area_sqm)
    capacity_households = int(saleable_residential_area_sqm // max(average_supply_area_sqm, 1.0))
    capacity_gap_sqm = max(used_area_sqm - saleable_residential_area_sqm, 0.0)
    return PlanAreaLedger(
        gross_floor_area_sqm=gross_floor_area_sqm,
        gross_usable_area_sqm=gross_usable_area_sqm,
        public_contribution_area_sqm=public_contribution_area_sqm,
        saleable_residential_area_sqm=saleable_residential_area_sqm,
        rental_area_sqm=rental_area_sqm,
        member_area_sqm=member_area_sqm,
        general_sale_area_sqm=general_sale_area_sqm,
        residual_saleable_area_sqm=residual_saleable_area_sqm,
        average_supply_area_sqm=average_supply_area_sqm,
        rental_reference_supply_area_sqm=rental_reference_supply_area_sqm,
        capacity_households=capacity_households,
        mix_demand_area_sqm=mix_demand_area_sqm,
        capacity_gap_sqm=capacity_gap_sqm,
    )


def build_qa_outcome(
    *,
    inputs: UnionProjectInputs,
    plan_area_ledger: PlanAreaLedger,
    planned_households: int,
    member_households: int,
    rental_households: int,
    general_sale_households: int,
) -> QaOutcome:
    rows: list[dict[str, str]] = []
    warnings: list[WarningMessage] = []
    project = inputs.seoul_project
    official_planned = official_value(project, "official_planned_households", "planned_households")
    official_rental = official_value(project, "official_rental_households", "rental_households")
    official_general = official_value(project, "official_general_sale_households", "sale_households")
    official_public_area = official_value(project, "official_public_facility_area_sqm", "public_facility_area_sqm")
    alignment_scores: list[float] = []
    if official_planned is not None:
        delta = abs(planned_households - int(official_planned))
        ok = delta <= 1
        rows.append({"항목": "공식 총세대수 정합성", "값": f"{planned_households:,} / 공식 {int(official_planned):,}", "판정": "통과" if ok else "점검"})
        alignment_scores.append(1.0 if ok else 0.65 if delta <= 3 else 0.35)
    if official_rental is not None:
        delta = abs(rental_households - int(official_rental))
        ok = delta <= 1
        rows.append({"항목": "공식 임대세대수 정합성", "값": f"{rental_households:,} / 공식 {int(official_rental):,}", "판정": "통과" if ok else "점검"})
        alignment_scores.append(1.0 if ok else 0.60 if delta <= 3 else 0.30)
    if official_general is not None:
        delta = abs(general_sale_households - int(official_general))
        ok = delta <= 1
        rows.append({"항목": "공식 일반분양 정합성", "값": f"{general_sale_households:,} / 공식 {int(official_general):,}", "판정": "통과" if ok else "점검"})
        alignment_scores.append(1.0 if ok else 0.60 if delta <= 3 else 0.30)
    if official_public_area is not None:
        delta = abs(plan_area_ledger.public_contribution_area_sqm - float(official_public_area))
        ok = delta <= 10.0
        rows.append({"항목": "공식 공공기여 면적 정합성", "값": f"{plan_area_ledger.public_contribution_area_sqm:,.1f}㎡ / 공식 {float(official_public_area):,.1f}㎡", "판정": "통과" if ok else "점검"})
        alignment_scores.append(1.0 if ok else 0.65 if delta <= 250.0 else 0.35)
    conservation_ok = (
        member_households + rental_households + general_sale_households <= planned_households
        and plan_area_ledger.public_contribution_area_sqm + plan_area_ledger.saleable_residential_area_sqm <= plan_area_ledger.gross_floor_area_sqm + 1.0
        and plan_area_ledger.member_area_sqm + plan_area_ledger.rental_area_sqm + plan_area_ledger.general_sale_area_sqm <= plan_area_ledger.saleable_residential_area_sqm + 1.0
    )
    rows.append({"항목": "세대수 보존식", "값": f"조합원 {member_households:,} + 임대 {rental_households:,} + 일반분양 {general_sale_households:,} <= 총 {planned_households:,}", "판정": "통과" if member_households + rental_households + general_sale_households <= planned_households else "실패"})
    rows.append({"항목": "면적 보존식", "값": f"가처분 {plan_area_ledger.saleable_residential_area_sqm:,.1f}㎡ / 사용 {plan_area_ledger.member_area_sqm + plan_area_ledger.rental_area_sqm + plan_area_ledger.general_sale_area_sqm:,.1f}㎡", "판정": "통과" if plan_area_ledger.member_area_sqm + plan_area_ledger.rental_area_sqm + plan_area_ledger.general_sale_area_sqm <= plan_area_ledger.saleable_residential_area_sqm + 1.0 else "실패"})
    regulatory_strength = 1.0 if (official_public_area is not None or official_rental is not None) else 0.78 if inputs.region_is_seoul else 0.55
    official_alignment_strength = sum(alignment_scores) / len(alignment_scores) if alignment_scores else 0.55
    confidence_cap = 98.0 if official_alignment_strength >= 0.95 and conservation_ok else 84.0 if conservation_ok else 68.0
    return QaOutcome(
        regulatory_strength=regulatory_strength,
        official_alignment_strength=official_alignment_strength,
        conservation_ok=conservation_ok,
        monotonic_ok=True,
        confidence_cap=confidence_cap,
        rows=rows,
        warnings=warnings,
    )


def compute_confidence_score(
    *,
    qa_outcome: QaOutcome,
    old_asset_source: str,
    price_source: str,
    constraint_resolution: ConstraintResolution,
) -> float:
    regulatory_score = qa_outcome.regulatory_strength * 100.0
    official_alignment_score = qa_outcome.official_alignment_strength * 100.0
    rights_score = 92.0 if old_asset_source == "manual" else 82.0 if old_asset_source in {"trade_vs_public", "manual_override", "heuristic_default"} else 76.0 if old_asset_source == "recent_trade" else 62.0
    price_score = 92.0 if price_source in {"general_sale_price", "general_sale_ppy"} else 82.0 if price_source == "comparison_new_price" else 58.0
    raw_score = (regulatory_score * 0.35) + (official_alignment_score * 0.25) + (price_score * 0.20) + (rights_score * 0.20)
    score = clamp(raw_score, 20.0, qa_outcome.confidence_cap)
    if constraint_resolution.rental_source == "policy_profile" and constraint_resolution.public_contribution_source == "policy_profile":
        score = min(score, 79.0)
    if old_asset_source == "heuristic" or price_source == "fallback":
        score = min(score, 74.0)
    return score


def estimate_union_plan_preview(inputs: UnionProjectInputs) -> UnionPlanPreview:
    policy = seoul_policy_adjustment(
        project_kind=inputs.project_kind,
        region_is_seoul=inputs.region_is_seoul,
        current_far_pct=inputs.current_far_pct,
        target_far_pct=inputs.target_far_pct or (official_value(inputs.seoul_project, "official_target_far_pct", "target_far_pct") if inputs.seoul_project else None),
        total_site_area_sqm=inputs.total_site_area_sqm or (inputs.seoul_project.site_area_sqm if inputs.seoul_project else None),
        current_households=inputs.current_households,
        current_unit_supply_area=inputs.current_unit_supply_area,
        avg_official_land_price_per_sqm=inputs.avg_official_land_price_per_sqm,
    )
    remaining_months, duration_source = estimate_remaining_months(inputs.current_stage, inputs.seoul_project, inputs.project_kind)
    default_target_far_pct = 230.0 if inputs.project_kind == ProjectKind.RECONSTRUCTION and inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER else 260.0 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 250.0
    target_far_pct = (
        inputs.target_far_pct
        or official_value(inputs.seoul_project, "official_target_far_pct", "target_far_pct")
        or policy.estimated_target_far_pct
        or default_target_far_pct
    )
    official_target_bcr_pct = official_value(inputs.seoul_project, "official_target_bcr_pct", "target_building_coverage_ratio_pct")
    target_bcr_pct = inputs.target_building_coverage_ratio_pct or official_target_bcr_pct or inputs.current_building_coverage_ratio_pct
    if inputs.target_building_coverage_ratio_pct is not None:
        target_bcr_source = "manual"
    elif official_target_bcr_pct is not None:
        target_bcr_source = "official_cleanup"
    else:
        target_bcr_source = "heuristic"
    required_avg_floors = None
    if target_bcr_pct is not None and target_bcr_pct > 0 and target_far_pct:
        required_avg_floors = target_far_pct / target_bcr_pct

    official_site_area = inputs.seoul_project.site_area_sqm if inputs.seoul_project else None
    current_gross_floor_area_sqm = estimate_current_gross_floor_area_sqm(inputs, official_site_area, inputs.seoul_project.gross_floor_area_sqm if inputs.seoul_project else None)
    site_resolution, site_warnings = resolve_site_area(
        manual_total_site_area_sqm=inputs.total_site_area_sqm,
        official_site_area_sqm=official_site_area,
        land_share_sqm=inputs.land_share_sqm,
        current_households=inputs.current_households,
        current_far_pct=inputs.current_far_pct,
        current_gross_floor_area_sqm=current_gross_floor_area_sqm,
        current_building_coverage_ratio_pct=inputs.current_building_coverage_ratio_pct,
        average_current_floors=inputs.average_current_floors,
    )
    if site_resolution.selected_total_site_area_sqm is not None:
        gross_floor_area_sqm = site_resolution.selected_total_site_area_sqm * (target_far_pct / 100.0)
    elif inputs.current_far_pct is not None:
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(target_far_pct, inputs.current_far_pct, 1.0)
    else:
        gross_floor_area_sqm = current_gross_floor_area_sqm * (1.38 if inputs.project_kind == ProjectKind.REDEVELOPMENT else 1.28)

    default_supply_area = max(estimate_supply_area_from_exclusive_area(inputs.expected_new_exclusive_area, inputs.project_kind), 75.0) if uses_land_based_flow(inputs.project_kind, inputs.reconstruction_style) else inputs.current_unit_supply_area
    initial_supply_rows = inputs.planned_unit_mix_rows or inputs.existing_unit_mix_rows
    average_supply_area_sqm = weighted_average_supply_area(initial_supply_rows, default_supply_area)
    average_exclusive_area_sqm = weighted_average_exclusive_area(initial_supply_rows, inputs.expected_new_exclusive_area or inputs.current_unit_exclusive_area)
    residential_efficiency, residential_efficiency_source = estimate_residential_efficiency(
        project_kind=inputs.project_kind,
        reconstruction_style=inputs.reconstruction_style,
        required_avg_floors=required_avg_floors,
        target_bcr_pct=target_bcr_pct,
        current_far_pct=inputs.current_far_pct,
        target_far_pct=target_far_pct,
        average_exclusive_area_sqm=average_exclusive_area_sqm,
    )

    gross_usable_area_sqm = gross_floor_area_sqm * residential_efficiency
    initial_simulated_total_households = max(int(round(gross_usable_area_sqm / max(average_supply_area_sqm, 1.0))), 1)
    member_seed = (
        inputs.seoul_project.owner_count
        if uses_land_based_flow(inputs.project_kind, inputs.reconstruction_style) and inputs.seoul_project and inputs.seoul_project.owner_count
        else inputs.seoul_project.current_households
        if inputs.seoul_project and inputs.seoul_project.current_households
        else inputs.current_households
    )
    member_households = max(int(round(member_seed * (1.0 - inputs.cash_settlement_rate))), 1)
    official_planned_households = official_value(inputs.seoul_project, "official_planned_households", "planned_households")
    official_rental_households = official_value(inputs.seoul_project, "official_rental_households", "rental_households")
    official_general_sale_households = official_value(inputs.seoul_project, "official_general_sale_households", "sale_households")
    if official_planned_households is not None and (official_rental_households is not None or official_general_sale_households is not None):
        official_member_households = int(official_planned_households) - int(official_rental_households or 0) - int(official_general_sale_households or 0)
        if official_member_households > 0:
            member_households = official_member_households
    constraint_set = resolve_regulatory_constraint_set(inputs)
    constraint_resolution = resolve_regulatory_constraints(
        inputs=inputs,
        constraint_set=constraint_set,
        planned_households_candidate=initial_simulated_total_households,
        member_households=member_households,
        gross_floor_area_sqm=gross_floor_area_sqm,
        gross_usable_area_sqm=gross_usable_area_sqm,
    )
    planned_households = max(constraint_resolution.planned_households, member_households + constraint_resolution.resolved_rental_households)
    planned_mix_rows, planned_mix_source = auto_planned_unit_mix_rows(inputs, planned_households)
    average_supply_area_sqm = weighted_average_supply_area(planned_mix_rows or inputs.existing_unit_mix_rows, default_supply_area)
    area_capacity_households = max(int((gross_usable_area_sqm - constraint_resolution.resolved_public_contribution_area_sqm) // max(average_supply_area_sqm, 1.0)), 1)
    if constraint_resolution.planned_households_source == "simulation":
        planned_households = max(member_households + constraint_resolution.resolved_rental_households, min(planned_households, area_capacity_households))
        constraint_resolution.planned_households = planned_households
        planned_mix_rows, planned_mix_source = auto_planned_unit_mix_rows(inputs, planned_households)
        average_supply_area_sqm = weighted_average_supply_area(planned_mix_rows or inputs.existing_unit_mix_rows, default_supply_area)

    rental_allocations = [0 for _ in planned_mix_rows]
    remaining_rental = min(constraint_resolution.resolved_rental_households, planned_households)
    for index in sorted(range(len(planned_mix_rows)), key=lambda idx: planned_mix_rows[idx].exclusive_area_sqm):
        if remaining_rental <= 0:
            break
        allocated = min(planned_mix_rows[index].households, remaining_rental)
        rental_allocations[index] = allocated
        remaining_rental -= allocated
    member_allocations = allocation_from_capacities([max(planned_mix_rows[idx].households - rental_allocations[idx], 0) for idx in range(len(planned_mix_rows))], member_households)
    general_allocations = allocation_from_capacities(
        [max(planned_mix_rows[idx].households - rental_allocations[idx] - member_allocations[idx], 0) for idx in range(len(planned_mix_rows))],
        min(constraint_resolution.resolved_general_sale_households, max(planned_households - sum(member_allocations) - sum(rental_allocations), 0)),
    )
    plan_area_ledger = compute_plan_area_ledger(
        gross_floor_area_sqm=gross_floor_area_sqm,
        residential_efficiency=residential_efficiency,
        average_supply_area_sqm=average_supply_area_sqm,
        planned_mix_rows=planned_mix_rows,
        public_contribution_area_sqm=constraint_resolution.resolved_public_contribution_area_sqm,
        rental_allocations=rental_allocations,
        member_allocations=member_allocations,
        general_allocations=general_allocations,
    )
    if official_planned_households is not None and plan_area_ledger.capacity_gap_sqm > 1.0:
        total_used_area = plan_area_ledger.member_area_sqm + plan_area_ledger.rental_area_sqm + plan_area_ledger.general_sale_area_sqm
        if total_used_area > 0:
            scale = plan_area_ledger.saleable_residential_area_sqm / total_used_area
            plan_area_ledger.member_area_sqm *= scale
            plan_area_ledger.rental_area_sqm *= scale
            plan_area_ledger.general_sale_area_sqm *= scale
            plan_area_ledger.residual_saleable_area_sqm = 0.0
            plan_area_ledger.capacity_gap_sqm = 0.0
    general_sale_households = sum(general_allocations)
    rental_households = sum(rental_allocations)
    constraint_resolution.resolved_general_sale_households = general_sale_households
    constraint_resolution.resolved_general_sale_ratio = safe_div(general_sale_households, max(planned_households - rental_households, 1), 0.0)
    qa_outcome = build_qa_outcome(
        inputs=inputs,
        plan_area_ledger=plan_area_ledger,
        planned_households=planned_households,
        member_households=member_households,
        rental_households=rental_households,
        general_sale_households=general_sale_households,
    )
    return UnionPlanPreview(
        remaining_months=remaining_months,
        duration_source=duration_source,
        site_resolution=site_resolution,
        site_warnings=site_warnings + qa_outcome.warnings,
        target_far_pct=target_far_pct,
        target_bcr_pct=target_bcr_pct,
        target_bcr_source=target_bcr_source,
        required_avg_floors=required_avg_floors,
        current_gross_floor_area_sqm=current_gross_floor_area_sqm,
        gross_floor_area_sqm=gross_floor_area_sqm,
        average_supply_area_sqm=average_supply_area_sqm,
        average_exclusive_area_sqm=average_exclusive_area_sqm,
        residential_efficiency=residential_efficiency,
        residential_efficiency_source=residential_efficiency_source,
        planned_households=planned_households,
        planned_households_source=constraint_resolution.planned_households_source,
        simulated_total_households=area_capacity_households,
        member_households=member_households,
        general_sale_households=general_sale_households,
        general_sale_source=constraint_resolution.general_sale_source,
        rental_households=rental_households,
        donation_ratio=constraint_resolution.resolved_public_contribution_ratio,
        donation_source=constraint_resolution.public_contribution_source,
        rental_ratio=safe_div(rental_households, max(planned_households, 1), 0.0),
        rental_source=constraint_resolution.rental_source,
        general_sale_ratio=safe_div(general_sale_households, max(planned_households - rental_households, 1), 0.0),
        planned_mix_rows=planned_mix_rows,
        planned_mix_source=planned_mix_source,
        constraint_resolution=constraint_resolution,
        plan_area_ledger=plan_area_ledger,
        qa_outcome=qa_outcome,
        resolved_public_contribution_area_sqm=constraint_resolution.resolved_public_contribution_area_sqm,
        resolved_public_contribution_ratio=constraint_resolution.resolved_public_contribution_ratio,
        resolved_rental_households=rental_households,
        resolved_general_sale_households=general_sale_households,
    )


def add_standard_union_warnings(
    *,
    inputs: UnionProjectInputs,
    warnings: list[WarningMessage],
    site_resolution: SiteResolution,
    member_households: int,
    planned_households: int,
    general_sale_households: int,
    total_old_asset_source: str,
    business_price_source: str,
    qa_outcome: QaOutcome,
) -> None:
    if site_resolution.selected_total_site_area_sqm is None:
        warnings.append(warning("risk", "입력 부족", "전체 대지면적을 확정하기 어려워 용적률과 평형 기준 휴리스틱으로 계산했습니다."))
    if inputs.project_kind == ProjectKind.REDEVELOPMENT and inputs.land_share_sqm is None:
        warnings.append(warning("risk", "입력 부족", "재개발은 내 대지지분이 없으면 권리가액과 분담금 오차가 크게 커집니다."))
    if planned_households < member_households:
        warnings.append(warning("risk", "법적 상한 초과", f"예상 총세대수 {planned_households:,}세대로는 권리자/조합원 {member_households:,}세대를 담기 어렵습니다."))
    if general_sale_households <= 0:
        warnings.append(warning("warn", "보수 추정", "일반분양 세대수가 0세대로 계산되어 사업수지가 매우 보수적으로 보일 수 있습니다."))
    if total_old_asset_source == "heuristic":
        warnings.append(warning("warn", "휴리스틱 의존", "종전자산총액을 감정평가서 없이 추정해 비례율과 정산액 신뢰도가 낮습니다."))
    if business_price_source == "fallback":
        warnings.append(warning("warn", "휴리스틱 의존", "일반분양가 또는 비교 신축 시세가 없어 매수가 기반 기본 보정치로 가격을 추정했습니다."))
    warnings.extend(qa_outcome.warnings)


def calculate_union_project(inputs: UnionProjectInputs) -> CalculationResult:
    warnings: list[WarningMessage] = []
    plan_preview = estimate_union_plan_preview(inputs)
    warnings.extend(plan_preview.site_warnings)
    policy = seoul_policy_adjustment(
        project_kind=inputs.project_kind,
        region_is_seoul=inputs.region_is_seoul,
        current_far_pct=inputs.current_far_pct,
        target_far_pct=plan_preview.target_far_pct,
        total_site_area_sqm=inputs.total_site_area_sqm or (inputs.seoul_project.site_area_sqm if inputs.seoul_project else None),
        current_households=inputs.current_households,
        current_unit_supply_area=inputs.current_unit_supply_area,
        avg_official_land_price_per_sqm=inputs.avg_official_land_price_per_sqm,
    )

    planned_households = plan_preview.planned_households
    member_households = plan_preview.member_households
    general_sale_households = plan_preview.general_sale_households
    rental_households = plan_preview.rental_households
    constraint_resolution = plan_preview.constraint_resolution
    plan_area_ledger = plan_preview.plan_area_ledger
    qa_outcome = plan_preview.qa_outcome

    general_sale_reference_exclusive_area = max(estimate_exclusive_area_from_supply_area(plan_preview.average_supply_area_sqm, inputs.project_kind), 1.0)
    general_sale_unit_price, business_price_source = resolve_business_unit_price(
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=inputs.comparison_new_price,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=general_sale_reference_exclusive_area,
        target_supply_area_sqm=plan_preview.average_supply_area_sqm,
    )
    expected_supply_area_sqm = estimate_supply_area_from_exclusive_area(inputs.expected_new_exclusive_area, inputs.project_kind)
    exit_unit_price, exit_price_source = resolve_exit_unit_price(
        comparison_new_price=inputs.comparison_new_price,
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
    )
    member_sale_price_ratio, _member_sale_ratio_source = default_member_sale_price_ratio(inputs.project_kind, inputs.current_stage, inputs.member_sale_price_ratio_override)
    member_unit_price = resolve_business_unit_price(
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=inputs.comparison_new_price,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
        target_supply_area_sqm=expected_supply_area_sqm,
    )[0] * member_sale_price_ratio
    average_member_unit_price = member_unit_price

    gross_floor_area_pyeong = plan_preview.gross_floor_area_sqm / 3.3058
    current_gross_area_pyeong = plan_preview.current_gross_floor_area_sqm / 3.3058
    direct_construction_cost = gross_floor_area_pyeong * inputs.construction_cost_per_pyeong
    demolition_cost = current_gross_area_pyeong * inputs.construction_cost_per_pyeong * (0.08 if uses_land_based_flow(inputs.project_kind, inputs.reconstruction_style) else 0.06)
    design_and_pm_cost = direct_construction_cost * (0.06 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.065)
    union_cost = direct_construction_cost * 0.018 + member_households * 8_000_000.0
    old_asset_estimate, old_asset_source = estimate_old_asset_value(
        project_kind=inputs.project_kind,
        reconstruction_style=inputs.reconstruction_style,
        purchase_price=inputs.purchase_price,
        appraised_old_asset_value=inputs.appraised_old_asset_value,
        official_price_reference=inputs.official_price_reference,
        recent_same_complex_trade_price=inputs.recent_same_complex_trade_price,
        adjustment_factor_override=inputs.adjustment_factor_override,
        region_is_seoul=inputs.region_is_seoul,
        floor_no=inputs.floor_no,
    )
    total_old_asset_value, total_old_asset_source = estimate_total_old_asset_value(
        project_kind=inputs.project_kind,
        reconstruction_style=inputs.reconstruction_style,
        explicit_total_old_asset_value=inputs.total_old_asset_value,
        old_asset_estimate=old_asset_estimate,
        member_households=member_households,
        land_share_sqm=inputs.land_share_sqm,
        site_resolution=plan_preview.site_resolution,
    )

    allocation_rows: list[dict[str, str]] = []
    general_sale_revenue = general_sale_unit_price * general_sale_households * inputs.sale_rate
    rental_revenue = (price_from_supply_pyeong(1000.0 if inputs.region_is_seoul else 800.0, plan_area_ledger.rental_reference_supply_area_sqm) or 0.0) * rental_households
    member_sale_revenue = member_unit_price * member_households
    for row in plan_preview.planned_mix_rows:
        allocation_rows.append({"평형": row.label, "세대수": f"{row.households:,}세대", "전용면적": f"{row.exclusive_area_sqm:,.1f}㎡", "공급면적": f"{row.supply_area_sqm:,.1f}㎡"})
    if member_households > 0:
        average_member_unit_price = member_sale_revenue / member_households
    ancillary_revenue = direct_construction_cost * 0.02
    other_disposal_revenue = direct_construction_cost * 0.01
    total_revenue_before_cost = member_sale_revenue + general_sale_revenue + rental_revenue + ancillary_revenue + other_disposal_revenue

    settlement_compensation_cost = total_old_asset_value * (0.005 + inputs.cash_settlement_rate * 0.08)
    sales_expense = general_sale_revenue * 0.025
    taxes_public_cost = (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + sales_expense + settlement_compensation_cost) * 0.03
    pf_base_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + taxes_public_cost
    pf_principal = pf_base_cost * inputs.pf_financing_ratio
    financing_cost = pf_principal * inputs.pf_rate * (inputs.pf_interest_months / 12.0)
    move_loan_interest_cost = member_households * inputs.average_move_loan_amount * inputs.move_loan_rate * (inputs.move_loan_duration_months / 12.0)
    contingency_cost = (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + taxes_public_cost + sales_expense) * 0.05

    levy_reference_result = ReconstructionLevyResult(0.0, 0.0, 0.0, 0.0, "미적용")
    levy_application_label = "미적용"
    levy_applied_total = 0.0
    levy_applied_per_member = 0.0
    if inputs.project_kind == ProjectKind.RECONSTRUCTION:
        total_reconstruction_profit = max(total_revenue_before_cost - (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + settlement_compensation_cost + taxes_public_cost + sales_expense + financing_cost + move_loan_interest_cost + contingency_cost), 0.0)
        levy_reference_result = calculate_reconstruction_levy(
            total_reconstruction_profit=total_reconstruction_profit,
            member_households=member_households,
            is_one_homeowner=inputs.is_one_homeowner,
            holding_years=inputs.holding_years,
        ) if inputs.manual_reconstruction_levy_total is None else ReconstructionLevyResult(inputs.manual_reconstruction_levy_total, safe_div(inputs.manual_reconstruction_levy_total, member_households, 0.0), 0.0, 0.0, "직접 입력")
        if inputs.include_reconstruction_levy:
            levy_applied_total = levy_reference_result.total_levy
            levy_applied_per_member = levy_reference_result.levy_per_member
            levy_application_label = "손익 반영"
        else:
            levy_application_label = "참고만"

    total_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + settlement_compensation_cost + taxes_public_cost + financing_cost + move_loan_interest_cost + sales_expense + contingency_cost + levy_applied_total
    proportional_ratio = safe_div(total_revenue_before_cost - total_cost, total_old_asset_value, 0.0) * 100.0 if total_old_asset_value > 0 else None
    rights_value = old_asset_estimate * safe_div(proportional_ratio or 0.0, 100.0, 0.0) if proportional_ratio is not None else None
    settlement_amount = None if rights_value is None else average_member_unit_price - rights_value + levy_applied_per_member
    after_tax_profit = exit_unit_price - (inputs.purchase_price + max(settlement_amount or 0.0, 0.0))

    add_standard_union_warnings(
        inputs=inputs,
        warnings=warnings,
        site_resolution=plan_preview.site_resolution,
        member_households=member_households,
        planned_households=planned_households,
        general_sale_households=general_sale_households,
        total_old_asset_source=total_old_asset_source,
        business_price_source=business_price_source,
        qa_outcome=qa_outcome,
    )
    for note in constraint_resolution.override_notes:
        warnings.append(warning("warn", "자동 보정", note))
    confidence_score = compute_confidence_score(
        qa_outcome=qa_outcome,
        old_asset_source=old_asset_source,
        price_source=business_price_source,
        constraint_resolution=constraint_resolution,
    )
    confidence_label = "높음" if confidence_score >= 80 else "보통" if confidence_score >= 60 else "낮음"

    top_cards = [
        ("비례율", f"{proportional_ratio:.2f}%" if proportional_ratio is not None else "-", "공식 계획값과 법정 제약을 함께 반영한 결과입니다."),
        ("예상 정산액", settlement_label(settlement_amount), "권리가액과 조합원 분양가 추정 기준입니다."),
        ("일반분양 세대수", f"{general_sale_households:,}세대", "공식값 우선, 없으면 면적 원장과 제약식 기준입니다."),
        ("공공기여 면적", f"{constraint_resolution.resolved_public_contribution_area_sqm:,.0f}㎡", "공식값 또는 법정/정책 프로필 기준입니다."),
        ("결과 신뢰도", f"{confidence_label} ({confidence_score:.1f}점)", "법정 제약 근거, 공식 계획 정합성, 가격/권리가액 근거를 함께 반영했습니다."),
    ]
    summary_lines = [
        f"서울 {inputs.project_kind.value} 계산은 공식 계획값과 법정 하한을 우선 반영해 총 {planned_households:,}세대, 일반분양 {general_sale_households:,}세대로 정리했습니다.",
        f"임대주택은 {rental_households:,}세대, 공공기여는 {constraint_resolution.resolved_public_contribution_area_sqm:,.1f}㎡로 반영해 이전의 단순 비율 휴리스틱보다 보수적으로 계산했습니다.",
        f"예상 정산액은 {settlement_label(settlement_amount)}이고, 매수 후 단순 수익 추정은 {fmt_money(after_tax_profit)}입니다.",
    ]
    policy_rows = [
        {"항목": "정책 프로필", "값": constraint_resolution.profile_id, "출처 URL": REFERENCE_URLS["seoul_ordinance"]},
        {"항목": "프로필 버전", "값": constraint_resolution.policy_profile_version, "기준일": "2024-01-19"},
        {"항목": "프로젝트 라우트", "값": constraint_resolution.project_route},
        {"항목": "임대주택 반영", "값": f"{rental_households:,}세대 ({fmt_pct(safe_div(rental_households, max(planned_households, 1), 0.0))})", "출처": humanize_source(constraint_resolution.rental_source)},
        {"항목": "법정 최소 임대세대수", "값": f"{constraint_resolution.legal_min_rental_households:,}세대", "출처 URL": REFERENCE_URLS["molit_rental_notice"]},
        {"항목": "공공기여 면적", "값": f"{constraint_resolution.resolved_public_contribution_area_sqm:,.1f}㎡ ({fmt_pct(constraint_resolution.resolved_public_contribution_ratio)})", "출처": humanize_source(constraint_resolution.public_contribution_source)},
        {"항목": "법정 최소 공공기여 면적", "값": f"{constraint_resolution.legal_min_public_contribution_area_sqm:,.1f}㎡", "출처 URL": REFERENCE_URLS["seoul_ordinance"]},
        {"항목": "서울 사업성 보정계수", "값": f"{policy.coefficient:.2f}" if policy.active else "미적용"},
        {"항목": "재건축부담금 적용", "값": levy_application_label if inputs.project_kind == ProjectKind.RECONSTRUCTION else "미적용"},
    ]
    source_rows = [
        {"항목": "서울 공식 계획 세대수", "값": str(official_value(inputs.seoul_project, "official_planned_households", "planned_households") or "-"), "출처": humanize_source("official_cleanup"), "출처 URL": REFERENCE_URLS["cleanup"]},
        {"항목": "서울 공식 임대 세대수", "값": str(official_value(inputs.seoul_project, "official_rental_households", "rental_households") or "-"), "출처": humanize_source("official_cleanup"), "출처 URL": REFERENCE_URLS["cleanup"]},
        {"항목": "서울 공식 공공기여 면적", "값": f"{float(official_value(inputs.seoul_project, 'official_public_facility_area_sqm', 'public_facility_area_sqm') or 0.0):,.1f}㎡" if inputs.seoul_project else "-", "출처": humanize_source("official_cleanup"), "출처 URL": REFERENCE_URLS["cleanup"]},
        {"항목": "일반분양 가격 기준", "값": fmt_money(general_sale_unit_price), "출처": humanize_source(business_price_source), "출처 URL": REFERENCE_URLS["applyhome"] if business_price_source in {'general_sale_price', 'general_sale_ppy'} else "-"},
        {"항목": "출구가치 기준", "값": fmt_money(exit_unit_price), "출처": humanize_source(exit_price_source), "출처 URL": REFERENCE_URLS["applyhome"] if exit_price_source == 'general_sale_price' else "-"},
        {"항목": "종전자산 추정 기준", "값": fmt_money(old_asset_estimate), "출처": humanize_source(old_asset_source), "출처 URL": REFERENCE_URLS["cleanup"] if old_asset_source in {'trade_vs_public', 'heuristic_default'} else "-"},
    ]
    return CalculationResult(
        mode=inputs.project_kind,
        top_cards=top_cards,
        summary_lines=summary_lines,
        warnings=dedupe_warning_messages(warnings),
        why_rows=[
            {"구분": "사업", "항목": "예상 총세대수", "값": f"{planned_households:,}세대"},
            {"구분": "사업", "항목": "일반분양 세대수", "값": f"{general_sale_households:,}세대"},
            {"구분": "사업", "항목": "임대주택 세대수", "값": f"{rental_households:,}세대"},
            {"구분": "면적", "항목": "총 연면적", "값": f"{plan_preview.gross_floor_area_sqm:,.1f}㎡"},
            {"구분": "면적", "항목": "공공기여 면적", "값": f"{constraint_resolution.resolved_public_contribution_area_sqm:,.1f}㎡"},
            {"구분": "면적", "항목": "가처분 주거면적", "값": f"{plan_area_ledger.saleable_residential_area_sqm:,.1f}㎡"},
        ],
        business_rows=[
            {"항목": "총수입", "값": fmt_money(total_revenue_before_cost)},
            {"항목": "총사업비", "값": fmt_money(total_cost)},
            {"항목": "일반분양 수입", "값": fmt_money(general_sale_revenue)},
            {"항목": "임대 회수액", "값": fmt_money(rental_revenue)},
            {"항목": "비례율", "값": f"{proportional_ratio:.2f}%" if proportional_ratio is not None else "-"},
        ],
        settlement_rows=[
            {"항목": "권리가액 추정", "값": fmt_money(rights_value)},
            {"항목": "조합원 분양가 추정", "값": fmt_money(average_member_unit_price)},
            {"항목": "예상 정산액", "값": settlement_label(settlement_amount)},
            {"항목": "단순 수익 추정", "값": fmt_money(after_tax_profit)},
            {"항목": "재건축부담금 참고치", "값": fmt_money(levy_reference_result.total_levy if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.0)},
        ],
        sensitivity_rows=[],
        policy_rows=policy_rows,
        source_rows=source_rows,
        allocation_rows=allocation_rows,
        planned_mix_rows=[{"평형": row.label, "세대수": f"{row.households:,}세대", "전용면적": f"{row.exclusive_area_sqm:,.1f}㎡", "공급면적": f"{row.supply_area_sqm:,.1f}㎡"} for row in plan_preview.planned_mix_rows],
        qa_rows=qa_outcome.rows,
        debug_metrics={
            "planned_households": float(planned_households),
            "general_sale_households": float(general_sale_households),
            "rental_households": float(rental_households),
            "public_contribution_area_sqm": float(constraint_resolution.resolved_public_contribution_area_sqm),
            "proportional_ratio": float(proportional_ratio or 0.0),
            "after_tax_profit": float(after_tax_profit),
            "confidence_score": float(confidence_score),
            "gross_floor_area_sqm": float(plan_preview.gross_floor_area_sqm),
            "saleable_residential_area_sqm": float(plan_area_ledger.saleable_residential_area_sqm),
        },
    )
