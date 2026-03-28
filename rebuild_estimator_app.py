from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from html import escape, unescape
from html.parser import HTMLParser
from io import BytesIO, StringIO
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request

try:
    import streamlit as st
except Exception:
    st = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


SCENARIOS: dict[str, dict[str, float]] = {
    "낙관": {
        "sale_rate": 1.00,
        "cash_settlement_rate": 0.00,
        "construction_cost_per_pyeong": 8_500_000.0,
        "pf_rate": 0.070,
        "duration_multiplier": 0.82,
    },
    "기준": {
        "sale_rate": 0.97,
        "cash_settlement_rate": 0.03,
        "construction_cost_per_pyeong": 9_000_000.0,
        "pf_rate": 0.085,
        "duration_multiplier": 1.00,
    },
    "보수": {
        "sale_rate": 0.92,
        "cash_settlement_rate": 0.07,
        "construction_cost_per_pyeong": 10_000_000.0,
        "pf_rate": 0.100,
        "duration_multiplier": 1.28,
    },
}

ASSUMPTION_PROFILES: dict[str, dict[str, float]] = {
    "공격": {
        "donation_ratio": 0.05,
        "rental_ratio": 0.07,
        "general_sale_ratio": 0.26,
        "duration_buffer": 0.92,
    },
    "기준": {
        "donation_ratio": 0.08,
        "rental_ratio": 0.10,
        "general_sale_ratio": 0.22,
        "duration_buffer": 1.00,
    },
    "보수": {
        "donation_ratio": 0.12,
        "rental_ratio": 0.12,
        "general_sale_ratio": 0.18,
        "duration_buffer": 1.12,
    },
}

REDEVELOPMENT_PROFILE_FLOORS = {
    "공격": 1.06,
    "기준": 1.00,
    "보수": 0.94,
}

STAGE_BASE_MONTHS: dict[str, int] = {
    "재건축진단": 120,
    "정비구역지정": 96,
    "추진위승인": 84,
    "조합설립인가": 72,
    "사업시행인가": 48,
    "관리처분인가": 36,
    "이주/철거": 24,
    "착공": 18,
    "준공/입주": 0,
}

ADVANCED_DETAIL_STAGES = {"관리처분인가", "이주/철거", "착공", "준공/입주"}

EXIT_SCENARIOS: tuple[str, ...] = (
    "입주권 단계 매도",
    "준공 직후 매도",
    "입주 후 3년 보유",
)

MANUAL_KEYS = {
    "proportional_ratio": "추정비례율",
    "member_sale_revenue": "조합원분양수입",
    "general_sale_revenue": "일반분양수입",
    "total_revenue": "총수입",
    "total_cost": "총지출",
    "total_old_asset_value": "종전자산총액",
    "reconstruction_levy": "재건축부담금",
    "old_asset_formula": "종전자산 산식",
}

DISPLAY_KEY_LABELS: dict[str, str] = {
    "proportional_ratio": "추정비례율",
    "member_sale_revenue": "조합원분양수입",
    "general_sale_revenue": "일반분양수입",
    "total_revenue": "총수입",
    "total_cost": "총지출",
    "total_old_asset_value": "종전자산총액",
    "reconstruction_levy": "재건축부담금",
    "old_asset_formula": "종전자산 산식",
    "member_price_table_count": "문서 분양가표 건수",
    "parser_status": "파서 상태",
    "document_stage": "문서 인식 단계",
    "document_schedule": "문서 일정 메모",
    "old_asset_estimate": "종전자산 추정액",
    "adjustment_factor": "보정계수",
    "planned_households": "예상 총세대수",
    "general_sale_ratio": "일반분양 비율",
    "site_area_sqm": "대지면적",
    "target_far": "목표 용적률",
    "building_coverage_ratio": "목표 건폐율",
    "current_households": "권리자/기존 세대수",
    "public_facility_area_sqm": "공공시설 반영면적",
    "sale_households": "일반분양 세대수",
    "rental_households": "임대주택 세대수",
    "donation_area_sqm": "명시 기부채납 면적",
    "pf_financing_ratio": "PF 조달비율",
    "pf_interest_months": "PF 이자 반영개월",
    "avg_move_loan_amount": "세대당 평균 이주비",
    "move_loan_duration_months": "이주비 대여개월",
}

SOURCE_LABELS: dict[str, str] = {
    "manual_appraisal": "사용자 감정가 입력",
    "public_price_adjusted": "공시가격 x 보정계수",
    "trade_backsolve": "실거래가 역산",
    "purchase_price_heuristic": "매수가 기반 추정",
    "document_total_old_asset": "문서 종전자산총액",
    "user_total_old_asset": "사용자 종전자산총액",
    "scaled_individual_old_asset": "개별 종전자산 확대추정",
    "user_override": "사용자 보정계수",
    "document_formula": "문서 산식 반영",
    "trade_vs_public": "실거래/공시가 비교",
    "heuristic_default": "휴리스틱 기본값",
    "engine": "계산 엔진",
    "official_cleanup": "서울 정비사업 정보몽땅",
    "manual": "직접 입력",
    "document": "업로드 문서",
    "preset": "기본 프리셋",
    "schedule_board": "서울 향후일정 게시판",
    "bucket_override": "상세 비용 직접입력",
    "manual_override": "직접 수정",
    "simulation": "시뮬레이션 엔진",
}

VALUE_LABELS: dict[str, str] = {
    "pypdf_missing": "`pypdf` 설치 필요",
    "unsupported": "지원하지 않는 파일",
    "parse_error": "파싱 실패",
}

COST_BUCKET_META: tuple[tuple[str, str, str], ...] = (
    ("main_construction", "본공사", "연면적과 공사비 단가 기반"),
    ("demolition_and_site", "철거/정비기반", "기존 연면적과 공사비의 일정 비율"),
    ("design_supervision_pm", "설계/감리/PM", "본공사비 연동"),
    ("union_and_professional", "조합운영/전문용역", "행정, 운영, 정비사업전문관리"),
    ("financing", "금융비", "PF 이자, 이주비 이자, 시간 비용"),
    ("taxes_public", "세금/공과", "공과금, 보험, 부담금"),
    ("compensation_litigation", "보상/청산/소송", "청산비, 소송비, 기타 분쟁비"),
    ("sales_and_disposal", "분양/처분비", "일반분양 마케팅, 처분비"),
    ("contingency", "예비비", "불확실성 버퍼"),
)

FIELD_HELP: dict[str, str] = {
    "project_kind": "재건축은 기존 공동주택을 다시 짓는 경우, 재개발은 권리자와 세입자 보상까지 함께 고려해야 하는 정비사업입니다.",
    "purchase_price": "현재 검토 중인 매물의 실제 매수가입니다. 취득세 전 가격 기준으로 넣어도 됩니다.",
    "current_stage": "현재 사업단계입니다. 남은 사업기간, 금융비, 공사비 인플레이션에 직접 반영됩니다.",
    "comparison_new_price": "준공 후 이 매물이 따라갈 가능성이 있는 신축 시세입니다. 현재 매물가가 아니라 출구가격 앵커입니다.",
    "general_sale_price": "준공 또는 분양 시점 기준의 예상 일반분양 평균가입니다. 현재 주변 실거래가와 같은 뜻이 아닙니다.",
    "current_households": "재건축은 기존 세대수, 재개발은 토지등소유자 수 또는 분양대상 권리자 수에 가깝게 입력할수록 정확합니다.",
    "current_far": "현재 구역의 현황 용적률입니다. 대지지분이나 공식 대지면적이 없을 때 대지면적 역산에 사용합니다.",
    "target_far": "정비계획 또는 예상 정비계획 기준 목표 용적률입니다. 총세대수 시뮬레이션의 핵심 값입니다.",
    "target_bcr": "계획 건폐율입니다. 목표 FAR와 함께 넣으면 필요 평균층수와 과도한 세대계획 여부를 점검할 수 있습니다.",
    "construction_cost": "평당 공사비입니다. 공사계약 전이면 최근 유사 사업장의 범위를 참고해 입력하고, 모르면 기준 시나리오부터 보세요.",
    "land_share": "내 물건 기준 대지지분입니다. 알면 가장 우선 사용하고, 모르면 비워두면 자동추정합니다.",
    "current_bcr": "현황 건폐율입니다. 대지지분과 현황 용적률이 모두 없을 때 기존 평균층수와 함께 대지면적 추정에 사용합니다.",
    "avg_current_floors": "기존 단지의 평균 층수입니다. 현황 건폐율로 대지면적을 역산할 때만 사용합니다.",
    "target_households_override": "자동 산출된 예상 총세대수가 마음에 들지 않을 때만 직접 덮어쓰세요.",
    "general_sale_ratio_override": "일반분양 비율은 기본적으로 자동 산출됩니다. 분양계획이 명확할 때만 직접 수정하는 값을 넣으세요.",
    "donation_ratio_override": "기부채납 비율은 공공시설, 공원, 도로 등으로 빠지는 면적을 간편 반영한 값입니다. 정비사업 정보몽땅의 토지이용계획·공동이용시설 계획이 있으면 그 값이 우선합니다.",
    "rental_ratio_override": "임대주택 비율은 재개발에서 중요합니다. 공식 주택공급계획이 있으면 그 값이 우선하고, 없으면 사업유형과 프리셋으로 추정합니다. 도시정비법 시행령 제9조 범위를 참고합니다.",
    "sale_rate": "일반분양분이 실제로 판매되는 비율입니다. 100% 미만이면 미분양 리스크를 반영합니다.",
    "cash_settlement_rate": "현금청산, 분양제외 등으로 조합원 분양분에서 빠질 비율입니다.",
    "pf_rate": "사업비 조달에 반영할 PF 금리입니다.",
    "move_loan_rate": "이주비 이자율 또는 추가자금 조달금리의 근사치입니다.",
    "pf_financing_ratio": "총 사업비 중 PF 등 차입으로 조달한다고 보는 비율입니다. 실제 조달계획이 있으면 그 비율을 우선 넣으세요.",
    "pf_interest_months": "PF 이자가 실제로 붙는 기간입니다. 공사 전후 전 기간이 아니라 차입이 발생하는 구간만 반영하는 게 맞습니다.",
    "avg_move_loan_amount": "서울시 매뉴얼 기준 조합원이주비 이자 추산은 `조합원 수 × 세대당 평균 무이자 이주비 × 연이자율 × 대여기간`입니다. 세대당 평균 무이자 이주비를 넣으세요.",
    "move_loan_duration_months": "세대당 평균 무이자 이주비가 실제로 대여되는 기간입니다. 이주 개시부터 입주 전까지의 대략적 개월 수를 넣습니다.",
    "official_price_reconstruction": "재건축 정밀계산에서만 쓰는 참고값입니다. 공동주택 공시가격이나 감정가가 있으면 권리가액 추정 보정에 사용합니다.",
    "official_price_redevelopment": "재개발 정밀계산에서만 쓰는 참고값입니다. 토지/건물 공시가격 또는 감정가를 넣으면 권리가액 참고 추정에 사용합니다.",
    "unit_mix": "재건축에서 기존 평형별 세대수와 면적을 넣으면 현재 연면적과 세대구성을 더 정확하게 추정합니다. 형식: 타입,세대수,전용,공급",
    "member_price_text": "정밀모드에서 배정평형 비교가 필요할 때만 쓰는 참고값입니다. 빠른 수익성 답에는 필수가 아닙니다. 형식: 타입,전용,공급,분양가(억)",
}


class ProjectKind(str, Enum):
    RECONSTRUCTION = "재건축"
    REDEVELOPMENT = "재개발"

MONEY_TOKEN_PATTERN = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*(jo|eok|cheonman|baekman|manwon|조|억|천만|만원|원)?",
    re.IGNORECASE,
)
PERCENT_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
DATE_RANGE_PATTERN = re.compile(r"(20\d{2}[./-]\d{1,2})(?:\s*[~\-]\s*(20\d{2}[./-]\d{1,2}))?")


@dataclass
class SourceRecord:
    key: str
    value: str
    source: str
    confidence: float
    notes: str = ""


@dataclass
class MemberPriceRecord:
    label: str
    exclusive_area_sqm: float
    supply_area_sqm: float
    member_sale_price: float


@dataclass
class ParsedProjectNotice:
    proportional_ratio: float | None
    old_asset_formula: str | None
    member_price_table: list[MemberPriceRecord]
    revenue_items: dict[str, float]
    cost_items: dict[str, float]
    extracted_records: list[SourceRecord]
    source_name: str
    document_stage: str | None = None
    document_schedule: str | None = None
    document_cost_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class AutofillProjectData:
    query: str
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
    building_area_sqm: float | None = None
    gross_floor_area_sqm: float | None = None
    target_building_coverage_ratio: float | None = None
    current_building_coverage_ratio: float | None = None
    target_far: float | None = None
    current_households: int | None = None
    owner_count: int | None = None
    tenant_count: int | None = None
    planned_households: int | None = None
    sale_households: int | None = None
    rental_households: int | None = None
    public_facility_area_sqm: float | None = None
    donation_area_sqm: float | None = None
    schedule_text: str | None = None
    source_records: list[SourceRecord] = field(default_factory=list)


@dataclass
class CostBucket:
    key: str
    label: str
    amount: float
    source: str
    description: str
    overridden: bool = False


@dataclass
class UnitMixRow:
    label: str
    households: int
    exclusive_area_sqm: float
    supply_area_sqm: float


@dataclass
class RightsInputs:
    expected_new_exclusive_area: float | None
    appraised_old_asset_value: float | None
    total_old_asset_value: float | None
    official_price_reference: float | None
    adjustment_factor_override: float | None
    member_price_text: str


@dataclass
class QuickDealInputs:
    project_kind: ProjectKind
    scenario_profile: str
    current_stage: str
    purchase_price: float
    current_unit_exclusive_area: float
    current_unit_supply_area: float
    comparison_new_price: float | None
    general_sale_price: float | None
    current_households: int
    current_far: float | None
    target_far: float | None
    land_share: float | None
    site_area_sqm: float | None
    current_building_coverage_ratio: float | None
    target_building_coverage_ratio: float | None
    average_current_floors: float | None
    floor_no: int
    official_price_reference: float | None
    recent_same_complex_trade_price: float | None
    sale_rate: float | None
    cash_settlement_rate: float | None
    construction_cost_per_pyeong: float | None
    pf_rate: float | None
    move_loan_rate: float
    target_households_override: int | None
    general_sale_ratio_override: float | None
    donation_ratio_override: float | None
    rental_ratio_override: float | None
    delay_one_year: bool
    aggressive_upsize: bool
    capital_area: bool
    autofill_project: AutofillProjectData | None = None
    parsed_notice: ParsedProjectNotice | None = None
    applied_document_fields: set[str] = field(default_factory=set)
    use_doc_price_table: bool = False
    lookup_enabled: bool = False


@dataclass
class AdvancedProjectInputs:
    rights_inputs: RightsInputs
    unit_mix_rows: list[UnitMixRow]
    pf_financing_ratio: float
    pf_interest_months: float
    average_move_loan_amount: float
    move_loan_duration_months: float
    acquisition_rate: float
    annual_holding_rate: float
    capital_gains_effective_rate: float
    brokerage_rate: float
    ancillary_revenue: float
    other_disposal_revenue: float
    liquidation_cost_override: float | None
    cost_bucket_overrides: dict[str, float]


@dataclass
class ConfidenceReport:
    input_completion: float
    autofill_strength: float
    schedule_certainty: float
    valuation_strength: float
    total: float
    label: str


@dataclass
class SimulationResult:
    site_area_sqm: float | None
    site_source: str
    current_gross_floor_area_sqm: float
    gross_floor_area_sqm: float
    average_supply_area_sqm: float
    simulated_total_households: int
    planned_households: int
    member_households: int
    general_sale_households: int
    rental_households: int
    donation_ratio: float
    rental_ratio: float
    general_sale_ratio: float
    saleable_area_factor: float
    required_avg_floors: float | None
    public_facility_area_sqm: float | None
    donation_area_sqm: float | None
    sources: dict[str, str]


@dataclass
class FeasibilityCheck:
    level: str
    title: str
    message: str


@dataclass
class AdvancedRightsResult:
    old_asset_estimate: float
    total_old_asset_value: float
    rights_value: float
    old_asset_source: str
    total_old_asset_source: str
    adjustment_factor: float
    floor_factor: float
    price_table: list[MemberPriceRecord]
    allocation_options: list[dict[str, float | str]]


@dataclass
class QuickResult:
    scenario_name: str
    remaining_months: float
    current_unit_exclusive_area: float
    additional_cash_needed: float
    time_cost_to_exit: float
    selected_exit_name: str
    selected_exit: dict[str, float | str | None]
    project_summary: dict[str, float]
    exits: list[dict[str, float | str | None]]
    cost_buckets: list[CostBucket]
    confidence_report: ConfidenceReport
    assumption_summary: dict[str, float]
    summary_lines: list[str]
    source_records: list[SourceRecord]
    sensitivity_rows: list[dict[str, str]]
    simulation_result: SimulationResult
    feasibility_checks: list[FeasibilityCheck]
    max_bid_price: float
    break_even_purchase_price: float
    selected_allocation: dict[str, float | str] | None = None
    upsize_allocation: dict[str, float | str] | None = None
    advanced_rights_result: AdvancedRightsResult | None = None
    old_asset_estimate: float | None = None
    total_old_asset_value: float | None = None
    rights_value: float | None = None
    old_asset_source: str | None = None
    total_old_asset_source: str | None = None
    adjustment_factor: float | None = None
    floor_factor: float | None = None
    price_table: list[MemberPriceRecord] = field(default_factory=list)
    allocation_options: list[dict[str, float | str]] = field(default_factory=list)


def cache_data(*args, **kwargs):
    def decorator(func):
        if st is None:
            return func
        return st.cache_data(*args, **kwargs)(func)

    return decorator


def record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(key=key, value=value, source=source, confidence=confidence, notes=notes)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return default if den == 0 else num / den


def won_from_eok(value: float) -> float:
    return float(value) * 100_000_000.0


def eok_from_won(value: float | None) -> float:
    return 0.0 if value is None else float(value) / 100_000_000.0


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


def humanize_source(source: str) -> str:
    if source.startswith("CSV:"):
        return f"CSV 문서: {source[4:]}"
    if source.startswith("PDF:"):
        return f"PDF 문서: {source[4:]}"
    return SOURCE_LABELS.get(source, source)


def humanize_key(key: str) -> str:
    return DISPLAY_KEY_LABELS.get(key, key)


def humanize_value(value: object) -> str:
    return VALUE_LABELS.get(str(value), str(value))


def parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = str(text).strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(text: str | None) -> int | None:
    parsed = parse_float(text)
    if parsed is None:
        return None
    return int(round(parsed))


def parse_korean_money(text: str) -> float | None:
    if not text:
        return None
    compact = str(text).replace(" ", "")
    match = MONEY_TOKEN_PATTERN.search(compact)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    multipliers = {
        "jo": 1_0000_0000_0000,
        "eok": 100_000_000,
        "cheonman": 10_000_000,
        "baekman": 1_000_000,
        "manwon": 10_000,
        "조": 1_0000_0000_0000,
        "억": 100_000_000,
        "천만": 10_000_000,
        "만원": 10_000,
        "원": 1,
        "": 1,
    }
    return number * multipliers.get(unit, 1)


def parse_member_price_text(raw_text: str) -> list[MemberPriceRecord]:
    records: list[MemberPriceRecord] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        try:
            label = parts[0]
            exclusive = float(parts[1])
            supply = float(parts[2])
            price = won_from_eok(float(parts[3]))
        except ValueError:
            continue
        records.append(MemberPriceRecord(label=label, exclusive_area_sqm=exclusive, supply_area_sqm=supply, member_sale_price=price))
    return records


def default_member_price_table(
    user_text: str,
    doc_table: list[MemberPriceRecord],
    use_doc_table: bool,
    project_kind: ProjectKind,
    comparison_new_price: float | None,
    general_sale_price: float | None,
    purchase_price: float,
    current_exclusive_area: float,
    expected_new_area: float | None,
) -> list[MemberPriceRecord]:
    text_table = parse_member_price_text(user_text)
    if text_table:
        return text_table
    if use_doc_table and doc_table:
        return doc_table
    base_market_price = comparison_new_price or general_sale_price or purchase_price * 1.45
    base_exclusive = expected_new_area or max(current_exclusive_area, 59.0)
    if project_kind == ProjectKind.REDEVELOPMENT:
        sizes = sorted({59.0, 74.0, 84.0, round(base_exclusive)})
    else:
        sizes = sorted({59.0, 84.0, 101.0, round(base_exclusive)})
    rows: list[MemberPriceRecord] = []
    for size in sizes:
        area_ratio = safe_div(size, base_exclusive, 1.0)
        member_price = base_market_price * (area_ratio**0.98) * 0.85
        rows.append(MemberPriceRecord(label=f"{int(size)}형", exclusive_area_sqm=float(size), supply_area_sqm=round(size / 0.78, 2), member_sale_price=member_price))
    return rows


def normalize_stage_name(raw_stage: str | None) -> str | None:
    if not raw_stage:
        return None
    text = str(raw_stage).strip()
    mappings = (
        ("조합해산", "준공/입주"),
        ("준공", "준공/입주"),
        ("입주", "준공/입주"),
        ("착공", "착공"),
        ("철거", "이주/철거"),
        ("이주", "이주/철거"),
        ("관리처분", "관리처분인가"),
        ("사업시행", "사업시행인가"),
        ("조합설립", "조합설립인가"),
        ("추진위원", "추진위승인"),
        ("정비구역", "정비구역지정"),
        ("정비계획", "정비구역지정"),
        ("안전진단", "재건축진단"),
        ("진단", "재건축진단"),
    )
    for needle, normalized in mappings:
        if needle in text:
            return normalized
    return text if text in STAGE_BASE_MONTHS else None


def is_advanced_detail_available(stage: str, parsed_notice: ParsedProjectNotice | None) -> bool:
    if stage in ADVANCED_DETAIL_STAGES:
        return True
    if parsed_notice and parsed_notice.document_stage in ADVANCED_DETAIL_STAGES:
        return True
    if parsed_notice and (
        parsed_notice.old_asset_formula
        or parsed_notice.member_price_table
        or parsed_notice.cost_items.get("total_old_asset_value")
    ):
        return True
    return False


def guess_project_kind(text: str | None) -> ProjectKind:
    raw = str(text or "")
    if "재개발" in raw:
        return ProjectKind.REDEVELOPMENT
    return ProjectKind.RECONSTRUCTION


def floor_factor(floor_no: int) -> float:
    if floor_no <= 3:
        return 0.98
    if floor_no >= 13:
        return 1.02
    return 1.00


def parse_unit_mix_text(raw_text: str) -> list[UnitMixRow]:
    rows: list[UnitMixRow] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        try:
            rows.append(
                UnitMixRow(
                    label=parts[0],
                    households=int(float(parts[1])),
                    exclusive_area_sqm=float(parts[2]),
                    supply_area_sqm=float(parts[3]),
                )
            )
        except ValueError:
            continue
    return rows


def weighted_average_supply_area(unit_mix_rows: list[UnitMixRow], default_supply_area: float) -> float:
    if not unit_mix_rows:
        return default_supply_area
    weighted_area = sum(item.households * item.supply_area_sqm for item in unit_mix_rows)
    total_households = sum(item.households for item in unit_mix_rows)
    return safe_div(weighted_area, total_households, default_supply_area)


def estimate_current_gross_floor_area_sqm(quick_inputs: QuickDealInputs, advanced_inputs: AdvancedProjectInputs) -> float:
    if advanced_inputs.unit_mix_rows:
        return sum(item.households * item.supply_area_sqm for item in advanced_inputs.unit_mix_rows) * 1.08
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        if quick_inputs.land_share and quick_inputs.current_households and quick_inputs.current_far:
            site_area_sqm = quick_inputs.land_share * quick_inputs.current_households
            return site_area_sqm * (quick_inputs.current_far / 100.0)
        if quick_inputs.site_area_sqm and quick_inputs.current_far:
            return quick_inputs.site_area_sqm * (quick_inputs.current_far / 100.0)
    return quick_inputs.current_households * quick_inputs.current_unit_supply_area * 1.08


def estimate_member_base_count(quick_inputs: QuickDealInputs, base_cash_rate: float) -> int:
    project = quick_inputs.autofill_project
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        seed = (project.owner_count if project and project.owner_count else None) or quick_inputs.current_households
    else:
        seed = (project.current_households if project and project.current_households else None) or quick_inputs.current_households
    return max(int(round(seed * (1 - base_cash_rate))), 1)


def estimate_donation_ratio(quick_inputs: QuickDealInputs, profile: dict[str, float]) -> tuple[float, str]:
    if quick_inputs.donation_ratio_override is not None:
        return clamp(quick_inputs.donation_ratio_override, 0.0, 0.40), "manual_override"
    project = quick_inputs.autofill_project
    if project and project.public_facility_area_sqm is not None and project.official_area_sqm:
        return clamp(project.public_facility_area_sqm / project.official_area_sqm, 0.0, 0.40), "official_cleanup"
    base_ratio = profile["donation_ratio"]
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        base_ratio = max(base_ratio, 0.10)
    return clamp(base_ratio, 0.0, 0.40), "preset"


def estimate_rental_ratio(quick_inputs: QuickDealInputs, profile: dict[str, float]) -> tuple[float, str]:
    if quick_inputs.rental_ratio_override is not None:
        return clamp(quick_inputs.rental_ratio_override, 0.0, 0.40), "manual_override"
    project = quick_inputs.autofill_project
    if project and project.rental_households is not None and project.planned_households is not None:
        return clamp(project.rental_households / max(project.planned_households, 1), 0.0, 0.40), "official_cleanup"
    base_ratio = profile["rental_ratio"]
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        base_ratio = max(base_ratio, 0.12)
    else:
        base_ratio = min(base_ratio, 0.03)
    return clamp(base_ratio, 0.0, 0.40), "preset"


def simulate_project_plan(
    quick_inputs: QuickDealInputs,
    advanced_inputs: AdvancedProjectInputs,
    base_cash_rate: float,
    profile: dict[str, float],
) -> SimulationResult:
    current_gross_floor_area_sqm = estimate_current_gross_floor_area_sqm(quick_inputs, advanced_inputs)
    site_area_sqm, site_source = estimate_site_area(quick_inputs, current_gross_floor_area_sqm)
    donation_ratio, donation_source = estimate_donation_ratio(quick_inputs, profile)
    rental_ratio, rental_source = estimate_rental_ratio(quick_inputs, profile)
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        redev_base_exclusive = advanced_inputs.rights_inputs.expected_new_exclusive_area or 59.0
        default_supply_area = max(redev_base_exclusive / 0.78, 75.0)
    else:
        default_supply_area = quick_inputs.current_unit_supply_area
    average_supply_area_sqm = weighted_average_supply_area(advanced_inputs.unit_mix_rows, default_supply_area)

    if site_area_sqm and quick_inputs.target_far:
        gross_floor_area_sqm = site_area_sqm * (quick_inputs.target_far / 100.0)
    elif quick_inputs.current_far and quick_inputs.target_far:
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(quick_inputs.target_far, quick_inputs.current_far, 1.0)
    else:
        growth_multiplier = 1.28 if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION else 1.38
        gross_floor_area_sqm = current_gross_floor_area_sqm * growth_multiplier

    saleable_area_factor = clamp(1.0 - donation_ratio, 0.55, 1.0)
    residential_efficiency = 0.84 if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.80
    simulated_total_households = max(
        int(round((gross_floor_area_sqm * residential_efficiency * saleable_area_factor) / max(average_supply_area_sqm, 1.0))),
        1,
    )
    project = quick_inputs.autofill_project
    if quick_inputs.target_households_override is not None:
        planned_households = quick_inputs.target_households_override
        households_source = "manual_override"
    elif project and project.planned_households is not None:
        planned_households = project.planned_households
        households_source = "official_cleanup"
    else:
        planned_households = simulated_total_households
        households_source = "simulation"

    member_households = estimate_member_base_count(quick_inputs, base_cash_rate)
    if project and project.rental_households is not None and project.planned_households is not None and quick_inputs.rental_ratio_override is None:
        rental_households = project.rental_households
        rental_source = "official_cleanup"
    else:
        rental_households = int(round(planned_households * rental_ratio))

    available_general_sale = max(planned_households - member_households - rental_households, 0)
    if project and project.sale_households is not None and project.planned_households is not None and quick_inputs.general_sale_ratio_override is None:
        general_sale_households = min(project.sale_households, available_general_sale)
        general_sale_source = "official_cleanup"
    elif quick_inputs.general_sale_ratio_override is not None:
        requested_ratio = clamp(quick_inputs.general_sale_ratio_override, 0.0, 1.0)
        general_sale_households = min(int(round(max(planned_households - rental_households, 0) * requested_ratio)), available_general_sale)
        general_sale_source = "manual_override"
    else:
        general_sale_households = available_general_sale
        general_sale_source = "simulation"
    general_sale_ratio = safe_div(general_sale_households, max(planned_households - rental_households, 1), 0.0)

    required_avg_floors = None
    if quick_inputs.target_building_coverage_ratio and quick_inputs.target_building_coverage_ratio > 0:
        required_avg_floors = (quick_inputs.target_far / 100.0) / quick_inputs.target_building_coverage_ratio if quick_inputs.target_far else None

    return SimulationResult(
        site_area_sqm=site_area_sqm,
        site_source=site_source,
        current_gross_floor_area_sqm=current_gross_floor_area_sqm,
        gross_floor_area_sqm=gross_floor_area_sqm,
        average_supply_area_sqm=average_supply_area_sqm,
        simulated_total_households=simulated_total_households,
        planned_households=planned_households,
        member_households=member_households,
        general_sale_households=general_sale_households,
        rental_households=rental_households,
        donation_ratio=donation_ratio,
        rental_ratio=rental_ratio,
        general_sale_ratio=general_sale_ratio,
        saleable_area_factor=saleable_area_factor,
        required_avg_floors=required_avg_floors,
        public_facility_area_sqm=project.public_facility_area_sqm if project else None,
        donation_area_sqm=project.donation_area_sqm if project else None,
        sources={
            "households": households_source,
            "general_sale_ratio": general_sale_source,
            "donation_ratio": donation_source,
            "rental_ratio": rental_source,
        },
    )


def build_feasibility_checks(
    quick_inputs: QuickDealInputs,
    simulation: SimulationResult,
) -> list[FeasibilityCheck]:
    checks: list[FeasibilityCheck] = []
    if simulation.required_avg_floors is not None:
        if simulation.required_avg_floors > 35:
            checks.append(FeasibilityCheck("risk", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층이 필요해 과도할 수 있습니다."))
        elif simulation.required_avg_floors > 25:
            checks.append(FeasibilityCheck("warn", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층이 필요합니다. 인허가·사업성 검토가 더 필요합니다."))
        else:
            checks.append(FeasibilityCheck("ok", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층 수준으로 계산됩니다."))
    else:
        checks.append(FeasibilityCheck("note", "층수 점검", "목표 건폐율이 없어서 평균층수 점검은 생략했습니다."))

    if simulation.planned_households > int(simulation.simulated_total_households * 1.15):
        checks.append(FeasibilityCheck("warn", "세대수 과다 가능성", f"입력/공식 계획 세대수 {simulation.planned_households:,}세대가 엔진 추정 {simulation.simulated_total_households:,}세대보다 많이 큽니다."))
    elif simulation.planned_households < simulation.member_households:
        checks.append(FeasibilityCheck("risk", "세대수 부족", f"예상 총세대수 {simulation.planned_households:,}세대로는 분양대상 {simulation.member_households:,}세대를 담기 어렵습니다."))
    else:
        checks.append(FeasibilityCheck("ok", "세대수 점검", f"예상 총세대수 {simulation.planned_households:,}세대, 일반분양 {simulation.general_sale_households:,}세대로 계산했습니다."))

    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        tenant_seed = quick_inputs.autofill_project.tenant_count if quick_inputs.autofill_project else None
        if tenant_seed:
            checks.append(FeasibilityCheck("ok", "세입자 반영", f"서울 공식값 기준 세입자 {tenant_seed:,}명을 보상비 추정에 반영했습니다."))
        else:
            checks.append(FeasibilityCheck("note", "세입자 반영", "세입자 수 공식값이 없어 재개발 세입자 보상은 보수적 휴리스틱으로 계산했습니다."))
    else:
        checks.append(FeasibilityCheck("note", "재건축 비용 구조", "재건축은 기본적으로 주거이전비·영업손실보상비를 자동 적용하지 않았습니다."))
    return checks


def adjustment_factor(
    public_price: float | None,
    recent_trade: float | None,
    override_value: float | None,
    old_asset_formula: str | None,
    applied_fields: set[str],
    capital_area: bool,
) -> tuple[float, str]:
    if override_value:
        return clamp(override_value, 1.05, 1.65), "user_override"
    if old_asset_formula and "old_asset_formula" in applied_fields:
        tail = old_asset_formula.split("x")[-1] if "x" in old_asset_formula.lower() else old_asset_formula.split("×")[-1]
        digits = "".join(ch for ch in tail if ch.isdigit() or ch == ".")
        try:
            return clamp(float(digits), 1.05, 1.65), "document_formula"
        except ValueError:
            pass
    if public_price and recent_trade:
        return clamp(recent_trade / public_price, 1.05, 1.65), "trade_vs_public"
    return (1.25 if capital_area else 1.18), "heuristic_default"


def simple_top_drivers(duration_cost: float, construction_cost: float, additional_cash_needed: float) -> list[str]:
    items = [
        ("추가투입금", max(additional_cash_needed, 0.0), "선택 평형과 권리가액 차이"),
        ("본공사비", max(construction_cost, 0.0), "연면적과 평당 공사비"),
        ("시간비용", max(duration_cost, 0.0), "보유비용과 이자"),
    ]
    items.sort(key=lambda row: row[1], reverse=True)
    return [f"{name}: {reason}" for name, _, reason in items[:3]]


def read_csv_with_fallbacks(file_bytes: bytes) -> list[list[str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            text = file_bytes.decode(encoding)
            break
        except Exception as exc:
            last_error = exc
    else:
        if last_error:
            raise last_error
        text = file_bytes.decode("utf-8")
    rows: list[list[str]] = []
    for line in StringIO(text):
        rows.append([part.strip() for part in line.rstrip("\n").split(",")])
    return rows


def parse_source_rows(rows: list[list[str]], file_name: str) -> ParsedProjectNotice:
    if not rows:
        return ParsedProjectNotice(None, None, [], {}, {}, [], file_name)
    header = [cell.lower() for cell in rows[0]]
    extracted_records: list[SourceRecord] = []
    revenue_items: dict[str, float] = {}
    cost_items: dict[str, float] = {}
    proportional_ratio: float | None = None
    old_asset_formula: str | None = None
    document_stage: str | None = None
    document_schedule: str | None = None
    document_cost_breakdown: dict[str, float] = {}
    if "key" in header and "value" in header:
        key_idx = header.index("key")
        value_idx = header.index("value")
        for row in rows[1:]:
            if max(key_idx, value_idx) >= len(row):
                continue
            key_raw = re.sub(r"\s+", "", row[key_idx])
            value = row[value_idx].strip()
            if not key_raw or not value:
                continue
            if key_raw in {"stage", "문서단계", "사업단계"}:
                document_stage = normalize_stage_name(value)
                extracted_records.append(record("document_stage", document_stage or value, f"CSV:{file_name}", 0.80))
                continue
            if key_raw in {"schedule", "향후일정", "예정시기"}:
                document_schedule = value
                extracted_records.append(record("document_schedule", value, f"CSV:{file_name}", 0.74))
                continue
            key = next((canonical for canonical, label in MANUAL_KEYS.items() if key_raw == re.sub(r"\s+", "", label)), key_raw)
            if key == "proportional_ratio":
                pct_match = PERCENT_PATTERN.search(value)
                proportional_ratio = float(pct_match.group(1)) if pct_match else parse_float(value)
                if proportional_ratio is not None:
                    extracted_records.append(record(key, f"{proportional_ratio:.2f}", f"CSV:{file_name}", 0.86))
            elif key in {"member_sale_revenue", "general_sale_revenue", "total_revenue"}:
                amount = parse_korean_money(value)
                if amount is not None:
                    revenue_items[key] = amount
                    extracted_records.append(record(key, f"{amount:,.0f}", f"CSV:{file_name}", 0.78))
            elif key in {"total_cost", "reconstruction_levy", "total_old_asset_value"}:
                amount = parse_korean_money(value)
                if amount is not None:
                    cost_items[key] = amount
                    extracted_records.append(record(key, f"{amount:,.0f}", f"CSV:{file_name}", 0.78))
            elif key == "old_asset_formula":
                old_asset_formula = value
                extracted_records.append(record(key, value, f"CSV:{file_name}", 0.72))
            elif key.startswith("bucket_"):
                amount = parse_korean_money(value)
                if amount is not None:
                    document_cost_breakdown[key[7:]] = amount
        return ParsedProjectNotice(
            proportional_ratio=proportional_ratio,
            old_asset_formula=old_asset_formula,
            member_price_table=[],
            revenue_items=revenue_items,
            cost_items=cost_items,
            extracted_records=extracted_records,
            source_name=file_name,
            document_stage=document_stage,
            document_schedule=document_schedule,
            document_cost_breakdown=document_cost_breakdown,
        )
    member_price_table: list[MemberPriceRecord] = []
    for row in rows[1:]:
        if len(row) < 4:
            continue
        label = row[0].strip()
        exclusive = parse_float(row[1])
        supply = parse_float(row[2])
        price = parse_korean_money(row[3]) or (won_from_eok(parse_float(row[3]) or 0) if parse_float(row[3]) else None)
        if label and exclusive and supply and price:
            member_price_table.append(
                MemberPriceRecord(
                    label=label,
                    exclusive_area_sqm=exclusive,
                    supply_area_sqm=supply,
                    member_sale_price=price,
                )
            )
    return ParsedProjectNotice(
        proportional_ratio=None,
        old_asset_formula=None,
        member_price_table=member_price_table,
        revenue_items={},
        cost_items={},
        extracted_records=[record("member_price_table_count", str(len(member_price_table)), f"CSV:{file_name}", 0.90)],
        source_name=file_name,
    )


def detect_document_stage(text: str) -> str | None:
    return normalize_stage_name(text)


def parse_uploaded_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        rows = read_csv_with_fallbacks(file_bytes)
        return parse_source_rows(rows, file_name)
    if lower_name.endswith(".pdf"):
        if PdfReader is None:
            return ParsedProjectNotice(
                proportional_ratio=None,
                old_asset_formula=None,
                member_price_table=[],
                revenue_items={},
                cost_items={},
                extracted_records=[record("parser_status", "pypdf_missing", f"PDF:{file_name}", 0.10, "pypdf 설치 필요")],
                source_name=file_name,
            )
        try:
            reader = PdfReader(BytesIO(file_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            revenue_items: dict[str, float] = {}
            cost_items: dict[str, float] = {}
            extracted_records: list[SourceRecord] = []
            proportional_ratio: float | None = None
            old_asset_formula: str | None = None
            document_stage = detect_document_stage(text)
            document_schedule = None
            match = DATE_RANGE_PATTERN.search(text)
            if match:
                document_schedule = match.group(0)
            member_price_table: list[MemberPriceRecord] = []
            table_pattern = re.compile(
                r"(?P<label>\d+\s*[A-Za-z가-힣]+)\s+"
                r"(?P<exclusive>\d+(?:\.\d+)?)\s+"
                r"(?P<supply>\d+(?:\.\d+)?)\s+"
                r"(?P<price>\d[\d,]*(?:\.\d+)?\s*(?:억|만원|원)?)"
            )
            for line in lines:
                compact = re.sub(r"\s+", "", line)
                if "비례율" in compact and proportional_ratio is None:
                    pct_match = PERCENT_PATTERN.search(line)
                    if pct_match:
                        proportional_ratio = float(pct_match.group(1))
                        extracted_records.append(record("proportional_ratio", f"{proportional_ratio:.2f}", f"PDF:{file_name}", 0.74))
                if old_asset_formula is None and ("공동주택" in compact or "공시가격" in compact) and ("x" in compact.lower() or "×" in compact):
                    old_asset_formula = line[:200]
                    extracted_records.append(record("old_asset_formula", old_asset_formula, f"PDF:{file_name}", 0.68))
                for canonical, label in MANUAL_KEYS.items():
                    if label.replace(" ", "") in compact:
                        amount = parse_korean_money(line)
                        if amount is None:
                            continue
                        if canonical in {"member_sale_revenue", "general_sale_revenue", "total_revenue"}:
                            revenue_items[canonical] = amount
                        else:
                            cost_items[canonical] = amount
                        extracted_records.append(record(canonical, f"{amount:,.0f}", f"PDF:{file_name}", 0.70))
                for matched in table_pattern.finditer(line):
                    price = parse_korean_money(matched.group("price"))
                    if price is None:
                        continue
                    member_price_table.append(
                        MemberPriceRecord(
                            label=matched.group("label"),
                            exclusive_area_sqm=float(matched.group("exclusive")),
                            supply_area_sqm=float(matched.group("supply")),
                            member_sale_price=price,
                        )
                    )
            if member_price_table:
                extracted_records.append(record("member_price_table_count", str(len(member_price_table)), f"PDF:{file_name}", 0.64))
            if document_stage:
                extracted_records.append(record("document_stage", document_stage, f"PDF:{file_name}", 0.62))
            if document_schedule:
                extracted_records.append(record("document_schedule", document_schedule, f"PDF:{file_name}", 0.60))
            return ParsedProjectNotice(
                proportional_ratio=proportional_ratio,
                old_asset_formula=old_asset_formula,
                member_price_table=member_price_table[:12],
                revenue_items=revenue_items,
                cost_items=cost_items,
                extracted_records=extracted_records,
                source_name=file_name,
                document_stage=document_stage,
                document_schedule=document_schedule,
            )
        except Exception as exc:
            return ParsedProjectNotice(
                proportional_ratio=None,
                old_asset_formula=None,
                member_price_table=[],
                revenue_items={},
                cost_items={},
                extracted_records=[record("parser_status", "parse_error", f"PDF:{file_name}", 0.10, str(exc)[:160])],
                source_name=file_name,
            )
    return ParsedProjectNotice(
        proportional_ratio=None,
        old_asset_formula=None,
        member_price_table=[],
        revenue_items={},
        cost_items={},
        extracted_records=[record("parser_status", "unsupported", file_name, 0.10)],
        source_name=file_name,
    )


def try_parse_uploaded_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    try:
        return parse_uploaded_notice(file_name, file_bytes)
    except Exception as exc:
        return ParsedProjectNotice(
            proportional_ratio=None,
            old_asset_formula=None,
            member_price_table=[],
            revenue_items={},
            cost_items={},
            extracted_records=[record("parser_status", "parse_error", file_name, 0.10, str(exc)[:160])],
            source_name=file_name,
        )


def merge_notices(notices: list[ParsedProjectNotice]) -> ParsedProjectNotice | None:
    if not notices:
        return None
    proportional_ratio = next((item.proportional_ratio for item in notices if item.proportional_ratio is not None), None)
    old_asset_formula = next((item.old_asset_formula for item in notices if item.old_asset_formula), None)
    document_stage = next((item.document_stage for item in notices if item.document_stage), None)
    document_schedule = next((item.document_schedule for item in notices if item.document_schedule), None)
    member_price_table = next((item.member_price_table for item in notices if item.member_price_table), [])
    revenue_items: dict[str, float] = {}
    cost_items: dict[str, float] = {}
    document_cost_breakdown: dict[str, float] = {}
    extracted_records: list[SourceRecord] = []
    for notice in notices:
        revenue_items.update(notice.revenue_items)
        cost_items.update(notice.cost_items)
        document_cost_breakdown.update(notice.document_cost_breakdown)
        extracted_records.extend(notice.extracted_records)
    return ParsedProjectNotice(
        proportional_ratio=proportional_ratio,
        old_asset_formula=old_asset_formula,
        member_price_table=member_price_table,
        revenue_items=revenue_items,
        cost_items=cost_items,
        extracted_records=extracted_records,
        source_name=", ".join(item.source_name for item in notices),
        document_stage=document_stage,
        document_schedule=document_schedule,
        document_cost_breakdown=document_cost_breakdown,
    )


class SimpleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            value = " ".join(" ".join(self._current_cell).split())
            self._current_row.append(value)
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs_dict = dict(attrs)
            self._href = attrs_dict.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = " ".join(" ".join(self._text).split())
            self.items.append((text, self._href))
            self._href = None


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


@cache_data(ttl=60 * 60, show_spinner=False)
def cleanup_search_projects(query: str) -> list[AutofillProjectData]:
    keyword = query.strip()
    if not keyword:
        return []
    encoded = urllib.parse.quote(keyword)
    url = f"https://cleanup.seoul.go.kr/cleanup/bsnssttus/lsubBsnsSttus.do?scupBsnsSttus.asscNm={encoded}"
    html_text = fetch_html(url)
    rows = re.findall(r"<tr>(.*?)</tr>", html_text, re.S)
    results: list[AutofillProjectData] = []
    for row in rows[1:]:
        if "조회된 목록이 없습니다." in row:
            continue
        cells = [unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell))).strip() for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 6:
            continue
        slug_match = re.search(r"cafeOpenPopup\('([^']+)'\)", row)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        results.append(
            AutofillProjectData(
                query=keyword,
                project_name=cells[3],
                district=cells[1],
                business_type=cells[2],
                project_kind=guess_project_kind(cells[2]),
                progress_stage=normalize_stage_name(cells[5]),
                representative_lot=cells[4],
                project_slug=slug,
                source_url=f"https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl={slug}",
                source_records=[record("document_stage", normalize_stage_name(cells[5]) or cells[5], "official_cleanup", 0.82)],
            )
        )
    return results[:12]


def extract_text_tokens(html_text: str) -> list[str]:
    parser = SimpleTextParser()
    parser.feed(html_text)
    return parser.parts


def extract_tables(html_text: str) -> list[list[list[str]]]:
    parser = TableParser()
    parser.feed(html_text)
    return parser.tables


def extract_links(html_text: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(html_text)
    return parser.items


def extract_households_from_supply_table(table: list[list[str]]) -> int | None:
    if len(table) < 3:
        return None
    header_row = table[0]
    data_row = table[-1]
    try:
        start_idx = header_row.index("동수") + 1
    except ValueError:
        start_idx = 4
    counts: list[int] = []
    for cell in data_row[start_idx:]:
        stripped = cell.replace(",", "")
        if not stripped or "." in stripped:
            continue
        if stripped.isdigit():
            value = int(stripped)
            if value > 0:
                counts.append(value)
    return sum(counts) if counts else None


def extract_public_facility_areas(
    land_use_table: list[list[str]],
    facility_table: list[list[str]],
) -> tuple[float | None, float | None]:
    land_public_area = None
    if len(land_use_table) >= 3:
        numeric_cells = [parse_float(cell) for cell in land_use_table[-1]]
        valid_values = [value for value in numeric_cells if value is not None]
        if len(valid_values) > 1:
            land_public_area = sum(valid_values[1:])

    facility_public_area = 0.0
    donation_area = 0.0
    for row in facility_table[1:]:
        if len(row) < 3:
            continue
        area = parse_float(row[2])
        if area is None:
            continue
        facility_public_area += area
        if len(row) > 3 and "기부채납" in row[3]:
            donation_area += area

    public_area = None
    candidates = [value for value in (land_public_area, facility_public_area or None) if value is not None]
    if candidates:
        public_area = max(candidates)
    return public_area, donation_area or None


def normalize_cleanup_source_rows(project: AutofillProjectData) -> list[SourceRecord]:
    rows = list(project.source_records)
    if project.site_area_sqm is not None:
        rows.append(record("site_area_sqm", f"{project.site_area_sqm:,.1f}", "official_cleanup", 0.88))
    if project.target_building_coverage_ratio is not None:
        rows.append(record("building_coverage_ratio", f"{project.target_building_coverage_ratio:.1f}", "official_cleanup", 0.86))
    if project.target_far is not None:
        rows.append(record("target_far", f"{project.target_far:.1f}", "official_cleanup", 0.86))
    if project.current_households is not None:
        rows.append(record("current_households", str(project.current_households), "official_cleanup", 0.86))
    if project.planned_households is not None:
        rows.append(record("planned_households", str(project.planned_households), "official_cleanup", 0.82))
    if project.sale_households is not None:
        rows.append(record("sale_households", str(project.sale_households), "official_cleanup", 0.80))
    if project.rental_households is not None:
        rows.append(record("rental_households", str(project.rental_households), "official_cleanup", 0.80))
    if project.public_facility_area_sqm is not None:
        rows.append(record("public_facility_area_sqm", f"{project.public_facility_area_sqm:,.1f}", "official_cleanup", 0.78))
    if project.donation_area_sqm is not None:
        rows.append(record("donation_area_sqm", f"{project.donation_area_sqm:,.1f}", "official_cleanup", 0.76))
    return rows


@cache_data(ttl=60 * 60, show_spinner=False)
def cleanup_fetch_project_summary(project_slug: str) -> AutofillProjectData | None:
    if not project_slug:
        return None
    main_url = f"https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl={urllib.parse.quote(project_slug)}"
    main_html = fetch_html(main_url)
    links = extract_links(main_html)
    cafe_id_match = re.search(r"cafeId=([A-Z0-9]+)", main_html)
    if not cafe_id_match:
        return None
    cafe_id = cafe_id_match.group(1)
    summary_href = next((href for text, href in links if text == "사업개요" and "mastr-cleanup-bsnsSumry" in href), None)
    if not summary_href:
        summary_href = f"/cafe/mastr-cleanup-bsnsSumry/execute.do?cafeId={cafe_id}&stepSeCode=102&div=sumry"
    summary_url = urllib.parse.urljoin("https://cleanup.seoul.go.kr", unescape(summary_href))
    summary_html = fetch_html(summary_url)
    tables = extract_tables(summary_html)
    basics = tables[0] if len(tables) > 0 else []
    land_use_table = tables[2] if len(tables) > 2 else []
    building_table = tables[3] if len(tables) > 3 else []
    sale_table = tables[4] if len(tables) > 4 else []
    rental_table = tables[5] if len(tables) > 5 else []
    facility_table = tables[6] if len(tables) > 6 else []
    basics_map: dict[str, str] = {}
    for row in basics:
        for idx in range(0, len(row) - 1, 2):
            basics_map[row[idx]] = row[idx + 1]
    building_row = building_table[1] if len(building_table) > 1 else []
    current_households = parse_int(basics_map.get("조합원 수", "").replace("명", ""))
    owner_count = parse_int((basics_map.get("토지등 소유자 수", "") or "").replace("명", ""))
    tenant_count = parse_int((basics_map.get("세입자 수", "") or "").replace("명", ""))
    planned_sale = extract_households_from_supply_table(sale_table)
    planned_rental = extract_households_from_supply_table(rental_table)
    public_facility_area_sqm, donation_area_sqm = extract_public_facility_areas(land_use_table, facility_table)
    project = AutofillProjectData(
        query=project_slug,
        project_name=basics_map.get("정비구역 명칭", project_slug),
        district=(basics_map.get("정비구역 위치", "").split()[0] if basics_map.get("정비구역 위치") else ""),
        business_type=basics_map.get("사업구분", ""),
        project_kind=guess_project_kind(basics_map.get("사업구분", "")),
        progress_stage=None,
        representative_lot=basics_map.get("정비구역 위치", ""),
        project_slug=project_slug,
        cafe_id=cafe_id,
        source_url=summary_url,
        official_area_sqm=parse_float(basics_map.get("정비구역 면적(㎡)")),
        site_area_sqm=parse_float(building_row[1]) if len(building_row) > 1 else None,
        building_area_sqm=parse_float(building_row[2]) if len(building_row) > 2 else None,
        gross_floor_area_sqm=parse_float(building_row[3]) if len(building_row) > 3 else None,
        target_building_coverage_ratio=parse_float(building_row[4]) if len(building_row) > 4 else None,
        target_far=parse_float(building_row[5]) if len(building_row) > 5 else None,
        current_households=current_households,
        owner_count=owner_count,
        tenant_count=tenant_count,
        planned_households=(planned_sale or 0) + (planned_rental or 0) or None,
        sale_households=planned_sale,
        rental_households=planned_rental,
        public_facility_area_sqm=public_facility_area_sqm,
        donation_area_sqm=donation_area_sqm,
    )
    project.schedule_text = cleanup_fetch_schedule_text(cafe_id)
    project.source_records = normalize_cleanup_source_rows(project)
    return project


@cache_data(ttl=60 * 60, show_spinner=False)
def cleanup_fetch_schedule_text(cafe_id: str) -> str | None:
    if not cafe_id:
        return None
    url = f"https://cleanup.seoul.go.kr/assc/bbs-use/vscrScdl.do?cafeId={urllib.parse.quote(cafe_id)}"
    try:
        html_text = fetch_html(url)
    except urllib.error.URLError:
        return None
    tokens = extract_text_tokens(html_text)
    if "등록된 게시물이 없습니다." in tokens:
        return None
    content_tokens = [token for token in tokens if token not in {"향후일정", "전체", "건이 검색되었습니다.", "일정", "내용"}]
    if len(content_tokens) > 6:
        return " / ".join(content_tokens[5:11])
    return None


def estimate_remaining_months(stage: str, autofill: AutofillProjectData | None, delay_one_year: bool, profile_name: str, scenario_name: str) -> tuple[float, str]:
    base_months = float(STAGE_BASE_MONTHS.get(stage, 72))
    scenario = SCENARIOS[scenario_name]
    profile = ASSUMPTION_PROFILES[profile_name]
    source = "manual"
    schedule_text = (autofill.schedule_text if autofill else None) or ""
    if schedule_text:
        matches = DATE_RANGE_PATTERN.findall(schedule_text)
        if matches:
            try:
                start_text = matches[0][0].replace(".", "-").replace("/", "-")
                year, month = [int(part) for part in start_text.split("-")[:2]]
                now = datetime.now()
                delta_months = max((year - now.year) * 12 + (month - now.month), 0)
                base_months = max(delta_months, 6)
                source = "schedule_board"
            except Exception:
                source = "manual"
    months = base_months * scenario["duration_multiplier"] * profile["duration_buffer"]
    if delay_one_year:
        months += 12
    return months, source


def default_pf_financing_ratio(project_kind: ProjectKind) -> float:
    return 0.60 if project_kind == ProjectKind.RECONSTRUCTION else 0.65


def default_pf_interest_months(remaining_months: float) -> float:
    return clamp(remaining_months * 0.55, 6.0, max(remaining_months, 6.0))


def default_average_move_loan_amount(purchase_price: float, project_kind: ProjectKind) -> float:
    multiplier = 0.40 if project_kind == ProjectKind.RECONSTRUCTION else 0.30
    return purchase_price * multiplier


def default_move_loan_duration_months(remaining_months: float) -> float:
    return clamp(remaining_months, 12.0, 30.0)


def estimate_site_area(inputs: QuickDealInputs, current_gross_floor_area_sqm: float) -> tuple[float | None, str]:
    if inputs.land_share:
        return inputs.land_share * inputs.current_households, "manual"
    if inputs.site_area_sqm:
        return inputs.site_area_sqm, "official_cleanup" if inputs.lookup_enabled else "manual"
    if inputs.current_far:
        return current_gross_floor_area_sqm / max(inputs.current_far / 100.0, 0.01), "simulation"
    if inputs.current_building_coverage_ratio and inputs.average_current_floors:
        return current_gross_floor_area_sqm / max(inputs.current_building_coverage_ratio * inputs.average_current_floors, 0.01), "simulation"
    return None, "simulation"


def build_cost_buckets(base_amounts: dict[str, float], overrides: dict[str, float], document_buckets: dict[str, float]) -> list[CostBucket]:
    buckets: list[CostBucket] = []
    for key, label, description in COST_BUCKET_META:
        if overrides.get(key):
            amount = overrides[key]
            source = "bucket_override"
            overridden = True
        elif document_buckets.get(key):
            amount = document_buckets[key]
            source = "document"
            overridden = False
        else:
            amount = base_amounts.get(key, 0.0)
            source = "engine"
            overridden = False
        buckets.append(CostBucket(key=key, label=label, amount=amount, source=source, description=description, overridden=overridden))
    return buckets


def analyze_scenario(quick_inputs: QuickDealInputs, advanced_inputs: AdvancedProjectInputs, scenario_name: str, show_advanced_detail: bool) -> QuickResult:
    scenario = SCENARIOS[scenario_name]
    profile = ASSUMPTION_PROFILES[quick_inputs.scenario_profile]
    parsed_notice = quick_inputs.parsed_notice
    rights_inputs = advanced_inputs.rights_inputs
    records: list[SourceRecord] = []

    remaining_months, duration_source = estimate_remaining_months(
        stage=quick_inputs.current_stage,
        autofill=quick_inputs.autofill_project,
        delay_one_year=quick_inputs.delay_one_year,
        profile_name=quick_inputs.scenario_profile,
        scenario_name=scenario_name,
    )
    base_sale_rate = quick_inputs.sale_rate if quick_inputs.sale_rate is not None else scenario["sale_rate"]
    base_cash_rate = quick_inputs.cash_settlement_rate if quick_inputs.cash_settlement_rate is not None else scenario["cash_settlement_rate"]
    base_cost_per_pyeong = quick_inputs.construction_cost_per_pyeong or scenario["construction_cost_per_pyeong"]
    base_pf_rate = quick_inputs.pf_rate or scenario["pf_rate"]
    simulation = simulate_project_plan(quick_inputs, advanced_inputs, base_cash_rate, profile)
    pf_financing_ratio = clamp(advanced_inputs.pf_financing_ratio, 0.0, 0.95)
    pf_interest_months = max(advanced_inputs.pf_interest_months, 0.0)
    average_move_loan_amount = max(advanced_inputs.average_move_loan_amount, 0.0)
    move_loan_duration_months = max(advanced_inputs.move_loan_duration_months, 0.0)

    official_price_reference = rights_inputs.official_price_reference or quick_inputs.official_price_reference
    adj_factor, adj_source = adjustment_factor(
        public_price=official_price_reference,
        recent_trade=quick_inputs.recent_same_complex_trade_price,
        override_value=rights_inputs.adjustment_factor_override,
        old_asset_formula=parsed_notice.old_asset_formula if parsed_notice else None,
        applied_fields=quick_inputs.applied_document_fields,
        capital_area=quick_inputs.capital_area,
    )
    floor_adj = floor_factor(quick_inputs.floor_no) if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION else 1.0
    if rights_inputs.appraised_old_asset_value:
        old_asset_estimate = rights_inputs.appraised_old_asset_value
        old_asset_source = "manual_appraisal"
    elif official_price_reference:
        old_asset_estimate = official_price_reference * adj_factor * floor_adj
        old_asset_source = "public_price_adjusted"
    elif quick_inputs.recent_same_complex_trade_price:
        old_asset_estimate = quick_inputs.recent_same_complex_trade_price * floor_adj
        old_asset_source = "trade_backsolve"
    else:
        fallback_multiplier = 0.78 if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.74
        old_asset_estimate = quick_inputs.purchase_price * fallback_multiplier * floor_adj
        old_asset_source = "purchase_price_heuristic"

    member_count = simulation.member_households
    if parsed_notice and parsed_notice.cost_items.get("total_old_asset_value") and "total_old_asset_value" in quick_inputs.applied_document_fields:
        total_old_asset_value = parsed_notice.cost_items["total_old_asset_value"]
        total_old_asset_source = "document_total_old_asset"
    elif rights_inputs.total_old_asset_value:
        total_old_asset_value = rights_inputs.total_old_asset_value
        total_old_asset_source = "user_total_old_asset"
    else:
        total_old_asset_value = old_asset_estimate * member_count
        total_old_asset_source = "scaled_individual_old_asset"

    price_table = default_member_price_table(
        user_text=rights_inputs.member_price_text,
        doc_table=parsed_notice.member_price_table if parsed_notice else [],
        use_doc_table=quick_inputs.use_doc_price_table,
        project_kind=quick_inputs.project_kind,
        comparison_new_price=quick_inputs.comparison_new_price,
        general_sale_price=quick_inputs.general_sale_price,
        purchase_price=quick_inputs.purchase_price,
        current_exclusive_area=quick_inputs.current_unit_exclusive_area,
        expected_new_area=rights_inputs.expected_new_exclusive_area,
    )

    general_sale_households = simulation.general_sale_households
    rental_households = simulation.rental_households
    donation_ratio = simulation.donation_ratio
    rental_ratio = simulation.rental_ratio
    general_sale_ratio = simulation.general_sale_ratio
    gross_floor_area_pyeong = simulation.gross_floor_area_sqm / 3.3058
    current_gross_area_pyeong = simulation.current_gross_floor_area_sqm / 3.3058

    direct_construction_cost = gross_floor_area_pyeong * base_cost_per_pyeong
    if quick_inputs.delay_one_year and quick_inputs.current_stage not in {"착공", "준공/입주"}:
        direct_construction_cost *= 1.04
    demolition_cost = current_gross_area_pyeong * base_cost_per_pyeong * 0.06
    design_ratio = 0.06 if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.065
    design_and_pm_cost = direct_construction_cost * design_ratio
    union_and_professional_cost = direct_construction_cost * 0.018 + member_count * 8_000_000.0
    if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION and quick_inputs.current_stage == "재건축진단":
        union_and_professional_cost += max(member_count * 250_000.0, 80_000_000.0)

    average_member_sale_price = statistics.mean(item.member_sale_price for item in price_table)
    benchmark_new_price = quick_inputs.comparison_new_price or quick_inputs.general_sale_price or average_member_sale_price / 0.85
    member_sale_revenue = member_count * average_member_sale_price
    general_sale_unit_price = quick_inputs.general_sale_price or benchmark_new_price
    general_sale_revenue = general_sale_households * general_sale_unit_price * base_sale_rate
    ancillary_revenue = advanced_inputs.ancillary_revenue or direct_construction_cost * 0.02
    other_disposal_revenue = advanced_inputs.other_disposal_revenue or direct_construction_cost * 0.01

    sales_expense = general_sale_revenue * 0.025
    tenant_count = (quick_inputs.autofill_project.tenant_count if quick_inputs.autofill_project else None) or 0
    housing_relocation_cost = 0.0
    business_loss_cost = 0.0
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        eligible_tenants = max(int(round((tenant_count or member_count * 0.18) * 0.33)), 1)
        housing_relocation_cost = eligible_tenants * 18_000_000.0
        business_loss_cost = eligible_tenants * 6_000_000.0
    settlement_and_litigation_cost = (
        advanced_inputs.liquidation_cost_override
        if advanced_inputs.liquidation_cost_override is not None
        else total_old_asset_value * (0.005 + base_cash_rate * 0.08) + housing_relocation_cost + business_loss_cost
    )
    taxes_public_cost = (
        direct_construction_cost
        + demolition_cost
        + design_and_pm_cost
        + union_and_professional_cost
        + sales_expense
        + settlement_and_litigation_cost
    ) * 0.03
    pf_eligible_cost = (
        direct_construction_cost
        + demolition_cost
        + design_and_pm_cost
        + union_and_professional_cost
        + sales_expense
        + taxes_public_cost
    )
    pf_principal = max(pf_eligible_cost * pf_financing_ratio, 0.0)
    financing_cost = pf_principal * base_pf_rate * (pf_interest_months / 12.0)
    move_loan_interest_cost = member_count * average_move_loan_amount * quick_inputs.move_loan_rate * (move_loan_duration_months / 12.0)
    contingency_cost = (
        direct_construction_cost
        + demolition_cost
        + design_and_pm_cost
        + union_and_professional_cost
        + taxes_public_cost
        + sales_expense
    ) * 0.05

    if parsed_notice and "member_sale_revenue" in quick_inputs.applied_document_fields and "member_sale_revenue" in parsed_notice.revenue_items:
        member_sale_revenue = parsed_notice.revenue_items["member_sale_revenue"]
    if parsed_notice and "general_sale_revenue" in quick_inputs.applied_document_fields and "general_sale_revenue" in parsed_notice.revenue_items:
        general_sale_revenue = parsed_notice.revenue_items["general_sale_revenue"]

    base_bucket_amounts = {
        "main_construction": direct_construction_cost,
        "demolition_and_site": demolition_cost,
        "design_supervision_pm": design_and_pm_cost,
        "union_and_professional": union_and_professional_cost,
        "financing": financing_cost + move_loan_interest_cost,
        "taxes_public": taxes_public_cost,
        "compensation_litigation": settlement_and_litigation_cost,
        "sales_and_disposal": sales_expense,
        "contingency": contingency_cost,
    }
    buckets = build_cost_buckets(base_bucket_amounts, advanced_inputs.cost_bucket_overrides, parsed_notice.document_cost_breakdown if parsed_notice else {})
    total_cost = sum(bucket.amount for bucket in buckets)
    total_revenue = member_sale_revenue + general_sale_revenue + ancillary_revenue + other_disposal_revenue

    if parsed_notice and "total_revenue" in quick_inputs.applied_document_fields and "total_revenue" in parsed_notice.revenue_items:
        total_revenue = parsed_notice.revenue_items["total_revenue"]
    if parsed_notice and "total_cost" in quick_inputs.applied_document_fields and "total_cost" in parsed_notice.cost_items:
        total_cost = parsed_notice.cost_items["total_cost"]

    proportional_ratio = safe_div(total_revenue - total_cost, total_old_asset_value, 0.0) * 100.0
    if parsed_notice and "proportional_ratio" in quick_inputs.applied_document_fields and parsed_notice.proportional_ratio is not None:
        proportional_ratio = parsed_notice.proportional_ratio
    rights_value = old_asset_estimate * (proportional_ratio / 100.0)

    allocations: list[dict[str, float | str]] = []
    low_coverage_allocations: list[dict[str, float | str]] = []
    for item in price_table:
        additional_contribution = item.member_sale_price - rights_value
        cover_ratio = safe_div(rights_value, item.member_sale_price, 0.0)
        size_proximity = 1.0 - min(abs(item.exclusive_area_sqm - quick_inputs.current_unit_exclusive_area) / max(quick_inputs.current_unit_exclusive_area, 1.0), 1.0)
        burden_score = 1.0 - min(max(additional_contribution, 0.0) / max(quick_inputs.purchase_price, 1.0), 1.0)
        score = 0.5 * size_proximity + 0.3 * min(cover_ratio, 1.0) + 0.2 * burden_score
        signal = "가능성 높음" if score >= 0.75 else "보통" if score >= 0.55 else "낮음"
        allocation = {
            "평형": item.label,
            "전용㎡": item.exclusive_area_sqm,
            "공급㎡": item.supply_area_sqm,
            "조합원분양가": item.member_sale_price,
            "예상 추가분담금": additional_contribution,
            "커버율": cover_ratio,
            "점수": score,
            "판정": signal,
        }
        if cover_ratio < 0.35 and not quick_inputs.aggressive_upsize:
            low_coverage_allocations.append(allocation)
            continue
        allocations.append(allocation)
    allocations.sort(key=lambda row: float(row["점수"]), reverse=True)
    if not allocations and low_coverage_allocations:
        low_coverage_allocations.sort(key=lambda row: float(row["점수"]), reverse=True)
        allocations = low_coverage_allocations[:3]
    selected = allocations[0] if allocations else None
    upsize_candidates = sorted(
        [row for row in allocations if float(row["전용㎡"]) > quick_inputs.current_unit_exclusive_area + 0.1],
        key=lambda row: float(row["전용㎡"]),
    )
    upsize_option = upsize_candidates[0] if upsize_candidates else None
    quick_additional_cash = max(average_member_sale_price - rights_value, 0.0)
    selected_additional_cash = max(float(selected["예상 추가분담금"]), 0.0) if selected else quick_additional_cash

    exits: list[dict[str, float | str | None]] = []
    for exit_name in EXIT_SCENARIOS:
        if exit_name == "입주권 단계 매도":
            months = max(remaining_months * 0.65, 6.0)
            realization = 0.80
        elif exit_name == "준공 직후 매도":
            months = remaining_months
            realization = 0.95
        else:
            months = remaining_months + 36.0
            realization = 1.02**3
        years = max(months / 12.0, 0.5)
        gross_exit_value = benchmark_new_price * realization
        acquisition_cost = quick_inputs.purchase_price * advanced_inputs.acquisition_rate
        holding_cost = quick_inputs.purchase_price * advanced_inputs.annual_holding_rate * years
        capital_interest = max(selected_additional_cash, 0.0) * max(base_pf_rate + 0.01, 0.04) * years * 0.45
        disposal_cost = gross_exit_value * advanced_inputs.brokerage_rate
        pretax_profit = gross_exit_value - disposal_cost - (
            quick_inputs.purchase_price
            + acquisition_cost
            + holding_cost
            + max(selected_additional_cash, 0.0)
            + capital_interest
        )
        after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * advanced_inputs.capital_gains_effective_rate
        total_outflow = (
            quick_inputs.purchase_price
            + acquisition_cost
            + holding_cost
            + max(selected_additional_cash, 0.0)
            + capital_interest
        )
        roi = safe_div(after_tax_profit, total_outflow, 0.0)
        net_exit_inflow = gross_exit_value - disposal_cost - max(pretax_profit, 0.0) * advanced_inputs.capital_gains_effective_rate
        irr = (net_exit_inflow / total_outflow) ** (1.0 / years) - 1.0 if total_outflow > 0 and net_exit_inflow > 0 else None
        break_even_purchase = max(
            (gross_exit_value - disposal_cost - holding_cost - max(selected_additional_cash, 0.0) - capital_interest) / max(1.0 + advanced_inputs.acquisition_rate, 0.01),
            0.0,
        )
        exits.append(
            {
                "엑시트": exit_name,
                "예상 시점(년)": years,
                "자산가치": gross_exit_value,
                "세전 순이익": pretax_profit,
                "세후 순이익": after_tax_profit,
                "ROI": roi,
                "IRR": irr,
                "보유비용": holding_cost,
                "시간비용": holding_cost + capital_interest,
                "손익분기 매수가": break_even_purchase,
                "권장 최대 매수가": break_even_purchase * 0.90,
            }
        )

    selected_exit = next(item for item in exits if item["엑시트"] == "준공 직후 매도")
    time_cost_to_exit = float(selected_exit["시간비용"])
    break_even_purchase_price = float(selected_exit["손익분기 매수가"])
    max_bid_price = float(selected_exit["권장 최대 매수가"])
    project_summary = {
        "총수입": total_revenue,
        "총지출": total_cost,
        "추정비례율": proportional_ratio,
        "세대당 평균 추가분담금": max(average_member_sale_price - rights_value, 0.0),
        "예상 총세대수": float(simulation.planned_households),
        "엔진 추정 총세대수": float(simulation.simulated_total_households),
        "일반분양 비율": general_sale_ratio,
        "일반분양 세대수": float(general_sale_households),
        "임대주택 세대수": float(rental_households),
        "기부채납 비율": donation_ratio,
        "임대주택 비율": rental_ratio,
        "본공사비": next(bucket.amount for bucket in buckets if bucket.key == "main_construction"),
        "금융비": next(bucket.amount for bucket in buckets if bucket.key == "financing"),
    }

    input_completion = (
        sum(
            [
                bool(quick_inputs.current_households),
                quick_inputs.current_far is not None,
                quick_inputs.target_far is not None,
                quick_inputs.target_building_coverage_ratio is not None,
                bool(quick_inputs.general_sale_price or quick_inputs.comparison_new_price),
                simulation.site_area_sqm is not None,
            ]
        )
        / 6.0
    ) * 100.0
    autofill_strength = 92.0 if quick_inputs.lookup_enabled and quick_inputs.autofill_project else 58.0
    schedule_certainty = 85.0 if duration_source == "schedule_board" else clamp(100.0 - STAGE_BASE_MONTHS.get(quick_inputs.current_stage, 72) * 0.45, 22.0, 88.0)
    valuation_strength = statistics.mean(
        [
            0.96 if old_asset_source == "manual_appraisal" else 0.82 if old_asset_source == "public_price_adjusted" else 0.68 if old_asset_source == "trade_backsolve" else 0.48,
            0.90 if simulation.sources["households"] == "official_cleanup" else 0.75 if simulation.sources["households"] == "manual_override" else 0.60,
            0.84 if adj_source == "document_formula" else 0.78 if adj_source == "trade_vs_public" else 0.58,
        ]
    ) * 100.0
    confidence_total = input_completion * 0.35 + autofill_strength * 0.20 + schedule_certainty * 0.20 + valuation_strength * 0.25
    confidence_label = "높음" if confidence_total >= 80 else "보통" if confidence_total >= 60 else "낮음"
    confidence_report = ConfidenceReport(
        input_completion=input_completion,
        autofill_strength=autofill_strength,
        schedule_certainty=schedule_certainty,
        valuation_strength=valuation_strength,
        total=confidence_total,
        label=confidence_label,
    )

    sensitivity_rows: list[dict[str, str]] = []
    for sale_rate in (0.92, 0.95, 0.97, 1.00):
        for cost_multiplier in (0.95, 1.00, 1.05, 1.10):
            variant_sale_revenue = general_sale_households * general_sale_unit_price * sale_rate
            variant_total_revenue = member_sale_revenue + variant_sale_revenue + ancillary_revenue + other_disposal_revenue
            variant_total_cost = total_cost - direct_construction_cost + direct_construction_cost * cost_multiplier
            variant_ratio = safe_div(variant_total_revenue - variant_total_cost, total_old_asset_value, 0.0) * 100.0
            sensitivity_rows.append({"판매율": f"{sale_rate * 100:.0f}%", "공사비 배수": f"{cost_multiplier:.2f}x", "비례율": f"{variant_ratio:.2f}%"})

    land_share_est = safe_div(simulation.site_area_sqm or 0.0, quick_inputs.current_households, 0.0) if simulation.site_area_sqm else 0.0
    top_drivers = simple_top_drivers(time_cost_to_exit, direct_construction_cost, selected_additional_cash)
    cost_note = "재개발 세입자 보상비를 포함했습니다." if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT else "재건축은 주거이전비·영업손실보상비를 기본 제외했습니다."
    if selected:
        first_line = f"현재 입력 기준 추천 평형은 {selected['평형']}이고 예상 추가분담금은 {fmt_money(selected_additional_cash)}입니다."
    else:
        first_line = f"현재 입력 기준 세대당 평균 추가분담금은 {fmt_money(quick_additional_cash)}입니다."
    if upsize_option is not None:
        upsize_delta = float(upsize_option["전용㎡"]) - quick_inputs.current_unit_exclusive_area
        second_line = f"한 단계 넓힌 {upsize_option['평형']} 기준 추가분담금은 {fmt_money(max(float(upsize_option['예상 추가분담금']), 0.0))}로, 현재보다 전용 {upsize_delta:.1f}㎡ 넓어지는 가정입니다."
    else:
        second_line = f"준공 직후 매도 기준 세후순이익은 {fmt_money(float(selected_exit['세후 순이익']))}입니다. ROI는 {fmt_pct(float(selected_exit['ROI']))}로 참고만 보세요."
    summary_lines = [
        first_line,
        second_line,
        f"예상 총세대수는 {simulation.planned_households:,}세대, 일반분양은 {general_sale_households:,}세대({fmt_pct(general_sale_ratio)})로 계산했습니다.",
        f"손익분기 매수가는 {fmt_money(break_even_purchase_price)}, 권장 최대 매수가는 {fmt_money(max_bid_price)}입니다.",
        f"대지지분은 세대당 약 {land_share_est:,.2f}㎡로 추정했고 출처는 {humanize_source(simulation.site_source)}입니다. {cost_note}",
        f"금융비는 PF 조달비율 {fmt_pct(pf_financing_ratio)}, PF 이자 {pf_interest_months:.0f}개월, 세대당 평균 이주비 {fmt_money(average_move_loan_amount)}, 이주비 대여 {move_loan_duration_months:.0f}개월 가정입니다.",
        f"가장 영향이 큰 요인은 {', '.join(top_drivers)}입니다.",
    ]

    records.extend(
        [
            record("old_asset_estimate", f"{old_asset_estimate:,.0f}", old_asset_source, 0.78),
            record("total_old_asset_value", f"{total_old_asset_value:,.0f}", total_old_asset_source, 0.68),
            record("adjustment_factor", f"{adj_factor:.3f}", adj_source, 0.70),
            record("remaining_months", f"{remaining_months:.1f}", duration_source, 0.66),
            record("total_revenue", f"{total_revenue:,.0f}", "engine", 0.70),
            record("total_cost", f"{total_cost:,.0f}", "engine", 0.70),
            record("proportional_ratio", f"{proportional_ratio:.2f}", "engine", 0.70),
            record("planned_households", str(simulation.planned_households), simulation.sources["households"], 0.70),
            record("general_sale_ratio", f"{general_sale_ratio * 100:.2f}%", simulation.sources["general_sale_ratio"], 0.68),
            record("pf_financing_ratio", f"{pf_financing_ratio * 100:.1f}%", "manual", 0.64),
            record("pf_interest_months", f"{pf_interest_months:.1f}", "manual", 0.64),
            record("avg_move_loan_amount", f"{average_move_loan_amount:,.0f}", "manual", 0.64),
            record("move_loan_duration_months", f"{move_loan_duration_months:.1f}", "manual", 0.64),
        ]
    )

    return QuickResult(
        scenario_name=scenario_name,
        remaining_months=remaining_months,
        current_unit_exclusive_area=quick_inputs.current_unit_exclusive_area,
        additional_cash_needed=selected_additional_cash,
        time_cost_to_exit=time_cost_to_exit,
        selected_exit_name="준공 직후 매도",
        selected_exit=selected_exit,
        project_summary=project_summary,
        exits=exits,
        cost_buckets=buckets,
        confidence_report=confidence_report,
        assumption_summary={
            "sale_rate": base_sale_rate,
            "cash_settlement_rate": base_cash_rate,
            "donation_ratio": donation_ratio,
            "rental_ratio": rental_ratio,
            "general_sale_ratio": general_sale_ratio,
            "construction_cost_per_pyeong": base_cost_per_pyeong,
            "pf_rate": base_pf_rate,
            "pf_financing_ratio": pf_financing_ratio,
            "pf_interest_months": pf_interest_months,
            "average_move_loan_amount": average_move_loan_amount,
            "move_loan_duration_months": move_loan_duration_months,
        },
        summary_lines=summary_lines,
        source_records=records,
        sensitivity_rows=sensitivity_rows,
        simulation_result=simulation,
        feasibility_checks=build_feasibility_checks(quick_inputs, simulation),
        max_bid_price=max_bid_price,
        break_even_purchase_price=break_even_purchase_price,
        selected_allocation=selected,
        upsize_allocation=upsize_option,
        advanced_rights_result=(
            AdvancedRightsResult(
                old_asset_estimate=old_asset_estimate,
                total_old_asset_value=total_old_asset_value,
                rights_value=rights_value,
                old_asset_source=old_asset_source,
                total_old_asset_source=total_old_asset_source,
                adjustment_factor=adj_factor,
                floor_factor=floor_adj,
                price_table=price_table,
                allocation_options=allocations,
            )
            if show_advanced_detail
            else None
        ),
        old_asset_estimate=old_asset_estimate if show_advanced_detail else None,
        total_old_asset_value=total_old_asset_value if show_advanced_detail else None,
        rights_value=rights_value if show_advanced_detail else None,
        old_asset_source=old_asset_source if show_advanced_detail else None,
        total_old_asset_source=total_old_asset_source if show_advanced_detail else None,
        adjustment_factor=adj_factor if show_advanced_detail else None,
        floor_factor=floor_adj if show_advanced_detail else None,
        price_table=price_table if show_advanced_detail else [],
        allocation_options=allocations,
    )


def source_badge(text: str, tone: str = "base") -> str:
    color_map = {"base": "#274754", "ok": "#2f6a42", "warn": "#845421"}
    background_map = {"base": "#e6f2f5", "ok": "#e7f4ea", "warn": "#fff1df"}
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;"
        f"font-weight:700;margin-right:6px;background:{background_map[tone]};color:{color_map[tone]};'>{escape(text)}</span>"
    )


def inject_styles() -> None:
    if st is None:
        return
    st.markdown(
        """
        <style>
        :root {
            --ink: #18323b;
            --muted: #5d737a;
            --line: #d7e3e1;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(225, 239, 235, 0.55), transparent 30%),
                linear-gradient(180deg, #f9fbfa 0%, #f4f8f7 100%);
        }
        .hero-card, .section-card {
            border: 1px solid var(--line);
            border-radius: 22px;
            background: rgba(255,255,255,0.92);
            box-shadow: 0 10px 26px rgba(24,50,59,0.06);
            padding: 20px 22px;
        }
        .hero-card h1 {
            margin: 0 0 6px 0;
            color: var(--ink);
            font-size: 30px;
            line-height: 1.15;
        }
        .hero-card p, .mini-note {
            margin: 0;
            color: var(--muted);
            font-size: 14px;
        }
        .soft-title {
            color: var(--ink);
            font-weight: 700;
            margin-bottom: 6px;
        }
        .result-blurb {
            background: linear-gradient(135deg, #f3faf7 0%, #f8fbff 100%);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 14px 16px;
            margin: 10px 0;
        }
        table.codex-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        table.codex-table th {
            text-align: left;
            background: #eff5f3;
            color: var(--ink);
            padding: 10px 12px;
            border-bottom: 1px solid var(--line);
        }
        table.codex-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #edf1ef;
            color: #24424b;
            vertical-align: top;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_table(rows: list[dict[str, object]], title: str | None = None) -> None:
    if st is None:
        return
    if not rows:
        st.info("표시할 데이터가 없습니다.")
        return
    headers = list(rows[0].keys())
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(header, '')))}</td>" for header in headers)
        body.append(f"<tr>{cells}</tr>")
    st.markdown(
        "<div class='section-card'>"
        + (f"<div class='soft-title'>{escape(title)}</div>" if title else "")
        + "<table class='codex-table'><thead><tr>"
        + "".join(f"<th>{escape(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_source_records(records: list[SourceRecord], title: str) -> None:
    rows = [
        {
            "항목": humanize_key(item.key),
            "값": humanize_value(item.value),
            "출처": humanize_source(item.source),
            "신뢰도": f"{item.confidence * 100:.1f}%",
            "비고": item.notes,
        }
        for item in records
    ]
    render_table(rows, title)


def render_project_autofill(project: AutofillProjectData | None) -> None:
    if st is None or not project:
        return
    st.markdown(
        "<div class='section-card'>"
        f"<div class='soft-title'>{escape(project.project_name)}</div>"
        f"<div>{source_badge('서울 공식값 사용', 'ok')}{source_badge(project.business_type or '사업유형 미확인')}{source_badge((project.project_kind.value if project.project_kind else '유형 미확인'), 'base')}</div>"
        f"<p class='mini-note'>대표지번: {escape(project.representative_lot or '-')} / 조합원·권리자 수: {project.current_households or project.owner_count or '-'} / 계획 세대수: {project.planned_households or '-'}</p>"
        f"<p class='mini-note'>목표 건폐율: {project.target_building_coverage_ratio or '-'}% / 목표 용적률: {project.target_far or '-'}% / 일반분양: {project.sale_households or '-'}세대 / 임대: {project.rental_households or '-'}세대</p>"
        f"<p class='mini-note'>공공시설 반영면적: {project.public_facility_area_sqm or '-'}㎡ / 명시 기부채납: {project.donation_area_sqm or '-'}㎡ / 출처: 서울 정비사업 정보몽땅</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def project_summary_rows(result: QuickResult) -> list[dict[str, str]]:
    return [
        {"항목": "총수입", "값": fmt_money(result.project_summary["총수입"])},
        {"항목": "총지출", "값": fmt_money(result.project_summary["총지출"])},
        {"항목": "추정비례율", "값": fmt_plain_pct(result.project_summary["추정비례율"])},
        {"항목": "세대당 평균 추가분담금", "값": fmt_money(result.project_summary["세대당 평균 추가분담금"])},
        {"항목": "예상 총세대수", "값": f"{int(result.project_summary['예상 총세대수']):,}세대"},
        {"항목": "엔진 추정 총세대수", "값": f"{int(result.project_summary['엔진 추정 총세대수']):,}세대"},
        {"항목": "일반분양 비율", "값": fmt_pct(result.project_summary["일반분양 비율"])},
        {"항목": "일반분양 세대수", "값": f"{int(result.project_summary['일반분양 세대수']):,}세대"},
        {"항목": "임대주택 세대수", "값": f"{int(result.project_summary['임대주택 세대수']):,}세대"},
        {"항목": "기부채납 비율", "값": fmt_pct(result.project_summary["기부채납 비율"])},
        {"항목": "임대주택 비율", "값": fmt_pct(result.project_summary["임대주택 비율"])},
    ]


def exit_rows(result: QuickResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in result.exits:
        rows.append(
            {
                "엑시트": str(item["엑시트"]),
                "예상 시점": f"{float(item['예상 시점(년)']):.2f}년",
                "세후 순이익": fmt_money(float(item["세후 순이익"])),
                "ROI": fmt_pct(float(item["ROI"])),
                "IRR": "-" if item["IRR"] is None else fmt_pct(float(item["IRR"])),
                "시간비용": fmt_money(float(item["시간비용"])),
                "손익분기 매수가": fmt_money(float(item["손익분기 매수가"])),
            }
        )
    return rows


def allocation_rows(result: QuickResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in result.allocation_options[:5]:
        area_delta = float(row["전용㎡"]) - result.current_unit_exclusive_area
        rows.append(
            {
                "평형": str(row["평형"]),
                "전용㎡": f"{float(row['전용㎡']):,.1f}",
                "현재 대비": "동급" if abs(area_delta) < 0.1 else f"{area_delta:+.1f}㎡",
                "예상 추가분담금": fmt_money(float(row["예상 추가분담금"])),
                "커버율": fmt_pct(float(row["커버율"])),
                "판정": str(row["판정"]),
            }
        )
    return rows


def bucket_rows(result: QuickResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for bucket in result.cost_buckets:
        rows.append({"비용 버킷": bucket.label, "금액": fmt_money(bucket.amount), "출처": humanize_source(bucket.source), "설명": bucket.description})
    return rows


def simulation_rows(result: QuickResult) -> list[dict[str, str]]:
    simulation = result.simulation_result
    rows = [
        {"항목": "예상 총세대수", "값": f"{simulation.planned_households:,}세대", "출처": humanize_source(simulation.sources["households"])},
        {"항목": "엔진 추정 총세대수", "값": f"{simulation.simulated_total_households:,}세대", "출처": humanize_source("simulation")},
        {"항목": "일반분양 세대수", "값": f"{simulation.general_sale_households:,}세대", "출처": humanize_source(simulation.sources["general_sale_ratio"])},
        {"항목": "일반분양 비율", "값": fmt_pct(simulation.general_sale_ratio), "출처": humanize_source(simulation.sources["general_sale_ratio"])},
        {"항목": "임대주택 세대수", "값": f"{simulation.rental_households:,}세대", "출처": humanize_source(simulation.sources["rental_ratio"])},
        {"항목": "기부채납 비율", "값": fmt_pct(simulation.donation_ratio), "출처": humanize_source(simulation.sources["donation_ratio"])},
        {"항목": "대지면적", "값": f"{simulation.site_area_sqm:,.1f}㎡" if simulation.site_area_sqm is not None else "-", "출처": humanize_source(simulation.site_source)},
    ]
    if simulation.required_avg_floors is not None:
        rows.append({"항목": "필요 평균층수", "값": f"{simulation.required_avg_floors:.1f}층", "출처": humanize_source("simulation")})
    return rows


def feasibility_rows(result: QuickResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    tone_map = {"ok": "정상", "warn": "주의", "risk": "경고", "note": "참고"}
    for item in result.feasibility_checks:
        rows.append({"상태": tone_map.get(item.level, item.level), "점검항목": item.title, "설명": item.message})
    return rows


def scenario_overview_rows(results: list[QuickResult]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for result in results:
        upsize_text = "-"
        if result.upsize_allocation is not None:
            upsize_text = fmt_money(max(float(result.upsize_allocation["예상 추가분담금"]), 0.0))
        rows.append(
            {
                "시나리오": result.scenario_name,
                "추천 평형 추가분담금": fmt_money(result.additional_cash_needed),
                "한 단계 확장": upsize_text,
                "손익분기 매수가": fmt_money(result.break_even_purchase_price),
                "일반분양 세대수": f"{result.simulation_result.general_sale_households:,}세대",
                "신뢰도": f"{result.confidence_report.label} ({result.confidence_report.total:.1f}점)",
            }
        )
    return rows


def summarize_document_state(parsed_notice: ParsedProjectNotice | None) -> list[str]:
    if not parsed_notice:
        return []
    messages = []
    if parsed_notice.document_stage:
        messages.append(f"문서 단계 인식: {parsed_notice.document_stage}")
    if parsed_notice.document_schedule:
        messages.append(f"문서 일정 인식: {parsed_notice.document_schedule}")
    if parsed_notice.member_price_table:
        messages.append(f"문서 분양가표 {len(parsed_notice.member_price_table)}건 인식")
    issues = [item for item in parsed_notice.extracted_records if item.key == "parser_status"]
    for issue in issues[:2]:
        messages.append(f"{humanize_source(issue.source)} - {humanize_value(issue.value)}")
    return messages


def render_result_summary(result: QuickResult) -> None:
    if st is None:
        return
    recommended_label = "대표 평형 추정"
    recommended_sub = f"예상 {result.remaining_months / 12:.1f}년"
    if result.selected_allocation is not None:
        recommended_label = str(result.selected_allocation["평형"])
        recommended_sub = f"커버율 {fmt_pct(float(result.selected_allocation['커버율']))}"
    upsize_value = "-"
    upsize_sub = "확장 평형 없음"
    if result.upsize_allocation is not None:
        upsize_value = fmt_money(max(float(result.upsize_allocation["예상 추가분담금"]), 0.0))
        area_delta = float(result.upsize_allocation["전용㎡"]) - result.current_unit_exclusive_area
        upsize_sub = f"{result.upsize_allocation['평형']} / +{area_delta:.1f}㎡"
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("추천 평형 추가분담금", fmt_money(result.additional_cash_needed), f"{recommended_label} / {recommended_sub}")
    c2.metric("한 단계 넓히면", upsize_value, upsize_sub)
    c3.metric("손익분기 매수가", fmt_money(result.break_even_purchase_price), "세후 0원 기준")
    c4.metric("예상 시간비용", fmt_money(result.time_cost_to_exit), "보유비용 + 자금이자")
    c5.metric("준공 직후 세후순이익", fmt_money(float(result.selected_exit["세후 순이익"])), "ROI는 하단 시나리오 표 참고")
    c6.metric("신뢰도", result.confidence_report.label, f"{result.confidence_report.total:.1f}점")
    for line in result.summary_lines:
        st.markdown(f"<div class='result-blurb'>{escape(line)}</div>", unsafe_allow_html=True)


def render_input_guide(project_kind: ProjectKind) -> None:
    if st is None:
        return
    kind_text = (
        "재개발은 현재 아파트 평형보다 대지지분, 권리자 수, 목표 용적률이 더 중요합니다. 세입자·보상비도 보수적으로 자동 반영합니다."
        if project_kind == ProjectKind.REDEVELOPMENT
        else "재건축은 주거이전비·영업손실보상비를 기본 제외하고 안전진단 비용만 조기 단계에 반영합니다."
    )
    st.markdown(
        "<div class='section-card'>"
        "<div class='soft-title'>입력 가이드</div>"
        "<p class='mini-note'>이 계산기는 ROI보다 평형별 추가분담금과 손익분기 매수가를 먼저 보여주도록 설계했습니다. ROI는 하단 시나리오 표에서 보조지표로만 확인하세요.</p>"
        "<p class='mini-note'>일반분양 평균가는 준공 또는 분양 시점 기준의 예상 일반분양 평균가입니다. 현재 주변 실거래가와 같은 의미가 아닙니다.</p>"
        "<p class='mini-note'>목표 용적률과 목표 건폐율을 같이 넣으면 총세대수와 평균층수를 자동 점검합니다. 목표 건폐율이 없으면 세대수 과다 경고는 약해집니다.</p>"
        "<p class='mini-note'>기부채납 비율은 도로·공원·공공시설로 빠지는 면적을 묶어 반영한 간편값이며, 공식 토지이용계획이 있으면 그 값이 우선합니다.</p>"
        "<p class='mini-note'>임대주택 비율은 공식 주택공급계획이 있으면 그 값이 우선하고, 없으면 사업유형과 프리셋으로 자동 추정합니다.</p>"
        f"<p class='mini-note'>{escape(kind_text)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def default_unit_mix_text(current_exclusive_area: float, current_supply_area: float, current_households: int) -> str:
    return f"기존대표형,{current_households},{current_exclusive_area:.1f},{current_supply_area:.1f}"


def main() -> None:
    if st is None:
        print("streamlit이 설치되지 않았습니다. `pip install streamlit` 후 `streamlit run app.py`로 실행해 주세요.")
        return
    inject_styles()
    st.set_page_config(page_title="재건축/재개발 매물 즉시 수익성 계산기", layout="wide")
    st.markdown(
        """
        <div class="hero-card">
            <h1>재건축/재개발 매물 즉시 수익성 계산기</h1>
            <p>매물 검토에 필요한 핵심 수치만 먼저 넣고, 총세대수·일반분양·임대·기부채납은 자동 추정한 뒤 정밀 계산은 관리처분 이후에만 더 열어보는 구조로 구성했습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("계산 모드")
        calc_mode = st.radio("작업 방식", ["빠른 검토", "정밀 계산"], horizontal=False)
        scenario_focus = st.selectbox("화면 기준 시나리오", list(SCENARIOS.keys()), index=1)
        assumption_profile = st.select_slider("초보자 가정 프리셋", options=list(ASSUMPTION_PROFILES.keys()), value="기준")
        st.caption("기부채납, 임대비율, 일반분양비율을 잘 모르면 `기준`으로 두고 먼저 본 뒤 필요할 때만 수정하세요.")
        lookup_enabled = st.checkbox("서울 공식값 자동조회 사용", value=True)
        aggressive_upsize = st.checkbox("공격적 평형 업사이즈 허용", value=False)
        uploaded_files = st.file_uploader("문서 업로드", type=["pdf", "csv"], accept_multiple_files=True)

    parsed_notices: list[ParsedProjectNotice] = []
    if uploaded_files:
        for file in uploaded_files:
            parsed_notices.append(try_parse_uploaded_notice(file.name, file.getvalue()))
    merged_notice = merge_notices(parsed_notices)

    autofill_project: AutofillProjectData | None = None
    if lookup_enabled:
        with st.expander("서울 공식값 자동조회", expanded=True):
            st.caption("서울 정비사업 정보몽땅에서 사업장명으로 조회합니다. 주소는 안 넣어도 됩니다.")
            search_query = st.text_input("서울 사업장명 검색", value="")
            search_results = cleanup_search_projects(search_query) if search_query.strip() else []
            if search_query and not search_results:
                st.warning("일치하는 서울 사업장을 찾지 못했습니다. 아래 수동 입력으로 계속 진행할 수 있습니다.")
            if search_results:
                labels = [f"{item.project_name} / {item.district} / {item.progress_stage or '단계 미확인'}" for item in search_results]
                selected_label = st.selectbox("검색 결과", labels)
                selected_project = search_results[labels.index(selected_label)]
                fetched = cleanup_fetch_project_summary(selected_project.project_slug)
                if fetched:
                    fetched.progress_stage = selected_project.progress_stage
                    fetched.project_name = selected_project.project_name or fetched.project_name
                    fetched.district = selected_project.district or fetched.district
                    fetched.representative_lot = selected_project.representative_lot or fetched.representative_lot
                    autofill_project = fetched
                    render_project_autofill(autofill_project)

    extracted_options = []
    if merged_notice:
        extracted_options = sorted({item.key for item in merged_notice.extracted_records if item.key not in {"member_price_table_count", "parser_status", "document_stage", "document_schedule"}})
        st.markdown(f"{source_badge('문서 인식됨', 'ok')} {escape(merged_notice.source_name)}", unsafe_allow_html=True)
        for message in summarize_document_state(merged_notice):
            st.caption(message)

    default_stage = normalize_stage_name(autofill_project.progress_stage) if autofill_project and normalize_stage_name(autofill_project.progress_stage) else "조합설립인가"

    default_project_kind = autofill_project.project_kind if autofill_project and autofill_project.project_kind else ProjectKind.RECONSTRUCTION
    st.subheader("1. 빠른 입력")
    project_kind_value = st.radio(
        "사업유형",
        [ProjectKind.RECONSTRUCTION.value, ProjectKind.REDEVELOPMENT.value],
        index=0 if default_project_kind == ProjectKind.RECONSTRUCTION else 1,
        horizontal=True,
        help=FIELD_HELP["project_kind"],
    )
    project_kind = ProjectKind(project_kind_value)
    render_input_guide(project_kind)
    redevelopment_base_exclusive_area = 59.0
    redevelopment_base_supply_area = 75.6
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        purchase_price_eok = st.number_input("매수가(억)", min_value=0.0, value=35.0, step=0.1, help=FIELD_HELP["purchase_price"])
        current_stage = st.selectbox("현재 사업단계", list(STAGE_BASE_MONTHS.keys()), index=list(STAGE_BASE_MONTHS.keys()).index(default_stage), help=FIELD_HELP["current_stage"])
    with c2:
        if project_kind == ProjectKind.REDEVELOPMENT:
            current_unit_exclusive_area = st.number_input(
                "기준 분양 전용(재개발 자동값)",
                min_value=20.0,
                value=redevelopment_base_exclusive_area,
                step=1.0,
                disabled=True,
                help="재개발은 현재 아파트 평형 대신 59㎡ 기본 비교 평형을 내부 계산 기준으로 씁니다.",
            )
            current_unit_supply_area = st.number_input(
                "기준 분양 공급(재개발 자동값)",
                min_value=20.0,
                value=redevelopment_base_supply_area,
                step=1.0,
                disabled=True,
                help="재개발은 현재 공급면적 대신 기본 비교 평형의 공급면적을 임시 기준으로 사용합니다.",
            )
            st.caption("재개발은 이 칸보다 대지지분과 권리자 수 입력이 훨씬 중요합니다.")
        else:
            current_unit_exclusive_area = st.number_input("현재 전용면적(㎡)", min_value=20.0, value=84.0, step=1.0)
            current_unit_supply_area = st.number_input("현재 공급면적(㎡)", min_value=20.0, value=107.7, step=1.0)
    with c3:
        comparison_new_price_eok = st.number_input("비교 신축 시세(억)", min_value=0.0, value=48.0, step=0.1, help=FIELD_HELP["comparison_new_price"])
        general_sale_price_eok = st.number_input("일반분양 평균가(억)", min_value=0.0, value=14.0, step=0.1, help=FIELD_HELP["general_sale_price"])
    with c4:
        default_households = (
            autofill_project.owner_count
            if project_kind == ProjectKind.REDEVELOPMENT and autofill_project and autofill_project.owner_count
            else autofill_project.current_households
            if autofill_project and autofill_project.current_households
            else 480
        )
        current_households_label = "권리자/조합원 수" if project_kind == ProjectKind.REDEVELOPMENT else "기존 세대수"
        current_households = st.number_input(current_households_label, min_value=1, value=int(default_households), step=1, help=FIELD_HELP["current_households"])
        construction_cost_per_pyeong_man = st.number_input("공사비(만원/평)", min_value=0.0, value=900.0, step=10.0, help=FIELD_HELP["construction_cost"])
    st.caption("빠른 검토는 이 블록과 아래 사업 기본값만 채워도 바로 결과가 나옵니다.")

    with st.expander("2. 사업 기본값과 자동 추정", expanded=True):
        st.caption("서울 공식값이 있으면 우선 사용하고, 없으면 입력값과 시뮬레이션으로 보완합니다.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            current_far = st.number_input("현황 용적률(%)", min_value=0.0, value=180.0, step=1.0, help=FIELD_HELP["current_far"])
            land_share_label = "내 대지지분(㎡)" if project_kind == ProjectKind.REDEVELOPMENT else "대지지분(㎡)"
            land_share = st.number_input(land_share_label, min_value=0.0, value=0.0, step=0.1, help=FIELD_HELP["land_share"])
        with c2:
            target_far = st.number_input("목표 용적률(%)", min_value=0.0, value=float(autofill_project.target_far or 260.0) if autofill_project else 260.0, step=1.0, help=FIELD_HELP["target_far"])
            target_building_coverage_ratio_pct = st.number_input("목표 건폐율(%)", min_value=0.0, value=float(autofill_project.target_building_coverage_ratio or 0.0) if autofill_project else 0.0, step=1.0, help=FIELD_HELP["target_bcr"])
        with c3:
            current_building_coverage_ratio_pct = st.number_input("현황 건폐율(%)", min_value=0.0, value=0.0, step=1.0, help=FIELD_HELP["current_bcr"])
            average_current_floors = st.number_input("기존 평균 층수", min_value=0.0, value=0.0, step=1.0, help=FIELD_HELP["avg_current_floors"])
        with c4:
            st.markdown(
                f"{source_badge('대지지분을 모르면 비워두세요', 'warn')}{source_badge('서울 공식값이 있으면 우선 사용', 'ok')}{source_badge('없으면 용적률·건폐율로 자동추정', 'base')}",
                unsafe_allow_html=True,
            )
        if project_kind == ProjectKind.REDEVELOPMENT:
            st.caption("재개발은 대지지분과 권리자 수 입력 정확도가 특히 중요합니다. 둘 중 하나라도 비어 있으면 총세대수와 추가분담 추정 오차가 커집니다.")

    with st.expander("3. 자동 제안값 조정과 금융 가정", expanded=False):
        preview_profile = ASSUMPTION_PROFILES[assumption_profile]
        st.caption("총세대수, 일반분양비율, 기부채납, 임대비율은 먼저 자동 제안값으로 보여주고, 필요할 때만 직접 덮어쓸 수 있게 했습니다.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sale_rate_pct = st.number_input("일반분양 판매율(%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0, help=FIELD_HELP["sale_rate"])
            cash_settlement_rate_pct = st.number_input("현금청산률(%)", min_value=0.0, max_value=100.0, value=3.0, step=1.0, help=FIELD_HELP["cash_settlement_rate"])
        with c2:
            pf_rate_pct = st.number_input("PF 금리(%)", min_value=0.0, max_value=30.0, value=8.5, step=0.1, help=FIELD_HELP["pf_rate"])
            move_loan_rate_pct = st.number_input("이주비 금리(%)", min_value=0.0, max_value=20.0, value=5.0, step=0.1, help=FIELD_HELP["move_loan_rate"])
        with c3:
            delay_one_year = st.checkbox("일정 1년 지연 반영", value=False)
            capital_area = st.checkbox("수도권 프로젝트", value=True)
        with c4:
            st.markdown(
                f"{source_badge('자동 제안값 먼저 확인', 'ok')}{source_badge('분양계획이 있으면 직접 수정', 'base')}{source_badge('금융 가정도 아래에서 조정', 'warn')}",
                unsafe_allow_html=True,
            )

        preview_quick_inputs = QuickDealInputs(
            project_kind=project_kind,
            scenario_profile=assumption_profile,
            current_stage=current_stage,
            purchase_price=won_from_eok(purchase_price_eok),
            current_unit_exclusive_area=redevelopment_base_exclusive_area if project_kind == ProjectKind.REDEVELOPMENT else current_unit_exclusive_area,
            current_unit_supply_area=redevelopment_base_supply_area if project_kind == ProjectKind.REDEVELOPMENT else current_unit_supply_area,
            comparison_new_price=won_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
            general_sale_price=won_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
            current_households=int(current_households),
            current_far=current_far or None,
            target_far=target_far or None,
            land_share=land_share or None,
            site_area_sqm=autofill_project.site_area_sqm if autofill_project else None,
            current_building_coverage_ratio=(current_building_coverage_ratio_pct / 100.0) if current_building_coverage_ratio_pct else None,
            target_building_coverage_ratio=(target_building_coverage_ratio_pct / 100.0) if target_building_coverage_ratio_pct else None,
            average_current_floors=average_current_floors or None,
            floor_no=10,
            official_price_reference=None,
            recent_same_complex_trade_price=None,
            sale_rate=sale_rate_pct / 100.0,
            cash_settlement_rate=cash_settlement_rate_pct / 100.0,
            construction_cost_per_pyeong=construction_cost_per_pyeong_man * 10_000,
            pf_rate=pf_rate_pct / 100.0,
            move_loan_rate=move_loan_rate_pct / 100.0,
            target_households_override=None,
            general_sale_ratio_override=None,
            donation_ratio_override=None,
            rental_ratio_override=None,
            delay_one_year=delay_one_year,
            aggressive_upsize=aggressive_upsize,
            capital_area=capital_area,
            autofill_project=autofill_project,
            parsed_notice=merged_notice,
            applied_document_fields=set(),
            use_doc_price_table=False,
            lookup_enabled=bool(autofill_project),
        )
        preview_advanced_inputs = AdvancedProjectInputs(
            rights_inputs=RightsInputs(
                expected_new_exclusive_area=None,
                appraised_old_asset_value=None,
                total_old_asset_value=None,
                official_price_reference=None,
                adjustment_factor_override=None,
                member_price_text="",
            ),
            unit_mix_rows=[],
            pf_financing_ratio=default_pf_financing_ratio(project_kind),
            pf_interest_months=0.0,
            average_move_loan_amount=0.0,
            move_loan_duration_months=0.0,
            acquisition_rate=0.015,
            annual_holding_rate=0.003,
            capital_gains_effective_rate=0.20,
            brokerage_rate=0.004,
            ancillary_revenue=0.0,
            other_disposal_revenue=0.0,
            liquidation_cost_override=None,
            cost_bucket_overrides={},
        )
        preview_remaining_months, _ = estimate_remaining_months(
            stage=current_stage,
            autofill=autofill_project,
            delay_one_year=delay_one_year,
            profile_name=assumption_profile,
            scenario_name=scenario_focus,
        )
        preview_simulation = simulate_project_plan(
            preview_quick_inputs,
            preview_advanced_inputs,
            preview_quick_inputs.cash_settlement_rate or 0.0,
            preview_profile,
        )

        st.markdown("#### 자동 제안값")
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("총세대수", f"{preview_simulation.planned_households:,}세대", humanize_source(preview_simulation.sources["households"]))
        p2.metric("일반분양", f"{preview_simulation.general_sale_households:,}세대", fmt_pct(preview_simulation.general_sale_ratio))
        p3.metric("기부채납", fmt_pct(preview_simulation.donation_ratio), humanize_source(preview_simulation.sources["donation_ratio"]))
        p4.metric("임대주택", f"{preview_simulation.rental_households:,}세대", fmt_pct(preview_simulation.rental_ratio))
        if preview_simulation.required_avg_floors is not None:
            p5.metric("필요 평균층수", f"{preview_simulation.required_avg_floors:.1f}층", f"남은 {preview_remaining_months / 12:.1f}년")
        else:
            p5.metric("필요 평균층수", "-", f"남은 {preview_remaining_months / 12:.1f}년")

        st.markdown("#### 자동값 직접 수정")
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            use_target_households_override = st.checkbox("총세대수 직접수정", value=False, key="use_target_households_override")
            target_households_override_value = st.number_input(
                "직접 입력 총세대수",
                min_value=1,
                value=max(preview_simulation.planned_households, 1),
                step=1,
                disabled=not use_target_households_override,
                help=FIELD_HELP["target_households_override"],
                key="target_households_override_value",
            )
        with o2:
            use_general_sale_ratio_override = st.checkbox("일반분양 비율 직접수정", value=False, key="use_general_sale_ratio_override")
            general_sale_ratio_override_pct = st.number_input(
                "직접 입력 일반분양 비율(%)",
                min_value=0.0,
                max_value=100.0,
                value=round(clamp(preview_simulation.general_sale_ratio * 100.0, 0.0, 100.0), 1),
                step=1.0,
                disabled=not use_general_sale_ratio_override,
                help=FIELD_HELP["general_sale_ratio_override"],
                key="general_sale_ratio_override_pct",
            )
        with o3:
            use_donation_ratio_override = st.checkbox("기부채납 비율 직접수정", value=False, key="use_donation_ratio_override")
            donation_ratio_override_pct = st.number_input(
                "직접 입력 기부채납 비율(%)",
                min_value=0.0,
                max_value=40.0,
                value=round(preview_simulation.donation_ratio * 100.0, 1),
                step=1.0,
                disabled=not use_donation_ratio_override,
                help=FIELD_HELP["donation_ratio_override"],
                key="donation_ratio_override_pct",
            )
        with o4:
            use_rental_ratio_override = st.checkbox("임대주택 비율 직접수정", value=False, key="use_rental_ratio_override")
            rental_ratio_override_pct = st.number_input(
                "직접 입력 임대주택 비율(%)",
                min_value=0.0,
                max_value=40.0,
                value=round(preview_simulation.rental_ratio * 100.0, 1),
                step=1.0,
                disabled=not use_rental_ratio_override,
                help=FIELD_HELP["rental_ratio_override"],
                key="rental_ratio_override_pct",
            )

        st.markdown("#### 금융 가정")
        st.caption("이주비 이자는 `조합원 수 × 세대당 평균 무이자 이주비 × 연이자율 × 대여기간` 방식으로, PF 이자는 `PF 조달원금 × 금리 × 반영개월` 방식으로 계산합니다.")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            pf_financing_ratio_pct = st.number_input(
                "PF 조달비율(%)",
                min_value=0.0,
                max_value=95.0,
                value=round(default_pf_financing_ratio(project_kind) * 100.0, 1),
                step=1.0,
                help=FIELD_HELP["pf_financing_ratio"],
            )
        with f2:
            pf_interest_months = st.number_input(
                "PF 이자 반영기간(개월)",
                min_value=0.0,
                value=round(default_pf_interest_months(preview_remaining_months), 1),
                step=1.0,
                help=FIELD_HELP["pf_interest_months"],
            )
        with f3:
            average_move_loan_amount_eok = st.number_input(
                "세대당 평균 무이자 이주비(억)",
                min_value=0.0,
                value=round(eok_from_won(default_average_move_loan_amount(won_from_eok(purchase_price_eok), project_kind)), 2),
                step=0.1,
                help=FIELD_HELP["avg_move_loan_amount"],
            )
        with f4:
            move_loan_duration_months = st.number_input(
                "이주비 대여기간(개월)",
                min_value=0.0,
                value=round(default_move_loan_duration_months(preview_remaining_months), 1),
                step=1.0,
                help=FIELD_HELP["move_loan_duration_months"],
            )

    detail_allowed = calc_mode == "정밀 계산" and is_advanced_detail_available(current_stage, merged_notice)
    with st.expander("4. 정밀 계산 전용 입력", expanded=calc_mode == "정밀 계산"):
        if calc_mode == "정밀 계산" and not detail_allowed:
            st.info("관리처분인가 이후 단계이거나 관련 문서가 있을 때 권리가액과 배정평형을 더 신뢰도 있게 보여줍니다. 지금은 빠른 검토 중심으로 계산합니다.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            expected_new_default = 74.0 if project_kind == ProjectKind.REDEVELOPMENT else 84.0
            expected_new_exclusive_area = st.number_input("예상 새 전용면적(㎡)", min_value=0.0, value=expected_new_default, step=1.0)
            official_price_label = "공동주택 공시가격 또는 감정가(억)" if project_kind == ProjectKind.RECONSTRUCTION else "토지/건물 공시가격 또는 감정가(억)"
            official_price_help = FIELD_HELP["official_price_reconstruction"] if project_kind == ProjectKind.RECONSTRUCTION else FIELD_HELP["official_price_redevelopment"]
            official_price_reference_eok = st.number_input(official_price_label, min_value=0.0, value=0.0, step=0.1, help=official_price_help)
        with c2:
            appraised_old_asset_eok = st.number_input("내 감정가/종전자산가액(억)", min_value=0.0, value=0.0, step=0.1)
            total_old_asset_value_eok = st.number_input("단지 종전자산총액(억)", min_value=0.0, value=0.0, step=1.0)
        with c3:
            adjustment_factor_override = st.number_input("보정계수 직접입력", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            floor_no = st.number_input(
                "층수(정밀 참고)",
                min_value=1,
                value=1 if project_kind == ProjectKind.REDEVELOPMENT else 10,
                step=1,
                disabled=project_kind == ProjectKind.REDEVELOPMENT,
                help="재개발은 층수 보정을 쓰지 않으므로 비활성화됩니다." if project_kind == ProjectKind.REDEVELOPMENT else None,
            )
        with c4:
            recent_trade_price_eok = st.number_input(
                "최근 실거래 중앙값(억)",
                min_value=0.0,
                value=0.0,
                step=0.1,
                disabled=project_kind == ProjectKind.REDEVELOPMENT,
                help="재개발은 최근 아파트 실거래 대신 대지지분과 감정가 기준으로 보는 편이 낫습니다." if project_kind == ProjectKind.REDEVELOPMENT else None,
            )
            acquisition_rate_pct = st.number_input("취득세 실효세율(%)", min_value=0.0, max_value=100.0, value=1.5, step=0.1)
            annual_holding_rate_pct = st.number_input("연 보유비용률(%)", min_value=0.0, max_value=100.0, value=0.3, step=0.1)
            capital_gains_effective_rate_pct = st.number_input("양도세 실효세율(%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
            brokerage_rate_pct = st.number_input("중개/처분비율(%)", min_value=0.0, max_value=100.0, value=0.4, step=0.1)
        unit_mix_text = st.text_area(
            "기존 세대 타입별 분포(선택)",
            value=default_unit_mix_text(current_unit_exclusive_area, current_unit_supply_area, int(current_households)) if project_kind == ProjectKind.RECONSTRUCTION else "",
            height=90,
            help=FIELD_HELP["unit_mix"],
            disabled=project_kind == ProjectKind.REDEVELOPMENT,
        )
        member_price_text = st.text_area(
            "조합원 분양가표(선택)",
            value="59형,59,75.6,8.5\n84형,84,107.7,12.0\n101형,101,129.5,15.0",
            height=110,
            help=FIELD_HELP["member_price_text"],
        )

    with st.expander("5. 상세 비용 버킷 직접입력", expanded=False):
        st.caption("비워두면 자동 계산값을 사용합니다. 숫자를 넣은 버킷만 직접입력값으로 덮어씁니다.")
        bucket_override_inputs: dict[str, float] = {}
        columns = st.columns(3)
        for idx, (key, label, description) in enumerate(COST_BUCKET_META):
            with columns[idx % 3]:
                bucket_override_inputs[key] = won_from_eok(st.number_input(f"{label}(억)", min_value=0.0, value=0.0, step=0.1, key=f"bucket_{key}", help=description))
        ancillary_revenue_eok = st.number_input("부대복리/상가 수입(억)", min_value=0.0, value=0.0, step=0.1)
        other_disposal_revenue_eok = st.number_input("기타 처분수입(억)", min_value=0.0, value=0.0, step=0.1)
        liquidation_cost_eok = st.number_input("청산/소송 비용(억)", min_value=0.0, value=0.0, step=0.1)

    applied_document_fields = set()
    use_doc_price_table = False
    if merged_notice:
        with st.expander("6. 문서값 반영 선택", expanded=False):
            applied_document_fields = set(st.multiselect("계산에 반영할 문서 추출값", extracted_options, format_func=humanize_key))
            use_doc_price_table = st.checkbox("문서 분양가표 사용", value=False, disabled=not merged_notice.member_price_table)
            st.caption("문서 숫자는 자동 확정하지 않습니다. 체크한 값만 계산에 넣습니다.")

        quick_inputs = QuickDealInputs(
        project_kind=project_kind,
        scenario_profile=assumption_profile,
        current_stage=current_stage,
        purchase_price=won_from_eok(purchase_price_eok),
        current_unit_exclusive_area=redevelopment_base_exclusive_area if project_kind == ProjectKind.REDEVELOPMENT else current_unit_exclusive_area,
        current_unit_supply_area=redevelopment_base_supply_area if project_kind == ProjectKind.REDEVELOPMENT else current_unit_supply_area,
        comparison_new_price=won_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
        general_sale_price=won_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
        current_households=int(current_households),
        current_far=current_far or None,
        target_far=target_far or None,
        land_share=land_share or None,
        site_area_sqm=autofill_project.site_area_sqm if autofill_project else None,
        current_building_coverage_ratio=(current_building_coverage_ratio_pct / 100.0) if current_building_coverage_ratio_pct else None,
        target_building_coverage_ratio=(target_building_coverage_ratio_pct / 100.0) if target_building_coverage_ratio_pct else None,
        average_current_floors=average_current_floors or None,
        floor_no=1 if project_kind == ProjectKind.REDEVELOPMENT else int(floor_no),
        official_price_reference=won_from_eok(official_price_reference_eok) if official_price_reference_eok else None,
        recent_same_complex_trade_price=None if project_kind == ProjectKind.REDEVELOPMENT else (won_from_eok(recent_trade_price_eok) if recent_trade_price_eok else None),
        sale_rate=sale_rate_pct / 100.0,
        cash_settlement_rate=cash_settlement_rate_pct / 100.0,
        construction_cost_per_pyeong=construction_cost_per_pyeong_man * 10_000,
        pf_rate=pf_rate_pct / 100.0,
        move_loan_rate=move_loan_rate_pct / 100.0,
        target_households_override=int(target_households_override_value) if use_target_households_override else None,
        general_sale_ratio_override=(general_sale_ratio_override_pct / 100.0) if use_general_sale_ratio_override else None,
        donation_ratio_override=(donation_ratio_override_pct / 100.0) if use_donation_ratio_override else None,
        rental_ratio_override=(rental_ratio_override_pct / 100.0) if use_rental_ratio_override else None,
        delay_one_year=delay_one_year,
        aggressive_upsize=aggressive_upsize,
        capital_area=capital_area,
        autofill_project=autofill_project,
        parsed_notice=merged_notice,
        applied_document_fields=applied_document_fields,
        use_doc_price_table=use_doc_price_table,
        lookup_enabled=bool(autofill_project),
    )
    advanced_inputs = AdvancedProjectInputs(
        rights_inputs=RightsInputs(
            expected_new_exclusive_area=expected_new_exclusive_area or None,
            appraised_old_asset_value=won_from_eok(appraised_old_asset_eok) if appraised_old_asset_eok else None,
            total_old_asset_value=won_from_eok(total_old_asset_value_eok) if total_old_asset_value_eok else None,
            official_price_reference=won_from_eok(official_price_reference_eok) if official_price_reference_eok else None,
            adjustment_factor_override=adjustment_factor_override or None,
            member_price_text=member_price_text,
        ),
        unit_mix_rows=parse_unit_mix_text(unit_mix_text),
        pf_financing_ratio=pf_financing_ratio_pct / 100.0,
        pf_interest_months=pf_interest_months,
        average_move_loan_amount=won_from_eok(average_move_loan_amount_eok),
        move_loan_duration_months=move_loan_duration_months,
        acquisition_rate=acquisition_rate_pct / 100.0,
        annual_holding_rate=annual_holding_rate_pct / 100.0,
        capital_gains_effective_rate=capital_gains_effective_rate_pct / 100.0,
        brokerage_rate=brokerage_rate_pct / 100.0,
        ancillary_revenue=won_from_eok(ancillary_revenue_eok),
        other_disposal_revenue=won_from_eok(other_disposal_revenue_eok),
        liquidation_cost_override=won_from_eok(liquidation_cost_eok) if liquidation_cost_eok else None,
        cost_bucket_overrides={key: value for key, value in bucket_override_inputs.items() if value > 0},
    )

    results = [analyze_scenario(quick_inputs, advanced_inputs, scenario_name, detail_allowed) for scenario_name in SCENARIOS]
    focus_result = next(item for item in results if item.scenario_name == scenario_focus)

    st.subheader("결과")
    if not quick_inputs.lookup_enabled:
        st.warning("서울 공식값을 못 불러온 상태라 일부 값은 수동 입력과 휴리스틱으로 계산됩니다.")
    if detail_allowed and focus_result.old_asset_source == "purchase_price_heuristic":
        st.warning("정밀계산용 참고가격이 없어서 권리가액은 매수가 기반 휴리스틱으로 추정했습니다.")
    render_result_summary(focus_result)

    tab1, tab2, tab3 = st.tabs(["핵심 결과", "시나리오/민감도", "정밀 근거"])
    with tab1:
        render_table(scenario_overview_rows(results), "시나리오 한눈에 보기")
        left, right = st.columns([1.1, 0.9])
        with left:
            render_table(project_summary_rows(focus_result), "사업성 요약")
        with right:
            render_table(feasibility_rows(focus_result), "세대수/층수 점검")
        render_table(simulation_rows(focus_result), "자동 추정과 공식값 반영")
        left, right = st.columns([1.1, 0.9])
        with left:
            if focus_result.allocation_options:
                if not detail_allowed:
                    st.caption("관리처분 이전 단계에서는 권리가액과 분양가표가 개략치이므로, 아래 추가분담금은 빠른 검토용 시뮬레이션으로 보세요.")
                render_table(allocation_rows(focus_result), "평형별 추가분담 시뮬레이션")
            else:
                st.markdown(
                    "<div class='section-card'><div class='soft-title'>평형별 추가분담 시뮬레이션</div><p class='mini-note'>현재 입력값으로는 평형별 추가분담 시뮬레이션을 만들기 어려웠습니다. 일반분양 평균가나 예상 새 전용면적을 한 번 더 확인해 주세요.</p></div>",
                    unsafe_allow_html=True,
                )
        with right:
            assumption_rows = [
                {"가정값": "일반분양 판매율", "값": fmt_pct(focus_result.assumption_summary["sale_rate"])},
                {"가정값": "현금청산률", "값": fmt_pct(focus_result.assumption_summary["cash_settlement_rate"])},
                {"가정값": "기부채납 비율", "값": fmt_pct(focus_result.assumption_summary["donation_ratio"])},
                {"가정값": "임대주택 비율", "값": fmt_pct(focus_result.assumption_summary["rental_ratio"])},
                {"가정값": "일반분양 비율", "값": fmt_pct(focus_result.assumption_summary["general_sale_ratio"])},
                {"가정값": "PF 금리", "값": fmt_pct(focus_result.assumption_summary["pf_rate"])},
                {"가정값": "PF 조달비율", "값": fmt_pct(focus_result.assumption_summary["pf_financing_ratio"])},
                {"가정값": "PF 이자 반영기간", "값": f"{focus_result.assumption_summary['pf_interest_months']:.0f}개월"},
                {"가정값": "세대당 평균 이주비", "값": fmt_money(focus_result.assumption_summary["average_move_loan_amount"])},
                {"가정값": "이주비 대여기간", "값": f"{focus_result.assumption_summary['move_loan_duration_months']:.0f}개월"},
            ]
            render_table(assumption_rows, "이번 계산에 들어간 핵심 가정")

    with tab2:
        render_table(exit_rows(focus_result), "엑시트별 손익")
        render_table(focus_result.sensitivity_rows, "민감도")

    with tab3:
        render_table(bucket_rows(focus_result), "비용 버킷")
        if detail_allowed and focus_result.advanced_rights_result is not None:
            detail_rows = [
                {"항목": "종전자산 추정액", "값": fmt_money(focus_result.advanced_rights_result.old_asset_estimate), "출처": humanize_source(focus_result.advanced_rights_result.old_asset_source)},
                {"항목": "단지 종전자산총액", "값": fmt_money(focus_result.advanced_rights_result.total_old_asset_value), "출처": humanize_source(focus_result.advanced_rights_result.total_old_asset_source)},
                {"항목": "권리가액", "값": fmt_money(focus_result.advanced_rights_result.rights_value), "출처": "계산 엔진"},
                {"항목": "보정계수", "값": f"{focus_result.advanced_rights_result.adjustment_factor:.3f}", "출처": humanize_source("engine")},
            ]
            render_table(detail_rows, "정밀 계산 정보")
        render_source_records(focus_result.source_records, "계산 근거")
        if merged_notice:
            render_source_records(merged_notice.extracted_records, "문서 추출 결과")
        if autofill_project:
            render_source_records(autofill_project.source_records, "서울 공식값 반영 결과")

    st.caption("권리가액, 분담금, 공사비, 일정은 법적 확정값이 아니라 의사결정 보조용 추정치입니다. 특히 관리처분인가 이전 단계에서는 빠른 매물 검토용 개략치로 보는 것이 안전합니다.")


if __name__ == "__main__":
    main()
