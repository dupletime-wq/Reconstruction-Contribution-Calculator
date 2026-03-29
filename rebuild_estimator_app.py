from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from html import escape, unescape
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
import re
import statistics
from typing import Generic, Protocol, TypeVar
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

BASELINE_SCENARIO_NAME = "기준"

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
    "재건축진단": 156,
    "정비구역지정": 132,
    "추진위승인": 108,
    "조합설립인가": 96,
    "사업시행인가": 72,
    "관리처분인가": 48,
    "이주/철거": 30,
    "착공": 24,
    "준공/입주": 0,
}

STAGE_SCHEDULE_FLOORS: dict[str, int] = {
    "재건축진단": 120,
    "정비구역지정": 102,
    "추진위승인": 84,
    "조합설립인가": 72,
    "사업시행인가": 54,
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
    "member_sale_price_ratio": "조합원 분양가 비율",
    "rental_revenue": "임대주택수입",
    "site_area_sqm": "대지면적",
    "target_far": "목표 용적률",
    "building_coverage_ratio": "목표 건폐율",
    "current_households": "권리자/기존 세대수",
    "public_facility_area_sqm": "공공시설 반영면적",
    "sale_households": "일반분양 세대수",
    "sale_households_total": "분양주택 세대수",
    "rental_households": "임대주택 세대수",
    "donation_area_sqm": "명시 기부채납 면적",
    "planned_unit_mix_source": "준공 후 공급 평형 계획",
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
    "naver_land": "네이버 부동산 공개 페이지",
    "naver_land_heuristic": "네이버 단지정보 기반 부지면적 추정",
    "kgeop_public": "KGeoP 공개 지도",
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
    "general_sale_price_basis_area": "입력한 일반분양 평균가가 어느 전용면적 기준인지 적는 값입니다. 예를 들어 84㎡ 기준 14억이면 84를 넣어야 다른 평형으로 합리적으로 환산할 수 있습니다.",
    "general_sale_price_per_pyeong": "블로그나 사업성 분석 글처럼 공급면적 기준 평당 분양가로 계산하고 싶을 때 쓰는 값입니다. 이 값을 넣으면 일반분양 총액 입력보다 우선해서 사용합니다.",
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
    "member_sale_price_ratio": "조합원 분양가를 일반분양가 대비 몇 %로 볼지 정하는 값입니다. 문서 분양가표가 없을 때 빠른 정밀도를 높이는 보정값으로 쓰면 좋습니다.",
    "rental_sale_price_per_pyeong": "임대주택 수입을 공급평당 얼마로 볼지 정하는 값입니다. 블로그 사례나 서울시 추정 흐름에서는 1,000만원/평 수준을 자주 사용합니다.",
    "pf_financing_ratio": "총 사업비 중 PF 등 차입으로 조달한다고 보는 비율입니다. 실제 조달계획이 있으면 그 비율을 우선 넣으세요.",
    "pf_interest_months": "PF 이자가 실제로 붙는 기간입니다. 공사 전후 전 기간이 아니라 차입이 발생하는 구간만 반영하는 게 맞습니다.",
    "avg_move_loan_amount": "서울시 매뉴얼 기준 조합원이주비 이자 추산은 `조합원 수 × 세대당 평균 무이자 이주비 × 연이자율 × 대여기간`입니다. 세대당 평균 무이자 이주비를 넣으세요.",
    "move_loan_duration_months": "세대당 평균 무이자 이주비가 실제로 대여되는 기간입니다. 이주 개시부터 입주 전까지의 대략적 개월 수를 넣습니다.",
    "official_price_reconstruction": "재건축 정밀계산에서만 쓰는 참고값입니다. 공동주택 공시가격이나 감정가가 있으면 권리가액 추정 보정에 사용합니다.",
    "official_price_redevelopment": "재개발 정밀계산에서만 쓰는 참고값입니다. 토지/건물 공시가격 또는 감정가를 넣으면 권리가액 참고 추정에 사용합니다.",
    "unit_mix": "재건축에서 기존 평형별 세대수와 면적을 넣으면 현재 연면적과 세대구성을 더 정확하게 추정합니다. 형식: 타입,세대수,전용,공급",
    "planned_unit_mix": "준공 후 공급할 평형 계획입니다. 형식: 타입,세대수,전용,공급. 비워두면 59/74/84/101/114 중심 자동안을 사용하고, 넣으면 총세대수와 분양수입 계산에 이 값이 우선 반영됩니다.",
    "member_price_text": "정밀모드에서 배정평형 비교가 필요할 때만 쓰는 참고값입니다. 빠른 수익성 답에는 필수가 아닙니다. 형식: 타입,전용,공급,분양가(억)",
}


class ProjectKind(str, Enum):
    RECONSTRUCTION = "재건축"
    REDEVELOPMENT = "재개발"

class ReconstructionStyle(str, Enum):
    APARTMENT = "공동주택형"
    DETACHED_CLUSTER = "단독주택 묶음형"


T = TypeVar("T")


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
class ObservedValue(Generic[T]):
    value: T
    source: str
    confidence: float
    observed_at: str
    note: str = ""


@dataclass
class SearchResult:
    source: str
    project_id: str
    title: str
    subtitle: str
    url: str = ""
    confidence: float = 0.0
    capability: str = "external_link_only"
    structured_fields_count: int = 0
    status_reason: str = ""


@dataclass
class FieldCandidate:
    field_name: str
    value: object
    source: str
    confidence: float
    note: str = ""


@dataclass
class UnitMixCandidateBundle:
    source: str
    confidence: float
    rows: list["UnitMixRow"] = field(default_factory=list)
    note: str = ""


@dataclass
class SourceHealth:
    source: str
    status: str
    reason: str = ""


class SearchAdapter(Protocol):
    def search(self, query: str) -> list[SearchResult]:
        ...


class ProjectAdapter(Protocol):
    def fetch(self, project_id: str) -> "AutofillProjectData | None":
        ...


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
    average_current_floors: float | None = None
    current_building_count: int | None = None
    target_building_coverage_ratio: float | None = None
    current_building_coverage_ratio: float | None = None
    target_far: float | None = None
    current_households: int | None = None
    owner_count: int | None = None
    tenant_count: int | None = None
    planned_households: int | None = None
    sale_households_total: int | None = None
    sale_households: int | None = None
    rental_households: int | None = None
    public_facility_area_sqm: float | None = None
    donation_area_sqm: float | None = None
    schedule_text: str | None = None
    source_records: list[SourceRecord] = field(default_factory=list)
    observed_fields: dict[str, ObservedValue[object]] = field(default_factory=dict)
    field_candidates: dict[str, list[FieldCandidate]] = field(default_factory=dict)
    external_links: list[tuple[str, str]] = field(default_factory=list)
    search_source: str = "official_cleanup"
    search_capability: str = "official_cleanup"
    search_status_reason: str = ""
    structured_fields_count: int = 0
    existing_unit_mix_rows: list["UnitMixRow"] = field(default_factory=list)
    planned_unit_mix_candidates: list["UnitMixRow"] = field(default_factory=list)
    unit_mix_source: str = "simulation"
    unit_mix_confidence: float = 0.0
    source_health: list[SourceHealth] = field(default_factory=list)


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
    reconstruction_style: ReconstructionStyle
    scenario_profile: str
    current_stage: str
    purchase_price: float
    current_unit_exclusive_area: float
    current_unit_supply_area: float
    comparison_new_price: float | None
    general_sale_price: float | None
    general_sale_price_basis_exclusive_area: float | None
    general_sale_price_per_pyeong_manwon: float | None
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
    member_sale_price_ratio_override: float | None
    rental_sale_price_per_pyeong_manwon: float | None
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
    planned_unit_mix_rows: list[UnitMixRow] = field(default_factory=list)


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
    additional_cash_needed: float | None
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
    scenario_delta_summary: str = ""
    scenario_visibility: bool = True
    planned_unit_mix_rows: list[UnitMixRow] = field(default_factory=list)
    planned_unit_mix_source: str = "simulation"


def cache_data(*args, **kwargs):
    def decorator(func):
        if st is None:
            return func
        return st.cache_data(*args, **kwargs)(func)

    return decorator


def record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(key=key, value=value, source=source, confidence=confidence, notes=notes)


def observed(value: T, source: str, confidence: float, note: str = "") -> ObservedValue[T]:
    return ObservedValue(value=value, source=source, confidence=confidence, observed_at=datetime.now().strftime("%Y-%m-%d %H:%M"), note=note)


def attach_observed(project: AutofillProjectData, field_name: str, value: object, source: str, confidence: float, note: str = "") -> None:
    if value in (None, "", []):
        return
    project.observed_fields[field_name] = observed(value, source, confidence, note)
    project.field_candidates.setdefault(field_name, []).append(FieldCandidate(field_name, value, source, confidence, note))


def count_structured_project_fields(project: AutofillProjectData | None) -> int:
    if project is None:
        return 0
    fields = (
        project.site_area_sqm,
        project.target_building_coverage_ratio,
        project.target_far,
        project.current_households,
        project.owner_count,
        project.planned_households,
        project.sale_households_total,
        project.sale_households,
        project.rental_households,
        project.public_facility_area_sqm,
        project.donation_area_sqm,
    )
    return sum(1 for value in fields if value not in (None, "", []))


def sync_project_capability(project: AutofillProjectData, capability: str | None = None, status_reason: str | None = None) -> AutofillProjectData:
    if capability is not None:
        project.search_capability = capability
    if status_reason is not None:
        project.search_status_reason = status_reason
    project.structured_fields_count = count_structured_project_fields(project)
    return project


def add_source_health(project: AutofillProjectData, source: str, status: str, reason: str = "") -> None:
    project.source_health.append(SourceHealth(source=source, status=status, reason=reason))


def merge_external_links(*projects: AutofillProjectData | None) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    links: list[tuple[str, str]] = []
    for project in projects:
        if not project:
            continue
        for label, url in project.external_links:
            key = (label, url)
            if key in seen:
                continue
            seen.add(key)
            links.append(key)
    return links


def choose_observed_value(
    current: ObservedValue[object] | None,
    candidate: ObservedValue[object] | None,
) -> ObservedValue[object] | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    priority = {
        "manual": 6,
        "document": 5,
        "official_cleanup": 4,
        "naver_land": 3,
        "kgeop_public": 2,
        "simulation": 1,
        "engine": 0,
    }
    current_rank = priority.get(current.source, 0)
    candidate_rank = priority.get(candidate.source, 0)
    if candidate_rank > current_rank:
        return candidate
    if candidate_rank == current_rank and candidate.confidence >= current.confidence:
        return candidate
    return current


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


def settlement_label(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return "추가분담금"
    if value < 0:
        return "환급금"
    return "정산 없음"


def fmt_settlement(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"추가분담금 {fmt_money(value)}"
    if value < 0:
        return f"환급금 {fmt_money(abs(value))}"
    return "정산 없음"


def scale_price_by_area(anchor_price: float, anchor_exclusive_area: float | None, target_exclusive_area: float | None) -> float:
    base_area = max(float(anchor_exclusive_area or 0.0), 1.0)
    target_area = max(float(target_exclusive_area or base_area), 1.0)
    return float(anchor_price) * ((target_area / base_area) ** 0.98)


def price_from_supply_pyeong(price_per_pyeong_manwon: float | None, target_supply_area_sqm: float | None) -> float | None:
    if price_per_pyeong_manwon is None or target_supply_area_sqm is None:
        return None
    return float(price_per_pyeong_manwon) * 10_000.0 * (float(target_supply_area_sqm) / 3.3058)


def resolve_market_unit_price(
    *,
    general_sale_price: float | None,
    general_sale_price_basis_exclusive_area: float | None,
    general_sale_price_per_pyeong_manwon: float | None,
    comparison_new_price: float | None,
    comparison_anchor_exclusive_area: float | None,
    purchase_price: float,
    target_exclusive_area: float | None,
    target_supply_area_sqm: float | None,
) -> float:
    if general_sale_price_per_pyeong_manwon is not None and target_supply_area_sqm is not None:
        per_pyeong_price = price_from_supply_pyeong(general_sale_price_per_pyeong_manwon, target_supply_area_sqm)
        if per_pyeong_price is not None:
            return per_pyeong_price
    if general_sale_price:
        return scale_price_by_area(general_sale_price, general_sale_price_basis_exclusive_area or 84.0, target_exclusive_area)
    if comparison_new_price:
        return scale_price_by_area(comparison_new_price, comparison_anchor_exclusive_area or target_exclusive_area, target_exclusive_area)
    fallback_anchor = comparison_anchor_exclusive_area or target_exclusive_area or 84.0
    return scale_price_by_area(purchase_price * 1.45, fallback_anchor, target_exclusive_area)


def default_member_sale_price_ratio(
    quick_inputs: "QuickDealInputs",
    current_stage: str,
    override_value: float | None,
) -> tuple[float, str]:
    if override_value is not None:
        return clamp(override_value, 0.55, 0.95), "manual_override"
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        base_ratio = 0.70
    elif quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        base_ratio = 0.72
    else:
        base_ratio = 0.75
    if quick_inputs.capital_area and quick_inputs.project_kind == ProjectKind.RECONSTRUCTION:
        base_ratio -= 0.02
    if current_stage in {"관리처분인가", "이주/철거", "착공", "준공/입주"}:
        base_ratio += 0.02
    return clamp(base_ratio, 0.60, 0.90), "preset"


def default_rental_sale_price_per_pyeong_manwon(
    quick_inputs: "QuickDealInputs",
    override_value: float | None,
) -> tuple[float, str]:
    if override_value is not None:
        return max(float(override_value), 0.0), "manual_override"
    return (1000.0 if quick_inputs.capital_area else 800.0), "preset"


def apply_scenario_to_baseline(
    baseline_value: float,
    scenario_name: str,
    key: str,
    *,
    low: float,
    high: float,
) -> float:
    baseline_scenario = SCENARIOS[BASELINE_SCENARIO_NAME]
    scenario = SCENARIOS[scenario_name]
    delta = float(scenario[key]) - float(baseline_scenario[key])
    return clamp(float(baseline_value) + delta, low, high)


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


def weighted_average_exclusive_area(unit_mix_rows: list[UnitMixRow], default_exclusive_area: float) -> float:
    if not unit_mix_rows:
        return default_exclusive_area
    weighted_area = sum(item.households * item.exclusive_area_sqm for item in unit_mix_rows)
    total_households = sum(item.households for item in unit_mix_rows)
    return safe_div(weighted_area, total_households, default_exclusive_area)


def estimate_supply_area_from_exclusive_area(
    exclusive_area_sqm: float,
    *,
    project_kind: ProjectKind | None = None,
    reconstruction_style: ReconstructionStyle | None = None,
) -> float:
    size = max(float(exclusive_area_sqm), 1.0)
    if project_kind == ProjectKind.REDEVELOPMENT or reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        ratio = 1.27 if size <= 59 else 1.25 if size <= 84 else 1.22
    elif size <= 59:
        ratio = 1.30
    elif size <= 74:
        ratio = 1.28
    elif size <= 84:
        ratio = 1.27
    elif size <= 101:
        ratio = 1.25
    else:
        ratio = 1.23
    return round(size * ratio, 2)


def infer_unit_mix_label(exclusive_area_sqm: float) -> str:
    return f"{int(round(exclusive_area_sqm))}형"


def estimate_exclusive_area_from_supply_area(
    supply_area_sqm: float,
    *,
    project_kind: ProjectKind | None = None,
    reconstruction_style: ReconstructionStyle | None = None,
) -> float:
    supply = max(float(supply_area_sqm), 1.0)
    ratios = [1.27, 1.25] if project_kind == ProjectKind.REDEVELOPMENT or reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER else [1.30, 1.27, 1.23]
    return round(statistics.mean(supply / ratio for ratio in ratios), 2)


def heuristic_current_building_coverage_ratio(avg_floors: float, building_count: int | None = None) -> float:
    floors = max(float(avg_floors), 1.0)
    if floors <= 6:
        ratio = 0.20
    elif floors <= 10:
        ratio = 0.18
    elif floors <= 15:
        ratio = 0.16
    else:
        ratio = 0.14
    if building_count and building_count >= 10:
        ratio += 0.01
    elif building_count and building_count <= 3:
        ratio -= 0.01
    return clamp(ratio, 0.12, 0.24)


def default_member_price_table(
    user_text: str,
    doc_table: list[MemberPriceRecord],
    use_doc_table: bool,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
    comparison_new_price: float | None,
    general_sale_price: float | None,
    general_sale_price_basis_exclusive_area: float | None,
    general_sale_price_per_pyeong_manwon: float | None,
    purchase_price: float,
    current_exclusive_area: float,
    expected_new_area: float | None,
    member_sale_price_ratio: float,
    planned_unit_mix_rows: list[UnitMixRow] | None = None,
) -> list[MemberPriceRecord]:
    text_table = parse_member_price_text(user_text)
    if text_table:
        return text_table
    if use_doc_table and doc_table:
        return doc_table
    base_exclusive = expected_new_area or max(current_exclusive_area, 59.0)
    if planned_unit_mix_rows:
        sizes = sorted({float(round(item.exclusive_area_sqm)) for item in planned_unit_mix_rows if item.exclusive_area_sqm > 0})
    elif project_kind == ProjectKind.REDEVELOPMENT or reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        sizes = sorted({59.0, 74.0, 84.0, round(base_exclusive)})
    else:
        sizes = sorted({59.0, 84.0, 101.0, 114.0, round(base_exclusive)})
    rows: list[MemberPriceRecord] = []
    for size in sizes:
        supply_area = estimate_supply_area_from_exclusive_area(
            size,
            project_kind=project_kind,
            reconstruction_style=reconstruction_style,
        )
        market_price = resolve_market_unit_price(
            general_sale_price=general_sale_price,
            general_sale_price_basis_exclusive_area=general_sale_price_basis_exclusive_area,
            general_sale_price_per_pyeong_manwon=general_sale_price_per_pyeong_manwon,
            comparison_new_price=comparison_new_price,
            comparison_anchor_exclusive_area=base_exclusive,
            purchase_price=purchase_price,
            target_exclusive_area=size,
            target_supply_area_sqm=supply_area,
        )
        member_price = market_price * member_sale_price_ratio
        rows.append(MemberPriceRecord(label=infer_unit_mix_label(size), exclusive_area_sqm=float(size), supply_area_sqm=supply_area, member_sale_price=member_price))
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


def uses_land_based_flow(quick_inputs: QuickDealInputs) -> bool:
    return quick_inputs.project_kind == ProjectKind.REDEVELOPMENT or quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER


def uses_apartment_reconstruction_flow(quick_inputs: QuickDealInputs) -> bool:
    return quick_inputs.project_kind == ProjectKind.RECONSTRUCTION and quick_inputs.reconstruction_style == ReconstructionStyle.APARTMENT


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
        if len(parts) not in {3, 4}:
            continue
        try:
            exclusive_area = float(parts[2])
            supply_area = (
                float(parts[3])
                if len(parts) == 4
                else estimate_supply_area_from_exclusive_area(exclusive_area)
            )
            rows.append(
                UnitMixRow(
                    label=parts[0],
                    households=int(float(parts[1])),
                    exclusive_area_sqm=exclusive_area,
                    supply_area_sqm=supply_area,
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


def allocate_counts_by_weights(total_count: int, weights: list[float]) -> list[int]:
    if total_count <= 0 or not weights:
        return [0 for _ in weights]
    positive_weights = [max(weight, 0.0) for weight in weights]
    weight_sum = sum(positive_weights)
    if weight_sum <= 0:
        positive_weights = [1.0 for _ in weights]
        weight_sum = float(len(weights))
    raw_values = [total_count * (weight / weight_sum) for weight in positive_weights]
    floors = [int(value) for value in raw_values]
    remainder = total_count - sum(floors)
    remainders = sorted(
        enumerate([value - int(value) for value in raw_values]),
        key=lambda item: item[1],
        reverse=True,
    )
    for index, _ in remainders[:remainder]:
        floors[index] += 1
    return floors


def auto_planned_unit_mix_rows(
    quick_inputs: QuickDealInputs,
    unit_mix_rows: list[UnitMixRow],
    planned_households: int,
) -> list[UnitMixRow]:
    if planned_households <= 0:
        return []
    average_exclusive = weighted_average_exclusive_area(unit_mix_rows, quick_inputs.current_unit_exclusive_area)
    if uses_land_based_flow(quick_inputs):
        sizes = [59.0, 74.0, 84.0]
    elif average_exclusive >= 100:
        sizes = [59.0, 84.0, 101.0, 114.0]
    elif average_exclusive >= 84:
        sizes = [59.0, 74.0, 84.0, 101.0]
    else:
        sizes = [59.0, 74.0, 84.0]

    if unit_mix_rows and uses_apartment_reconstruction_flow(quick_inputs):
        total_households = max(sum(item.households for item in unit_mix_rows), 1)
        small_share = sum(item.households for item in unit_mix_rows if item.exclusive_area_sqm <= 60.0) / total_households
        large_share = sum(item.households for item in unit_mix_rows if item.exclusive_area_sqm >= 100.0) / total_households
        if len(sizes) == 4:
            mid_share = max(1.0 - small_share - large_share, 0.0)
            weights = [
                max(small_share, 0.18),
                max(mid_share * 0.30, 0.12),
                max(mid_share * 0.45, 0.20),
                max(large_share, 0.10),
            ]
        else:
            mid_share = max(1.0 - small_share, 0.0)
            weights = [max(small_share, 0.25), max(mid_share * 0.35, 0.18), max(mid_share * 0.45, 0.22)]
    else:
        if len(sizes) == 4:
            if average_exclusive >= 100:
                weights = [0.14, 0.18, 0.34, 0.34]
            elif average_exclusive >= 84:
                weights = [0.22, 0.18, 0.40, 0.20]
            else:
                weights = [0.42, 0.18, 0.26, 0.14]
        else:
            if uses_land_based_flow(quick_inputs):
                weights = [0.34, 0.22, 0.44]
            elif average_exclusive <= 65:
                weights = [0.55, 0.20, 0.25]
            elif average_exclusive <= 84:
                weights = [0.40, 0.20, 0.40]
            else:
                weights = [0.26, 0.18, 0.56]

    counts = allocate_counts_by_weights(planned_households, weights)
    rows: list[UnitMixRow] = []
    for size, households in zip(sizes, counts):
        if households <= 0:
            continue
        rows.append(
            UnitMixRow(
                label=infer_unit_mix_label(size),
                households=households,
                exclusive_area_sqm=float(size),
                supply_area_sqm=estimate_supply_area_from_exclusive_area(
                    size,
                    project_kind=quick_inputs.project_kind,
                    reconstruction_style=quick_inputs.reconstruction_style,
                ),
            )
        )
    return rows


def resolve_planned_unit_mix_rows(
    quick_inputs: QuickDealInputs,
    advanced_inputs: AdvancedProjectInputs,
    planned_households: int,
) -> tuple[list[UnitMixRow], str]:
    if advanced_inputs.planned_unit_mix_rows:
        return advanced_inputs.planned_unit_mix_rows, "manual_override"
    return auto_planned_unit_mix_rows(quick_inputs, advanced_inputs.unit_mix_rows, planned_households), "simulation"


def allocation_from_capacities(capacities: list[int], target_count: int) -> list[int]:
    if target_count <= 0 or not capacities:
        return [0 for _ in capacities]
    remaining = target_count
    allocated = [0 for _ in capacities]
    capacity_sum = sum(max(capacity, 0) for capacity in capacities)
    if capacity_sum <= 0:
        return allocated
    proportional = allocate_counts_by_weights(remaining, [float(max(capacity, 0)) for capacity in capacities])
    for index, amount in enumerate(proportional):
        allocated[index] = min(amount, max(capacities[index], 0))
    leftover = remaining - sum(allocated)
    if leftover > 0:
        order = sorted(range(len(capacities)), key=lambda idx: capacities[idx] - allocated[idx], reverse=True)
        for index in order:
            available = capacities[index] - allocated[index]
            if available <= 0:
                continue
            add_amount = min(available, leftover)
            allocated[index] += add_amount
            leftover -= add_amount
            if leftover <= 0:
                break
    return allocated


def price_table_lookup(
    price_table: list[MemberPriceRecord],
    target_exclusive_area: float,
) -> MemberPriceRecord | None:
    if not price_table:
        return None
    return min(price_table, key=lambda item: abs(item.exclusive_area_sqm - target_exclusive_area))


def estimate_current_gross_floor_area_sqm(quick_inputs: QuickDealInputs, advanced_inputs: AdvancedProjectInputs) -> float:
    if advanced_inputs.unit_mix_rows and uses_apartment_reconstruction_flow(quick_inputs):
        return sum(item.households * item.supply_area_sqm for item in advanced_inputs.unit_mix_rows) * 1.08
    if uses_land_based_flow(quick_inputs):
        if quick_inputs.site_area_sqm and quick_inputs.current_far:
            return quick_inputs.site_area_sqm * (quick_inputs.current_far / 100.0)
        if quick_inputs.land_share and quick_inputs.current_households and quick_inputs.current_far:
            site_area_sqm = quick_inputs.land_share * quick_inputs.current_households
            return site_area_sqm * (quick_inputs.current_far / 100.0)
    return quick_inputs.current_households * quick_inputs.current_unit_supply_area * 1.08


def estimate_member_base_count(quick_inputs: QuickDealInputs, base_cash_rate: float) -> int:
    project = quick_inputs.autofill_project
    if uses_land_based_flow(quick_inputs):
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
    elif quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
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
    planned_mix_rows = advanced_inputs.planned_unit_mix_rows
    if uses_land_based_flow(quick_inputs):
        redev_base_exclusive = advanced_inputs.rights_inputs.expected_new_exclusive_area or 59.0
        default_supply_area = max(
            estimate_supply_area_from_exclusive_area(
                redev_base_exclusive,
                project_kind=quick_inputs.project_kind,
                reconstruction_style=quick_inputs.reconstruction_style,
            ),
            75.0,
        )
    else:
        default_supply_area = quick_inputs.current_unit_supply_area
    average_supply_area_sqm = weighted_average_supply_area(planned_mix_rows or advanced_inputs.unit_mix_rows, default_supply_area)

    if site_area_sqm and quick_inputs.target_far:
        gross_floor_area_sqm = site_area_sqm * (quick_inputs.target_far / 100.0)
    elif quick_inputs.current_far and quick_inputs.target_far:
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(quick_inputs.target_far, quick_inputs.current_far, 1.0)
    else:
        if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
            growth_multiplier = 1.38
        elif quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
            growth_multiplier = 1.32
        else:
            growth_multiplier = 1.28
        gross_floor_area_sqm = current_gross_floor_area_sqm * growth_multiplier

    saleable_area_factor = clamp(1.0 - donation_ratio, 0.55, 1.0)
    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        residential_efficiency = 0.80
    elif quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        residential_efficiency = 0.82
    else:
        residential_efficiency = 0.84
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
    elif planned_mix_rows:
        planned_households = sum(item.households for item in planned_mix_rows)
        households_source = "manual_override"
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
    has_unit_mix: bool = False,
    has_planned_unit_mix: bool = False,
) -> list[FeasibilityCheck]:
    checks: list[FeasibilityCheck] = []
    if simulation.required_avg_floors is not None:
        if simulation.required_avg_floors > 35:
            checks.append(FeasibilityCheck("risk", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층이 필요해 과도할 수 있습니다."))
        elif simulation.required_avg_floors > 25:
            checks.append(FeasibilityCheck("warn", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층이 필요합니다. 인허가와 사업성 검토를 더 보수적으로 보세요."))
        else:
            checks.append(FeasibilityCheck("ok", "층수 부담", f"목표 FAR와 목표 건폐율 기준 평균 {simulation.required_avg_floors:.1f}층 수준으로 계산했습니다."))
    else:
        checks.append(FeasibilityCheck("note", "층수 점검 생략", "목표 건폐율이 없어서 필요 평균층수 점검은 생략했습니다."))

    if simulation.planned_households > int(simulation.simulated_total_households * 1.15):
        checks.append(FeasibilityCheck("warn", "세대수 과다 가능성", f"입력/공식 계획 세대수 {simulation.planned_households:,}세대가 엔진 추정 {simulation.simulated_total_households:,}세대보다 많이 큽니다."))
    elif simulation.planned_households < simulation.member_households:
        checks.append(FeasibilityCheck("risk", "세대수 부족", f"예상 총세대수 {simulation.planned_households:,}세대로는 분양대상 {simulation.member_households:,}세대를 담기 어렵습니다."))
    else:
        checks.append(FeasibilityCheck("ok", "세대수 점검", f"예상 총세대수 {simulation.planned_households:,}세대, 일반분양 {simulation.general_sale_households:,}세대로 계산했습니다."))

    if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT:
        if quick_inputs.autofill_project and quick_inputs.autofill_project.project_kind and quick_inputs.autofill_project.project_kind != quick_inputs.project_kind:
            checks.append(FeasibilityCheck("risk", "사업유형 불일치", f"서울 공식 사업유형은 {quick_inputs.autofill_project.project_kind.value}인데 현재 {quick_inputs.project_kind.value} 모드로 계산 중입니다."))
        if not quick_inputs.land_share:
            checks.append(FeasibilityCheck("risk", "대지지분 누락", "재개발은 내 대지지분이 없으면 권리가액과 정산액 추정이 크게 흔들립니다."))
        tenant_seed = quick_inputs.autofill_project.tenant_count if quick_inputs.autofill_project else None
        if tenant_seed:
            checks.append(FeasibilityCheck("ok", "세입자 보상 반영", f"서울 공식값 기준 세입자 {tenant_seed:,}명을 보상비 추정에 반영했습니다."))
        else:
            checks.append(FeasibilityCheck("note", "세입자 보상 반영", "세입자 공식값이 없어 재개발 보상비는 보수적 휴리스틱으로 계산했습니다."))
    elif quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        if not quick_inputs.land_share:
            checks.append(FeasibilityCheck("risk", "대지지분 누락", "단독주택 묶음형 재건축은 아파트 평형보다 내 대지지분과 권리자 수가 훨씬 중요합니다. 대지지분이 없으면 정산액 왜곡이 커집니다."))
        checks.append(FeasibilityCheck("note", "토지형 재건축 모드", "단독주택 묶음형 재건축은 대지지분·권리자 수 중심으로 계산하고, 층수와 기존 평형은 참고만 사용합니다."))
        checks.append(FeasibilityCheck("note", "보상비 처리", "단독주택 묶음형 재건축은 재개발처럼 세입자 보상비를 자동 가산하지 않고, 재건축 비용 구조를 유지합니다."))
    else:
        checks.append(FeasibilityCheck("note", "재건축 비용 구조", "아파트형 재건축은 주거이전비·영업손실보상비를 기본 자동 반영하지 않습니다."))
        if quick_inputs.current_households >= 300 and not has_unit_mix:
            checks.append(
                FeasibilityCheck(
                    "warn",
                    "평형 분포 누락",
                    "대단지 재건축인데 기존 평형 분포 입력이 없어 조합원분양수입을 단일 평형 기준으로 추정했습니다. 대형 평형 비중이 큰 단지는 기존 타입 분포를 넣어야 오차가 줄어듭니다.",
                )
            )
        if not has_planned_unit_mix:
            checks.append(
                FeasibilityCheck(
                    "note",
                    "준공 후 공급 평형 자동안",
                    "준공 후 공급할 59/84/114 등의 세대수 계획이 없어 자동 분포로 계산했습니다. 실제 공급 계획과 다르면 일반분양수입과 조합원분양수입이 함께 흔들릴 수 있습니다.",
                )
            )
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


def simple_top_drivers(duration_cost: float, construction_cost: float, settlement_amount: float) -> list[str]:
    items = [
        ("정산액", abs(settlement_amount), "선택 평형과 권리가액 차이"),
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


def header_index_map(header_row: list[str]) -> dict[str, int]:
    normalized = {re.sub(r"\s+", "", cell): idx for idx, cell in enumerate(header_row)}
    alias_groups = {
        "label": ("주택형", "평형", "타입", "구분", "전용면적"),
        "households": ("세대수", "공급세대수", "가구수", "호수"),
        "exclusive": ("전용면적", "전용", "전용㎡", "전용면적㎡"),
        "supply": ("공급면적", "공급", "공급㎡", "분양면적"),
    }
    result: dict[str, int] = {}
    for key, aliases in alias_groups.items():
        for alias in aliases:
            if alias in normalized:
                result[key] = normalized[alias]
                break
    return result


def extract_unit_mix_rows_from_table(table: list[list[str]]) -> list[UnitMixRow]:
    if len(table) < 2:
        return []
    index_map = header_index_map(table[0])
    if "households" not in index_map or "exclusive" not in index_map:
        return []
    rows: list[UnitMixRow] = []
    for raw_row in table[1:]:
        if len(raw_row) <= max(index_map.values()):
            continue
        households = parse_int(raw_row[index_map["households"]])
        exclusive_area = parse_float(raw_row[index_map["exclusive"]])
        if households is None or households <= 0 or exclusive_area is None or exclusive_area <= 0:
            continue
        label = raw_row[index_map.get("label", index_map["exclusive"])].strip() or infer_unit_mix_label(exclusive_area)
        supply_area = None
        if "supply" in index_map:
            supply_area = parse_float(raw_row[index_map["supply"]])
        rows.append(
            UnitMixRow(
                label=label,
                households=households,
                exclusive_area_sqm=exclusive_area,
                supply_area_sqm=supply_area or estimate_supply_area_from_exclusive_area(exclusive_area),
            )
        )
    return rows


def choose_best_unit_mix_candidate(tables: list[list[list[str]]]) -> tuple[list[UnitMixRow], str, float]:
    best_rows: list[UnitMixRow] = []
    best_score = 0
    for table in tables:
        rows = extract_unit_mix_rows_from_table(table)
        score = sum(item.households for item in rows)
        if len(rows) >= 2 and score > best_score:
            best_rows = rows
            best_score = score
    if best_rows:
        return best_rows, "official_cleanup", 0.72
    return [], "simulation", 0.0


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
    if project.sale_households_total is not None:
        rows.append(record("sale_households_total", str(project.sale_households_total), "official_cleanup", 0.80))
    if project.sale_households is not None:
        rows.append(record("sale_households", str(project.sale_households), "official_cleanup", 0.80))
    if project.rental_households is not None:
        rows.append(record("rental_households", str(project.rental_households), "official_cleanup", 0.80))
    if project.public_facility_area_sqm is not None:
        rows.append(record("public_facility_area_sqm", f"{project.public_facility_area_sqm:,.1f}", "official_cleanup", 0.78))
    if project.donation_area_sqm is not None:
        rows.append(record("donation_area_sqm", f"{project.donation_area_sqm:,.1f}", "official_cleanup", 0.76))
    return rows


def hydrate_cleanup_observations(project: AutofillProjectData) -> AutofillProjectData:
    attach_observed(project, "site_area_sqm", project.site_area_sqm, "official_cleanup", 0.88)
    attach_observed(project, "target_building_coverage_ratio", project.target_building_coverage_ratio, "official_cleanup", 0.86)
    attach_observed(project, "target_far", project.target_far, "official_cleanup", 0.86)
    attach_observed(project, "current_households", project.current_households or project.owner_count, "official_cleanup", 0.86)
    attach_observed(project, "planned_households", project.planned_households, "official_cleanup", 0.82)
    attach_observed(project, "sale_households_total", project.sale_households_total, "official_cleanup", 0.80)
    attach_observed(project, "sale_households", project.sale_households, "official_cleanup", 0.80)
    attach_observed(project, "rental_households", project.rental_households, "official_cleanup", 0.80)
    attach_observed(project, "public_facility_area_sqm", project.public_facility_area_sqm, "official_cleanup", 0.78)
    attach_observed(project, "donation_area_sqm", project.donation_area_sqm, "official_cleanup", 0.76)
    return project


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
    planned_sale_total = extract_households_from_supply_table(sale_table)
    planned_rental = extract_households_from_supply_table(rental_table)
    public_facility_area_sqm, donation_area_sqm = extract_public_facility_areas(land_use_table, facility_table)
    existing_unit_mix_rows, unit_mix_source, unit_mix_confidence = choose_best_unit_mix_candidate(tables)
    member_seed = current_households or owner_count
    planned_general_sale = None
    if planned_sale_total is not None and member_seed is not None:
        planned_general_sale = max(planned_sale_total - member_seed, 0)
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
        planned_households=(planned_sale_total or 0) + (planned_rental or 0) or None,
        sale_households_total=planned_sale_total,
        sale_households=planned_general_sale,
        rental_households=planned_rental,
        public_facility_area_sqm=public_facility_area_sqm,
        donation_area_sqm=donation_area_sqm,
        existing_unit_mix_rows=existing_unit_mix_rows,
        unit_mix_source=unit_mix_source,
        unit_mix_confidence=unit_mix_confidence,
    )
    project.schedule_text = cleanup_fetch_schedule_text(cafe_id)
    project.source_records = normalize_cleanup_source_rows(project)
    project.search_source = "official_cleanup"
    sync_project_capability(project, "official_cleanup")
    add_source_health(project, "official_cleanup", "ok", "서울 정비몽땅 공식 표를 구조화했습니다.")
    project.external_links.append(("서울 공식 사업개요", summary_url))
    if project.source_url:
        project.external_links.append(("서울 공식 메인", project.source_url))
    return hydrate_cleanup_observations(project)


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


class CleanupAdapter:
    source = "official_cleanup"

    def search(self, query: str) -> list[SearchResult]:
        return [
            SearchResult(
                source=self.source,
                project_id=item.project_slug,
                title=item.project_name,
                subtitle=" / ".join(part for part in [item.district, item.business_type, item.progress_stage or "단계 미확인"] if part),
                url=item.source_url,
                confidence=0.88,
                capability="official_cleanup",
                structured_fields_count=count_structured_project_fields(item),
            )
            for item in cleanup_search_projects(query)
        ]

    def fetch(self, project_id: str) -> AutofillProjectData | None:
        return cleanup_fetch_project_summary(project_id)


def parse_naver_search_links(html_text: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    for match in re.finditer(r'href="(?P<href>/complexes/\d+[^"]*)".{0,240}?>(?P<label>[^<]+)</a>', html_text, re.S):
        href = unescape(match.group("href"))
        title = unescape(re.sub(r"\s+", " ", match.group("label"))).strip()
        if not title:
            continue
        results.append(
            SearchResult(
                source="naver_land",
                project_id=urllib.parse.urljoin("https://fin.land.naver.com", href),
                title=title,
                subtitle="네이버 부동산 공개 단지 페이지",
                url=urllib.parse.urljoin("https://fin.land.naver.com", href),
                confidence=0.40,
                capability="external_structured",
            )
        )
    return results


def naver_parse_area_pair(item: dict[str, object]) -> tuple[float | None, float | None]:
    for key in ("kbTendency", "kabTendency"):
        raw = str(item.get(key) or "")
        parts = [part for part in raw.split("^") if part]
        if len(parts) >= 2:
            supply = parse_float(parts[0])
            exclusive = parse_float(parts[1])
            if supply and exclusive:
                return supply, exclusive
    size_range = str(item.get("sizeRangeDisplay") or item.get("size") or "")
    if "~" in size_range:
        supply = parse_float(size_range.split("~", 1)[0])
        if supply:
            return supply, estimate_exclusive_area_from_supply_area(supply)
    supply = parse_float(size_range)
    if supply:
        return supply, estimate_exclusive_area_from_supply_area(supply)
    return None, None


def naver_mobile_search_complexes(query: str) -> list[dict[str, object]]:
    keyword = query.strip()
    if not keyword:
        return []
    url = f"https://m.land.naver.com/search/moreList?q={urllib.parse.quote(keyword)}&page=1"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.6",
            "Referer": f"https://m.land.naver.com/search?query={urllib.parse.quote(keyword)}",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    result = payload.get("result") or {}
    complexes = result.get("complexList") or []
    return [item for item in complexes if isinstance(item, dict)]


def naver_project_id_from_item(item: dict[str, object], query: str) -> str:
    hscp_no = str(item.get("hscpNo") or item.get("complexCode") or "").strip()
    complex_name = str(item.get("complexName") or item.get("hscpNm") or query).strip()
    return urllib.parse.urlencode({"hscpNo": hscp_no, "name": complex_name, "query": query}, doseq=False)


def naver_build_project_from_item(item: dict[str, object], query: str) -> AutofillProjectData:
    project_name = str(item.get("complexName") or item.get("hscpNm") or query).strip()
    supply_area_sqm, exclusive_area_sqm = naver_parse_area_pair(item)
    households = parse_int(str(item.get("householdNumber") or ""))
    floor_number = parse_float(str(item.get("floorNumber") or ""))
    project = AutofillProjectData(
        query=query,
        project_name=project_name,
        district=str(item.get("dvsnName") or item.get("dvsnNm") or "").strip(),
        business_type=str(item.get("complexTypeName") or "").strip(),
        project_kind=guess_project_kind(str(item.get("complexTypeName") or "")) if item.get("complexTypeName") else None,
        progress_stage=None,
        representative_lot=str(item.get("addressMobile") or item.get("address") or "").strip(),
        source_url=urllib.parse.urljoin("https://m.land.naver.com", str(item.get("url") or f"/search/result/{urllib.parse.quote(project_name)}")),
        search_source="naver_land",
        current_households=households,
        average_current_floors=floor_number,
        current_building_count=parse_int(str(item.get("buildingNumber") or "")),
    )
    project.external_links.append(("네이버 부동산 모바일 검색", f"https://m.land.naver.com/search/result/{urllib.parse.quote(project_name)}"))
    if project.source_url:
        project.external_links.append(("네이버 부동산 단지 링크", project.source_url))
    kgeop_keyword = project.representative_lot or f"{project.district} {project_name}".strip()
    if kgeop_keyword:
        project.external_links.append(("KGeoP 주소/필지 검색", f"https://kgeop.go.kr/cmm/unitySearch/getUnitySearchList.do?searchKeyword={urllib.parse.quote(kgeop_keyword)}"))
    if households is not None:
        attach_observed(project, "current_households", households, "naver_land", 0.76)
        project.source_records.append(record("current_households", str(households), "naver_land", 0.76))
    if floor_number is not None:
        attach_observed(project, "average_current_floors", floor_number, "naver_land", 0.58)
        project.source_records.append(record("avg_current_floors", f"{floor_number:.1f}", "naver_land", 0.52))
    if project.current_building_count is not None:
        project.source_records.append(record("building_count", str(project.current_building_count), "naver_land", 0.46))
    if supply_area_sqm or exclusive_area_sqm:
        supply = supply_area_sqm or estimate_supply_area_from_exclusive_area(exclusive_area_sqm or 84.0)
        exclusive = exclusive_area_sqm or estimate_exclusive_area_from_supply_area(supply)
        seed_households = households or 1
        label = infer_unit_mix_label(exclusive)
        project.existing_unit_mix_rows = [UnitMixRow(label=label, households=seed_households, exclusive_area_sqm=exclusive, supply_area_sqm=supply)]
        project.unit_mix_source = "naver_land"
        project.unit_mix_confidence = 0.62
    sync_project_capability(project, "external_structured")
    add_source_health(project, "naver_land", "partial", "네이버 모바일 검색 결과에서 단지 기본정보를 구조화했습니다.")
    return project


def naver_extract_metric(tokens: list[str], key: str, suffix: str = "") -> str | None:
    for idx, token in enumerate(tokens[:-1]):
        compact = re.sub(r"\s+", "", token)
        if compact == key and idx + 1 < len(tokens):
            value = tokens[idx + 1]
            if suffix and suffix not in value:
                continue
            return value
    return None


@cache_data(ttl=60 * 30, show_spinner=False)
def naver_search_projects(query: str) -> list[SearchResult]:
    keyword = query.strip()
    if not keyword:
        return []
    try:
        complexes = naver_mobile_search_complexes(keyword)
    except Exception:
        complexes = []
    if complexes:
        results: list[SearchResult] = []
        for item in complexes[:8]:
            project = naver_build_project_from_item(item, keyword)
            subtitle_parts = [project.district, project.business_type]
            if project.current_households:
                subtitle_parts.append(f"{project.current_households}세대")
            results.append(
                SearchResult(
                    source="naver_land",
                    project_id=naver_project_id_from_item(item, keyword),
                    title=project.project_name or keyword,
                    subtitle=" / ".join(part for part in subtitle_parts if part) or "네이버 부동산 모바일 검색 결과",
                    url=project.source_url,
                    confidence=0.66,
                    capability="external_structured",
                    structured_fields_count=count_structured_project_fields(project) + (1 if project.existing_unit_mix_rows else 0),
                    status_reason="네이버 모바일 검색 결과 기반 단지 기본정보",
                )
            )
        return results
    url = f"https://m.land.naver.com/search/result/{urllib.parse.quote(keyword)}"
    try:
        html_text = fetch_html(url)
        results = parse_naver_search_links(html_text)
        if results:
            return results[:8]
    except urllib.error.URLError:
        pass
    return [
        SearchResult(
            source="naver_land",
            project_id=url,
            title=f"{keyword} 네이버 공개 검색",
            subtitle="공개 검색 페이지를 보조 링크로 제공합니다.",
            url=url,
            confidence=0.18,
            capability="external_link_only",
            status_reason="정적 HTML에서 구조화 단지 정보를 찾지 못했습니다.",
        )
    ]


@cache_data(ttl=60 * 30, show_spinner=False)
def naver_fetch_project_summary(project_id: str) -> AutofillProjectData | None:
    if not project_id:
        return None
    if "=" in project_id and "&" in project_id:
        params = urllib.parse.parse_qs(project_id)
        hscp_no = (params.get("hscpNo") or [""])[0]
        query = (params.get("query") or params.get("name") or [""])[0]
        try:
            complexes = naver_mobile_search_complexes(query)
        except Exception:
            complexes = []
        for item in complexes:
            candidate_hscp = str(item.get("hscpNo") or item.get("complexCode") or "").strip()
            if hscp_no and candidate_hscp != hscp_no:
                continue
            return naver_build_project_from_item(item, query)
    try:
        html_text = fetch_html(project_id)
    except urllib.error.URLError:
        return None
    tokens = extract_text_tokens(html_text)
    title_match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    raw_title = unescape(title_match.group(1)).strip() if title_match else project_id
    project_name = raw_title.split(":")[0].split("-")[0].strip() or "네이버 공개 페이지"
    project = AutofillProjectData(
        query=project_name,
        project_name=project_name,
        district="",
        business_type="",
        project_kind=None,
        progress_stage=None,
        source_url=project_id,
        search_source="naver_land",
    )
    project.external_links.append(("네이버 부동산 공개 페이지", project_id))
    project.current_households = parse_int(naver_extract_metric(tokens, "총세대수", "세대"))
    project.target_far = parse_float(naver_extract_metric(tokens, "용적률", "%"))
    project.target_building_coverage_ratio = parse_float(naver_extract_metric(tokens, "건폐율", "%"))
    attach_observed(project, "current_households", project.current_households, "naver_land", 0.54)
    attach_observed(project, "target_far", project.target_far, "naver_land", 0.50)
    attach_observed(project, "target_building_coverage_ratio", project.target_building_coverage_ratio, "naver_land", 0.50)
    if project.current_households is not None:
        project.source_records.append(record("current_households", str(project.current_households), "naver_land", 0.54))
    if project.target_far is not None:
        project.source_records.append(record("target_far", f"{project.target_far:.1f}", "naver_land", 0.50))
    if project.target_building_coverage_ratio is not None:
        project.source_records.append(record("building_coverage_ratio", f"{project.target_building_coverage_ratio:.1f}", "naver_land", 0.50))
    is_generic_title = project_name.strip().lower() in {"npay 부동산", "naver", "네이버"}
    if is_generic_title and not any([project.current_households, project.target_far, project.target_building_coverage_ratio]):
        project.project_name = ""
    if count_structured_project_fields(project) >= 2:
        sync_project_capability(project, "external_structured")
        add_source_health(project, "naver_land", "partial", "일부 공개 메트릭만 구조화했습니다.")
    else:
        sync_project_capability(project, "external_link_only", "정적 HTML에서 단지 메트릭 추출에 실패해 링크만 제공합니다.")
        add_source_health(project, "naver_land", "link_only", project.search_status_reason)
    return project


class NaverComplexAdapter:
    source = "naver_land"

    def search(self, query: str) -> list[SearchResult]:
        return naver_search_projects(query)

    def fetch(self, project_id: str) -> AutofillProjectData | None:
        return naver_fetch_project_summary(project_id)


@cache_data(ttl=60 * 30, show_spinner=False)
def kgeop_search_projects(query: str) -> list[SearchResult]:
    keyword = query.strip()
    if not keyword:
        return []
    url = f"https://kgeop.go.kr/cmm/unitySearch/getUnitySearchList.do?searchKeyword={urllib.parse.quote(keyword)}"
    return [
        SearchResult(
            source="kgeop_public",
            project_id=url,
            title=f"{keyword} KGeoP 공개 지도",
            subtitle="주소/필지/위치 정합성 확인용 KGeoP 검색 링크",
            url=url,
            confidence=0.12,
            capability="external_link_only",
            status_reason="대지지분 직접 추출은 아직 지원하지 않고 KGeoP 검색 링크를 제공합니다.",
        )
    ]


@cache_data(ttl=60 * 30, show_spinner=False)
def kgeop_fetch_project_summary(project_id: str) -> AutofillProjectData | None:
    if not project_id:
        return None
    project = AutofillProjectData(
        query="",
        project_name="KGeoP 공개 지도",
        district="",
        business_type="",
        project_kind=None,
        progress_stage=None,
        source_url=project_id,
        search_source="kgeop_public",
    )
    project.external_links.append(("KGeoP 공개 지도", project_id))
    project.source_records.append(record("parser_status", "unsupported", "kgeop_public", 0.10, "공개 페이지는 보조 확인 링크로만 제공합니다."))
    sync_project_capability(project, "external_link_only", "공개 지도 링크만 제공합니다.")
    add_source_health(project, "kgeop_public", "link_only", project.search_status_reason)
    return project


class KGeoPAdapter:
    source = "kgeop_public"

    def search(self, query: str) -> list[SearchResult]:
        return kgeop_search_projects(query)

    def fetch(self, project_id: str) -> AutofillProjectData | None:
        return kgeop_fetch_project_summary(project_id)


def merge_autofill_projects(*projects: AutofillProjectData | None) -> AutofillProjectData | None:
    available = [project for project in projects if project is not None]
    if not available:
        return None
    base = available[0]
    for candidate in available[1:]:
        if not candidate:
            continue
        for field_name, observed_value in candidate.observed_fields.items():
            chosen = choose_observed_value(base.observed_fields.get(field_name), observed_value) or observed_value
            base.observed_fields[field_name] = chosen
            base.field_candidates.setdefault(field_name, []).extend(candidate.field_candidates.get(field_name, []))
        base.external_links = merge_external_links(base, candidate)
        if not base.project_name and candidate.project_name:
            base.project_name = candidate.project_name
        if not base.source_url and candidate.source_url:
            base.source_url = candidate.source_url
        if not base.existing_unit_mix_rows and candidate.existing_unit_mix_rows:
            base.existing_unit_mix_rows = list(candidate.existing_unit_mix_rows)
            base.unit_mix_source = candidate.unit_mix_source
            base.unit_mix_confidence = candidate.unit_mix_confidence
        if not base.planned_unit_mix_candidates and candidate.planned_unit_mix_candidates:
            base.planned_unit_mix_candidates = list(candidate.planned_unit_mix_candidates)
        base.source_records.extend(candidate.source_records)
        base.source_health.extend(candidate.source_health)
    for field_name, observed_value in base.observed_fields.items():
        try:
            current_value = getattr(base, field_name, None)
            source_rank = {"manual": 6, "document": 5, "official_cleanup": 4, "external_structured": 3, "naver_land": 2, "kgeop_public": 1, "simulation": 0}
            current_source = ""
            if field_name in base.field_candidates and base.field_candidates[field_name]:
                current_source = max(base.field_candidates[field_name], key=lambda item: (source_rank.get(item.source, 0), item.confidence)).source
            if current_value in (None, "", []) or source_rank.get(observed_value.source, 0) >= source_rank.get(current_source, 0):
                setattr(base, field_name, observed_value.value)
        except Exception:
            continue
    sync_project_capability(base, base.search_capability, base.search_status_reason)
    return base


def search_all_projects(query: str, include_external: bool) -> list[SearchResult]:
    adapters: list[SearchAdapter] = [CleanupAdapter()]
    if include_external:
        adapters.extend([NaverComplexAdapter(), KGeoPAdapter()])
    results: list[SearchResult] = []
    seen: set[tuple[str, str]] = set()
    for adapter in adapters:
        try:
            found = adapter.search(query)
        except Exception:
            continue
        for item in found:
            key = (item.source, item.project_id)
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
    return results[:18]


def fetch_project_from_search_result(result: SearchResult) -> AutofillProjectData | None:
    if result.source == "official_cleanup":
        return CleanupAdapter().fetch(result.project_id)
    if result.source == "naver_land":
        return NaverComplexAdapter().fetch(result.project_id)
    if result.source == "kgeop_public":
        return KGeoPAdapter().fetch(result.project_id)
    return None


def estimate_remaining_months(
    stage: str,
    autofill: AutofillProjectData | None,
    delay_one_year: bool,
    profile_name: str,
    scenario_name: str,
    project_kind: ProjectKind,
    reconstruction_style: ReconstructionStyle,
) -> tuple[float, str]:
    base_months = float(STAGE_BASE_MONTHS.get(stage, 72))
    scenario = SCENARIOS[scenario_name]
    profile = ASSUMPTION_PROFILES[profile_name]
    source = "manual"
    if project_kind == ProjectKind.REDEVELOPMENT:
        base_months *= 1.10
    elif reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        base_months *= 1.06
    schedule_text = (autofill.schedule_text if autofill else None) or ""
    if schedule_text:
        matches = DATE_RANGE_PATTERN.findall(schedule_text)
        if matches:
            try:
                now = datetime.now()
                delta_months_candidates: list[int] = []
                for start_text, end_text in matches:
                    for candidate_text in (start_text, end_text):
                        if not candidate_text:
                            continue
                        normalized = candidate_text.replace(".", "-").replace("/", "-")
                        year, month = [int(part) for part in normalized.split("-")[:2]]
                        delta_months_candidates.append(max((year - now.year) * 12 + (month - now.month), 0))
                if delta_months_candidates:
                    schedule_floor = float(STAGE_SCHEDULE_FLOORS.get(stage, 12))
                    if project_kind == ProjectKind.REDEVELOPMENT:
                        schedule_floor *= 1.10
                    elif reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
                        schedule_floor *= 1.06
                    base_months = max(max(delta_months_candidates), schedule_floor, 6)
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
    if inputs.site_area_sqm:
        return inputs.site_area_sqm, "official_cleanup" if inputs.lookup_enabled else "manual"
    if inputs.land_share:
        return inputs.land_share * inputs.current_households, "manual"
    if inputs.current_far:
        return current_gross_floor_area_sqm / max(inputs.current_far / 100.0, 0.01), "simulation"
    if inputs.current_building_coverage_ratio and inputs.average_current_floors:
        return current_gross_floor_area_sqm / max(inputs.current_building_coverage_ratio * inputs.average_current_floors, 0.01), "simulation"
    project = inputs.autofill_project
    if (
        project
        and project.search_source == "naver_land"
        and project.average_current_floors
        and current_gross_floor_area_sqm > 0
    ):
        heuristic_bcr = heuristic_current_building_coverage_ratio(project.average_current_floors, project.current_building_count)
        estimated_site_area = current_gross_floor_area_sqm / max(project.average_current_floors * heuristic_bcr, 0.01)
        return estimated_site_area, "naver_land_heuristic"
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
        project_kind=quick_inputs.project_kind,
        reconstruction_style=quick_inputs.reconstruction_style,
    )
    sale_rate_baseline = quick_inputs.sale_rate if quick_inputs.sale_rate is not None else SCENARIOS[BASELINE_SCENARIO_NAME]["sale_rate"]
    cash_rate_baseline = quick_inputs.cash_settlement_rate if quick_inputs.cash_settlement_rate is not None else SCENARIOS[BASELINE_SCENARIO_NAME]["cash_settlement_rate"]
    construction_cost_baseline = quick_inputs.construction_cost_per_pyeong or SCENARIOS[BASELINE_SCENARIO_NAME]["construction_cost_per_pyeong"]
    pf_rate_baseline = quick_inputs.pf_rate or SCENARIOS[BASELINE_SCENARIO_NAME]["pf_rate"]
    base_sale_rate = apply_scenario_to_baseline(sale_rate_baseline, scenario_name, "sale_rate", low=0.0, high=1.0)
    base_cash_rate = apply_scenario_to_baseline(cash_rate_baseline, scenario_name, "cash_settlement_rate", low=0.0, high=0.40)
    base_cost_per_pyeong = apply_scenario_to_baseline(construction_cost_baseline, scenario_name, "construction_cost_per_pyeong", low=1_000_000.0, high=30_000_000.0)
    base_pf_rate = apply_scenario_to_baseline(pf_rate_baseline, scenario_name, "pf_rate", low=0.0, high=0.30)
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
    land_based_flow = uses_land_based_flow(quick_inputs)
    floor_adj = floor_factor(quick_inputs.floor_no) if uses_apartment_reconstruction_flow(quick_inputs) else 1.0
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
        fallback_multiplier = 0.74 if land_based_flow else 0.78
        old_asset_estimate = quick_inputs.purchase_price * fallback_multiplier * floor_adj
        old_asset_source = "purchase_price_heuristic"

    member_count = simulation.member_households
    official_kind_matches = (
        quick_inputs.autofill_project is None
        or quick_inputs.autofill_project.project_kind is None
        or quick_inputs.autofill_project.project_kind == quick_inputs.project_kind
    )
    settlement_ready = (
        official_kind_matches
        and (
            not land_based_flow
            or (
                rights_inputs.appraised_old_asset_value is not None
                or official_price_reference is not None
                or rights_inputs.total_old_asset_value is not None
                or (quick_inputs.land_share is not None and quick_inputs.land_share > 0 and simulation.site_area_sqm is not None)
            )
        )
    )
    if parsed_notice and parsed_notice.cost_items.get("total_old_asset_value") and "total_old_asset_value" in quick_inputs.applied_document_fields:
        total_old_asset_value = parsed_notice.cost_items["total_old_asset_value"]
        total_old_asset_source = "document_total_old_asset"
    elif rights_inputs.total_old_asset_value:
        total_old_asset_value = rights_inputs.total_old_asset_value
        total_old_asset_source = "user_total_old_asset"
    elif land_based_flow and quick_inputs.land_share and simulation.site_area_sqm:
        share_ratio = safe_div(quick_inputs.land_share, simulation.site_area_sqm, 0.0)
        total_old_asset_value = safe_div(old_asset_estimate, share_ratio, old_asset_estimate * member_count) if share_ratio > 0 else old_asset_estimate * member_count
        total_old_asset_source = "scaled_individual_old_asset"
    else:
        total_old_asset_value = old_asset_estimate * member_count
        total_old_asset_source = "scaled_individual_old_asset"

    member_sale_price_ratio, member_sale_price_ratio_source = default_member_sale_price_ratio(
        quick_inputs,
        quick_inputs.current_stage,
        advanced_inputs.member_sale_price_ratio_override,
    )
    planned_unit_mix_rows, planned_unit_mix_source = resolve_planned_unit_mix_rows(
        quick_inputs,
        advanced_inputs,
        simulation.planned_households,
    )
    price_table = default_member_price_table(
        user_text=rights_inputs.member_price_text,
        doc_table=parsed_notice.member_price_table if parsed_notice else [],
        use_doc_table=quick_inputs.use_doc_price_table,
        project_kind=quick_inputs.project_kind,
        reconstruction_style=quick_inputs.reconstruction_style,
        comparison_new_price=quick_inputs.comparison_new_price,
        general_sale_price=quick_inputs.general_sale_price,
        general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
        purchase_price=quick_inputs.purchase_price,
        current_exclusive_area=quick_inputs.current_unit_exclusive_area,
        expected_new_area=rights_inputs.expected_new_exclusive_area,
        member_sale_price_ratio=member_sale_price_ratio,
        planned_unit_mix_rows=planned_unit_mix_rows,
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

    average_member_exclusive_area = weighted_average_exclusive_area(
        advanced_inputs.unit_mix_rows,
        rights_inputs.expected_new_exclusive_area or quick_inputs.current_unit_exclusive_area or 84.0,
    )
    average_member_supply_area = weighted_average_supply_area(
        advanced_inputs.unit_mix_rows,
        max(
            quick_inputs.current_unit_supply_area or 0.0,
            estimate_supply_area_from_exclusive_area(
                rights_inputs.expected_new_exclusive_area or quick_inputs.current_unit_exclusive_area or 84.0,
                project_kind=quick_inputs.project_kind,
                reconstruction_style=quick_inputs.reconstruction_style,
            ),
        ),
    )
    general_sale_reference_exclusive_area = max(
        estimate_exclusive_area_from_supply_area(
            simulation.average_supply_area_sqm,
            project_kind=quick_inputs.project_kind,
            reconstruction_style=quick_inputs.reconstruction_style,
        ),
        1.0,
    )
    general_sale_reference_supply_area = max(simulation.average_supply_area_sqm, average_member_supply_area, 1.0)
    benchmark_anchor_area = rights_inputs.expected_new_exclusive_area or average_member_exclusive_area or quick_inputs.current_unit_exclusive_area or 84.0
    benchmark_new_price = resolve_market_unit_price(
        general_sale_price=quick_inputs.general_sale_price,
        general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=quick_inputs.comparison_new_price,
        comparison_anchor_exclusive_area=benchmark_anchor_area,
        purchase_price=quick_inputs.purchase_price,
        target_exclusive_area=benchmark_anchor_area,
        target_supply_area_sqm=average_member_supply_area,
    )
    fallback_general_sale_unit_price = resolve_market_unit_price(
        general_sale_price=quick_inputs.general_sale_price,
        general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=quick_inputs.comparison_new_price,
        comparison_anchor_exclusive_area=benchmark_anchor_area,
        purchase_price=quick_inputs.purchase_price,
        target_exclusive_area=general_sale_reference_exclusive_area,
        target_supply_area_sqm=general_sale_reference_supply_area,
    )
    average_member_sale_price = resolve_market_unit_price(
        general_sale_price=quick_inputs.general_sale_price,
        general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=quick_inputs.comparison_new_price,
        comparison_anchor_exclusive_area=benchmark_anchor_area,
        purchase_price=quick_inputs.purchase_price,
        target_exclusive_area=average_member_exclusive_area,
        target_supply_area_sqm=average_member_supply_area,
    ) * member_sale_price_ratio
    rental_sale_price_per_pyeong_manwon, rental_price_source = default_rental_sale_price_per_pyeong_manwon(
        quick_inputs,
        advanced_inputs.rental_sale_price_per_pyeong_manwon,
    )
    if rights_inputs.member_price_text.strip() or (quick_inputs.use_doc_price_table and parsed_notice and parsed_notice.member_price_table):
        average_member_sale_price = statistics.mean(item.member_sale_price for item in price_table)

    if planned_unit_mix_source == "manual_override":
        mix_rows = planned_unit_mix_rows or [
            UnitMixRow(
                label="기준안",
                households=max(simulation.planned_households, 1),
                exclusive_area_sqm=benchmark_anchor_area,
                supply_area_sqm=max(simulation.average_supply_area_sqm, average_member_supply_area, 1.0),
            )
        ]
        rental_allocations = [0 for _ in mix_rows]
        remaining_rental = rental_households
        for index in sorted(range(len(mix_rows)), key=lambda idx: mix_rows[idx].exclusive_area_sqm):
            if remaining_rental <= 0:
                break
            allocated = min(mix_rows[index].households, remaining_rental)
            rental_allocations[index] = allocated
            remaining_rental -= allocated
        member_allocations = allocation_from_capacities(
            [max(mix_rows[idx].households - rental_allocations[idx], 0) for idx in range(len(mix_rows))],
            member_count,
        )
        general_allocations = [
            max(mix_rows[idx].households - rental_allocations[idx] - member_allocations[idx], 0)
            for idx in range(len(mix_rows))
        ]
        allocated_member_households = sum(member_allocations)
        rental_households = sum(rental_allocations)
        general_sale_households = sum(general_allocations)
        member_sale_revenue = 0.0
        general_sale_revenue = 0.0
        rental_revenue = 0.0
        for index, mix_row in enumerate(mix_rows):
            matched_price = price_table_lookup(price_table, mix_row.exclusive_area_sqm)
            member_unit_price = matched_price.member_sale_price if matched_price else resolve_market_unit_price(
                general_sale_price=quick_inputs.general_sale_price,
                general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
                general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
                comparison_new_price=quick_inputs.comparison_new_price,
                comparison_anchor_exclusive_area=benchmark_anchor_area,
                purchase_price=quick_inputs.purchase_price,
                target_exclusive_area=mix_row.exclusive_area_sqm,
                target_supply_area_sqm=mix_row.supply_area_sqm,
            ) * member_sale_price_ratio
            general_unit_price = resolve_market_unit_price(
                general_sale_price=quick_inputs.general_sale_price,
                general_sale_price_basis_exclusive_area=quick_inputs.general_sale_price_basis_exclusive_area,
                general_sale_price_per_pyeong_manwon=quick_inputs.general_sale_price_per_pyeong_manwon,
                comparison_new_price=quick_inputs.comparison_new_price,
                comparison_anchor_exclusive_area=benchmark_anchor_area,
                purchase_price=quick_inputs.purchase_price,
                target_exclusive_area=mix_row.exclusive_area_sqm,
                target_supply_area_sqm=mix_row.supply_area_sqm,
            )
            rental_unit_price = price_from_supply_pyeong(rental_sale_price_per_pyeong_manwon, mix_row.supply_area_sqm) or 0.0
            member_sale_revenue += member_allocations[index] * member_unit_price
            general_sale_revenue += general_allocations[index] * general_unit_price * base_sale_rate
            rental_revenue += rental_allocations[index] * rental_unit_price
        general_sale_unit_price = safe_div(general_sale_revenue, max(general_sale_households, 1), fallback_general_sale_unit_price)
        average_member_sale_price = safe_div(member_sale_revenue, max(allocated_member_households, 1), average_member_sale_price)
    else:
        member_sale_revenue = member_count * average_member_sale_price
        general_sale_unit_price = fallback_general_sale_unit_price
        general_sale_revenue = general_sale_households * general_sale_unit_price * base_sale_rate
        rental_supply_area_sqm = clamp(simulation.average_supply_area_sqm * 0.80, 75.0, 95.0)
        rental_unit_price = price_from_supply_pyeong(rental_sale_price_per_pyeong_manwon, rental_supply_area_sqm) or 0.0
        rental_revenue = rental_households * rental_unit_price
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
    total_revenue = member_sale_revenue + general_sale_revenue + rental_revenue + ancillary_revenue + other_disposal_revenue

    if parsed_notice and "total_revenue" in quick_inputs.applied_document_fields and "total_revenue" in parsed_notice.revenue_items:
        total_revenue = parsed_notice.revenue_items["total_revenue"]
    if parsed_notice and "total_cost" in quick_inputs.applied_document_fields and "total_cost" in parsed_notice.cost_items:
        total_cost = parsed_notice.cost_items["total_cost"]

    proportional_ratio = safe_div(total_revenue - total_cost, total_old_asset_value, 0.0) * 100.0
    if parsed_notice and "proportional_ratio" in quick_inputs.applied_document_fields and parsed_notice.proportional_ratio is not None:
        proportional_ratio = parsed_notice.proportional_ratio
    display_proportional_ratio = proportional_ratio if settlement_ready else None
    rights_value = old_asset_estimate * (proportional_ratio / 100.0) if settlement_ready else 0.0

    allocations: list[dict[str, float | str]] = []
    low_coverage_allocations: list[dict[str, float | str]] = []
    if settlement_ready:
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
    if settlement_ready:
        quick_settlement_amount = average_member_sale_price - rights_value
        selected_settlement_amount = float(selected["예상 추가분담금"]) if selected else quick_settlement_amount
    else:
        quick_settlement_amount = None
        selected_settlement_amount = None
    selected_settlement_payment = max(selected_settlement_amount or 0.0, 0.0)
    selected_refund_amount = max(-(selected_settlement_amount or 0.0), 0.0)

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
        capital_interest = selected_settlement_payment * max(base_pf_rate + 0.01, 0.04) * years * 0.45
        disposal_cost = gross_exit_value * advanced_inputs.brokerage_rate
        pretax_profit = gross_exit_value - disposal_cost + selected_refund_amount - (
            quick_inputs.purchase_price
            + acquisition_cost
            + holding_cost
            + selected_settlement_payment
            + capital_interest
        )
        after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * advanced_inputs.capital_gains_effective_rate
        total_outflow = (
            quick_inputs.purchase_price
            + acquisition_cost
            + holding_cost
            + selected_settlement_payment
            + capital_interest
        )
        roi = safe_div(after_tax_profit, total_outflow, 0.0)
        net_exit_inflow = gross_exit_value - disposal_cost + selected_refund_amount - max(pretax_profit, 0.0) * advanced_inputs.capital_gains_effective_rate
        irr = (net_exit_inflow / total_outflow) ** (1.0 / years) - 1.0 if total_outflow > 0 and net_exit_inflow > 0 else None
        break_even_purchase = max(
            (gross_exit_value - disposal_cost - holding_cost + selected_refund_amount - selected_settlement_payment - capital_interest)
            / max(1.0 + advanced_inputs.acquisition_rate, 0.01),
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
        "추정비례율": display_proportional_ratio,
        "세대당 평균 정산액": average_member_sale_price - rights_value if settlement_ready else None,
        "임대주택수입": rental_revenue,
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
                bool(quick_inputs.general_sale_price or quick_inputs.general_sale_price_per_pyeong_manwon or quick_inputs.comparison_new_price),
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
            variant_total_revenue = member_sale_revenue + variant_sale_revenue + rental_revenue + ancillary_revenue + other_disposal_revenue
            variant_total_cost = total_cost - direct_construction_cost + direct_construction_cost * cost_multiplier
            variant_ratio = safe_div(variant_total_revenue - variant_total_cost, total_old_asset_value, 0.0) * 100.0
            sensitivity_rows.append({"판매율": f"{sale_rate * 100:.0f}%", "공사비 배수": f"{cost_multiplier:.2f}x", "비례율": f"{variant_ratio:.2f}%"})

    land_share_est = safe_div(simulation.site_area_sqm or 0.0, quick_inputs.current_households, 0.0) if simulation.site_area_sqm else 0.0
    top_drivers = simple_top_drivers(time_cost_to_exit, direct_construction_cost, selected_settlement_amount or 0.0)
    cost_note = "재개발 세입자 보상비를 포함했습니다." if quick_inputs.project_kind == ProjectKind.REDEVELOPMENT else "재건축은 주거이전비·영업손실보상비를 기본 제외했습니다."
    if not settlement_ready:
        first_line = "재개발 정산액은 대지지분 또는 감정가 기준이 없어서 계산에서 제외했습니다. 지금 결과는 사업수지와 출구가격 중심의 빠른 검토입니다."
    elif selected:
        first_line = f"현재 입력 기준 추천 평형은 {selected['평형']}이고 예상 정산액은 {fmt_settlement(selected_settlement_amount)}입니다."
    else:
        first_line = f"현재 입력 기준 세대당 평균 정산액은 {fmt_settlement(quick_settlement_amount)}입니다."
    if not settlement_ready:
        second_line = f"재개발은 내 대지지분, 감정가, 권리가액 자료가 없으면 환급금/추가분담금 추정이 쉽게 왜곡됩니다. 특히 공식 사업유형과 다른 모드 선택 시 오차가 커집니다."
    elif upsize_option is not None:
        upsize_delta = float(upsize_option["전용㎡"]) - quick_inputs.current_unit_exclusive_area
        second_line = f"한 단계 넓힌 {upsize_option['평형']} 기준 정산액은 {fmt_settlement(float(upsize_option['예상 추가분담금']))}이고, 현재보다 전용 {upsize_delta:.1f}㎡ 넓어지는 가정입니다."
    else:
        second_line = f"준공 직후 매도 기준 세후순이익은 {fmt_money(float(selected_exit['세후 순이익']))}입니다. ROI는 {fmt_pct(float(selected_exit['ROI']))}로 참고만 보세요."
    if quick_inputs.reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER:
        cost_note = "단독주택 묶음형 재건축은 대지지분 중심으로 계산하고, 세입자 보상비는 자동 가산하지 않았습니다."
    if not settlement_ready:
        first_line = "토지형 사업은 대지지분·감정가·권리가액 근거가 없으면 정산액을 계산에서 제외합니다. 지금 결과는 사업수지와 출구가격 중심의 빠른 검토입니다."
        second_line = "내 대지지분 또는 감정가가 없으면 환급금/추가분담금 추정은 쉽게 왜곡됩니다. 특히 토지형 재건축과 재개발은 아파트 평형 정보보다 토지 기준값이 더 중요합니다."
    summary_lines = [
        first_line,
        second_line,
        f"예상 총세대수는 {simulation.planned_households:,}세대, 일반분양은 {general_sale_households:,}세대({fmt_pct(general_sale_ratio)})로 계산했습니다.",
        f"준공 후 공급 평형 계획은 {humanize_source(planned_unit_mix_source)} 기준이며, {', '.join(f'{row.label} {row.households}세대' for row in planned_unit_mix_rows[:4]) or '자동안 없음'}으로 반영했습니다.",
        f"손익분기 매수가는 {fmt_money(break_even_purchase_price)}, 권장 최대 매수가는 {fmt_money(max_bid_price)}입니다.",
        f"대지지분은 세대당 약 {land_share_est:,.2f}㎡로 추정했고 출처는 {humanize_source(simulation.site_source)}입니다. {cost_note}",
        f"금융비는 PF 조달비율 {fmt_pct(pf_financing_ratio)}, PF 이자 {pf_interest_months:.0f}개월, 세대당 평균 이주비 {fmt_money(average_move_loan_amount)}, 이주비 대여 {move_loan_duration_months:.0f}개월 가정입니다.",
        f"조합원 분양가는 일반분양 대비 {fmt_pct(member_sale_price_ratio)}를 기본 가정으로 두고, 임대주택 수입은 평당 {rental_sale_price_per_pyeong_manwon:,.0f}만원 기준으로 반영했습니다.",
        f"가장 영향이 큰 요인은 {', '.join(top_drivers)}입니다.",
    ]

    if quick_inputs.land_share:
        summary_lines[5] = f"입력한 내 대지지분은 {quick_inputs.land_share:,.2f}㎡이고, 구역면적 출처는 {humanize_source(simulation.site_source)}입니다. {cost_note}"
    elif simulation.site_area_sqm and quick_inputs.current_households:
        summary_lines[5] = f"구역면적 기준 세대당 평균 부지면적 참고치는 약 {land_share_est:,.2f}㎡이고 출처는 {humanize_source(simulation.site_source)}입니다. 이 값은 내 대지지분과 다를 수 있습니다. {cost_note}"
    if uses_land_based_flow(quick_inputs) and quick_inputs.land_share and quick_inputs.autofill_project and quick_inputs.autofill_project.site_area_sqm:
        implied_total_site = quick_inputs.land_share * quick_inputs.current_households
        official_site = quick_inputs.autofill_project.site_area_sqm
        ratio = safe_div(implied_total_site, official_site, 0.0)
        if ratio < 0.6 or ratio > 1.4:
            summary_lines.insert(2, f"입력한 대지지분 x 권리자 수로 본 총면적은 {implied_total_site:,.0f}㎡인데, 서울 공식 구역면적은 {official_site:,.0f}㎡입니다. 대지지분 단위(㎡/평)와 값 자체를 다시 확인하세요.")

    records.extend(
        [
            record("old_asset_estimate", f"{old_asset_estimate:,.0f}", old_asset_source, 0.78),
            record("total_old_asset_value", f"{total_old_asset_value:,.0f}", total_old_asset_source, 0.68),
            record("adjustment_factor", f"{adj_factor:.3f}", adj_source, 0.70),
            record("remaining_months", f"{remaining_months:.1f}", duration_source, 0.66),
            record("total_revenue", f"{total_revenue:,.0f}", "engine", 0.70),
            record("total_cost", f"{total_cost:,.0f}", "engine", 0.70),
            record("proportional_ratio", "-" if display_proportional_ratio is None else f"{display_proportional_ratio:.2f}", "engine", 0.70),
            record("member_sale_price_ratio", f"{member_sale_price_ratio * 100:.1f}%", member_sale_price_ratio_source, 0.66),
            record("rental_revenue", f"{rental_revenue:,.0f}", rental_price_source, 0.64),
            record("planned_households", str(simulation.planned_households), simulation.sources["households"], 0.70),
            record("general_sale_ratio", f"{general_sale_ratio * 100:.2f}%", simulation.sources["general_sale_ratio"], 0.68),
            record("planned_unit_mix_source", planned_unit_mix_source, planned_unit_mix_source, 0.60, ", ".join(f"{row.label}:{row.households}" for row in planned_unit_mix_rows[:5])),
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
        additional_cash_needed=selected_settlement_amount,
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
            "member_sale_price_ratio": member_sale_price_ratio,
            "general_sale_price_basis_exclusive_area": quick_inputs.general_sale_price_basis_exclusive_area or 84.0,
            "general_sale_price_per_pyeong_manwon": quick_inputs.general_sale_price_per_pyeong_manwon or 0.0,
            "rental_sale_price_per_pyeong_manwon": rental_sale_price_per_pyeong_manwon,
        },
        summary_lines=summary_lines,
        source_records=records,
        sensitivity_rows=sensitivity_rows,
        simulation_result=simulation,
        feasibility_checks=build_feasibility_checks(
            quick_inputs,
            simulation,
            bool(advanced_inputs.unit_mix_rows),
            bool(advanced_inputs.planned_unit_mix_rows),
        ),
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
            if show_advanced_detail and settlement_ready
            else None
        ),
        old_asset_estimate=old_asset_estimate if show_advanced_detail and settlement_ready else None,
        total_old_asset_value=total_old_asset_value if show_advanced_detail and settlement_ready else None,
        rights_value=rights_value if show_advanced_detail and settlement_ready else None,
        old_asset_source=old_asset_source if show_advanced_detail and settlement_ready else None,
        total_old_asset_source=total_old_asset_source if show_advanced_detail and settlement_ready else None,
        adjustment_factor=adj_factor if show_advanced_detail and settlement_ready else None,
        floor_factor=floor_adj if show_advanced_detail and settlement_ready else None,
        price_table=price_table if show_advanced_detail and settlement_ready else [],
        allocation_options=allocations,
        planned_unit_mix_rows=planned_unit_mix_rows,
        planned_unit_mix_source=planned_unit_mix_source,
    )


def source_badge(text: str, tone: str = "base") -> str:
    color_map = {"base": "#274754", "ok": "#2f6a42", "warn": "#845421"}
    background_map = {"base": "#e6f2f5", "ok": "#e7f4ea", "warn": "#fff1df"}
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;"
        f"font-weight:700;margin-right:6px;background:{background_map[tone]};color:{color_map[tone]};'>{escape(text)}</span>"
    )


def capability_badge(capability: str, reason: str = "") -> str:
    labels = {
        "official_cleanup": ("공식 구조화", "ok"),
        "external_structured": ("외부 구조화", "base"),
        "external_link_only": ("링크 확인용", "warn"),
    }
    label, tone = labels.get(capability, ("자동조회", "base"))
    suffix = f" · {reason}" if reason else ""
    return source_badge(f"{label}{suffix}", tone)


def unit_mix_rows_to_text(rows: list[UnitMixRow]) -> str:
    return "\n".join(f"{row.label},{row.households},{row.exclusive_area_sqm:.1f},{row.supply_area_sqm:.1f}" for row in rows)


def default_existing_unit_mix_text(
    project: AutofillProjectData | None,
    current_exclusive_area: float,
    current_supply_area: float,
    current_households: int,
) -> str:
    if project and project.existing_unit_mix_rows:
        return unit_mix_rows_to_text(project.existing_unit_mix_rows)
    return default_unit_mix_text(current_exclusive_area, current_supply_area, current_households)


def default_planned_unit_mix_text(project: AutofillProjectData | None) -> str:
    if project and project.planned_unit_mix_candidates:
        return unit_mix_rows_to_text(project.planned_unit_mix_candidates)
    return ""


def precision_gap_messages(quick_inputs: QuickDealInputs, advanced_inputs: AdvancedProjectInputs) -> list[str]:
    messages: list[str] = []
    if quick_inputs.project_kind == ProjectKind.RECONSTRUCTION and quick_inputs.reconstruction_style == ReconstructionStyle.APARTMENT and not advanced_inputs.unit_mix_rows:
        messages.append("기존 평형 분포가 없어서 현재 연면적과 조합원 분포를 단일 기준 면적으로 추정했습니다.")
    if not advanced_inputs.rights_inputs.expected_new_exclusive_area:
        messages.append("예상 새 전용면적이 없어서 배정평형 비교를 보수적인 기본값으로 계산했습니다.")
    if not quick_inputs.general_sale_price_basis_exclusive_area and not quick_inputs.general_sale_price_per_pyeong_manwon:
        messages.append("일반분양 기준 면적이 없어 일반분양가를 비교 신축 시세 기준으로 환산했습니다.")
    if uses_land_based_flow(quick_inputs) and not quick_inputs.land_share:
        messages.append("대지지분이 없어서 토지형 사업의 정산액 왜곡 가능성이 큽니다.")
    return messages


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
    badge_text = {
        "official_cleanup": source_badge("서울 공식값 채택", "ok"),
        "naver_land": source_badge("네이버 공개값", "base"),
        "kgeop_public": source_badge("KGeoP 확인 링크", "warn"),
    }
    external_links = "".join(
        f"<li><a href='{escape(url)}' target='_blank'>{escape(label)}</a></li>"
        for label, url in project.external_links[:4]
        if url
    )
    card_html = (
        "<div class='section-card'>"
        f"<div class='soft-title'>{escape(project.project_name)}</div>"
        f"<div>{badge_text.get(project.search_source, source_badge('자동조회', 'base'))}{capability_badge(project.search_capability, project.search_status_reason)}{source_badge(project.business_type or '사업유형 미확인')}{source_badge((project.project_kind.value if project.project_kind else '유형 미확인'), 'base')}</div>"
        f"<p class='mini-note'>대표지번: {escape(project.representative_lot or '-')} / 조합원·권리자 수: {project.current_households or project.owner_count or '-'} / 계획 세대수: {project.planned_households or '-'}</p>"
        f"<p class='mini-note'>목표 건폐율: {project.target_building_coverage_ratio or '-'}% / 목표 용적률: {project.target_far or '-'}% / 분양주택: {project.sale_households_total or '-'}세대 / 추정 일반분양: {project.sale_households or '-'}세대 / 임대: {project.rental_households or '-'}세대</p>"
        f"<p class='mini-note'>공공시설 반영면적: {project.public_facility_area_sqm or '-'}㎡ / 명시 기부채납: {project.donation_area_sqm or '-'}㎡ / 출처: {humanize_source(project.search_source)}</p>"
        f"<p class='mini-note'>평균 층수 후보: {project.average_current_floors or '-'}층 / 동수 후보: {project.current_building_count or '-'}개동</p>"
        f"<p class='mini-note'>세대구성 후보: {len(project.existing_unit_mix_rows) or len(project.planned_unit_mix_candidates)}건 / 반영 출처: {humanize_source(project.unit_mix_source)}</p>"
        + (f"<div class='mini-note' style='margin-top:8px;'><strong>외부 확인 링크</strong><ul style='margin:6px 0 0 18px;'>{external_links}</ul></div>" if external_links else "")
        + "</div>"
    )
    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


def core_result_rows(result: QuickResult) -> list[dict[str, str]]:
    upsize_text = "-"
    if result.upsize_allocation is not None:
        upsize_text = fmt_settlement(float(result.upsize_allocation["예상 추가분담금"]))
    return [
        {
            "추천 평형 정산액": fmt_settlement(result.additional_cash_needed),
            "한 단계 확장": upsize_text,
            "손익분기 매수가": fmt_money(result.break_even_purchase_price),
            "일반분양 세대수": f"{result.simulation_result.general_sale_households:,}세대",
            "신뢰도": f"{result.confidence_report.label} ({result.confidence_report.total:.1f}점)",
        }
    ]


def why_rows(result: QuickResult) -> list[dict[str, str]]:
    price_mode = (
        f"공급평당가 우선 ({result.assumption_summary['general_sale_price_per_pyeong_manwon']:,.0f}만원/평)"
        if result.assumption_summary.get("general_sale_price_per_pyeong_manwon")
        else f"기준 전용 총액 앵커 ({result.assumption_summary.get('general_sale_price_basis_exclusive_area', 84.0):.0f}㎡ 기준)"
    )
    return [
        {"구분": "수입", "항목": "총수입", "값": fmt_money(result.project_summary["총수입"])},
        {"구분": "수입", "항목": "임대주택수입", "값": fmt_money(result.project_summary["임대주택수입"])},
        {"구분": "지출", "항목": "총지출", "값": fmt_money(result.project_summary["총지출"])},
        {"구분": "지출", "항목": "본공사비", "값": fmt_money(result.project_summary["본공사비"])},
        {"구분": "지출", "항목": "금융비", "값": fmt_money(result.project_summary["금융비"])},
        {"구분": "가정", "항목": "조합원 분양가율", "값": fmt_pct(result.assumption_summary["member_sale_price_ratio"])},
        {"구분": "가정", "항목": "일반분양가 기준", "값": price_mode},
        {"구분": "가정", "항목": "PF / 이주비", "값": f"PF {fmt_pct(result.assumption_summary['pf_rate'])}, {result.assumption_summary['pf_interest_months']:.0f}개월 / 이주비 {fmt_money(result.assumption_summary['average_move_loan_amount'])}"},
        {"구분": "가정", "항목": "자동추정 요약", "값": f"일반분양 {result.simulation_result.general_sale_households:,}세대 / 임대 {result.simulation_result.rental_households:,}세대 / 기부채납 {fmt_pct(result.simulation_result.donation_ratio)}"},
        {"구분": "가정", "항목": "임대수입 기준", "값": f"평당 {result.assumption_summary['rental_sale_price_per_pyeong_manwon']:,.0f}만원"},
    ]


def project_summary_rows(result: QuickResult) -> list[dict[str, str]]:
    return [
        {"항목": "총수입", "값": fmt_money(result.project_summary["총수입"])},
        {"항목": "총지출", "값": fmt_money(result.project_summary["총지출"])},
        {"항목": "추정비례율", "값": fmt_plain_pct(result.project_summary["추정비례율"])},
        {"항목": "세대당 평균 정산액", "값": fmt_settlement(result.project_summary["세대당 평균 정산액"])},
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
                "예상 정산액": fmt_settlement(float(row["예상 추가분담금"])),
                "커버율": fmt_pct(float(row["커버율"])),
                "판정": str(row["판정"]),
            }
        )
    return rows


def planned_unit_mix_display_rows(result: QuickResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in result.planned_unit_mix_rows:
        rows.append(
            {
                "타입": item.label,
                "세대수": f"{item.households:,}세대",
                "전용㎡": f"{item.exclusive_area_sqm:,.1f}",
                "공급㎡": f"{item.supply_area_sqm:,.1f}",
                "출처": humanize_source(result.planned_unit_mix_source),
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
        {"항목": "준공 후 평형 계획", "값": humanize_source(result.planned_unit_mix_source), "출처": humanize_source(result.planned_unit_mix_source)},
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
            upsize_text = fmt_settlement(float(result.upsize_allocation["예상 추가분담금"]))
        rows.append(
            {
                "시나리오": result.scenario_name,
                "추천 평형 정산액": fmt_settlement(result.additional_cash_needed),
                "한 단계 확장": upsize_text,
                "손익분기 매수가": fmt_money(result.break_even_purchase_price),
                "기준 대비": result.scenario_delta_summary or "-",
                "일반분양 세대수": f"{result.simulation_result.general_sale_households:,}세대",
                "시나리오 가정": f"분양률 {fmt_pct(result.assumption_summary['sale_rate'])} / 공사비 {result.assumption_summary['construction_cost_per_pyeong'] / 10_000:,.0f}만원/평 / PF {fmt_pct(result.assumption_summary['pf_rate'])} / 기간 {result.remaining_months / 12:.1f}년",
                "신뢰도": f"{result.confidence_report.label} ({result.confidence_report.total:.1f}점)",
            }
        )
    return rows


def annotate_scenario_results(results: list[QuickResult]) -> tuple[bool, str]:
    baseline = next((item for item in results if item.scenario_name == BASELINE_SCENARIO_NAME), results[0] if results else None)
    if baseline is None:
        return False, ""
    max_break_even_delta = 0.0
    max_settlement_delta = 0.0
    for result in results:
        delta_parts: list[str] = []
        if result.break_even_purchase_price and baseline.break_even_purchase_price:
            break_even_delta = result.break_even_purchase_price - baseline.break_even_purchase_price
            max_break_even_delta = max(max_break_even_delta, abs(break_even_delta))
            if result is baseline:
                delta_parts.append("기준 입력값")
            elif abs(break_even_delta) >= 10_000_000:
                delta_parts.append(f"매수가 {break_even_delta / 100_000_000:+.2f}억")
        if result.additional_cash_needed is not None and baseline.additional_cash_needed is not None:
            settlement_delta = result.additional_cash_needed - baseline.additional_cash_needed
            max_settlement_delta = max(max_settlement_delta, abs(settlement_delta))
            if result is not baseline and abs(settlement_delta) >= 10_000_000:
                delta_parts.append(f"정산액 {settlement_delta / 100_000_000:+.2f}억")
        result.scenario_delta_summary = " / ".join(delta_parts) if delta_parts else ("기준 입력값" if result is baseline else "차이 작음")
    visible = max_break_even_delta >= 30_000_000 or max_settlement_delta >= 20_000_000
    for result in results:
        result.scenario_visibility = visible
    summary = (
        f"기준 대비 최대 손익분기 매수가 차이는 {max_break_even_delta / 100_000_000:.2f}억, 정산액 차이는 {max_settlement_delta / 100_000_000:.2f}억입니다."
        if visible
        else "현재 입력에서는 낙관·기준·보수 시나리오 차이가 작아서 표를 접어도 될 정도입니다."
    )
    return visible, summary


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
    st.markdown("<div class='section-card'><div class='soft-title'>핵심 요약</div></div>", unsafe_allow_html=True)
    for line in result.summary_lines[:4]:
        st.markdown(f"<div class='result-blurb'>{escape(line)}</div>", unsafe_allow_html=True)
    render_table(core_result_rows(result), "핵심 결과")


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
        "<p class='mini-note'>이 계산기는 ROI보다 평형별 정산액(추가분담 또는 환급)과 손익분기 매수가를 먼저 보여주도록 설계했습니다. ROI는 하단 시나리오 표에서 보조지표로만 확인하세요.</p>"
        "<p class='mini-note'>일반분양 평균가는 준공 또는 분양 시점 기준의 예상 일반분양 평균가입니다. 현재 주변 실거래가와 같은 의미가 아닙니다.</p>"
        "<p class='mini-note'>일반분양가는 반드시 기준 전용면적과 같이 넣어야 합니다. 예를 들어 84㎡ 기준 14억인데 59㎡에 그대로 쓰면 사업수지가 크게 왜곡됩니다.</p>"
        "<p class='mini-note'>목표 용적률과 목표 건폐율을 같이 넣으면 총세대수와 평균층수를 자동 점검합니다. 목표 건폐율이 없으면 세대수 과다 경고는 약해집니다.</p>"
        "<p class='mini-note'>기부채납 비율은 도로·공원·공공시설로 빠지는 면적을 묶어 반영한 간편값이며, 공식 토지이용계획이 있으면 그 값이 우선합니다.</p>"
        "<p class='mini-note'>임대주택 비율은 공식 주택공급계획이 있으면 그 값이 우선하고, 없으면 사업유형과 프리셋으로 자동 추정합니다.</p>"
        f"<p class='mini-note'>{escape(kind_text)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def default_unit_mix_text(current_exclusive_area: float, current_supply_area: float, current_households: int) -> str:
    guessed_sizes = sorted({59.0, 74.0, 84.0, float(round(current_exclusive_area))})
    if current_exclusive_area >= 100:
        guessed_sizes.append(101.0)
    guessed_sizes = sorted({size for size in guessed_sizes if size > 0})
    weights = [0.20, 0.15, 0.45, 0.20] if len(guessed_sizes) >= 4 else [0.30, 0.20, 0.50]
    counts = allocate_counts_by_weights(current_households, weights[: len(guessed_sizes)])
    rows: list[str] = []
    for size, households in zip(guessed_sizes, counts):
        if households <= 0:
            continue
        supply = current_supply_area if abs(size - current_exclusive_area) < 0.1 else estimate_supply_area_from_exclusive_area(size)
        rows.append(f"{infer_unit_mix_label(size)},{households},{size:.1f},{supply:.1f}")
    return "\n".join(rows) or f"{infer_unit_mix_label(current_exclusive_area)},{current_households},{current_exclusive_area:.1f},{current_supply_area:.1f}"


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

    scenario_focus = BASELINE_SCENARIO_NAME
    st.markdown("### 1. 프로젝트 찾기")
    with st.expander("계산 설정", expanded=False):
        s1, s2, s3 = st.columns(3)
        with s1:
            calc_mode = st.radio("작업 방식", ["빠른 검토", "정밀 계산"], horizontal=True)
            assumption_profile = st.select_slider("가정 프리셋", options=list(ASSUMPTION_PROFILES.keys()), value="기준")
        with s2:
            lookup_enabled = st.checkbox("서울 공식값 자동조회", value=True)
            use_external_lookup = st.checkbox("외부 소스 추가조회", value=False)
        with s3:
            aggressive_upsize = st.checkbox("공격적 평형 업사이즈 허용", value=False)
            uploaded_files = st.file_uploader("문서 업로드", type=["pdf", "csv"], accept_multiple_files=True)
        st.caption("기부채납, 임대비율, 일반분양비율을 잘 모르면 `기준` 프리셋으로 먼저 보고 필요할 때만 자동값을 수정하세요.")

    parsed_notices: list[ParsedProjectNotice] = []
    if uploaded_files:
        for file in uploaded_files:
            parsed_notices.append(try_parse_uploaded_notice(file.name, file.getvalue()))
    merged_notice = merge_notices(parsed_notices)

    autofill_project: AutofillProjectData | None = None
    search_query = ""
    if lookup_enabled:
        st.caption("서울 공식값은 기본 자동조회로 두고, 외부 소스 추가조회를 켜면 네이버/KGeoP 공개 페이지를 보조 링크로만 함께 붙입니다.")
        search_query = st.text_input("프로젝트명 또는 단지명 검색", value="", placeholder="예: 방화6, 우면한라, 개포주공")
        search_results = search_all_projects(search_query, use_external_lookup) if search_query.strip() else []
        if search_query and not search_results:
            st.warning("일치하는 공개 검색 결과를 찾지 못했습니다. 아래 수동 입력으로 계속 진행할 수 있습니다.")
        if search_results:
            labels = [
                f"[{humanize_source(item.source)} · {item.capability}] {item.title} / {item.subtitle}{(' / ' + item.status_reason) if item.status_reason else ''}"
                for item in search_results
            ]
            selected_label = st.selectbox("검색 결과", labels)
            selected_result = search_results[labels.index(selected_label)]
            primary_project = fetch_project_from_search_result(selected_result)
            supplemental_projects: list[AutofillProjectData | None] = []
            if use_external_lookup and selected_result.source == "official_cleanup":
                for item in search_results:
                    if item.source == "official_cleanup":
                        continue
                    supplemental_projects.append(fetch_project_from_search_result(item))
            autofill_project = merge_autofill_projects(primary_project, *supplemental_projects)
            if autofill_project:
                cleanup_hit = next((item for item in cleanup_search_projects(search_query) if item.project_slug == selected_result.project_id), None) if selected_result.source == "official_cleanup" else None
                if cleanup_hit:
                    autofill_project.progress_stage = cleanup_hit.progress_stage or autofill_project.progress_stage
                    autofill_project.project_name = cleanup_hit.project_name or autofill_project.project_name
                    autofill_project.district = cleanup_hit.district or autofill_project.district
                    autofill_project.representative_lot = cleanup_hit.representative_lot or autofill_project.representative_lot
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
    reconstruction_style = ReconstructionStyle.APARTMENT
    if project_kind == ProjectKind.RECONSTRUCTION:
        reconstruction_style_value = st.radio(
            "재건축 세부유형",
            [ReconstructionStyle.APARTMENT.value, ReconstructionStyle.DETACHED_CLUSTER.value],
            index=0,
            horizontal=True,
            help="아파트 단지 재건축이면 공동주택형, 단독주택·다가구·다세대 여러 필지를 묶는 재건축이면 단독주택 묶음형을 선택하세요.",
        )
        reconstruction_style = ReconstructionStyle(reconstruction_style_value)
    land_based_reconstruction = reconstruction_style == ReconstructionStyle.DETACHED_CLUSTER
    if autofill_project and autofill_project.project_kind and autofill_project.project_kind != project_kind:
        st.warning(f"서울 공식 사업유형은 `{autofill_project.project_kind.value}`입니다. 지금 `{project_kind.value}` 모드로 계산하면 수익성과 정산액이 크게 왜곡될 수 있습니다.")
    with st.expander("입력 가이드", expanded=False):
        render_input_guide(project_kind)
    if land_based_reconstruction:
        st.caption("단독주택 묶음형 재건축은 아파트 평형보다 대지지분과 권리자 수가 더 중요해서, 입력 화면과 정산액 로직을 토지형으로 전환합니다.")
    redevelopment_base_exclusive_area = 59.0
    redevelopment_base_supply_area = 75.6
    autofill_exclusive_default = 84.0
    autofill_supply_default = 107.7
    if autofill_project and autofill_project.existing_unit_mix_rows:
        autofill_exclusive_default = weighted_average_exclusive_area(autofill_project.existing_unit_mix_rows, 84.0)
        autofill_supply_default = weighted_average_supply_area(autofill_project.existing_unit_mix_rows, 107.7)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        purchase_price_eok = st.number_input("매수가(억)", min_value=0.0, value=35.0, step=0.1, help=FIELD_HELP["purchase_price"])
        current_stage = st.selectbox("현재 사업단계", list(STAGE_BASE_MONTHS.keys()), index=list(STAGE_BASE_MONTHS.keys()).index(default_stage), help=FIELD_HELP["current_stage"])
    with c2:
        if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction:
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
            current_unit_exclusive_area = st.number_input("현재 전용면적(㎡)", min_value=20.0, value=float(round(autofill_exclusive_default, 1)), step=1.0)
            current_unit_supply_area = st.number_input("현재 공급면적(㎡)", min_value=20.0, value=float(round(autofill_supply_default, 1)), step=1.0)
    if land_based_reconstruction:
        st.caption("단독주택 묶음형 재건축은 현재 평형 대신 비교 기준 평형 59㎡/75.6㎡ 자동값을 사용합니다.")
    with c3:
        comparison_new_price_eok = st.number_input("비교 신축 시세(억)", min_value=0.0, value=48.0, step=0.1, help=FIELD_HELP["comparison_new_price"])
        general_sale_price_eok = st.number_input("일반분양 평균가(억)", min_value=0.0, value=14.0, step=0.1, help=FIELD_HELP["general_sale_price"])
        general_sale_price_basis_exclusive_area = st.number_input(
            "일반분양가 기준 전용(㎡)",
            min_value=20.0,
            value=84.0,
            step=1.0,
            help=FIELD_HELP["general_sale_price_basis_area"],
        )
    with c4:
        default_households = (
            autofill_project.owner_count
            if project_kind == ProjectKind.REDEVELOPMENT and autofill_project and autofill_project.owner_count
            else autofill_project.current_households
            if autofill_project and autofill_project.current_households
            else 480
        )
        current_households_label = "권리자/조합원 수" if project_kind == ProjectKind.REDEVELOPMENT else "기존 세대수"
        if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction:
            if autofill_project and autofill_project.owner_count:
                default_households = int(autofill_project.owner_count)
            current_households_label = "권리자/조합원 수"
        current_households = st.number_input(current_households_label, min_value=1, value=int(default_households), step=1, help=FIELD_HELP["current_households"])
        construction_cost_per_pyeong_man = st.number_input("공사비(만원/평)", min_value=0.0, value=900.0, step=10.0, help=FIELD_HELP["construction_cost"])
    st.caption("빠른 검토는 이 블록과 아래 사업 기본값만 채워도 바로 결과가 나옵니다.")

    with st.expander("2. 사업 기본값과 자동 추정", expanded=True):
        st.caption("서울 공식값이 있으면 우선 사용하고, 없으면 입력값과 시뮬레이션으로 보완합니다.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            current_far = st.number_input("현황 용적률(%)", min_value=0.0, value=180.0, step=1.0, help=FIELD_HELP["current_far"])
            land_share_label = "내 대지지분(㎡)" if project_kind == ProjectKind.REDEVELOPMENT else "대지지분(㎡)"
            if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction:
                land_share_label = "내 대지지분(㎡)"
            land_share = st.number_input(land_share_label, min_value=0.0, value=0.0, step=0.1, help=FIELD_HELP["land_share"])
        with c2:
            target_far = st.number_input("목표 용적률(%)", min_value=0.0, value=float(autofill_project.target_far or 260.0) if autofill_project else 260.0, step=1.0, help=FIELD_HELP["target_far"])
            target_building_coverage_ratio_pct = st.number_input("목표 건폐율(%)", min_value=0.0, value=float(autofill_project.target_building_coverage_ratio or 0.0) if autofill_project else 0.0, step=1.0, help=FIELD_HELP["target_bcr"])
        with c3:
            current_building_coverage_ratio_pct = st.number_input("현황 건폐율(%)", min_value=0.0, value=0.0, step=1.0, help=FIELD_HELP["current_bcr"])
            average_current_floors = st.number_input(
                "기존 평균 층수",
                min_value=0.0,
                value=float(autofill_project.average_current_floors or 0.0) if autofill_project else 0.0,
                step=1.0,
                help=FIELD_HELP["avg_current_floors"],
            )
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

        r1, r2, r3 = st.columns(3)
        with r1:
            general_sale_price_per_pyeong_manwon = st.number_input(
                "일반분양 평당가(만원/평, 선택)",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help=FIELD_HELP["general_sale_price_per_pyeong"],
            )
        with r2:
            member_sale_price_ratio_pct = st.number_input(
                "조합원 분양가 비율(%, 선택)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
                help=FIELD_HELP["member_sale_price_ratio"],
            )
        with r3:
            rental_sale_price_per_pyeong_manwon = st.number_input(
                "임대주택 평당가(만원/평, 선택)",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help=FIELD_HELP["rental_sale_price_per_pyeong"],
            )
        st.caption("평당가를 넣으면 블로그식 사업성 분석처럼 공급면적 기준으로 수익을 계산합니다. 일반분양 총액보다 우선해서 사용합니다.")

        preview_quick_inputs = QuickDealInputs(
            project_kind=project_kind,
            reconstruction_style=reconstruction_style,
            scenario_profile=assumption_profile,
            current_stage=current_stage,
            purchase_price=won_from_eok(purchase_price_eok),
            current_unit_exclusive_area=redevelopment_base_exclusive_area if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else current_unit_exclusive_area,
            current_unit_supply_area=redevelopment_base_supply_area if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else current_unit_supply_area,
            comparison_new_price=won_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
            general_sale_price=won_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
            general_sale_price_basis_exclusive_area=general_sale_price_basis_exclusive_area or None,
            general_sale_price_per_pyeong_manwon=general_sale_price_per_pyeong_manwon or None,
            current_households=int(current_households),
            current_far=current_far or None,
            target_far=target_far or None,
            land_share=land_share or None,
            site_area_sqm=autofill_project.site_area_sqm if autofill_project else None,
            current_building_coverage_ratio=(current_building_coverage_ratio_pct / 100.0) if current_building_coverage_ratio_pct else None,
            target_building_coverage_ratio=(target_building_coverage_ratio_pct / 100.0) if target_building_coverage_ratio_pct else None,
            average_current_floors=average_current_floors or None,
            floor_no=1 if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else 10,
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
            planned_unit_mix_rows=[],
            member_sale_price_ratio_override=(member_sale_price_ratio_pct / 100.0) if member_sale_price_ratio_pct else None,
            rental_sale_price_per_pyeong_manwon=rental_sale_price_per_pyeong_manwon or None,
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
            project_kind=project_kind,
            reconstruction_style=reconstruction_style,
        )
        preview_simulation = simulate_project_plan(
            preview_quick_inputs,
            preview_advanced_inputs,
            preview_quick_inputs.cash_settlement_rate or 0.0,
            preview_profile,
        )
        preview_planned_unit_mix_rows = auto_planned_unit_mix_rows(
            preview_quick_inputs,
            preview_advanced_inputs.unit_mix_rows,
            preview_simulation.planned_households,
        )

        st.markdown("#### 자동 제안값")
        render_table(
            [
                {
                    "예상 총세대수": f"{preview_simulation.planned_households:,}세대",
                    "일반분양": f"{preview_simulation.general_sale_households:,}세대 ({fmt_pct(preview_simulation.general_sale_ratio)})",
                    "임대주택": f"{preview_simulation.rental_households:,}세대 ({fmt_pct(preview_simulation.rental_ratio)})",
                    "기부채납": fmt_pct(preview_simulation.donation_ratio),
                    "필요 평균층수": f"{preview_simulation.required_avg_floors:.1f}층" if preview_simulation.required_avg_floors is not None else "-",
                    "남은 기간": f"{preview_remaining_months / 12:.1f}년",
                }
            ],
            "자동 제안 요약",
        )
        render_table(
            [
                {
                    "타입": item.label,
                    "세대수": f"{item.households:,}세대",
                    "전용㎡": f"{item.exclusive_area_sqm:,.1f}",
                    "공급㎡": f"{item.supply_area_sqm:,.1f}",
                }
                for item in preview_planned_unit_mix_rows
            ],
            "준공 후 공급 평형 자동안",
        )
        planned_unit_mix_text = st.text_area(
            "준공 후 공급 평형 계획 직접입력(선택)",
            value=default_planned_unit_mix_text(autofill_project),
            height=110,
            help=FIELD_HELP["planned_unit_mix"],
        )
        st.caption("비워두면 위 자동안을 사용합니다. 형식은 `타입,세대수,전용,공급` 입니다. 예: `84형,420,84,107.7`")

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
            expected_new_default = 74.0 if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else 84.0
            expected_new_exclusive_area = st.number_input("예상 새 전용면적(㎡)", min_value=0.0, value=expected_new_default, step=1.0)
            official_price_label = "공동주택 공시가격 또는 감정가(억)" if project_kind == ProjectKind.RECONSTRUCTION else "토지/건물 공시가격 또는 감정가(억)"
            official_price_help = FIELD_HELP["official_price_reconstruction"] if project_kind == ProjectKind.RECONSTRUCTION else FIELD_HELP["official_price_redevelopment"]
            if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction:
                official_price_label = "토지/건물 공시가격 또는 감정가(억)"
                official_price_help = FIELD_HELP["official_price_redevelopment"]
            official_price_reference_eok = st.number_input(official_price_label, min_value=0.0, value=0.0, step=0.1, help=official_price_help)
        with c2:
            appraised_old_asset_eok = st.number_input("내 감정가/종전자산가액(억)", min_value=0.0, value=0.0, step=0.1)
            total_old_asset_value_eok = st.number_input("단지 종전자산총액(억)", min_value=0.0, value=0.0, step=1.0)
        with c3:
            adjustment_factor_override = st.number_input("보정계수 직접입력", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            floor_no = st.number_input(
                "층수(정밀 참고)",
                min_value=1,
                value=1 if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else 10,
                step=1,
                disabled=project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction,
                help="재개발은 층수 보정을 쓰지 않으므로 비활성화됩니다." if project_kind == ProjectKind.REDEVELOPMENT else None,
            )
            if land_based_reconstruction:
                floor_no = 1
        with c4:
            recent_trade_price_eok = st.number_input(
                "최근 실거래 중앙값(억)",
                min_value=0.0,
                value=0.0,
                step=0.1,
                disabled=project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction,
                help="재개발은 최근 아파트 실거래 대신 대지지분과 감정가 기준으로 보는 편이 낫습니다." if project_kind == ProjectKind.REDEVELOPMENT else None,
            )
            if land_based_reconstruction:
                recent_trade_price_eok = 0.0
            acquisition_rate_pct = st.number_input("취득세 실효세율(%)", min_value=0.0, max_value=100.0, value=1.5, step=0.1)
            annual_holding_rate_pct = st.number_input("연 보유비용률(%)", min_value=0.0, max_value=100.0, value=0.3, step=0.1)
            capital_gains_effective_rate_pct = st.number_input("양도세 실효세율(%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
            brokerage_rate_pct = st.number_input("중개/처분비율(%)", min_value=0.0, max_value=100.0, value=0.4, step=0.1)
        unit_mix_text = st.text_area(
            "기존 세대 타입별 분포(선택)",
            value=default_existing_unit_mix_text(
                autofill_project,
                current_unit_exclusive_area,
                current_unit_supply_area,
                int(current_households),
            ) if project_kind == ProjectKind.RECONSTRUCTION and not land_based_reconstruction else "",
            height=90,
            help=FIELD_HELP["unit_mix"],
            disabled=project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction,
        )
        if land_based_reconstruction:
            unit_mix_text = ""
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
        reconstruction_style=reconstruction_style,
        scenario_profile=assumption_profile,
        current_stage=current_stage,
        purchase_price=won_from_eok(purchase_price_eok),
        current_unit_exclusive_area=redevelopment_base_exclusive_area if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else current_unit_exclusive_area,
        current_unit_supply_area=redevelopment_base_supply_area if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else current_unit_supply_area,
        comparison_new_price=won_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
        general_sale_price=won_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
        general_sale_price_basis_exclusive_area=general_sale_price_basis_exclusive_area or None,
        general_sale_price_per_pyeong_manwon=general_sale_price_per_pyeong_manwon or None,
        current_households=int(current_households),
        current_far=current_far or None,
        target_far=target_far or None,
        land_share=land_share or None,
        site_area_sqm=autofill_project.site_area_sqm if autofill_project else None,
        current_building_coverage_ratio=(current_building_coverage_ratio_pct / 100.0) if current_building_coverage_ratio_pct else None,
        target_building_coverage_ratio=(target_building_coverage_ratio_pct / 100.0) if target_building_coverage_ratio_pct else None,
        average_current_floors=average_current_floors or None,
        floor_no=1 if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else int(floor_no),
        official_price_reference=won_from_eok(official_price_reference_eok) if official_price_reference_eok else None,
        recent_same_complex_trade_price=None if project_kind == ProjectKind.REDEVELOPMENT or land_based_reconstruction else (won_from_eok(recent_trade_price_eok) if recent_trade_price_eok else None),
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
        planned_unit_mix_rows=parse_unit_mix_text(planned_unit_mix_text),
        member_sale_price_ratio_override=(member_sale_price_ratio_pct / 100.0) if member_sale_price_ratio_pct else None,
        rental_sale_price_per_pyeong_manwon=rental_sale_price_per_pyeong_manwon or None,
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
    scenario_visible, scenario_summary = annotate_scenario_results(results)
    focus_result = next(item for item in results if item.scenario_name == scenario_focus)

    st.markdown("### 4. 결과")
    if not quick_inputs.lookup_enabled:
        st.warning("서울 공식값을 못 불러온 상태라 일부 값은 수동 입력과 휴리스틱으로 계산됩니다.")
    if detail_allowed and focus_result.old_asset_source == "purchase_price_heuristic":
        st.warning("정밀계산용 참고가격이 없어서 권리가액은 매수가 기반 휴리스틱으로 추정했습니다.")
    for message in precision_gap_messages(quick_inputs, advanced_inputs):
        st.info(message)
    render_result_summary(focus_result)
    render_table(why_rows(focus_result), "왜 이렇게 계산됐는지")
    render_table(feasibility_rows(focus_result), "왜곡 위험 점검")

    with st.expander("시나리오 비교", expanded=scenario_visible):
        if scenario_visible:
            st.caption(scenario_summary)
            render_table(scenario_overview_rows(results), "시나리오 한눈에 보기")
        else:
            st.info(scenario_summary)

    with st.expander("자동 추정과 공식값 반영", expanded=False):
        render_table(simulation_rows(focus_result), "자동 추정과 공식값 반영")
        render_table(planned_unit_mix_display_rows(focus_result), "준공 후 공급 평형 계획")
        render_table(project_summary_rows(focus_result), "사업수지 요약")

    with st.expander("평형별 정산액 시뮬레이션", expanded=bool(focus_result.allocation_options)):
        if focus_result.allocation_options:
            if not detail_allowed:
                st.caption("관리처분 이전 단계에서는 권리가액과 분양가표가 개략치이므로, 아래 정산액은 빠른 검토용 시뮬레이션으로 보세요.")
            render_table(allocation_rows(focus_result), "평형별 정산액 시뮬레이션")
        else:
            st.info("현재 입력값으로는 평형별 정산액 시뮬레이션을 만들기 어려웠습니다. 일반분양 평균가나 예상 새 전용면적을 한 번 더 확인해 주세요.")

    with st.expander("엑시트와 민감도", expanded=False):
        render_table(exit_rows(focus_result), "엑시트별 손익")
        render_table(focus_result.sensitivity_rows, "민감도")

    with st.expander("정밀 근거와 비용 버킷", expanded=False):
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
            render_source_records(autofill_project.source_records, "자동조회 반영 결과")

    st.caption("권리가액, 분담금, 공사비, 일정은 법적 확정값이 아니라 의사결정 보조용 추정치입니다. 특히 관리처분인가 이전 단계에서는 빠른 매물 검토용 개략치로 보는 것이 안전합니다.")


if __name__ == "__main__":
    main()
