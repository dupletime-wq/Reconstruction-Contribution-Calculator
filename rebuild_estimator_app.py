from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from html import escape, unescape
from html.parser import HTMLParser
import re
import urllib.error
import urllib.parse
import urllib.request

try:
    import streamlit as st
except Exception:
    st = None


class ProjectKind(str, Enum):
    RECONSTRUCTION = "재건축"
    REDEVELOPMENT = "재개발"
    REMODELING = "아파트 리모델링"


class RemodelingKind(str, Enum):
    INCREASE = "세대수 증가형"
    NO_INCREASE = "비증가형"


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
    "heuristic": "휴리스틱",
    "policy": "서울 정책 기준",
    "general_sale_price": "일반분양 평균가",
    "general_sale_ppy": "일반분양 평당가",
    "comparison_new_price": "비교 신축 시세",
    "fallback": "기본 보정치",
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
    schedule_text: str | None = None
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


@dataclass
class UnionProjectInputs:
    project_kind: ProjectKind
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
    is_one_homeowner: bool
    holding_years: float


@dataclass
class RemodelingInputs:
    region_is_seoul: bool
    purchase_price: float
    completion_year: int
    current_households: int
    current_unit_exclusive_area: float
    expected_new_exclusive_area: float
    comparison_new_price: float | None
    general_sale_price: float | None
    general_sale_price_basis_exclusive_area: float | None
    general_sale_price_per_pyeong_manwon: float | None
    construction_cost_per_pyeong: float
    remodeling_kind: RemodelingKind
    additional_households: int | None
    current_floors: int
    vertical_extension: bool
    planned_added_floors: int
    official_price_reference: float | None
    total_site_area_sqm: float | None
    pf_rate: float
    sale_rate: float
    pf_financing_ratio: float
    project_duration_years: float
    move_cost_per_household: float


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


def cache_data(*args, **kwargs):
    def decorator(func):
        if st is None:
            return func
        return st.cache_data(*args, **kwargs)(func)

    return decorator


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0:
        return default
    return num / den


def won_from_eok(value: float) -> float:
    return float(value) * 100_000_000.0


def eok_from_won(value: float | None) -> float:
    if value is None:
        return 0.0
    return float(value) / 100_000_000.0


def maybe_float(value: float) -> float | None:
    return None if value <= 0 else float(value)


def maybe_int(value: int) -> int | None:
    return None if value <= 0 else int(value)


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
    elif project_kind == ProjectKind.REMODELING:
        ratio = 1.25 if area <= 84 else 1.22
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


def normalize_stage_name(raw_stage: str | None) -> str | None:
    if not raw_stage:
        return None
    text = str(raw_stage).strip()
    mappings = (
        ("준공", "준공/입주"),
        ("입주", "준공/입주"),
        ("착공", "착공"),
        ("철거", "이주/철거"),
        ("이주", "이주/철거"),
        ("관리처분", "관리처분인가"),
        ("사업시행", "사업시행인가"),
        ("조합설립", "조합설립인가"),
        ("추진위", "추진위승인"),
        ("정비구역", "정비구역지정"),
        ("정비계획", "정비구역지정"),
        ("안전진단", "재건축진단"),
        ("진단", "재건축진단"),
    )
    for needle, normalized in mappings:
        if needle in text:
            return normalized
    return text if text in STAGE_BASE_MONTHS else None


def guess_project_kind(text: str | None) -> ProjectKind | None:
    raw = str(text or "")
    if "재개발" in raw:
        return ProjectKind.REDEVELOPMENT
    if "재건축" in raw:
        return ProjectKind.RECONSTRUCTION
    return None


def default_member_sale_price_ratio(project_kind: ProjectKind, current_stage: str, override_value: float | None) -> tuple[float, str]:
    if override_value is not None:
        return clamp(override_value, 0.55, 0.95), "manual_override"
    base_ratio = 0.70 if project_kind == ProjectKind.REDEVELOPMENT else 0.75
    if current_stage in {"관리처분인가", "이주/철거", "착공", "준공/입주"}:
        base_ratio += 0.02
    return clamp(base_ratio, 0.60, 0.90), "heuristic"


def default_pf_financing_ratio(project_kind: ProjectKind) -> float:
    if project_kind == ProjectKind.REDEVELOPMENT:
        return 0.72
    if project_kind == ProjectKind.REMODELING:
        return 0.60
    return 0.68


def default_move_loan_amount(purchase_price: float, project_kind: ProjectKind) -> float:
    multiplier = 0.40 if project_kind == ProjectKind.RECONSTRUCTION else 0.30 if project_kind == ProjectKind.REDEVELOPMENT else 0.20
    return purchase_price * multiplier


def record(key: str, value: str, source: str, note: str = "") -> SourceRecord:
    return SourceRecord(key=key, value=value, source=source, note=note)


def warning(level: str, category: str, message: str) -> WarningMessage:
    return WarningMessage(level=level, category=category, message=message)


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
            self._current_row.append(" ".join(" ".join(self._current_cell).split()))
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


def extract_links(html_text: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(html_text)
    return parser.items


def extract_tables(html_text: str) -> list[list[list[str]]]:
    parser = TableParser()
    parser.feed(html_text)
    return parser.tables


def extract_text_tokens(html_text: str) -> list[str]:
    parser = SimpleTextParser()
    parser.feed(html_text)
    return parser.parts


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
        if stripped.isdigit():
            value = int(stripped)
            if value > 0:
                counts.append(value)
    return sum(counts) if counts else None


def extract_public_facility_areas(land_use_table: list[list[str]], facility_table: list[list[str]]) -> tuple[float | None, float | None]:
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


@cache_data(ttl=60 * 60, show_spinner=False)
def cleanup_search_projects(query: str) -> list[SeoulProjectData]:
    keyword = query.strip()
    if not keyword:
        return []
    encoded = urllib.parse.quote(keyword)
    url = f"https://cleanup.seoul.go.kr/cleanup/bsnssttus/lsubBsnsSttus.do?scupBsnsSttus.asscNm={encoded}"
    try:
        html_text = fetch_html(url)
    except urllib.error.URLError:
        return []
    rows = re.findall(r"<tr>(.*?)</tr>", html_text, re.S)
    results: list[SeoulProjectData] = []
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
            SeoulProjectData(
                project_name=cells[3],
                district=cells[1],
                business_type=cells[2],
                project_kind=guess_project_kind(cells[2]),
                progress_stage=normalize_stage_name(cells[5]),
                representative_lot=cells[4],
                project_slug=slug,
                source_url=f"https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl={slug}",
                source_records=[record("사업단계", normalize_stage_name(cells[5]) or cells[5], "official_cleanup")],
            )
        )
    return results[:12]


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


@cache_data(ttl=60 * 60, show_spinner=False)
def cleanup_fetch_project_summary(project_slug: str) -> SeoulProjectData | None:
    if not project_slug:
        return None
    try:
        main_url = f"https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl={urllib.parse.quote(project_slug)}"
        main_html = fetch_html(main_url)
        cafe_id_match = re.search(r"cafeId=([A-Z0-9]+)", main_html)
        if not cafe_id_match:
            return None
        cafe_id = cafe_id_match.group(1)
        links = extract_links(main_html)
        summary_href = next((href for text, href in links if text == "사업개요" and "mastr-cleanup-bsnsSumry" in href), None)
        if not summary_href:
            summary_href = f"/cafe/mastr-cleanup-bsnsSumry/execute.do?cafeId={cafe_id}&stepSeCode=102&div=sumry"
        summary_url = urllib.parse.urljoin("https://cleanup.seoul.go.kr", unescape(summary_href))
        summary_html = fetch_html(summary_url)
    except urllib.error.URLError:
        return None

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
    current_households = parse_int((basics_map.get("조합원 수", "") or "").replace("명", ""))
    owner_count = parse_int((basics_map.get("토지등 소유자 수", "") or "").replace("명", ""))
    tenant_count = parse_int((basics_map.get("세입자 수", "") or "").replace("명", ""))
    planned_sale_total = extract_households_from_supply_table(sale_table)
    planned_rental = extract_households_from_supply_table(rental_table)
    public_facility_area_sqm, donation_area_sqm = extract_public_facility_areas(land_use_table, facility_table)

    member_seed = current_households or owner_count
    planned_general_sale = None
    if planned_sale_total is not None and member_seed is not None:
        planned_general_sale = max(planned_sale_total - member_seed, 0)

    project = SeoulProjectData(
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
        gross_floor_area_sqm=parse_float(building_row[3]) if len(building_row) > 3 else None,
        target_building_coverage_ratio_pct=parse_float(building_row[4]) if len(building_row) > 4 else None,
        target_far_pct=parse_float(building_row[5]) if len(building_row) > 5 else None,
        current_households=current_households,
        owner_count=owner_count,
        tenant_count=tenant_count,
        planned_households=(planned_sale_total or 0) + (planned_rental or 0) or None,
        sale_households_total=planned_sale_total,
        sale_households=planned_general_sale,
        rental_households=planned_rental,
        public_facility_area_sqm=public_facility_area_sqm,
        donation_area_sqm=donation_area_sqm,
    )
    project.schedule_text = cleanup_fetch_schedule_text(cafe_id)
    project.source_records = [
        record("구역면적", f"{project.site_area_sqm:,.1f}㎡" if project.site_area_sqm is not None else "-", "official_cleanup"),
        record("계획 용적률", f"{project.target_far_pct:.1f}%" if project.target_far_pct is not None else "-", "official_cleanup"),
        record("계획 건폐율", f"{project.target_building_coverage_ratio_pct:.1f}%" if project.target_building_coverage_ratio_pct is not None else "-", "official_cleanup"),
        record("권리자/조합원 수", str(project.owner_count or project.current_households or "-"), "official_cleanup"),
        record("계획 세대수", str(project.planned_households or "-"), "official_cleanup"),
        record("일반분양 세대수", str(project.sale_households or "-"), "official_cleanup"),
        record("임대 세대수", str(project.rental_households or "-"), "official_cleanup"),
    ]
    return project


def estimate_remaining_months(stage: str, seoul_project: SeoulProjectData | None, project_kind: ProjectKind) -> tuple[float, str]:
    if project_kind == ProjectKind.REMODELING:
        return 48.0, "heuristic"
    base = float(STAGE_BASE_MONTHS.get(stage, 72))
    if seoul_project and seoul_project.schedule_text:
        return max(base - 6.0, 6.0), "official_cleanup"
    return base, "heuristic"


def estimate_current_gross_floor_area_sqm(
    project_kind: ProjectKind,
    current_households: int,
    current_unit_supply_area: float,
    current_far_pct: float | None,
    site_area_sqm: float | None,
    official_gross_floor_area_sqm: float | None,
) -> float:
    if official_gross_floor_area_sqm is not None:
        return official_gross_floor_area_sqm
    if site_area_sqm is not None and current_far_pct is not None:
        return site_area_sqm * (current_far_pct / 100.0)
    multiplier = 1.08 if project_kind != ProjectKind.REMODELING else 1.05
    return current_households * current_unit_supply_area * multiplier


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
    implied_site_area_sqm = None
    if land_share_sqm is not None and current_households > 0:
        implied_site_area_sqm = land_share_sqm * current_households

    if manual_total_site_area_sqm is not None:
        selected = manual_total_site_area_sqm
        source = "manual"
    elif official_site_area_sqm is not None:
        selected = official_site_area_sqm
        source = "official_cleanup"
    elif implied_site_area_sqm is not None:
        selected = implied_site_area_sqm
        source = "manual"
    elif current_far_pct is not None and current_far_pct > 0:
        selected = current_gross_floor_area_sqm / (current_far_pct / 100.0)
        source = "heuristic"
    elif current_building_coverage_ratio_pct is not None and average_current_floors is not None and current_building_coverage_ratio_pct > 0 and average_current_floors > 0:
        selected = current_gross_floor_area_sqm / ((current_building_coverage_ratio_pct / 100.0) * average_current_floors)
        source = "heuristic"
    else:
        selected = None
        source = "heuristic"

    if selected is not None and implied_site_area_sqm is not None:
        mismatch = abs(selected - implied_site_area_sqm) / max(selected, 1.0)
        if mismatch >= 0.20:
            warnings.append(
                warning(
                    "warn",
                    "서울 공식값과 충돌",
                    f"전체 대지면적 기준치는 {selected:,.0f}㎡인데 대지지분×권리자 수 추정치는 {implied_site_area_sqm:,.0f}㎡입니다. 단위와 입력값을 다시 확인해 주세요.",
                )
            )

    avg_site_area = safe_div(selected or 0.0, current_households, 0.0) if selected is not None and current_households > 0 else None
    resolution = SiteResolution(
        selected_total_site_area_sqm=selected,
        source=source,
        official_site_area_sqm=official_site_area_sqm,
        manual_site_area_sqm=manual_total_site_area_sqm,
        implied_site_area_sqm=implied_site_area_sqm,
        average_site_area_per_member_sqm=avg_site_area,
    )
    return resolution, warnings


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
        return PolicyAdjustment(active=False, note="서울 전용 제도라 자동 미적용입니다.")

    seoul_avg_price = SEOUL_AVG_OFFICIAL_PRICE_PER_SQM.get(project_kind)
    if seoul_avg_price is None:
        return PolicyAdjustment(active=False, note="서울 전용 제도가 없는 유형입니다.")

    if avg_official_land_price_per_sqm is not None:
        price_factor = clamp(seoul_avg_price / max(avg_official_land_price_per_sqm, 1.0), 1.0, 2.0)
        price_note = "대상지 평균 공시지가 입력값 기준"
    else:
        price_factor = 1.0
        price_note = "대상지 평균 공시지가가 없어 공시지가 보정계수는 1.0으로 보수 적용"

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


def estimate_old_asset_value(
    *,
    project_kind: ProjectKind,
    purchase_price: float,
    appraised_old_asset_value: float | None,
    official_price_reference: float | None,
    region_is_seoul: bool,
) -> tuple[float, str]:
    if appraised_old_asset_value is not None:
        return appraised_old_asset_value, "manual"
    if official_price_reference is not None:
        multiplier = 1.23 if region_is_seoul else 1.18
        return official_price_reference * multiplier, "heuristic"
    fallback_multiplier = 0.78 if project_kind == ProjectKind.RECONSTRUCTION else 0.74 if project_kind == ProjectKind.REDEVELOPMENT else 0.95
    return purchase_price * fallback_multiplier, "heuristic"


def estimate_total_old_asset_value(
    *,
    project_kind: ProjectKind,
    explicit_total_old_asset_value: float | None,
    old_asset_estimate: float,
    member_households: int,
    land_share_sqm: float | None,
    site_resolution: SiteResolution,
) -> tuple[float, str]:
    if explicit_total_old_asset_value is not None:
        return explicit_total_old_asset_value, "manual"
    if project_kind == ProjectKind.REDEVELOPMENT and land_share_sqm is not None and site_resolution.selected_total_site_area_sqm is not None and member_households > 0:
        avg_share = safe_div(site_resolution.selected_total_site_area_sqm, member_households, 0.0)
        share_ratio = clamp(safe_div(land_share_sqm, max(avg_share, 1.0), 1.0), 0.35, 2.50)
        return old_asset_estimate * member_households / share_ratio, "heuristic"
    return old_asset_estimate * member_households, "heuristic"


def estimate_donation_ratio(inputs: UnionProjectInputs) -> tuple[float, str]:
    if inputs.donation_ratio_override is not None:
        return clamp(inputs.donation_ratio_override, 0.0, 0.40), "manual_override"
    project = inputs.seoul_project
    if project and project.public_facility_area_sqm is not None and project.official_area_sqm:
        return clamp(project.public_facility_area_sqm / max(project.official_area_sqm, 1.0), 0.0, 0.40), "official_cleanup"
    default_ratio = 0.08 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.12
    return default_ratio, "heuristic"


def estimate_rental_ratio(inputs: UnionProjectInputs) -> tuple[float, str]:
    if inputs.rental_ratio_override is not None:
        return clamp(inputs.rental_ratio_override, 0.0, 0.40), "manual_override"
    project = inputs.seoul_project
    if project and project.rental_households is not None and project.planned_households:
        return clamp(project.rental_households / max(project.planned_households, 1), 0.0, 0.40), "official_cleanup"
    default_ratio = 0.02 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.12
    return default_ratio, "heuristic"


def calculate_reconstruction_levy(
    *,
    total_reconstruction_profit: float,
    member_households: int,
    is_one_homeowner: bool,
    holding_years: float,
) -> ReconstructionLevyResult:
    if total_reconstruction_profit <= 0 or member_households <= 0:
        return ReconstructionLevyResult(0.0, 0.0, 0.0, 0.0, "면제")

    average_profit = total_reconstruction_profit / member_households
    if average_profit <= 80_000_000.0:
        return ReconstructionLevyResult(0.0, 0.0, average_profit, 0.0, "면제")

    levy_total = 0.0
    bracket_label = "면제"
    for lower, upper, rate, base_amount in RECONSTRUCTION_LEVY_BRACKETS:
        if average_profit <= lower:
            continue
        if upper is None or average_profit <= upper:
            levy_per_member = base_amount + (average_profit - lower) * rate
            levy_total = levy_per_member * member_households
            bracket_label = f"{lower / 100_000_000.0:.1f}억 초과 구간"
            break

    relief_ratio = 0.0
    if is_one_homeowner:
        for start, end, relief in RECONSTRUCTION_LEVY_HOLDING_RELIEF:
            if holding_years >= start and (end is None or holding_years < end):
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


def compute_confidence_score(
    *,
    region_is_seoul: bool,
    seoul_project: SeoulProjectData | None,
    site_source: str,
    old_asset_source: str,
    price_source: str,
    important_fields: list[bool],
) -> float:
    completeness = safe_div(sum(1 for item in important_fields if item), len(important_fields), 0.0)
    official_strength = 0.95 if region_is_seoul and seoul_project is not None else 0.60
    site_strength = 0.90 if site_source == "official_cleanup" else 0.80 if site_source == "manual" else 0.55
    value_strength = 0.92 if old_asset_source == "manual" else 0.68
    price_strength = 0.92 if price_source in {"general_sale_price", "general_sale_ppy"} else 0.78 if price_source == "comparison_new_price" else 0.58
    score = (completeness * 100.0 * 0.45) + (official_strength * 100.0 * 0.20) + (site_strength * 100.0 * 0.15) + (value_strength * 100.0 * 0.10) + (price_strength * 100.0 * 0.10)
    return clamp(score, 20.0, 98.0)


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
) -> None:
    if site_resolution.selected_total_site_area_sqm is None:
        warnings.append(warning("risk", "입력 부족", "전체 대지면적을 확정하기 어려워 용적률과 평형 기준 휴리스틱으로 계산했습니다."))
    if inputs.project_kind == ProjectKind.REDEVELOPMENT and inputs.land_share_sqm is None:
        warnings.append(warning("risk", "입력 부족", "재개발은 내 대지지분이 없으면 권리가액과 분담금 오차가 크게 커집니다."))
    if planned_households < member_households:
        warnings.append(warning("risk", "법적 상한 초과", f"예상 총세대수 {planned_households:,}세대로는 권리자/조합원 {member_households:,}세대를 담기 어렵습니다."))
    if general_sale_households <= 0:
        warnings.append(warning("warn", "휴리스틱 의존", "일반분양 세대수가 0세대로 계산되어 사업수지가 매우 보수적으로 보일 수 있습니다."))
    if total_old_asset_source == "heuristic":
        warnings.append(warning("warn", "휴리스틱 의존", "종전자산총액을 감정평가서 없이 추정해 비례율과 정산액 신뢰도가 낮습니다."))
    if business_price_source == "fallback":
        warnings.append(warning("warn", "휴리스틱 의존", "일반분양가 또는 비교 신축 시세가 없어 매수가 기반 기본 보정치로 가격을 추정했습니다."))
    if inputs.project_kind == ProjectKind.REDEVELOPMENT and inputs.land_share_sqm is not None and inputs.land_share_sqm < 90:
        warnings.append(warning("warn", "입력 부족", "재개발은 토지면적 90㎡ 기준 등 분양대상 판정 이슈가 있어 개별 권리판정을 별도로 확인하는 것이 안전합니다."))


def calculate_union_project(inputs: UnionProjectInputs) -> CalculationResult:
    warnings: list[WarningMessage] = []
    policy = seoul_policy_adjustment(
        project_kind=inputs.project_kind,
        region_is_seoul=inputs.region_is_seoul,
        current_far_pct=inputs.current_far_pct,
        target_far_pct=inputs.target_far_pct or (inputs.seoul_project.target_far_pct if inputs.seoul_project else None),
        total_site_area_sqm=inputs.total_site_area_sqm or (inputs.seoul_project.site_area_sqm if inputs.seoul_project else None),
        current_households=inputs.current_households,
        current_unit_supply_area=inputs.current_unit_supply_area,
        avg_official_land_price_per_sqm=inputs.avg_official_land_price_per_sqm,
    )
    remaining_months, duration_source = estimate_remaining_months(inputs.current_stage, inputs.seoul_project, inputs.project_kind)
    default_target_far_pct = 260.0 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 250.0
    target_far_pct = (
        inputs.target_far_pct
        or (inputs.seoul_project.target_far_pct if inputs.seoul_project else None)
        or policy.estimated_target_far_pct
        or default_target_far_pct
    )
    official_site_area = inputs.seoul_project.site_area_sqm if inputs.seoul_project else None
    current_gross_floor_area_sqm = estimate_current_gross_floor_area_sqm(
        inputs.project_kind,
        inputs.current_households,
        inputs.current_unit_supply_area,
        inputs.current_far_pct,
        official_site_area,
        inputs.seoul_project.gross_floor_area_sqm if inputs.seoul_project else None,
    )
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
    warnings.extend(site_warnings)

    donation_ratio, donation_source = estimate_donation_ratio(inputs)
    rental_ratio, rental_source = estimate_rental_ratio(inputs)
    average_supply_area_sqm = estimate_supply_area_from_exclusive_area(inputs.expected_new_exclusive_area, inputs.project_kind)

    if site_resolution.selected_total_site_area_sqm is not None:
        gross_floor_area_sqm = site_resolution.selected_total_site_area_sqm * (target_far_pct / 100.0)
    elif inputs.current_far_pct is not None:
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(target_far_pct, inputs.current_far_pct, 1.0)
    else:
        multiplier = 1.28 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 1.38
        gross_floor_area_sqm = current_gross_floor_area_sqm * multiplier

    residential_efficiency = 0.84 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.80
    saleable_area_factor = clamp(1.0 - donation_ratio, 0.55, 1.0)
    simulated_total_households = max(
        int(round((gross_floor_area_sqm * residential_efficiency * saleable_area_factor) / max(average_supply_area_sqm, 1.0))),
        1,
    )

    official_planned_households = inputs.seoul_project.planned_households if inputs.seoul_project else None
    planned_households = inputs.target_households_override or official_planned_households or simulated_total_households
    member_seed = (
        inputs.seoul_project.owner_count
        if inputs.project_kind == ProjectKind.REDEVELOPMENT and inputs.seoul_project and inputs.seoul_project.owner_count
        else inputs.seoul_project.current_households
        if inputs.seoul_project and inputs.seoul_project.current_households
        else inputs.current_households
    )
    member_households = max(int(round(member_seed * (1.0 - inputs.cash_settlement_rate))), 1)
    official_rental = inputs.seoul_project.rental_households if inputs.seoul_project else None
    rental_households = official_rental or int(round(planned_households * rental_ratio))
    available_general_sale = max(planned_households - member_households - rental_households, 0)
    official_general_sale = inputs.seoul_project.sale_households if inputs.seoul_project else None
    if official_general_sale is not None and inputs.general_sale_ratio_override is None:
        general_sale_households = min(official_general_sale, available_general_sale)
        general_sale_source = "official_cleanup"
    elif inputs.general_sale_ratio_override is not None:
        general_sale_households = min(int(round(max(planned_households - rental_households, 0) * inputs.general_sale_ratio_override)), available_general_sale)
        general_sale_source = "manual_override"
    else:
        general_sale_households = available_general_sale
        general_sale_source = "heuristic"
    general_sale_ratio = safe_div(general_sale_households, max(planned_households - rental_households, 1), 0.0)

    general_sale_unit_price, business_price_source = resolve_business_unit_price(
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=inputs.comparison_new_price,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
        target_supply_area_sqm=average_supply_area_sqm,
    )
    exit_unit_price, exit_price_source = resolve_exit_unit_price(
        comparison_new_price=inputs.comparison_new_price,
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
    )
    member_sale_price_ratio, member_sale_ratio_source = default_member_sale_price_ratio(
        inputs.project_kind,
        inputs.current_stage,
        inputs.member_sale_price_ratio_override,
    )
    member_unit_price = general_sale_unit_price * member_sale_price_ratio
    rental_unit_price = price_from_supply_pyeong(1000.0 if inputs.region_is_seoul else 800.0, average_supply_area_sqm * 0.80) or 0.0

    gross_floor_area_pyeong = gross_floor_area_sqm / 3.3058
    current_gross_area_pyeong = current_gross_floor_area_sqm / 3.3058
    direct_construction_cost = gross_floor_area_pyeong * inputs.construction_cost_per_pyeong
    demolition_cost = current_gross_area_pyeong * inputs.construction_cost_per_pyeong * (0.06 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.08)
    design_and_pm_cost = direct_construction_cost * (0.06 if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.065)
    union_cost = direct_construction_cost * 0.018 + member_households * 8_000_000.0

    old_asset_estimate, old_asset_source = estimate_old_asset_value(
        project_kind=inputs.project_kind,
        purchase_price=inputs.purchase_price,
        appraised_old_asset_value=inputs.appraised_old_asset_value,
        official_price_reference=inputs.official_price_reference,
        region_is_seoul=inputs.region_is_seoul,
    )
    total_old_asset_value, total_old_asset_source = estimate_total_old_asset_value(
        project_kind=inputs.project_kind,
        explicit_total_old_asset_value=inputs.total_old_asset_value,
        old_asset_estimate=old_asset_estimate,
        member_households=member_households,
        land_share_sqm=inputs.land_share_sqm,
        site_resolution=site_resolution,
    )

    member_sale_revenue = member_unit_price * member_households
    general_sale_revenue = general_sale_unit_price * general_sale_households * inputs.sale_rate
    rental_revenue = rental_unit_price * rental_households
    ancillary_revenue = direct_construction_cost * 0.02
    other_disposal_revenue = direct_construction_cost * 0.01
    total_revenue_before_cost = member_sale_revenue + general_sale_revenue + rental_revenue + ancillary_revenue + other_disposal_revenue

    tenant_count = inputs.seoul_project.tenant_count if inputs.seoul_project and inputs.seoul_project.tenant_count else 0
    housing_relocation_cost = 0.0
    business_loss_cost = 0.0
    if inputs.project_kind == ProjectKind.REDEVELOPMENT:
        eligible_tenants = max(int(round((tenant_count or member_households * 0.18) * 0.33)), 1)
        housing_relocation_cost = eligible_tenants * 18_000_000.0
        business_loss_cost = eligible_tenants * 6_000_000.0
    settlement_compensation_cost = total_old_asset_value * (0.005 + inputs.cash_settlement_rate * 0.08) + housing_relocation_cost + business_loss_cost
    sales_expense = general_sale_revenue * 0.025
    taxes_public_cost = (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + sales_expense + settlement_compensation_cost) * 0.03
    pf_base_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + taxes_public_cost
    pf_principal = pf_base_cost * inputs.pf_financing_ratio
    financing_cost = pf_principal * inputs.pf_rate * (inputs.pf_interest_months / 12.0)
    move_loan_interest_cost = member_households * inputs.average_move_loan_amount * inputs.move_loan_rate * (inputs.move_loan_duration_months / 12.0)
    contingency_cost = (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + taxes_public_cost + sales_expense) * 0.05

    levy_result = ReconstructionLevyResult(0.0, 0.0, 0.0, 0.0, "미적용")
    if inputs.project_kind == ProjectKind.RECONSTRUCTION:
        total_reconstruction_profit = max(total_revenue_before_cost - (direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + settlement_compensation_cost + taxes_public_cost + sales_expense + financing_cost + move_loan_interest_cost + contingency_cost), 0.0)
        levy_result = calculate_reconstruction_levy(
            total_reconstruction_profit=total_reconstruction_profit,
            member_households=member_households,
            is_one_homeowner=inputs.is_one_homeowner,
            holding_years=inputs.holding_years,
        )

    total_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + union_cost + settlement_compensation_cost + taxes_public_cost + financing_cost + move_loan_interest_cost + sales_expense + contingency_cost + levy_result.total_levy
    total_revenue = total_revenue_before_cost
    proportional_ratio = safe_div(total_revenue - total_cost, total_old_asset_value, 0.0) * 100.0 if total_old_asset_value > 0 else None
    rights_value = old_asset_estimate * safe_div(proportional_ratio or 0.0, 100.0, 0.0) if proportional_ratio is not None else None
    settlement_amount = None if rights_value is None else member_unit_price - rights_value + levy_result.levy_per_member

    acquisition_rate = 0.015
    holding_rate = 0.003
    disposal_rate = 0.004
    capital_gains_effective_rate = 0.20
    years_to_exit = max(remaining_months / 12.0, 0.5)
    acquisition_cost = inputs.purchase_price * acquisition_rate
    holding_cost = inputs.purchase_price * holding_rate * years_to_exit
    settlement_payment = max(settlement_amount or 0.0, 0.0)
    settlement_refund = max(-(settlement_amount or 0.0), 0.0)
    capital_interest = settlement_payment * max(inputs.pf_rate + 0.01, 0.04) * years_to_exit * 0.45
    disposal_cost = exit_unit_price * disposal_rate
    pretax_profit = exit_unit_price - disposal_cost + settlement_refund - (inputs.purchase_price + acquisition_cost + holding_cost + settlement_payment + capital_interest)
    after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * capital_gains_effective_rate
    break_even_purchase_price = max(
        (exit_unit_price - disposal_cost - holding_cost + settlement_refund - settlement_payment - capital_interest) / max(1.0 + acquisition_rate, 0.01),
        0.0,
    )
    max_bid_price = break_even_purchase_price * 0.90

    add_standard_union_warnings(
        inputs=inputs,
        warnings=warnings,
        site_resolution=site_resolution,
        member_households=member_households,
        planned_households=planned_households,
        general_sale_households=general_sale_households,
        total_old_asset_source=total_old_asset_source,
        business_price_source=business_price_source,
    )
    if inputs.project_kind == ProjectKind.RECONSTRUCTION and levy_result.total_levy > 0:
        warnings.append(warning("warn", "입력 부족", f"재건축부담금이 총 {fmt_money(levy_result.total_levy)}로 추정됩니다. 60세 이상 납부유예 여부는 안내만 하고 수치 반영은 하지 않았습니다."))
    if inputs.project_kind == ProjectKind.REDEVELOPMENT and total_old_asset_source == "heuristic":
        warnings.append(warning("warn", "휴리스틱 의존", "재개발 종전자산총액을 대지지분 보정 휴리스틱으로 추정했습니다. 감정평가서가 있으면 꼭 다시 넣어 보세요."))
    if inputs.region_is_seoul and inputs.seoul_project is not None and inputs.seoul_project.project_kind and inputs.seoul_project.project_kind != inputs.project_kind:
        warnings.append(warning("risk", "서울 공식값과 충돌", f"서울 공식 사업유형은 {inputs.seoul_project.project_kind.value}인데 현재 {inputs.project_kind.value} 모드로 계산 중입니다."))

    confidence_score = compute_confidence_score(
        region_is_seoul=inputs.region_is_seoul,
        seoul_project=inputs.seoul_project,
        site_source=site_resolution.source,
        old_asset_source=old_asset_source,
        price_source=business_price_source,
        important_fields=[
            inputs.purchase_price > 0,
            inputs.current_households > 0,
            inputs.current_far_pct is not None,
            target_far_pct is not None,
            site_resolution.selected_total_site_area_sqm is not None,
            inputs.general_sale_price is not None or inputs.general_sale_price_per_pyeong_manwon is not None or inputs.comparison_new_price is not None,
            inputs.official_price_reference is not None or inputs.appraised_old_asset_value is not None,
        ],
    )
    confidence_label = "높음" if confidence_score >= 80 else "보통" if confidence_score >= 60 else "낮음"

    sensitivity_rows: list[dict[str, str]] = []
    for sale_delta in (0.95, 1.00, 1.05):
        for cost_delta in (0.95, 1.00, 1.05):
            variant_revenue = member_sale_revenue + (general_sale_revenue * sale_delta) + rental_revenue + ancillary_revenue + other_disposal_revenue
            variant_cost = total_cost - levy_result.total_levy
            variant_cost = variant_cost - direct_construction_cost + (direct_construction_cost * cost_delta) + levy_result.total_levy
            variant_ratio = safe_div(variant_revenue - variant_cost, total_old_asset_value, 0.0) * 100.0 if total_old_asset_value > 0 else 0.0
            sensitivity_rows.append(
                {
                    "분양가 배수": f"{sale_delta:.2f}x",
                    "공사비 배수": f"{cost_delta:.2f}x",
                    "비례율": f"{variant_ratio:.2f}%",
                }
            )

    source_rows = [
        {"항목": "대지면적", "값": f"{site_resolution.selected_total_site_area_sqm:,.1f}㎡" if site_resolution.selected_total_site_area_sqm is not None else "-", "출처": humanize_source(site_resolution.source)},
        {"항목": "일반분양가 기준", "값": fmt_money(general_sale_unit_price), "출처": humanize_source(business_price_source)},
        {"항목": "출구가치 기준", "값": fmt_money(exit_unit_price), "출처": humanize_source(exit_price_source)},
        {"항목": "종전자산 추정", "값": fmt_money(old_asset_estimate), "출처": humanize_source(old_asset_source)},
        {"항목": "종전자산총액", "값": fmt_money(total_old_asset_value), "출처": humanize_source(total_old_asset_source)},
        {"항목": "일반분양 세대수", "값": f"{general_sale_households:,}세대", "출처": humanize_source(general_sale_source)},
        {"항목": "기부채납 비율", "값": fmt_pct(donation_ratio), "출처": humanize_source(donation_source)},
        {"항목": "임대 비율", "값": fmt_pct(rental_ratio), "출처": humanize_source(rental_source)},
        {"항목": "조합원 분양가율", "값": fmt_pct(member_sale_price_ratio), "출처": humanize_source(member_sale_ratio_source)},
        {"항목": "예상 잔여기간", "값": f"{remaining_months / 12.0:.1f}년", "출처": humanize_source(duration_source)},
    ]

    why_rows = [
        {"구분": "가격", "항목": "일반분양 평균가", "값": fmt_money(general_sale_unit_price)},
        {"구분": "가격", "항목": "조합원 분양가", "값": fmt_money(member_unit_price)},
        {"구분": "사업", "항목": "예상 총세대수", "값": f"{planned_households:,}세대"},
        {"구분": "사업", "항목": "일반분양 세대수", "값": f"{general_sale_households:,}세대"},
        {"구분": "사업", "항목": "임대주택 세대수", "값": f"{rental_households:,}세대"},
        {"구분": "사업", "항목": "기부채납 비율", "값": fmt_pct(donation_ratio)},
        {"구분": "금융", "항목": "PF / 이주비", "값": f"PF {fmt_pct(inputs.pf_rate)}, 이주비 {fmt_pct(inputs.move_loan_rate)}"},
        {"구분": "제도", "항목": "서울 정책 계수", "값": f"{policy.coefficient:.2f}" if policy.active else "미적용"},
    ]

    business_rows = [
        {"항목": "총수입", "값": fmt_money(total_revenue)},
        {"항목": "조합원 분양수입", "값": fmt_money(member_sale_revenue)},
        {"항목": "일반분양수입", "값": fmt_money(general_sale_revenue)},
        {"항목": "임대주택수입", "값": fmt_money(rental_revenue)},
        {"항목": "총지출", "값": fmt_money(total_cost)},
        {"항목": "본공사비", "값": fmt_money(direct_construction_cost)},
        {"항목": "보상/청산비", "값": fmt_money(settlement_compensation_cost)},
        {"항목": "금융비", "값": fmt_money(financing_cost + move_loan_interest_cost)},
        {"항목": "재건축부담금", "값": fmt_money(levy_result.total_levy if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.0)},
        {"항목": "추정비례율", "값": fmt_plain_pct(proportional_ratio)},
    ]

    settlement_rows = [
        {"항목": "개별 종전자산 추정", "값": fmt_money(old_asset_estimate)},
        {"항목": "단지 종전자산총액", "값": fmt_money(total_old_asset_value)},
        {"항목": "권리가액", "값": fmt_money(rights_value)},
        {"항목": "조합원 분양가", "값": fmt_money(member_unit_price)},
        {"항목": "예상 정산액", "값": settlement_label(settlement_amount)},
        {"항목": "재건축부담금 1인당", "값": fmt_money(levy_result.levy_per_member if inputs.project_kind == ProjectKind.RECONSTRUCTION else 0.0)},
        {"항목": "출구가치", "값": fmt_money(exit_unit_price)},
        {"항목": "준공 직후 세후손익", "값": fmt_money(after_tax_profit)},
    ]

    policy_rows = [
        {"항목": "서울 사업성 보정계수", "값": f"{policy.coefficient:.2f}" if policy.active else "미적용"},
        {"항목": "공시지가 보정계수", "값": f"{policy.price_factor:.2f}" if policy.active else "-"},
        {"항목": "대지면적 보정계수", "값": f"{policy.area_factor:.2f}" if policy.active else "-"},
        {"항목": "세대밀도 보정계수", "값": f"{policy.density_factor:.2f}" if policy.active else "-"},
        {"항목": "현황용적률 인정", "값": f"{policy.recognized_far_pct:.1f}%" if policy.recognized_far_pct is not None else "해당 없음"},
        {"항목": "정책 기준 메모", "값": policy.note},
        {"항목": "재건축부담금 구간", "값": levy_result.bracket_label if inputs.project_kind == ProjectKind.RECONSTRUCTION else "미적용"},
        {"항목": "1세대1주택 장기보유 감경", "값": fmt_pct(levy_result.relief_ratio) if inputs.project_kind == ProjectKind.RECONSTRUCTION else "미적용"},
    ]

    top_cards = [
        ("예상 비례율", fmt_plain_pct(proportional_ratio), "재개발·재건축 사업수지 기준의 추정값입니다."),
        ("예상 추가분담금/환급금", settlement_label(settlement_amount), "권리가액과 조합원 분양가 차이에 재건축부담금을 반영했습니다."),
        ("일반분양 세대수", f"{general_sale_households:,}세대", "서울 공식 계획이 있으면 우선 반영하고, 없으면 자동 추정합니다."),
        ("권장 최대 매수가", fmt_money(max_bid_price), "준공 직후 매도 기준 손익분기 매수가에 10% 안전마진을 뒀습니다."),
        ("결과 신뢰도", f"{confidence_label} ({confidence_score:.1f}점)", "공식값 비중, 대지면적 근거, 가격 근거를 합산한 점수입니다."),
    ]

    summary_lines = [
        f"예상 총세대수는 {planned_households:,}세대, 일반분양은 {general_sale_households:,}세대로 계산했습니다.",
        f"대지면적은 {humanize_source(site_resolution.source)} 기준 {site_resolution.selected_total_site_area_sqm:,.0f}㎡를 사용했습니다." if site_resolution.selected_total_site_area_sqm is not None else "대지면적은 휴리스틱으로만 추정했습니다.",
        f"일반분양 평균가는 {humanize_source(business_price_source)} 기준 {fmt_money(general_sale_unit_price)}입니다.",
        f"권리가액은 {fmt_money(rights_value)}로 추정했고, 현재 기준 정산액은 {settlement_label(settlement_amount)}입니다.",
        f"준공 직후 매도 기준 세후 손익은 {fmt_money(after_tax_profit)}이며 손익분기 매수가는 {fmt_money(break_even_purchase_price)}입니다.",
    ]

    return CalculationResult(
        mode=inputs.project_kind,
        top_cards=top_cards,
        summary_lines=summary_lines,
        warnings=warnings,
        why_rows=why_rows,
        business_rows=business_rows,
        settlement_rows=settlement_rows,
        sensitivity_rows=sensitivity_rows,
        policy_rows=policy_rows,
        source_rows=source_rows,
    )


def calculate_remodeling(inputs: RemodelingInputs) -> CalculationResult:
    warnings: list[WarningMessage] = []
    current_year = datetime.now().year
    elapsed_years = max(current_year - inputs.completion_year, 0)
    max_additional_households = int(inputs.current_households * 0.15)
    additional_households = 0
    if inputs.remodeling_kind == RemodelingKind.INCREASE:
        suggested = max(int(round(inputs.current_households * 0.10)), 1)
        requested = inputs.additional_households if inputs.additional_households is not None else suggested
        additional_households = min(requested, max_additional_households)
        if requested > max_additional_households:
            warnings.append(warning("risk", "법적 상한 초과", f"세대수 증가형 리모델링은 기존 세대수의 15% 이내만 허용되어 입력값을 {additional_households:,}세대로 제한했습니다."))
    if elapsed_years < 15:
        warnings.append(warning("risk", "법적 상한 초과", f"준공 후 {elapsed_years}년 경과로 증축형 리모델링 기본 요건(15년 이상) 충족 여부를 다시 확인해야 합니다."))

    allowed_added_floors = 0
    if inputs.vertical_extension:
        allowed_added_floors = 3 if inputs.current_floors >= 15 else 2
        if inputs.planned_added_floors > allowed_added_floors:
            warnings.append(warning("risk", "법적 상한 초과", f"현재 {inputs.current_floors}층 건물은 수직증축 허용 상한이 {allowed_added_floors}개층입니다."))

    current_supply_area_sqm = estimate_supply_area_from_exclusive_area(inputs.current_unit_exclusive_area, ProjectKind.REMODELING)
    expected_supply_area_sqm = estimate_supply_area_from_exclusive_area(inputs.expected_new_exclusive_area, ProjectKind.REMODELING)
    planned_households = inputs.current_households + additional_households
    general_sale_households = additional_households

    current_gross_floor_area_sqm = current_supply_area_sqm * inputs.current_households * 1.05
    post_gross_floor_area_sqm = expected_supply_area_sqm * planned_households * 1.05
    direct_construction_cost = (post_gross_floor_area_sqm / 3.3058) * inputs.construction_cost_per_pyeong
    structure_reinforcement_cost = direct_construction_cost * 0.24
    expansion_cost = direct_construction_cost * (0.18 if inputs.remodeling_kind == RemodelingKind.INCREASE else 0.10)
    equipment_replacement_cost = direct_construction_cost * 0.16
    parking_community_cost = direct_construction_cost * 0.08
    design_pm_cost = direct_construction_cost * 0.06
    temporary_move_cost = inputs.current_households * inputs.move_cost_per_household
    financing_base = direct_construction_cost + structure_reinforcement_cost + expansion_cost + equipment_replacement_cost + parking_community_cost + design_pm_cost
    financing_cost = financing_base * inputs.pf_financing_ratio * inputs.pf_rate * inputs.project_duration_years
    contingency_cost = (direct_construction_cost + structure_reinforcement_cost + expansion_cost + equipment_replacement_cost + parking_community_cost + design_pm_cost) * 0.05
    total_cost = direct_construction_cost + structure_reinforcement_cost + expansion_cost + equipment_replacement_cost + parking_community_cost + design_pm_cost + temporary_move_cost + financing_cost + contingency_cost

    general_sale_unit_price, business_price_source = resolve_business_unit_price(
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        general_sale_price_per_pyeong_manwon=inputs.general_sale_price_per_pyeong_manwon,
        comparison_new_price=inputs.comparison_new_price,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
        target_supply_area_sqm=expected_supply_area_sqm,
    )
    exit_unit_price, exit_price_source = resolve_exit_unit_price(
        comparison_new_price=inputs.comparison_new_price,
        general_sale_price=inputs.general_sale_price,
        general_sale_basis_area=inputs.general_sale_price_basis_exclusive_area,
        purchase_price=inputs.purchase_price,
        target_exclusive_area=inputs.expected_new_exclusive_area,
    )
    current_unit_value = inputs.official_price_reference or inputs.purchase_price
    general_sale_revenue = general_sale_unit_price * general_sale_households * inputs.sale_rate
    current_total_asset_value = current_unit_value * inputs.current_households
    post_total_asset_value = exit_unit_price * inputs.current_households
    value_uplift_total = max(post_total_asset_value - current_total_asset_value, 0.0)
    total_revenue = general_sale_revenue + value_uplift_total
    proportional_like_ratio = safe_div(total_revenue - total_cost, max(current_total_asset_value, 1.0), 0.0) * 100.0
    per_household_burden = safe_div(max(total_cost - general_sale_revenue, 0.0), inputs.current_households, 0.0)
    value_uplift_per_household = safe_div(value_uplift_total, inputs.current_households, 0.0)
    net_burden_after_uplift = per_household_burden - value_uplift_per_household

    acquisition_rate = 0.015
    holding_rate = 0.003
    disposal_rate = 0.004
    capital_gains_effective_rate = 0.20
    acquisition_cost = inputs.purchase_price * acquisition_rate
    holding_cost = inputs.purchase_price * holding_rate * inputs.project_duration_years
    disposal_cost = exit_unit_price * disposal_rate
    pretax_profit = exit_unit_price - disposal_cost - (inputs.purchase_price + acquisition_cost + holding_cost + per_household_burden)
    after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * capital_gains_effective_rate
    break_even_purchase_price = max(
        (exit_unit_price - disposal_cost - holding_cost - per_household_burden) / max(1.0 + acquisition_rate, 0.01),
        0.0,
    )
    max_bid_price = break_even_purchase_price * 0.90

    if inputs.remodeling_kind == RemodelingKind.NO_INCREASE:
        warnings.append(warning("warn", "휴리스틱 의존", "비증가형 리모델링은 일반분양 수입이 없어 세대당 분담금과 가치상승 중심으로 평가했습니다."))
    if inputs.comparison_new_price is None and inputs.general_sale_price is None and inputs.general_sale_price_per_pyeong_manwon is None:
        warnings.append(warning("warn", "휴리스틱 의존", "비교 신축 시세 또는 일반분양 평균가가 없어 매수가 기반 보정치로 가치상승을 추정했습니다."))

    confidence_score = clamp(
        (
            safe_div(
                sum(
                    [
                        inputs.purchase_price > 0,
                        inputs.current_households > 0,
                        inputs.current_unit_exclusive_area > 0,
                        inputs.expected_new_exclusive_area > 0,
                        inputs.comparison_new_price is not None or inputs.general_sale_price is not None or inputs.general_sale_price_per_pyeong_manwon is not None,
                        inputs.official_price_reference is not None,
                    ]
                ),
                6,
                0.0,
            )
            * 100.0
            * 0.60
        )
        + (85.0 if inputs.official_price_reference is not None else 62.0) * 0.20
        + (82.0 if inputs.remodeling_kind == RemodelingKind.INCREASE else 74.0) * 0.20,
        25.0,
        95.0,
    )
    confidence_label = "높음" if confidence_score >= 80 else "보통" if confidence_score >= 60 else "낮음"

    sensitivity_rows: list[dict[str, str]] = []
    for sale_delta in (0.95, 1.00, 1.05):
        for cost_delta in (0.95, 1.00, 1.05):
            variant_revenue = (general_sale_revenue * sale_delta) + value_uplift_total
            variant_cost = total_cost * cost_delta
            variant_ratio = safe_div(variant_revenue - variant_cost, max(current_total_asset_value, 1.0), 0.0) * 100.0
            sensitivity_rows.append(
                {
                    "분양가 배수": f"{sale_delta:.2f}x",
                    "공사비 배수": f"{cost_delta:.2f}x",
                    "사업성 지수": f"{variant_ratio:.2f}%",
                }
            )

    why_rows = [
        {"구분": "유형", "항목": "리모델링 방식", "값": inputs.remodeling_kind.value},
        {"구분": "유형", "항목": "경과연수", "값": f"{elapsed_years}년"},
        {"구분": "사업", "항목": "증가 세대수", "값": f"{general_sale_households:,}세대"},
        {"구분": "사업", "항목": "예상 세대당 분담금", "값": fmt_money(per_household_burden)},
        {"구분": "사업", "항목": "세대당 가치상승", "값": fmt_money(value_uplift_per_household)},
        {"구분": "가격", "항목": "일반분양 기준", "값": fmt_money(general_sale_unit_price)},
        {"구분": "가격", "항목": "출구가치 기준", "값": fmt_money(exit_unit_price)},
        {"구분": "금융", "항목": "PF 금리/기간", "값": f"{fmt_pct(inputs.pf_rate)} / {inputs.project_duration_years:.1f}년"},
    ]

    business_rows = [
        {"항목": "총사업비", "값": fmt_money(total_cost)},
        {"항목": "본공사비", "값": fmt_money(direct_construction_cost)},
        {"항목": "구조보강비", "값": fmt_money(structure_reinforcement_cost)},
        {"항목": "증축/평면확장비", "값": fmt_money(expansion_cost)},
        {"항목": "설비교체비", "값": fmt_money(equipment_replacement_cost)},
        {"항목": "주차/커뮤니티비", "값": fmt_money(parking_community_cost)},
        {"항목": "임시이주비", "값": fmt_money(temporary_move_cost)},
        {"항목": "금융비", "값": fmt_money(financing_cost)},
        {"항목": "일반분양수입", "값": fmt_money(general_sale_revenue)},
        {"항목": "사업성 지수", "값": f"{proportional_like_ratio:.2f}%"},
    ]

    settlement_rows = [
        {"항목": "세대당 예상 분담금", "값": fmt_money(per_household_burden)},
        {"항목": "세대당 가치상승", "값": fmt_money(value_uplift_per_household)},
        {"항목": "가치상승 반영 순부담", "값": settlement_label(net_burden_after_uplift)},
        {"항목": "현재 기준 시세", "값": fmt_money(current_unit_value)},
        {"항목": "리모델링 후 출구가치", "값": fmt_money(exit_unit_price)},
        {"항목": "준공 직후 세후손익", "값": fmt_money(after_tax_profit)},
        {"항목": "재건축부담금", "값": "미적용"},
    ]

    policy_rows = [
        {"항목": "리모델링 유형", "값": inputs.remodeling_kind.value},
        {"항목": "세대수 증가 상한", "값": f"최대 {max_additional_households:,}세대"},
        {"항목": "입력 증가 세대수", "값": f"{general_sale_households:,}세대"},
        {"항목": "수직증축 사용", "값": "예" if inputs.vertical_extension else "아니오"},
        {"항목": "수직증축 층수 상한", "값": f"{allowed_added_floors}개층" if inputs.vertical_extension else "-"},
        {"항목": "입력 추가 층수", "값": f"{inputs.planned_added_floors}개층" if inputs.vertical_extension else "-"},
        {"항목": "증축형 기본연한", "값": "15년 이상"},
        {"항목": "재건축부담금 대상 여부", "값": "미적용"},
    ]

    source_rows = [
        {"항목": "현재 가치 기준", "값": fmt_money(current_unit_value), "출처": "공시가격/매수가"},
        {"항목": "일반분양 기준", "값": fmt_money(general_sale_unit_price), "출처": humanize_source(business_price_source)},
        {"항목": "출구가치 기준", "값": fmt_money(exit_unit_price), "출처": humanize_source(exit_price_source)},
        {"항목": "총세대수", "값": f"{planned_households:,}세대", "출처": "입력값"},
        {"항목": "일반분양 세대수", "값": f"{general_sale_households:,}세대", "출처": "입력값/법정 상한"},
        {"항목": "사업기간", "값": f"{inputs.project_duration_years:.1f}년", "출처": "직접 입력"},
    ]

    top_cards = [
        ("예상 비례율", f"{proportional_like_ratio:.2f}%", "현재 자산가치 대비 순사업이익 기준의 참고치입니다."),
        ("예상 추가분담금/환급금", settlement_label(per_household_burden), "리모델링은 세대당 분담금 중심으로 해석하는 것이 안전합니다."),
        ("일반분양 세대수", f"{general_sale_households:,}세대", "비증가형은 0세대, 증가형은 15% 상한 내에서만 계산합니다."),
        ("권장 최대 매수가", fmt_money(max_bid_price), "리모델링 완료 후 출구가치 기준 손익분기 매수가의 90%입니다."),
        ("결과 신뢰도", f"{confidence_label} ({confidence_score:.1f}점)", "가격 기준과 현재 가치 근거가 있을수록 점수가 높아집니다."),
    ]

    summary_lines = [
        f"리모델링 방식은 {inputs.remodeling_kind.value}이며, 증가 세대수는 {general_sale_households:,}세대로 계산했습니다.",
        f"세대당 예상 분담금은 {fmt_money(per_household_burden)}이고, 가치상승을 반영한 순부담은 {settlement_label(net_burden_after_uplift)}입니다.",
        f"리모델링 후 출구가치는 {fmt_money(exit_unit_price)}로 추정했고, 준공 직후 매도 기준 세후 손익은 {fmt_money(after_tax_profit)}입니다.",
        "재건축부담금은 리모델링 계산에 반영하지 않았습니다.",
    ]

    return CalculationResult(
        mode=ProjectKind.REMODELING,
        top_cards=top_cards,
        summary_lines=summary_lines,
        warnings=warnings,
        why_rows=why_rows,
        business_rows=business_rows,
        settlement_rows=settlement_rows,
        sensitivity_rows=sensitivity_rows,
        policy_rows=policy_rows,
        source_rows=source_rows,
    )


def inject_styles() -> None:
    if st is None:
        return
    st.markdown(
        """
        <style>
        :root {
            --ink: #17323a;
            --muted: #58727a;
            --line: #d6e3de;
            --card: rgba(255, 255, 255, 0.94);
            --soft: #f3f8f6;
        }
        .stApp {
            background:
                radial-gradient(circle at 0% 0%, rgba(215, 233, 226, 0.75), transparent 28%),
                radial-gradient(circle at 100% 0%, rgba(247, 228, 210, 0.60), transparent 24%),
                linear-gradient(180deg, #f7faf8 0%, #f3f7f5 100%);
        }
        .hero-card, .section-card, .metric-card {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 22px;
            box-shadow: 0 10px 26px rgba(23, 50, 58, 0.06);
        }
        .hero-card {
            padding: 24px;
            margin-bottom: 14px;
        }
        .hero-card h1 {
            margin: 0 0 8px 0;
            color: var(--ink);
            font-size: 31px;
            line-height: 1.12;
        }
        .hero-card p, .mini-note {
            margin: 0;
            color: var(--muted);
            font-size: 14px;
            line-height: 1.55;
        }
        .section-card {
            padding: 16px 18px;
            margin: 10px 0;
        }
        .metric-card {
            padding: 16px 16px 14px 16px;
            min-height: 136px;
        }
        .metric-label {
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .metric-value {
            color: var(--ink);
            font-size: 24px;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 8px;
        }
        .metric-note {
            color: var(--muted);
            font-size: 12px;
            line-height: 1.45;
        }
        .soft-title {
            color: var(--ink);
            font-weight: 800;
            margin-bottom: 6px;
        }
        .pill {
            display: inline-block;
            padding: 4px 10px;
            margin-right: 6px;
            margin-bottom: 6px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }
        .pill.base { background: #eaf2f5; color: #274754; }
        .pill.ok { background: #e8f4ea; color: #2d6a41; }
        .pill.warn { background: #fff1df; color: #8a5824; }
        .pill.risk { background: #fbe8e8; color: #9d4141; }
        table.codex-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        table.codex-table th {
            text-align: left;
            background: var(--soft);
            color: var(--ink);
            padding: 10px 12px;
            border-bottom: 1px solid var(--line);
        }
        table.codex-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #edf1ef;
            color: #264149;
            vertical-align: top;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, tone: str = "base") -> str:
    return f"<span class='pill {tone}'>{escape(text)}</span>"


def render_table(rows: list[dict[str, str]], title: str | None = None) -> None:
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
    title_html = f"<div class='soft-title'>{escape(title)}</div>" if title else ""
    st.markdown(
        "<div class='section-card'>"
        + title_html
        + "<table class='codex-table'><thead><tr>"
        + "".join(f"<th>{escape(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_metric_cards(cards: list[tuple[str, str, str]]) -> None:
    if st is None:
        return
    columns = st.columns(len(cards))
    for column, (label, value, note) in zip(columns, cards):
        with column:
            st.markdown(
                "<div class='metric-card'>"
                f"<div class='metric-label'>{escape(label)}</div>"
                f"<div class='metric-value'>{escape(value)}</div>"
                f"<div class='metric-note'>{escape(note)}</div>"
                "</div>",
                unsafe_allow_html=True,
            )


def render_project_card(project: SeoulProjectData) -> None:
    if st is None:
        return
    title_badges = (
        badge(project.district or "서울", "base")
        + badge(project.business_type or "사업유형 미확인", "ok")
        + badge(project.project_kind.value if project.project_kind else "유형 미확인", "base")
        + badge(project.progress_stage or "단계 미확인", "warn")
    )
    st.markdown(
        "<div class='section-card'>"
        f"<div class='soft-title'>{escape(project.project_name)}</div>"
        f"<div>{title_badges}</div>"
        f"<p class='mini-note'>대표지번: {escape(project.representative_lot or '-')}</p>"
        f"<p class='mini-note'>구역면적: {project.site_area_sqm or '-'}㎡ / 계획 용적률: {project.target_far_pct or '-'}% / 계획 세대수: {project.planned_households or '-'}</p>"
        f"<p class='mini-note'>일반분양: {project.sale_households or '-'}세대 / 임대: {project.rental_households or '-'}세대 / 세입자: {project.tenant_count or '-'}명</p>"
        + (f"<p class='mini-note'>향후 일정: {escape(project.schedule_text)}</p>" if project.schedule_text else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def render_warning_badges(items: list[WarningMessage]) -> None:
    if st is None or not items:
        return
    tone_map = {"ok": "ok", "warn": "warn", "risk": "risk"}
    st.markdown(
        "<div class='section-card'><div class='soft-title'>핵심 경고</div>"
        + "".join(badge(item.category, tone_map.get(item.level, "base")) for item in items[:6])
        + "</div>",
        unsafe_allow_html=True,
    )


def render_summary_lines(lines: list[str]) -> None:
    if st is None:
        return
    html = "".join(f"<p class='mini-note' style='margin-bottom:6px;'>{escape(line)}</p>" for line in lines)
    st.markdown(f"<div class='section-card'><div class='soft-title'>결과 요약</div>{html}</div>", unsafe_allow_html=True)


def union_input_help() -> dict[str, str]:
    return {
        "purchase_price": "현재 검토 중인 1개 물건의 매수가입니다. 수익성과 손익분기 매수가 계산의 출발점입니다. 실매수 예정가를 넣는 것이 가장 좋습니다.",
        "comparison_new_price": "준공 후 이 물건이 따라갈 가능성이 있는 신축 시세입니다. 엑시트 가치 계산에 먼저 씁니다. 없으면 일반분양 평균가로 대신 추정합니다.",
        "general_sale_price": "준공 또는 분양 시점 기준의 일반분양 평균가입니다. 사업수지와 비례율 계산에 우선 사용합니다. 없으면 비교 신축 시세로 보수 추정합니다.",
        "general_sale_price_basis": "입력한 일반분양 평균가가 어떤 전용면적 기준인지 적는 값입니다. 다른 평형으로 환산할 때 사용합니다. 모르면 보통 84㎡를 넣습니다.",
        "general_sale_ppy": "공급면적 기준 평당 분양가를 아는 경우에만 넣으세요. 이 값이 있으면 일반분양 총액 입력보다 우선합니다. 모르면 비워두면 됩니다.",
        "current_households": "재건축은 기존 세대수, 재개발은 권리자 수에 가깝게 넣을수록 좋습니다. 총세대수와 일반분양 세대수 계산의 기준값입니다. 공식값이 있으면 자동 반영됩니다.",
        "current_far": "현재 용적률입니다. 전체 대지면적이 없을 때 대지면적 역산에 사용합니다. 모르면 비워둘 수 있지만 신뢰도는 내려갑니다.",
        "target_far": "계획 또는 예상 목표 용적률입니다. 총세대수와 사업수지의 핵심 입력값입니다. 서울 공식값이 있으면 그 값을 먼저 보여줍니다.",
        "land_share": "내 물건 기준 대지지분입니다. 재개발과 토지형 계산에서 특히 중요합니다. 모르면 비워둘 수 있지만 분담금 오차가 커집니다.",
        "total_site_area": "전체 구역 대지면적입니다. 입력하면 가장 우선해서 사용합니다. 서울 공식값과 다르면 경고만 띄우고 계산은 입력값을 따릅니다.",
        "construction_cost": "평당 공사비입니다. 본공사비와 전체 사업비에 직접 반영됩니다. 모르면 기준값으로 시작한 뒤 민감도 표를 같이 보세요.",
        "official_price": "내 물건의 공시가격 또는 감정평가액입니다. 종전자산과 권리가액 추정에 가장 유용합니다. 없으면 매수가 기반 보정치로 대신 계산합니다.",
        "avg_official_land_price": "서울 사업성 보정계수의 공시지가 보정계수를 계산할 때만 쓰는 값입니다. 서울 외 지역은 사용하지 않습니다. 모르면 비워두면 1.0으로 보수 적용합니다.",
    }


def remodeling_input_help() -> dict[str, str]:
    return {
        "completion_year": "준공연도입니다. 증축형 리모델링의 기본 연한 판단에 씁니다. 현재 연도와 비교해 경과연수를 자동 계산합니다.",
        "additional_households": "세대수 증가형에서만 쓰는 값입니다. 입력하지 않으면 기존 세대수의 약 10%를 기본안으로 넣습니다. 법정 상한 15%를 넘기면 자동으로 제한합니다.",
        "planned_added_floors": "수직증축을 선택했을 때만 의미가 있습니다. 15층 이상 기존 건물은 최대 3개층, 14층 이하는 최대 2개층만 검증합니다. 상한을 넘기면 경고가 뜹니다.",
        "move_cost": "세대당 임시이주·이사·간접비를 단순화한 값입니다. 총사업비에 직접 더해집니다. 모르면 보수적으로 0.2억 정도에서 시작해 보세요.",
    }


def main() -> None:
    if st is None:
        print("streamlit이 설치되지 않았습니다. `streamlit run app.py`로 실행해 주세요.")
        return
    st.set_page_config(page_title="재건축·재개발·리모델링 계산기", layout="wide")
    inject_styles()
    st.markdown(
        """
        <div class="hero-card">
            <h1>재건축·재개발·리모델링 계산기</h1>
            <p>서울 정비몽땅 공식값은 자동으로 끌어오고, 나머지는 빠른 입력만으로 바로 계산하는 구조로 다시 정리했습니다. 장문 설명은 줄이고, 꼭 필요한 이유와 우선순위는 각 입력의 tooltip에 넣었습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    union_help = union_input_help()
    remodeling_help = remodeling_input_help()

    project_kind = ProjectKind(
        st.radio(
            "사업유형",
            [ProjectKind.RECONSTRUCTION.value, ProjectKind.REDEVELOPMENT.value, ProjectKind.REMODELING.value],
            horizontal=True,
        )
    )

    region_is_seoul = False
    seoul_project: SeoulProjectData | None = None
    if project_kind != ProjectKind.REMODELING:
        region_mode = st.radio(
            "입력 방식",
            ["서울 자동조회", "수동입력(서울 외 포함)"],
            horizontal=True,
            help="서울은 정비몽땅 검색으로 공식값을 먼저 채울 수 있습니다. 서울 외 지역은 수동입력 중심으로 계산합니다. 서울 외 지역에는 서울시 정책 보정계수를 적용하지 않습니다.",
        )
        region_is_seoul = region_mode == "서울 자동조회"
        if region_is_seoul:
            search_query = st.text_input(
                "서울 프로젝트 검색",
                placeholder="예: 방화6, 우면한라, 개포주공",
                help="정비몽땅에서 사업장을 찾아 공식 대지면적, 계획세대수, 임대세대수 등을 먼저 채웁니다. 검색 결과가 없으면 수동입력으로 계속 진행할 수 있습니다. 서울 사업장만 지원합니다.",
            )
            if len(search_query.strip()) >= 2:
                search_results = cleanup_search_projects(search_query)
                if search_results:
                    labels = [f"{item.project_name} / {item.district} / {item.business_type} / {item.progress_stage or '단계 미확인'}" for item in search_results]
                    selected_label = st.selectbox("검색 결과", labels)
                    selected = search_results[labels.index(selected_label)]
                    seoul_project = cleanup_fetch_project_summary(selected.project_slug)
                    if seoul_project:
                        seoul_project.progress_stage = selected.progress_stage or seoul_project.progress_stage
                        seoul_project.business_type = selected.business_type or seoul_project.business_type
                        seoul_project.district = selected.district or seoul_project.district
                        seoul_project.representative_lot = selected.representative_lot or seoul_project.representative_lot
                        render_project_card(seoul_project)
                else:
                    st.info("정비몽땅 공개 검색 결과가 없어 수동입력 기준으로 계속 계산합니다.")
        else:
            st.caption("서울 외 지역은 수동 입력값을 우선 사용하며 서울시 사업성 보정계수와 현황용적률 인정 계산은 적용하지 않습니다.")
    else:
        st.caption("리모델링은 현재 수동입력 중심으로 계산합니다. 재건축부담금은 적용하지 않고, 세대수 증가 상한과 수직증축 상한만 검증합니다.")

    if project_kind in {ProjectKind.RECONSTRUCTION, ProjectKind.REDEVELOPMENT}:
        default_households = (
            seoul_project.owner_count
            if project_kind == ProjectKind.REDEVELOPMENT and seoul_project and seoul_project.owner_count
            else seoul_project.current_households
            if seoul_project and seoul_project.current_households
            else 480
        )
        default_stage = seoul_project.progress_stage if seoul_project and seoul_project.progress_stage else "조합설립인가"
        current_exclusive_default = 59.0 if project_kind == ProjectKind.REDEVELOPMENT else 84.0
        current_supply_default = 75.6 if project_kind == ProjectKind.REDEVELOPMENT else 107.7

        st.subheader("빠른 입력")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            purchase_price_eok = st.number_input("매수가(억)", min_value=0.0, value=35.0, step=0.1, help=union_help["purchase_price"])
            current_stage = st.selectbox("현재 사업단계", list(STAGE_BASE_MONTHS.keys()), index=list(STAGE_BASE_MONTHS.keys()).index(default_stage))
        with c2:
            current_households = st.number_input("권리자/조합원 수" if project_kind == ProjectKind.REDEVELOPMENT else "기존 세대수", min_value=1, value=int(default_households), step=1, help=union_help["current_households"])
            current_unit_exclusive_area = st.number_input("현재 전용면적(㎡)", min_value=20.0, value=current_exclusive_default, step=1.0)
        with c3:
            expected_new_exclusive_area = st.number_input("예상 새 전용면적(㎡)", min_value=20.0, value=74.0 if project_kind == ProjectKind.REDEVELOPMENT else 84.0, step=1.0)
            comparison_new_price_eok = st.number_input("비교 신축 시세(억)", min_value=0.0, value=48.0, step=0.1, help=union_help["comparison_new_price"])
        with c4:
            general_sale_price_eok = st.number_input("일반분양 평균가(억)", min_value=0.0, value=14.0, step=0.1, help=union_help["general_sale_price"])
            construction_cost_per_pyeong_man = st.number_input("공사비(만원/평)", min_value=0.0, value=900.0 if project_kind == ProjectKind.RECONSTRUCTION else 950.0, step=10.0, help=union_help["construction_cost"])

        st.subheader("사업 기본값")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            current_far_pct = st.number_input("현황 용적률(%)", min_value=0.0, value=180.0, step=1.0, help=union_help["current_far"])
            land_share_sqm = st.number_input("내 대지지분(㎡)" if project_kind == ProjectKind.REDEVELOPMENT else "대지지분(㎡)", min_value=0.0, value=0.0, step=0.1, help=union_help["land_share"])
        with b2:
            target_far_seed = seoul_project.target_far_pct if seoul_project and seoul_project.target_far_pct else (260.0 if project_kind == ProjectKind.RECONSTRUCTION else 250.0)
            target_far_pct = st.number_input("목표 용적률(%)", min_value=0.0, value=float(target_far_seed), step=1.0, help=union_help["target_far"])
            total_site_area_sqm = st.number_input("전체 대지면적(㎡, 선택)", min_value=0.0, value=0.0, step=10.0, help=union_help["total_site_area"])
        with b3:
            general_sale_price_basis_exclusive_area = st.number_input("일반분양가 기준 전용(㎡)", min_value=20.0, value=84.0, step=1.0, help=union_help["general_sale_price_basis"])
            general_sale_price_per_pyeong_manwon = st.number_input("일반분양 평당가(만원/평, 선택)", min_value=0.0, value=0.0, step=100.0, help=union_help["general_sale_ppy"])
        with b4:
            current_unit_supply_area = st.number_input("현재 공급면적(㎡)", min_value=20.0, value=current_supply_default, step=1.0)
            official_price_reference_eok = st.number_input("공시가격/감정가(억, 선택)", min_value=0.0, value=0.0, step=0.1, help=union_help["official_price"])

        with st.expander("정밀 입력", expanded=False):
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                target_households_override = st.number_input("총세대수 직접입력(선택)", min_value=0, value=0, step=1)
                general_sale_ratio_override_pct = st.number_input("일반분양 비율 직접입력(%, 선택)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
            with d2:
                rental_ratio_override_pct = st.number_input("임대 비율 직접입력(%, 선택)", min_value=0.0, max_value=40.0, value=0.0, step=1.0)
                donation_ratio_override_pct = st.number_input("기부채납 비율 직접입력(%, 선택)", min_value=0.0, max_value=40.0, value=0.0, step=1.0)
            with d3:
                member_sale_price_ratio_pct = st.number_input("조합원 분양가율(%, 선택)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
                total_old_asset_value_eok = st.number_input("단지 종전자산총액(억, 선택)", min_value=0.0, value=0.0, step=1.0)
            with d4:
                appraised_old_asset_eok = st.number_input("내 종전자산가액(억, 선택)", min_value=0.0, value=0.0, step=0.1)
                avg_official_land_price_per_sqm = st.number_input("대상지 평균 공시지가(원/㎡, 선택)", min_value=0.0, value=0.0, step=10000.0, help=union_help["avg_official_land_price"])

            g1, g2 = st.columns(2)
            with g1:
                current_building_coverage_ratio_pct = st.number_input("현황 건폐율(%, 선택)", min_value=0.0, value=0.0, step=1.0)
            with g2:
                average_current_floors = st.number_input("기존 평균 층수(선택)", min_value=0.0, value=0.0, step=1.0)

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                sale_rate_pct = st.number_input("일반분양 판매율(%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0)
                cash_settlement_rate_pct = st.number_input("현금청산률(%)", min_value=0.0, max_value=100.0, value=3.0 if project_kind == ProjectKind.RECONSTRUCTION else 5.0, step=1.0)
            with f2:
                pf_rate_pct = st.number_input("PF 금리(%)", min_value=0.0, max_value=30.0, value=8.5, step=0.1)
                move_loan_rate_pct = st.number_input("이주비 금리(%)", min_value=0.0, max_value=20.0, value=5.0, step=0.1)
            with f3:
                pf_financing_ratio_pct = st.number_input("PF 조달비율(%)", min_value=0.0, max_value=95.0, value=round(default_pf_financing_ratio(project_kind) * 100.0, 1), step=1.0)
                pf_interest_months = st.number_input("PF 이자 반영기간(개월)", min_value=0.0, value=24.0, step=1.0)
            with f4:
                average_move_loan_amount_eok = st.number_input("세대당 평균 이주비(억)", min_value=0.0, value=round(eok_from_won(default_move_loan_amount(won_from_eok(purchase_price_eok), project_kind)), 2), step=0.1)
                move_loan_duration_months = st.number_input("이주비 대여기간(개월)", min_value=0.0, value=24.0, step=1.0)

            l1, l2 = st.columns(2)
            with l1:
                is_one_homeowner = st.checkbox("1세대 1주택자(재건축부담금 감경 검토용)", value=True if project_kind == ProjectKind.RECONSTRUCTION else False)
            with l2:
                holding_years = st.number_input("보유기간(년, 재건축부담금 감경 검토용)", min_value=0.0, value=10.0, step=1.0)

        inputs = UnionProjectInputs(
            project_kind=project_kind,
            region_is_seoul=region_is_seoul,
            seoul_project=seoul_project,
            purchase_price=won_from_eok(purchase_price_eok),
            current_stage=current_stage,
            current_households=int(current_households),
            current_unit_exclusive_area=current_unit_exclusive_area,
            current_unit_supply_area=current_unit_supply_area,
            expected_new_exclusive_area=expected_new_exclusive_area,
            comparison_new_price=maybe_float(won_from_eok(comparison_new_price_eok)),
            general_sale_price=maybe_float(won_from_eok(general_sale_price_eok)),
            general_sale_price_basis_exclusive_area=maybe_float(general_sale_price_basis_exclusive_area),
            general_sale_price_per_pyeong_manwon=maybe_float(general_sale_price_per_pyeong_manwon),
            construction_cost_per_pyeong=construction_cost_per_pyeong_man * 10_000.0,
            current_far_pct=maybe_float(current_far_pct),
            target_far_pct=maybe_float(target_far_pct),
            total_site_area_sqm=maybe_float(total_site_area_sqm),
            land_share_sqm=maybe_float(land_share_sqm),
            current_building_coverage_ratio_pct=maybe_float(current_building_coverage_ratio_pct),
            target_building_coverage_ratio_pct=None,
            average_current_floors=maybe_float(average_current_floors),
            official_price_reference=maybe_float(won_from_eok(official_price_reference_eok)),
            appraised_old_asset_value=maybe_float(won_from_eok(appraised_old_asset_eok)),
            total_old_asset_value=maybe_float(won_from_eok(total_old_asset_value_eok)),
            avg_official_land_price_per_sqm=maybe_float(avg_official_land_price_per_sqm),
            target_households_override=maybe_int(int(target_households_override)),
            general_sale_ratio_override=maybe_float(general_sale_ratio_override_pct / 100.0),
            rental_ratio_override=maybe_float(rental_ratio_override_pct / 100.0),
            donation_ratio_override=maybe_float(donation_ratio_override_pct / 100.0),
            member_sale_price_ratio_override=maybe_float(member_sale_price_ratio_pct / 100.0),
            sale_rate=sale_rate_pct / 100.0,
            cash_settlement_rate=cash_settlement_rate_pct / 100.0,
            pf_rate=pf_rate_pct / 100.0,
            move_loan_rate=move_loan_rate_pct / 100.0,
            pf_financing_ratio=pf_financing_ratio_pct / 100.0,
            pf_interest_months=pf_interest_months,
            average_move_loan_amount=won_from_eok(average_move_loan_amount_eok),
            move_loan_duration_months=move_loan_duration_months,
            is_one_homeowner=is_one_homeowner,
            holding_years=holding_years,
        )
        result = calculate_union_project(inputs)
    else:
        st.subheader("빠른 입력")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            purchase_price_eok = st.number_input("매수가(억)", min_value=0.0, value=18.0, step=0.1)
            completion_year = st.number_input("준공연도", min_value=1970, max_value=2100, value=2000, step=1, help=remodeling_help["completion_year"])
        with c2:
            current_households = st.number_input("현재 세대수", min_value=1, value=300, step=1)
            current_unit_exclusive_area = st.number_input("현재 전용면적(㎡)", min_value=20.0, value=84.0, step=1.0)
        with c3:
            expected_new_exclusive_area = st.number_input("리모델링 후 전용면적(㎡)", min_value=20.0, value=94.0, step=1.0)
            comparison_new_price_eok = st.number_input("비교 신축 시세(억)", min_value=0.0, value=20.0, step=0.1)
        with c4:
            general_sale_price_eok = st.number_input("일반분양 평균가(억)", min_value=0.0, value=0.0, step=0.1)
            construction_cost_per_pyeong_man = st.number_input("공사비(만원/평)", min_value=0.0, value=650.0, step=10.0)

        st.subheader("리모델링 기본값")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            remodeling_kind = RemodelingKind(st.radio("리모델링 방식", [RemodelingKind.INCREASE.value, RemodelingKind.NO_INCREASE.value], horizontal=True))
            additional_households = st.number_input("증가 세대수(선택)", min_value=0, value=0, step=1, help=remodeling_help["additional_households"])
        with b2:
            current_floors = st.number_input("현재 층수", min_value=1, value=15, step=1)
            vertical_extension = st.checkbox("수직증축 포함", value=True)
        with b3:
            planned_added_floors = st.number_input("계획 추가 층수", min_value=0, value=2, step=1, help=remodeling_help["planned_added_floors"])
            general_sale_price_basis_exclusive_area = st.number_input("일반분양가 기준 전용(㎡)", min_value=20.0, value=84.0, step=1.0)
        with b4:
            official_price_reference_eok = st.number_input("현재 공시가격/감정가(억, 선택)", min_value=0.0, value=0.0, step=0.1)
            general_sale_price_per_pyeong_manwon = st.number_input("일반분양 평당가(만원/평, 선택)", min_value=0.0, value=0.0, step=100.0)

        with st.expander("정밀 입력", expanded=False):
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                pf_rate_pct = st.number_input("PF 금리(%)", min_value=0.0, max_value=30.0, value=7.5, step=0.1)
                pf_financing_ratio_pct = st.number_input("PF 조달비율(%)", min_value=0.0, max_value=95.0, value=round(default_pf_financing_ratio(ProjectKind.REMODELING) * 100.0, 1), step=1.0)
            with d2:
                project_duration_years = st.number_input("예상 사업기간(년)", min_value=0.5, value=4.0, step=0.5)
                move_cost_per_household_eok = st.number_input("세대당 임시이주비(억)", min_value=0.0, value=0.2, step=0.1, help=remodeling_help["move_cost"])
            with d3:
                total_site_area_sqm = st.number_input("전체 대지면적(㎡, 선택)", min_value=0.0, value=0.0, step=10.0)
            with d4:
                sale_rate_pct = st.number_input("일반분양 판매율(%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0)

        inputs = RemodelingInputs(
            region_is_seoul=region_is_seoul,
            purchase_price=won_from_eok(purchase_price_eok),
            completion_year=int(completion_year),
            current_households=int(current_households),
            current_unit_exclusive_area=current_unit_exclusive_area,
            expected_new_exclusive_area=expected_new_exclusive_area,
            comparison_new_price=maybe_float(won_from_eok(comparison_new_price_eok)),
            general_sale_price=maybe_float(won_from_eok(general_sale_price_eok)),
            general_sale_price_basis_exclusive_area=maybe_float(general_sale_price_basis_exclusive_area),
            general_sale_price_per_pyeong_manwon=maybe_float(general_sale_price_per_pyeong_manwon),
            construction_cost_per_pyeong=construction_cost_per_pyeong_man * 10_000.0,
            remodeling_kind=remodeling_kind,
            additional_households=maybe_int(int(additional_households)),
            current_floors=int(current_floors),
            vertical_extension=vertical_extension,
            planned_added_floors=int(planned_added_floors),
            official_price_reference=maybe_float(won_from_eok(official_price_reference_eok)),
            total_site_area_sqm=maybe_float(total_site_area_sqm),
            pf_rate=pf_rate_pct / 100.0,
            sale_rate=sale_rate_pct / 100.0,
            pf_financing_ratio=pf_financing_ratio_pct / 100.0,
            project_duration_years=project_duration_years,
            move_cost_per_household=won_from_eok(move_cost_per_household_eok),
        )
        result = calculate_remodeling(inputs)

    st.subheader("결과")
    render_metric_cards(result.top_cards)
    render_summary_lines(result.summary_lines)
    render_warning_badges(result.warnings)

    with st.expander("왜 이렇게 계산됐는지", expanded=False):
        render_table(result.why_rows, "핵심 가정")

    with st.expander("왜곡 위험", expanded=True if result.warnings else False):
        if result.warnings:
            render_table(
                [
                    {
                        "수준": item.level,
                        "분류": item.category,
                        "내용": item.message,
                    }
                    for item in result.warnings
                ],
                "경고와 점검 포인트",
            )
        else:
            st.info("현재 입력 기준으로 큰 경고는 없습니다.")

    with st.expander("사업수지", expanded=False):
        render_table(result.business_rows, "사업수지 요약")

    with st.expander("정산/권리가액", expanded=False):
        render_table(result.settlement_rows, "정산·권리가액 요약")

    with st.expander("민감도", expanded=False):
        render_table(result.sensitivity_rows, "분양가·공사비 민감도")

    with st.expander("법/제도 반영", expanded=False):
        render_table(result.policy_rows, "법·제도 반영 요약")

    with st.expander("입력 근거와 출처", expanded=False):
        render_table(result.source_rows, "출처 요약")

    st.caption("이 계산기는 투자·의사결정 보조용 개략 추정치입니다. 관리처분계획, 감정평가서, 조합 안내문, 분양계획이 있으면 해당 수치를 우선해 다시 검토하는 것이 안전합니다.")


if __name__ == "__main__":
    main()
