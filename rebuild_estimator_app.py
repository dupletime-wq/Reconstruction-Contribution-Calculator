from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from io import BytesIO
import math
import re
import statistics

import pandas as pd
import streamlit as st

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


SCENARIOS: dict[str, dict[str, float]] = {
    "\ub0d9\uad00": {
        "sale_rate": 1.00,
        "cash_settlement_rate": 0.00,
        "construction_cost_per_pyeong": 8_500_000.0,
        "pf_rate": 0.07,
        "duration_multiplier": 0.80,
    },
    "\uae30\uc900": {
        "sale_rate": 0.97,
        "cash_settlement_rate": 0.03,
        "construction_cost_per_pyeong": 9_000_000.0,
        "pf_rate": 0.085,
        "duration_multiplier": 1.00,
    },
    "\ubcf4\uc218": {
        "sale_rate": 0.92,
        "cash_settlement_rate": 0.07,
        "construction_cost_per_pyeong": 10_000_000.0,
        "pf_rate": 0.10,
        "duration_multiplier": 1.35,
    },
}

STAGE_BASE_MONTHS: dict[str, int] = {
    "\uc7ac\uac74\ucd95\uc9c4\ub2e8": 120,
    "\uc815\ube44\uad6c\uc5ed\uc9c0\uc815": 96,
    "\ucd94\uc9c4\uc704\uc2b9\uc778": 84,
    "\uc870\ud569\uc124\ub9bd\uc778\uac00": 72,
    "\uc0ac\uc5c5\uc2dc\ud589\uc778\uac00": 48,
    "\uad00\ub9ac\ucc98\ubd84\uc778\uac00": 36,
    "\uc774\uc8fc/\ucca0\uac70": 24,
    "\ucc29\uacf5": 18,
    "\uc900\uacf5/\uc785\uc8fc": 0,
}

EXIT_SCENARIOS: tuple[str, ...] = (
    "\uc785\uc8fc\uad8c \ub2e8\uacc4 \ub9e4\ub3c4",
    "\uc900\uacf5 \uc9c1\ud6c4 \ub9e4\ub3c4",
    "\uc785\uc8fc \ud6c4 3\ub144 \ubcf4\uc720",
)

MONEY_TOKEN_PATTERN = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*(jo|eok|cheonman|baekman|manwon|\uc870|\uc5b5|\ucc9c\ub9cc|\ub9cc\uc6d0|\uc6d0)?",
    re.IGNORECASE,
)
PERCENT_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")

KEY_ALIASES: dict[str, str] = {
    "\ucd94\uc815\ube44\ub840\uc728": "proportional_ratio",
    "\ube44\ub840\uc728": "proportional_ratio",
    "\uc870\ud569\uc6d0\ubd84\uc591\uc218\uc785": "member_sale_revenue",
    "\uc77c\ubc18\ubd84\uc591\uc218\uc785": "general_sale_revenue",
    "\ucd1d\uc218\uc785": "total_revenue",
    "\ucd1d\uc9c0\ucd9c": "total_cost",
    "\uc885\uc804\uc790\uc0b0\ucd1d\uc561": "total_old_asset_value",
    "\uc7ac\uac74\ucd95\ubd80\ub2f4\uae08": "reconstruction_levy",
}

DISPLAY_KEY_LABELS: dict[str, str] = {
    "proportional_ratio": "\ucd94\uc815\ube44\ub840\uc728",
    "member_sale_revenue": "\uc870\ud569\uc6d0\ubd84\uc591\uc218\uc785",
    "general_sale_revenue": "\uc77c\ubc18\ubd84\uc591\uc218\uc785",
    "total_revenue": "\ucd1d\uc218\uc785",
    "total_cost": "\ucd1d\uc9c0\ucd9c",
    "total_old_asset_value": "\uc885\uc804\uc790\uc0b0\ucd1d\uc561",
    "reconstruction_levy": "\uc7ac\uac74\ucd95\ubd80\ub2f4\uae08",
    "old_asset_formula": "\uc885\uc804\uc790\uc0b0 \uc0b0\uc2dd",
    "member_price_table_count": "\ubb38\uc11c \ubd84\uc591\uac00\ud45c \uac74\uc218",
    "parser_status": "\ud30c\uc11c \uc0c1\ud0dc",
    "old_asset_estimate": "\uc885\uc804\uc790\uc0b0 \ucd94\uc815\uc561",
    "adjustment_factor": "\ubcf4\uc815\uacc4\uc218",
}

SOURCE_LABELS: dict[str, str] = {
    "manual_appraisal": "\uc0ac\uc6a9\uc790 \uac10\uc815\uac00 \uc785\ub825",
    "public_price_adjusted": "\uacf5\uc2dc\uac00\uaca9 x \ubcf4\uc815\uacc4\uc218",
    "trade_backsolve": "\uc2e4\uac70\ub798\uac00 \uc5ed\uc0b0",
    "purchase_price_heuristic": "\ub9e4\uc218\uac00 \uae30\ubc18 \ucd94\uc815",
    "document_total_old_asset": "\ubb38\uc11c \uc885\uc804\uc790\uc0b0\ucd1d\uc561",
    "user_total_old_asset": "\uc0ac\uc6a9\uc790 \uc885\uc804\uc790\uc0b0\ucd1d\uc561",
    "scaled_individual_old_asset": "\uac1c\ubcc4 \uc885\uc804\uc790\uc0b0 \ud655\ub300\ucd94\uc815",
    "user_override": "\uc0ac\uc6a9\uc790 \ubcf4\uc815\uacc4\uc218",
    "document_formula": "\ubb38\uc11c \uc0b0\uc2dd \ubc18\uc601",
    "trade_vs_public": "\uc2e4\uac70\ub798/\uacf5\uc2dc\uac00 \ube44\uad50",
    "heuristic_default": "\ud734\ub9ac\uc2a4\ud2f1 \uae30\ubcf8\uac12",
    "engine": "\uacc4\uc0b0 \uc5d4\uc9c4",
}

VALUE_LABELS: dict[str, str] = {
    "pypdf_missing": "`pypdf` \uc124\uce58 \ud544\uc694",
    "unsupported": "\uc9c0\uc6d0\ud558\uc9c0 \uc54a\ub294 \ud30c\uc77c",
}

COLUMN_LABELS: dict[str, str] = {
    "key": "\ud56d\ubaa9",
    "value": "\uac12",
    "source": "\ucd9c\ucc98",
    "confidence": "\uc2e0\ub8b0\ub3c4",
    "notes": "\ube44\uace0",
}


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


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(key=key, value=value, source=source, confidence=confidence, notes=notes)


def won_from_eok(value: float) -> float:
    return float(value) * 100_000_000.0


def eok_from_won(value: float | None) -> float:
    return 0.0 if value is None else float(value) / 100_000_000.0


def fmt_eok(value: float) -> str:
    return f"{value / 100_000_000.0:,.2f}\uc5b5"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return default if den == 0 else num / den


def humanize_key(key: str) -> str:
    return DISPLAY_KEY_LABELS.get(str(key), str(key))


def humanize_source(source: str) -> str:
    source_text = str(source)
    if source_text.startswith("CSV:"):
        return f"CSV \ubb38\uc11c: {source_text[4:]}"
    if source_text.startswith("PDF:"):
        return f"PDF \ubb38\uc11c: {source_text[4:]}"
    return SOURCE_LABELS.get(source_text, source_text)


def humanize_value(value: object) -> str:
    return VALUE_LABELS.get(str(value), str(value))


def localized_records_frame(records: list[SourceRecord]) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(item) for item in records])
    if frame.empty:
        return frame
    frame["key"] = frame["key"].map(humanize_key)
    frame["value"] = frame["value"].map(humanize_value)
    frame["source"] = frame["source"].map(humanize_source)
    frame["confidence"] = frame["confidence"].map(lambda x: f"{float(x) * 100:.1f}%")
    frame["notes"] = frame["notes"].fillna("")
    return frame.rename(columns=COLUMN_LABELS)


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
        "\uc870": 1_0000_0000_0000,
        "\uc5b5": 100_000_000,
        "\ucc9c\ub9cc": 10_000_000,
        "\ub9cc\uc6d0": 10_000,
        "\uc6d0": 1,
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
        records.append(
            MemberPriceRecord(
                label=label,
                exclusive_area_sqm=exclusive,
                supply_area_sqm=supply,
                member_sale_price=price,
            )
        )
    return records


def merge_notices(notices: list[ParsedProjectNotice]) -> ParsedProjectNotice | None:
    if not notices:
        return None
    proportional_ratio = next((item.proportional_ratio for item in notices if item.proportional_ratio is not None), None)
    old_asset_formula = next((item.old_asset_formula for item in notices if item.old_asset_formula), None)
    member_price_table = next((item.member_price_table for item in notices if item.member_price_table), [])
    revenue_items: dict[str, float] = {}
    cost_items: dict[str, float] = {}
    extracted_records: list[SourceRecord] = []
    for notice in notices:
        revenue_items.update(notice.revenue_items)
        cost_items.update(notice.cost_items)
        extracted_records.extend(notice.extracted_records)
    return ParsedProjectNotice(
        proportional_ratio=proportional_ratio,
        old_asset_formula=old_asset_formula,
        member_price_table=member_price_table,
        revenue_items=revenue_items,
        cost_items=cost_items,
        extracted_records=extracted_records,
        source_name=", ".join(item.source_name for item in notices),
    )


def parse_uploaded_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        frame = pd.read_csv(BytesIO(file_bytes))
        extracted_records: list[SourceRecord] = []
        revenue_items: dict[str, float] = {}
        cost_items: dict[str, float] = {}
        proportional_ratio: float | None = None
        old_asset_formula: str | None = None
        if {"key", "value"}.issubset({str(col).lower() for col in frame.columns}):
            key_col = next(col for col in frame.columns if str(col).lower() == "key")
            value_col = next(col for col in frame.columns if str(col).lower() == "value")
            for _, row in frame.iterrows():
                key_raw = re.sub(r"\s+", "", str(row[key_col]))
                key = KEY_ALIASES.get(key_raw, key_raw)
                value = str(row[value_col]).strip()
                if not value:
                    continue
                if key == "proportional_ratio":
                    pct_match = PERCENT_PATTERN.search(value)
                    proportional_ratio = float(pct_match.group(1)) if pct_match else float(value)
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
            return ParsedProjectNotice(
                proportional_ratio=proportional_ratio,
                old_asset_formula=old_asset_formula,
                member_price_table=[],
                revenue_items=revenue_items,
                cost_items=cost_items,
                extracted_records=extracted_records,
                source_name=file_name,
            )
        member_price_table = []
        for _, row in frame.iterrows():
            try:
                label = str(row.iloc[0]).strip()
                exclusive = float(row.iloc[1])
                supply = float(row.iloc[2])
                price = parse_korean_money(str(row.iloc[3]))
            except Exception:
                continue
            if label and price is not None:
                member_price_table.append(MemberPriceRecord(label, exclusive, supply, price))
        return ParsedProjectNotice(
            proportional_ratio=None,
            old_asset_formula=None,
            member_price_table=member_price_table,
            revenue_items={},
            cost_items={},
            extracted_records=[record("member_price_table_count", str(len(member_price_table)), f"CSV:{file_name}", 0.90)],
            source_name=file_name,
        )

    if lower_name.endswith(".pdf"):
        if PdfReader is None:
            return ParsedProjectNotice(
                proportional_ratio=None,
                old_asset_formula=None,
                member_price_table=[],
                revenue_items={},
                cost_items={},
                extracted_records=[record("parser_status", "pypdf_missing", f"PDF:{file_name}", 0.10, "pypdf \uc124\uce58 \ud544\uc694")],
                source_name=file_name,
            )
        reader = PdfReader(BytesIO(file_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        revenue_items: dict[str, float] = {}
        cost_items: dict[str, float] = {}
        extracted_records: list[SourceRecord] = []
        proportional_ratio: float | None = None
        old_asset_formula: str | None = None
        member_price_table: list[MemberPriceRecord] = []
        table_pattern = re.compile(
            r"(?P<label>\d+\s*[A-Za-z\uac00-\ud7a3]+)\s+"
            r"(?P<exclusive>\d+(?:\.\d+)?)\s+"
            r"(?P<supply>\d+(?:\.\d+)?)\s+"
            r"(?P<price>\d[\d,]*(?:\.\d+)?\s*(?:\uc5b5|\ub9cc\uc6d0|\uc6d0)?)"
        )
        for line in lines:
            compact = re.sub(r"\s+", "", line)
            if "\ube44\ub840\uc728" in compact and proportional_ratio is None:
                pct_match = PERCENT_PATTERN.search(line)
                if pct_match:
                    proportional_ratio = float(pct_match.group(1))
                    extracted_records.append(record("proportional_ratio", f"{proportional_ratio:.2f}", f"PDF:{file_name}", 0.74))
            if old_asset_formula is None and ("\uacf5\ub3d9\uc8fc\ud0dd" in compact or "\uacf5\uc2dc\uac00\uaca9" in compact) and ("x" in compact.lower() or "\u00d7" in compact):
                old_asset_formula = line[:200]
                extracted_records.append(record("old_asset_formula", old_asset_formula, f"PDF:{file_name}", 0.68))
            for label, key in KEY_ALIASES.items():
                if label in compact:
                    amount = parse_korean_money(line)
                    if amount is None:
                        continue
                    if key in {"member_sale_revenue", "general_sale_revenue", "total_revenue"}:
                        revenue_items[key] = amount
                    else:
                        cost_items[key] = amount
                    extracted_records.append(record(key, f"{amount:,.0f}", f"PDF:{file_name}", 0.70))
            for match in table_pattern.finditer(line):
                price = parse_korean_money(match.group("price"))
                if price is not None:
                    member_price_table.append(
                        MemberPriceRecord(
                            label=match.group("label"),
                            exclusive_area_sqm=float(match.group("exclusive")),
                            supply_area_sqm=float(match.group("supply")),
                            member_sale_price=price,
                        )
                    )
        if member_price_table:
            extracted_records.append(record("member_price_table_count", str(len(member_price_table)), f"PDF:{file_name}", 0.64))
        return ParsedProjectNotice(
            proportional_ratio=proportional_ratio,
            old_asset_formula=old_asset_formula,
            member_price_table=member_price_table[:12],
            revenue_items=revenue_items,
            cost_items=cost_items,
            extracted_records=extracted_records,
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


def is_capital_area(address: str) -> bool:
    return any(token in address for token in ("Seoul", "Gyeonggi", "Incheon", "\uc11c\uc6b8", "\uacbd\uae30", "\uc778\ucc9c"))


def floor_factor(floor_no: int) -> float:
    if floor_no <= 3 and floor_no > 0:
        return 0.98
    if floor_no >= 13:
        return 1.02
    return 1.00


def adjustment_factor(public_price: float | None, recent_trade: float | None, override_value: float | None, old_asset_formula: str | None, applied_fields: set[str], address: str) -> tuple[float, str]:
    if override_value:
        return clamp(override_value, 1.05, 1.65), "user_override"
    if old_asset_formula and "old_asset_formula" in applied_fields:
        tail = old_asset_formula.split("x")[-1] if "x" in old_asset_formula.lower() else old_asset_formula.split("\u00d7")[-1]
        digits = "".join(ch for ch in tail if ch.isdigit() or ch == ".")
        try:
            return clamp(float(digits), 1.05, 1.65), "document_formula"
        except ValueError:
            pass
    if public_price and recent_trade:
        return clamp(recent_trade / public_price, 1.05, 1.65), "trade_vs_public"
    return (1.25 if is_capital_area(address) else 1.18), "heuristic_default"


def default_member_price_table(
    user_text: str,
    doc_table: list[MemberPriceRecord],
    use_doc_table: bool,
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
    sizes = sorted({59.0, 84.0, 101.0, round(base_exclusive)})
    rows: list[MemberPriceRecord] = []
    for size in sizes:
        area_ratio = safe_div(size, base_exclusive, 1.0)
        member_price = base_market_price * (area_ratio**0.98) * 0.85
        rows.append(MemberPriceRecord(label=f"{int(size)}\ud615", exclusive_area_sqm=float(size), supply_area_sqm=round(size / 0.78, 2), member_sale_price=member_price))
    return rows


def analyze_scenario(inputs: dict, scenario_name: str) -> dict:
    scenario = SCENARIOS[scenario_name]
    records: list[SourceRecord] = []
    remaining_months = STAGE_BASE_MONTHS.get(inputs["current_stage"], 72) * scenario["duration_multiplier"] + (12 if inputs["delay_one_year"] else 0)
    base_sale_rate = inputs["sale_rate"] or scenario["sale_rate"]
    base_cash_rate = inputs["cash_settlement_rate"] or scenario["cash_settlement_rate"]
    base_cost_per_pyeong = inputs["construction_cost_per_pyeong"] or scenario["construction_cost_per_pyeong"]
    base_pf_rate = inputs["pf_rate"] or scenario["pf_rate"]

    adj_factor, adj_source = adjustment_factor(
        public_price=inputs["public_price"],
        recent_trade=inputs["recent_same_complex_trade_price"],
        override_value=inputs["adjustment_factor_override"],
        old_asset_formula=inputs["parsed_notice"].old_asset_formula if inputs["parsed_notice"] else None,
        applied_fields=inputs["applied_document_fields"],
        address=inputs["address"],
    )
    floor_adj = floor_factor(inputs["floor_no"])
    if inputs["appraised_old_asset_value"]:
        old_asset_estimate = inputs["appraised_old_asset_value"]
        old_asset_source = "manual_appraisal"
    elif inputs["public_price"]:
        old_asset_estimate = inputs["public_price"] * adj_factor * floor_adj
        old_asset_source = "public_price_adjusted"
    elif inputs["recent_same_complex_trade_price"]:
        old_asset_estimate = inputs["recent_same_complex_trade_price"] * floor_adj
        old_asset_source = "trade_backsolve"
    else:
        old_asset_estimate = inputs["purchase_price"] * 0.78 * floor_adj
        old_asset_source = "purchase_price_heuristic"

    if inputs["document_total_old_asset_value"] is not None:
        total_old_asset_value = inputs["document_total_old_asset_value"]
        total_old_asset_source = "document_total_old_asset"
    elif inputs["total_old_asset_value"]:
        total_old_asset_value = inputs["total_old_asset_value"]
        total_old_asset_source = "user_total_old_asset"
    else:
        member_count_seed = max(int(round(inputs["current_households"] * (1 - base_cash_rate))), 1)
        total_old_asset_value = old_asset_estimate * member_count_seed
        total_old_asset_source = "scaled_individual_old_asset"

    price_table = default_member_price_table(
        user_text=inputs["member_price_text"],
        doc_table=inputs["parsed_notice"].member_price_table if inputs["parsed_notice"] else [],
        use_doc_table=inputs["use_doc_price_table"],
        comparison_new_price=inputs["comparison_new_apt_price"],
        general_sale_price=inputs["general_sale_price"],
        purchase_price=inputs["purchase_price"],
        current_exclusive_area=inputs["current_unit_exclusive_area"],
        expected_new_area=inputs["expected_new_exclusive_area"],
    )

    if inputs["land_share"] and inputs["target_far"]:
        land_area_sqm = inputs["land_share"] * inputs["current_households"]
        gross_floor_area_sqm = land_area_sqm * (inputs["target_far"] / 100.0)
    elif inputs["current_far"] and inputs["target_far"]:
        current_gross_floor_area_sqm = inputs["current_households"] * inputs["current_unit_supply_area"] * 1.08
        gross_floor_area_sqm = current_gross_floor_area_sqm * safe_div(inputs["target_far"], inputs["current_far"], 1.0)
    else:
        avg_supply = statistics.mean(item.supply_area_sqm for item in price_table)
        gross_floor_area_sqm = inputs["planned_households"] * avg_supply * 1.15
    current_gross_floor_area_sqm = inputs["current_households"] * inputs["current_unit_supply_area"] * 1.08
    gross_floor_area_pyeong = gross_floor_area_sqm / 3.3058
    current_gross_area_pyeong = current_gross_floor_area_sqm / 3.3058

    direct_construction_cost = gross_floor_area_pyeong * base_cost_per_pyeong
    if inputs["delay_one_year"] and inputs["current_stage"] not in {"\ucc29\uacf5", "\uc900\uacf5/\uc785\uc8fc"}:
        direct_construction_cost *= 1.04
    demolition_cost = current_gross_area_pyeong * base_cost_per_pyeong * 0.06
    design_and_pm_cost = direct_construction_cost * 0.06
    reserve_cost = (direct_construction_cost + design_and_pm_cost + demolition_cost) * 0.05

    member_count = max(int(round(inputs["current_households"] * (1 - base_cash_rate))), 1)
    general_sale_households = max(inputs["planned_households"] - member_count, 0)
    if inputs["general_sale_ratio"] is not None:
        general_sale_households = max(int(round(inputs["planned_households"] * inputs["general_sale_ratio"])), 0)
        member_count = max(inputs["planned_households"] - general_sale_households, 1)

    average_member_sale_price = statistics.mean(item.member_sale_price for item in price_table)
    benchmark_new_price = inputs["comparison_new_apt_price"] or inputs["general_sale_price"] or average_member_sale_price / 0.85
    member_sale_revenue = member_count * average_member_sale_price
    general_sale_unit_price = inputs["general_sale_price"] or benchmark_new_price
    general_sale_revenue = general_sale_households * general_sale_unit_price * base_sale_rate
    ancillary_revenue = inputs["ancillary_revenue"] or direct_construction_cost * 0.02
    other_disposal_revenue = inputs["other_disposal_revenue"] or direct_construction_cost * 0.01

    sales_expense = general_sale_revenue * 0.025
    settlement_and_litigation_cost = inputs["liquidation_cost_override"] if inputs["liquidation_cost_override"] is not None else total_old_asset_value * (0.005 + base_cash_rate * 0.08)
    tax_and_charge_cost = (direct_construction_cost + demolition_cost + design_and_pm_cost + reserve_cost + sales_expense + settlement_and_litigation_cost) * 0.03
    pf_principal = max((direct_construction_cost + demolition_cost + design_and_pm_cost + sales_expense + tax_and_charge_cost - reserve_cost) * 0.60, 0.0)
    financing_cost = pf_principal * base_pf_rate * 0.55 * (remaining_months / 12.0)
    move_loan_months = max(min(remaining_months, 30.0), 12.0)
    move_loan_interest_cost = member_count * (old_asset_estimate * 0.40) * inputs["move_loan_rate"] * (move_loan_months / 12.0)

    business_boost = 1.0
    if inputs["apply_seoul_business_boost"] and ("\uc11c\uc6b8" in inputs["address"] or "Seoul" in inputs["address"]) and inputs["public_land_price_avg"]:
        business_boost = clamp(safe_div(inputs["seoul_average_public_land_price"], inputs["public_land_price_avg"], 1.0) + inputs["alpha"] + inputs["beta"], 1.0, 2.0)
        general_sale_revenue *= 1 + 0.06 * (business_boost - 1.0)

    parsed_notice = inputs["parsed_notice"]
    if parsed_notice and "member_sale_revenue" in inputs["applied_document_fields"] and "member_sale_revenue" in parsed_notice.revenue_items:
        member_sale_revenue = parsed_notice.revenue_items["member_sale_revenue"]
    if parsed_notice and "general_sale_revenue" in inputs["applied_document_fields"] and "general_sale_revenue" in parsed_notice.revenue_items:
        general_sale_revenue = parsed_notice.revenue_items["general_sale_revenue"]

    total_revenue = member_sale_revenue + general_sale_revenue + ancillary_revenue + other_disposal_revenue
    total_cost = direct_construction_cost + demolition_cost + design_and_pm_cost + reserve_cost + sales_expense + settlement_and_litigation_cost + tax_and_charge_cost + financing_cost + move_loan_interest_cost + inputs["reconstruction_levy"]

    if parsed_notice and "total_revenue" in inputs["applied_document_fields"] and "total_revenue" in parsed_notice.revenue_items:
        total_revenue = parsed_notice.revenue_items["total_revenue"]
    if parsed_notice and "total_cost" in inputs["applied_document_fields"] and "total_cost" in parsed_notice.cost_items:
        total_cost = parsed_notice.cost_items["total_cost"]

    proportional_ratio = safe_div(total_revenue - total_cost, total_old_asset_value, 0.0) * 100.0
    if parsed_notice and "proportional_ratio" in inputs["applied_document_fields"] and parsed_notice.proportional_ratio is not None:
        proportional_ratio = parsed_notice.proportional_ratio
    rights_value = old_asset_estimate * (proportional_ratio / 100.0)

    allocations: list[dict] = []
    for item in price_table:
        additional_contribution = item.member_sale_price - rights_value
        cover_ratio = safe_div(rights_value, item.member_sale_price, 0.0)
        size_proximity = 1.0 - min(abs(item.exclusive_area_sqm - inputs["current_unit_exclusive_area"]) / max(inputs["current_unit_exclusive_area"], 1.0), 1.0)
        burden_score = 1.0 - min(max(additional_contribution, 0.0) / max(inputs["purchase_price"], 1.0), 1.0)
        score = 0.5 * size_proximity + 0.3 * min(cover_ratio, 1.0) + 0.2 * burden_score
        if cover_ratio < 0.35 and not inputs["aggressive_upsize"]:
            continue
        signal = "\uac00\ub2a5\uc131 \ub192\uc74c" if score >= 0.75 else "\ubcf4\ud1b5" if score >= 0.55 else "\ub0ae\uc74c"
        allocations.append(
            {
                "\ud3c9\ud615": item.label,
                "\uc804\uc6a9\u33a1": item.exclusive_area_sqm,
                "\uacf5\uae09\u33a1": item.supply_area_sqm,
                "\uc870\ud569\uc6d0\ubd84\uc591\uac00": item.member_sale_price,
                "\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08": additional_contribution,
                "\ucee4\ubc84\uc728": cover_ratio,
                "\uc810\uc218": score,
                "\ud310\uc815": signal,
            }
        )
    allocations.sort(key=lambda row: row["\uc810\uc218"], reverse=True)
    allocations = allocations[:3] if allocations else []
    selected = allocations[0] if allocations else {
        "\ud3c9\ud615": "-",
        "\uc804\uc6a9\u33a1": 0.0,
        "\uacf5\uae09\u33a1": 0.0,
        "\uc870\ud569\uc6d0\ubd84\uc591\uac00": 0.0,
        "\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08": 0.0,
        "\ucee4\ubc84\uc728": 0.0,
        "\uc810\uc218": 0.0,
        "\ud310\uc815": "\ub0ae\uc74c",
    }

    exits: list[dict] = []
    for exit_name in EXIT_SCENARIOS:
        if exit_name == "\uc785\uc8fc\uad8c \ub2e8\uacc4 \ub9e4\ub3c4":
            months = max(remaining_months * 0.65, 6.0)
            realization = 0.80
        elif exit_name == "\uc900\uacf5 \uc9c1\ud6c4 \ub9e4\ub3c4":
            months = remaining_months
            realization = 0.95
        else:
            months = remaining_months + 36.0
            realization = 1.02**3
        years = max(months / 12.0, 0.5)
        gross_exit_value = benchmark_new_price * realization
        acquisition_cost = inputs["purchase_price"] * inputs["acquisition_rate"]
        holding_cost = inputs["purchase_price"] * inputs["annual_holding_rate"] * years
        capital_interest = max(selected["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"], 0.0) * max(base_pf_rate + 0.01, 0.04) * years * 0.45
        disposal_cost = gross_exit_value * inputs["brokerage_rate"]
        pretax_profit = gross_exit_value - disposal_cost - (inputs["purchase_price"] + acquisition_cost + holding_cost + max(selected["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"], 0.0) + capital_interest)
        after_tax_profit = pretax_profit - max(pretax_profit, 0.0) * inputs["capital_gains_effective_rate"]
        total_outflow = inputs["purchase_price"] + acquisition_cost + holding_cost + max(selected["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"], 0.0) + capital_interest
        roi = safe_div(after_tax_profit, total_outflow, 0.0)
        net_exit_inflow = gross_exit_value - disposal_cost - max(pretax_profit, 0.0) * inputs["capital_gains_effective_rate"]
        irr = None
        if total_outflow > 0 and net_exit_inflow > 0:
            irr = (net_exit_inflow / total_outflow) ** (1.0 / years) - 1.0
        break_even_purchase = net_exit_inflow - (acquisition_cost + holding_cost + max(selected["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"], 0.0) + capital_interest)
        break_even_additional = net_exit_inflow - (inputs["purchase_price"] + acquisition_cost + holding_cost + capital_interest)
        retention = max(1.0 - inputs["brokerage_rate"] - inputs["capital_gains_effective_rate"] * 0.80, 0.05)
        break_even_exit = total_outflow / retention
        exits.append(
            {
                "\uc5d1\uc2dc\ud2b8": exit_name,
                "\uc608\uc0c1 \uc2dc\uc810(\ub144)": years,
                "\uc790\uc0b0\uac00\uce58": gross_exit_value,
                "\uc138\uc804 \uc21c\uc774\uc775": pretax_profit,
                "\uc138\ud6c4 \uc21c\uc774\uc775": after_tax_profit,
                "ROI": roi,
                "IRR": irr,
                "\uc190\uc775\ubd84\uae30 \ub9e4\uc218\uac00": break_even_purchase,
                "\uc190\uc775\ubd84\uae30 \ucd94\uac00\ubd84\ub2f4\uae08": break_even_additional,
                "\uc190\uc775\ubd84\uae30 \uc900\uacf5\uc2dc\uc138": break_even_exit,
            }
        )

    completeness = [
        bool(inputs["current_households"]),
        bool(inputs["planned_households"]),
        inputs["land_share"] is not None,
        inputs["current_far"] is not None,
        inputs["target_far"] is not None,
        bool(price_table),
    ]
    project_input_completion = (sum(completeness) / len(completeness)) * 100.0
    valuation_strength = statistics.mean([0.96 if old_asset_source == "manual_appraisal" else 0.82 if old_asset_source == "public_price_adjusted" else 0.68 if old_asset_source == "trade_backsolve" else 0.36, 0.95 if total_old_asset_source == "user_total_old_asset" else 0.88 if total_old_asset_source == "document_total_old_asset" else 0.54, 0.84 if adj_source == "document_formula" else 0.78 if adj_source == "trade_vs_public" else 0.44]) * 100.0
    schedule_certainty = clamp(100.0 - STAGE_BASE_MONTHS.get(inputs["current_stage"], 72) * 0.45 - (12.0 if inputs["delay_one_year"] else 0.0), 20.0, 100.0)
    tax_completion = 100.0
    confidence_score = project_input_completion * 0.40 + valuation_strength * 0.30 + schedule_certainty * 0.20 + tax_completion * 0.10
    confidence_label = "\ub192\uc74c" if confidence_score >= 80 else "\ubcf4\ud1b5" if confidence_score >= 60 else "\ub0ae\uc74c"

    records.extend(
        [
            record("old_asset_estimate", f"{old_asset_estimate:,.0f}", old_asset_source, 0.78),
            record("total_old_asset_value", f"{total_old_asset_value:,.0f}", total_old_asset_source, 0.68),
            record("adjustment_factor", f"{adj_factor:.3f}", adj_source, 0.70),
            record("total_revenue", f"{total_revenue:,.0f}", "engine", 0.70),
            record("total_cost", f"{total_cost:,.0f}", "engine", 0.70),
            record("proportional_ratio", f"{proportional_ratio:.2f}", "engine", 0.70),
        ]
    )

    return {
        "scenario_name": scenario_name,
        "remaining_months": remaining_months,
        "old_asset_estimate": old_asset_estimate,
        "total_old_asset_value": total_old_asset_value,
        "adjustment_factor": adj_factor,
        "floor_factor": floor_adj,
        "rights_value": rights_value,
        "old_asset_source": old_asset_source,
        "total_old_asset_source": total_old_asset_source,
        "price_table": price_table,
        "allocations": allocations,
        "selected": selected,
        "project": {
            "\ucd1d\uc218\uc785": total_revenue,
            "\ucd1d\uc9c0\ucd9c": total_cost,
            "\ucd94\uc815\ube44\ub840\uc728": proportional_ratio,
            "\uc138\ub300\ub2f9 \ud3c9\uade0 \ubd84\ub2f4\uae08": max(average_member_sale_price - old_asset_estimate * (proportional_ratio / 100.0), 0.0),
            "\uc77c\ubc18\ubd84\uc591 \uc5ec\ub825": safe_div(general_sale_households, inputs["planned_households"], 0.0),
            "\uc9c1\uc811\uacf5\uc0ac\ube44": direct_construction_cost,
            "\ucca0\uac70/\uc815\ube44\uae30\ubc18": demolition_cost,
            "\uc124\uacc4/\uac10\ub9ac/PM": design_and_pm_cost,
            "\uc608\ube44\ube44": reserve_cost,
            "PF \uae08\uc735\ube44\uc6a9": financing_cost,
            "\uc774\uc8fc\ube44 \uc774\uc790": move_loan_interest_cost,
            "\ubd84\uc591\uacbd\ube44": sales_expense,
            "\uc81c\uc138\uacf5\uacfc\uae08": tax_and_charge_cost,
            "\uccad\uc0b0/\uc18c\uc1a1\ube44\uc6a9": settlement_and_litigation_cost,
            "\ubcf4\uc815\uacc4\uc218": business_boost,
        },
        "exits": exits,
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "source_records": records,
    }


def sensitivity_grid(inputs: dict, scenario_name: str, exit_name: str) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for sale_rate in [0.92, 0.95, 0.97, 1.00]:
        for cost_multiplier in [0.95, 1.00, 1.05, 1.10]:
            variant = dict(inputs)
            variant["sale_rate"] = sale_rate
            variant["construction_cost_per_pyeong"] = inputs["construction_cost_per_pyeong"] * cost_multiplier
            result = analyze_scenario(variant, scenario_name)
            exit_row = next(row for row in result["exits"] if row["\uc5d1\uc2dc\ud2b8"] == exit_name)
            rows.append(
                {
                    "\ud310\ub9e4\uc728(%)": round(sale_rate * 100, 1),
                    "\uacf5\uc0ac\ube44\ubc30\uc218": cost_multiplier,
                    "\uc138\ud6c4 \uc21c\uc774\uc775(\uc5b5)": exit_row["\uc138\ud6c4 \uc21c\uc774\uc775"] / 100_000_000,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="\uc7ac\uac74\ucd95 \ub9e4\uc218 \uc190\uc775 \ucd94\uc815\uae30", page_icon="\ud83c\udfd7", layout="wide")
    st.title("\uc11c\uc6b8\u00b7\uc218\ub3c4\uad8c \uc7ac\uac74\ucd95 \ub9e4\uc218 \uc190\uc775 \ucd94\uc815\uae30")
    st.caption("\uc77c\ubc18 \uc2a4\ud2b8\ub9bc\ub9bf \uc704\uc82f\ub9cc \uc0ac\uc6a9\ud558\ub294 \ub2e8\uc77c `app.py` \uad6c\uc131\uc785\ub2c8\ub2e4. \ubb38\uc11c \uc5c5\ub85c\ub4dc \uac12\uc740 \ubc14\ub85c \ubc18\uc601\ub418\uc9c0 \uc54a\uace0, \uc0ac\uc6a9\uc790\uac00 \uc120\ud0dd\ud55c \ud56d\ubaa9\ub9cc \uc801\uc6a9\ub429\ub2c8\ub2e4.")

    st.sidebar.header("\uc81c\uc5b4")
    aggressive_upsize = st.sidebar.checkbox("\uacf5\uaca9\uc801 \ud3c9\ud615 \uc5c5\uc0ac\uc774\uc988 \ud5c8\uc6a9", value=False)
    scenario_focus = st.sidebar.selectbox("\ud654\uba74 \uae30\uc900 \uc2dc\ub098\ub9ac\uc624", list(SCENARIOS.keys()), index=1)
    uploaded_files = st.sidebar.file_uploader("\ucd94\uc815\ubd84\ub2f4\uae08 PDF / CSV \uc5c5\ub85c\ub4dc", type=["pdf", "csv"], accept_multiple_files=True)

    parsed_notices: list[ParsedProjectNotice] = []
    if uploaded_files:
        for file in uploaded_files:
            parsed_notices.append(parse_uploaded_notice(file.name, file.getvalue()))
    merged_notice = merge_notices(parsed_notices)
    extracted_options = []
    if merged_notice:
        extracted_options = sorted({item.key for item in merged_notice.extracted_records if item.key not in {"member_price_table_count", "parser_status"}})
        st.sidebar.caption(f"\ud30c\uc2f1 \ubb38\uc11c: {merged_notice.source_name}")
    applied_document_fields = set(
        st.sidebar.multiselect(
            "\uc801\uc6a9\ud560 \ubb38\uc11c \ucd94\ucd9c\uac12",
            options=extracted_options,
            default=[],
            format_func=humanize_key,
        )
    )
    use_doc_price_table = st.sidebar.checkbox("\ubb38\uc11c \ubd84\uc591\uac00\ud45c \uc801\uc6a9", value=False, disabled=not (merged_notice and merged_notice.member_price_table))

    tabs = st.tabs([
        "\ube60\ub978 \uc785\ub825",
        "\ub2e8\uc9c0/\uc0ac\uc5c5 \uc815\ubcf4",
        "\uc885\uc804\uc790\uc0b0\u00b7\ubc30\uc815\ud3c9\ud615",
        "\uc0ac\uc5c5\uc218\uc9c0",
        "\ub0b4 \uc190\uc775",
        "\ubbfc\uac10\ub3c4\u00b7\uadfc\uac70",
    ])

    with tabs[0]:
        st.info("\ud575\uc2ec \ub9e4\ubb3c \uc815\ubcf4\ub9cc \ub123\uc5b4\ub3c4 \uae30\uc900 \ucd94\uc815\uc774 \ub3cc\uc544\uac11\ub2c8\ub2e4.")
        col1, col2, col3 = st.columns(3)
        with col1:
            complex_name = st.text_input("\ub2e8\uc9c0\uba85", value="\uc555\uad6c\uc815 \uc608\uc2dc \ub2e8\uc9c0")
            address = st.text_input("\uc8fc\uc18c", value="\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uac15\ub0a8\uad6c \uc555\uad6c\uc815\ub3d9")
            current_stage = st.selectbox("\ud604\uc7ac \uc0ac\uc5c5\ub2e8\uacc4", list(STAGE_BASE_MONTHS.keys()), index=3)
        with col2:
            current_unit_supply_area = st.number_input("\ud604\uc7ac \uacf5\uae09\uba74\uc801(\u33a1)", min_value=20.0, value=107.7, step=1.0)
            current_unit_exclusive_area = st.number_input("\ud604\uc7ac \uc804\uc6a9\uba74\uc801(\u33a1)", min_value=20.0, value=84.0, step=1.0)
            floor_no = st.number_input("\uce35\uc218", min_value=1, value=10, step=1)
        with col3:
            purchase_price_eok = st.number_input("\ub9e4\uc218\uac00(\uc5b5)", min_value=0.0, value=35.0, step=0.1)
            purchase_date = st.date_input("\ub9e4\uc218\uc608\uc815\uc77c", value=date.today())
            comparison_new_price_eok = st.number_input("\ube44\uad50 \uc2e0\ucd95 \uc2dc\uc138(\uc5b5)", min_value=0.0, value=48.0, step=0.1)
            expected_new_exclusive_area = st.number_input("\uc608\uc0c1 \uc0c8 \uc804\uc6a9\uba74\uc801(\u33a1)", min_value=0.0, value=84.0, step=1.0)

    with tabs[1]:
        with st.expander("\ub2e8\uc9c0 \uaddc\ubaa8 / \ubd84\uc591 \uac00\uc815", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                building_no = st.text_input("\ub3d9 \uc815\ubcf4", value="101\ub3d9")
                land_share = st.number_input("\ub300\uc9c0\uc9c0\ubd84(\u33a1)", min_value=0.0, value=25.0, step=0.1)
                current_households = st.number_input("\uae30\uc874 \uc138\ub300\uc218", min_value=1, value=480, step=1)
                planned_households = st.number_input("\uc608\uc0c1 \uc138\ub300\uc218", min_value=1, value=620, step=1)
            with col2:
                current_far = st.number_input("\ud604\ud669 \uc6a9\uc801\ub960(%)", min_value=0.0, value=180.0, step=1.0)
                target_far = st.number_input("\ubaa9\ud45c \uc6a9\uc801\ub960(%)", min_value=0.0, value=260.0, step=1.0)
                general_sale_ratio_pct = st.number_input("\uc77c\ubc18\ubd84\uc591 \ube44\uc728(%)", min_value=0.0, max_value=100.0, value=22.0, step=1.0)
                public_land_price_avg = st.number_input("\ub300\uc0c1\uc9c0 \ud3c9\uade0 \uacf5\uc2dc\uc9c0\uac00(\uc6d0/\u33a1)", min_value=0.0, value=32_000_000.0, step=100_000.0)
            with col3:
                construction_cost_per_pyeong_man = st.number_input("\uacf5\uc0ac\ube44(\ub9cc\uc6d0/\ud3c9)", min_value=0.0, value=900.0, step=10.0)
                general_sale_price_eok = st.number_input("\uc77c\ubc18\ubd84\uc591 \ud3c9\uade0\uac00(\uc5b5)", min_value=0.0, value=14.0, step=0.1)
                recent_trade_price_eok = st.number_input("\ub3d9\uc77c\ub2e8\uc9c0 \ucd5c\uadfc \uc2e4\uac70\ub798 \uc911\uc559\uac12(\uc5b5)", min_value=0.0, value=34.0, step=0.1)
                public_price_eok = st.number_input("\uacf5\ub3d9\uc8fc\ud0dd \uacf5\uc2dc\uac00\uaca9(\uc5b5)", min_value=0.0, value=25.0, step=0.1)

        with st.expander("\uae08\uc735 / \ub9ac\uc2a4\ud06c", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                pf_rate_pct = st.number_input("PF \uae08\ub9ac(%)", min_value=0.0, max_value=30.0, value=8.5, step=0.1)
                move_loan_rate_pct = st.number_input("\uc774\uc8fc\ube44 \uae08\ub9ac(%)", min_value=0.0, max_value=20.0, value=5.0, step=0.1)
                sale_rate_pct = st.number_input("\uc77c\ubc18\ubd84\uc591 \ud310\ub9e4\uc728(%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0)
            with col2:
                cash_settlement_rate_pct = st.number_input("\ud604\uae08\uccad\uc0b0\ub960(%)", min_value=0.0, max_value=100.0, value=3.0, step=1.0)
                delay_one_year = st.checkbox("1\ub144 \uc9c0\uc5f0 \ubc18\uc601", value=False)
                apply_seoul_business_boost = st.checkbox("\uc11c\uc6b8 \uc0ac\uc5c5\uc131 \ubcf4\uc815\uacc4\uc218 \uc801\uc6a9", value=False)
            with col3:
                seoul_average_public_land_price = st.number_input("\uc11c\uc6b8 \ud3c9\uade0 \uacf5\uc2dc\uc9c0\uac00", min_value=0.0, value=43_000_000.0, step=100_000.0)
                alpha = st.number_input("\ubcf4\uc815\uacc4\uc218 \uac00\uc0b0\uac12 \uc54c\ud30c", value=0.0, step=0.01, format="%.2f")
                beta = st.number_input("\ubcf4\uc815\uacc4\uc218 \uac00\uc0b0\uac12 \ubca0\ud0c0", value=0.0, step=0.01, format="%.2f")

        with st.expander("\uc218\ub3d9 \ubcf4\uc815", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                appraised_old_asset_eok = st.number_input("\ub0b4 \uac10\uc815\uac00/\uc885\uc804\uc790\uc0b0\uac00\uc561(\uc5b5)", min_value=0.0, value=0.0, step=0.1)
                total_old_asset_value_eok = st.number_input("\ub2e8\uc9c0 \uc885\uc804\uc790\uc0b0\ucd1d\uc561(\uc5b5)", min_value=0.0, value=0.0, step=1.0)
                adjustment_factor_override = st.number_input("\ubcf4\uc815\uacc4\uc218 \uc9c1\uc811 \uc785\ub825", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            with col2:
                total_market_value_eok = st.number_input("\ub2e8\uc9c0 \uc2dc\uac00\ucd1d\uc561 \ubcf4\uc815\uc6a9 \uc2dc\uac00(\uc5b5)", min_value=0.0, value=0.0, step=1.0)
                reconstruction_levy_eok = st.number_input("\uc7ac\uac74\ucd95\ubd80\ub2f4\uae08(\uc5b5)", min_value=0.0, value=0.0, step=0.1)
                liquidation_cost_eok = st.number_input("\uccad\uc0b0/\uc18c\uc1a1 \ube44\uc6a9(\uc5b5)", min_value=0.0, value=0.0, step=0.1)
            with col3:
                ancillary_revenue_eok = st.number_input("\ubd80\ub300\ubcf5\ub9ac/\uc0c1\uac00 \uc218\uc785(\uc5b5)", min_value=0.0, value=0.0, step=0.1)
                other_disposal_revenue_eok = st.number_input("\uae30\ud0c0 \ucc98\ubd84\uc218\uc785(\uc5b5)", min_value=0.0, value=0.0, step=0.1)

        st.markdown("#### \uc870\ud569\uc6d0 \ubd84\uc591\uac00\ud45c")
        member_price_text = st.text_area(
            "\ud55c \uc904\uc5d0 `\ud0c0\uc785,\uc804\uc6a9,\uacf5\uae09,\ubd84\uc591\uac00(\uc5b5)` \ud615\uc2dd\uc73c\ub85c \uc785\ub825",
            value="59\ud615,59,75.6,8.5\n84\ud615,84,107.7,12.0\n101\ud615,101,129.5,15.0",
            height=120,
        )

        st.markdown("#### \uc138\uae08 \uc2e4\ud6a8\uc138\uc728")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            acquisition_rate_pct = st.number_input("\ucde8\ub4dd\uc138 \uc2e4\ud6a8\uc138\uc728(%)", min_value=0.0, max_value=100.0, value=1.5, step=0.1)
        with col2:
            annual_holding_rate_pct = st.number_input("\uc5f0 \ubcf4\uc720\ube44\uc6a9\uc728(%)", min_value=0.0, max_value=100.0, value=0.3, step=0.1)
        with col3:
            capital_gains_effective_rate_pct = st.number_input("\uc591\ub3c4\uc138 \uc2e4\ud6a8\uc138\uc728(%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
        with col4:
            brokerage_rate_pct = st.number_input("\uc911\uac1c/\ucc98\ubd84\ube44\uc728(%)", min_value=0.0, max_value=100.0, value=0.4, step=0.1)

    inputs = {
        "complex_name": complex_name,
        "address": address,
        "current_stage": current_stage,
        "purchase_price": won_from_eok(purchase_price_eok),
        "purchase_date": purchase_date,
        "current_unit_supply_area": current_unit_supply_area,
        "current_unit_exclusive_area": current_unit_exclusive_area,
        "building_no": building_no,
        "floor_no": int(floor_no),
        "expected_new_exclusive_area": expected_new_exclusive_area or None,
        "comparison_new_apt_price": won_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
        "recent_same_complex_trade_price": won_from_eok(recent_trade_price_eok) if recent_trade_price_eok else None,
        "public_price": won_from_eok(public_price_eok) if public_price_eok else None,
        "appraised_old_asset_value": won_from_eok(appraised_old_asset_eok) if appraised_old_asset_eok else None,
        "land_share": land_share or None,
        "current_households": int(current_households),
        "planned_households": int(planned_households),
        "current_far": current_far or None,
        "target_far": target_far or None,
        "construction_cost_per_pyeong": construction_cost_per_pyeong_man * 10_000,
        "pf_rate": pf_rate_pct / 100.0,
        "move_loan_rate": move_loan_rate_pct / 100.0,
        "general_sale_price": won_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
        "general_sale_ratio": general_sale_ratio_pct / 100.0,
        "sale_rate": sale_rate_pct / 100.0,
        "cash_settlement_rate": cash_settlement_rate_pct / 100.0,
        "delay_one_year": delay_one_year,
        "apply_seoul_business_boost": apply_seoul_business_boost,
        "public_land_price_avg": public_land_price_avg or None,
        "seoul_average_public_land_price": seoul_average_public_land_price,
        "alpha": alpha,
        "beta": beta,
        "total_old_asset_value": won_from_eok(total_old_asset_value_eok) if total_old_asset_value_eok else None,
        "document_total_old_asset_value": merged_notice.cost_items.get("total_old_asset_value") if merged_notice else None,
        "total_market_value": won_from_eok(total_market_value_eok) if total_market_value_eok else None,
        "adjustment_factor_override": adjustment_factor_override or None,
        "reconstruction_levy": won_from_eok(reconstruction_levy_eok),
        "liquidation_cost_override": won_from_eok(liquidation_cost_eok) if liquidation_cost_eok else None,
        "ancillary_revenue": won_from_eok(ancillary_revenue_eok),
        "other_disposal_revenue": won_from_eok(other_disposal_revenue_eok),
        "member_price_text": member_price_text,
        "parsed_notice": merged_notice,
        "applied_document_fields": applied_document_fields,
        "use_doc_price_table": use_doc_price_table,
        "aggressive_upsize": aggressive_upsize,
        "acquisition_rate": acquisition_rate_pct / 100.0,
        "annual_holding_rate": annual_holding_rate_pct / 100.0,
        "capital_gains_effective_rate": capital_gains_effective_rate_pct / 100.0,
        "brokerage_rate": brokerage_rate_pct / 100.0,
    }

    results = [analyze_scenario(inputs, scenario_name) for scenario_name in SCENARIOS]
    focus_result = next(item for item in results if item["scenario_name"] == scenario_focus)
    focus_exit = next(item for item in focus_result["exits"] if item["\uc5d1\uc2dc\ud2b8"] == "\uc900\uacf5 \uc9c1\ud6c4 \ub9e4\ub3c4")
    project_ratio = focus_result["project"]["\ucd94\uc815\ube44\ub840\uc728"]
    selected_additional = focus_result["selected"]["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"]

    with tabs[0]:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("\uad8c\ub9ac\uac00\uc561", fmt_eok(focus_result["rights_value"]), f"\ucd94\uc815\ube44\ub840\uc728 {project_ratio:.2f}%")
        col2.metric("\ucd94\ucc9c \ubc30\uc815\ud3c9\ud615", focus_result["selected"]["\ud3c9\ud615"], f"\ucd94\uac00\ubd84\ub2f4\uae08 {fmt_eok(selected_additional)}")
        col3.metric("\uc900\uacf5 \uc9c1\ud6c4 \uc138\ud6c4 \uc21c\uc774\uc775", fmt_eok(focus_exit["\uc138\ud6c4 \uc21c\uc774\uc775"]), f"\ud22c\uc790\uc218\uc775\ub960 {focus_exit['ROI'] * 100:.1f}%")
        col4.metric("\uc2e0\ub8b0\ub3c4", focus_result["confidence_label"], f"{focus_result['confidence_score']:.1f}\uc810")

    with tabs[2]:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("\uc885\uc804\uc790\uc0b0 \ucd94\uc815\uc561", fmt_eok(focus_result["old_asset_estimate"]), humanize_source(focus_result["old_asset_source"]))
        col2.metric("\ub2e8\uc9c0 \uc885\uc804\uc790\uc0b0\ucd1d\uc561", fmt_eok(focus_result["total_old_asset_value"]), humanize_source(focus_result["total_old_asset_source"]))
        col3.metric("\ubcf4\uc815\uacc4\uc218", f"{focus_result['adjustment_factor']:.3f}", f"\uce35 \ubcf4\uc815 {focus_result['floor_factor']:.2f}x")
        col4.metric("\uad8c\ub9ac\uac00\uc561", fmt_eok(focus_result["rights_value"]), "\uc885\uc804\uc790\uc0b0 x \ucd94\uc815\ube44\ub840\uc728")
        allocation_frame = pd.DataFrame(focus_result["allocations"])
        if not allocation_frame.empty:
            allocation_frame["\uc870\ud569\uc6d0\ubd84\uc591\uac00"] = allocation_frame["\uc870\ud569\uc6d0\ubd84\uc591\uac00"].map(fmt_eok)
            allocation_frame["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"] = allocation_frame["\uc608\uc0c1 \ucd94\uac00\ubd84\ub2f4\uae08"].map(fmt_eok)
            allocation_frame["\ucee4\ubc84\uc728"] = allocation_frame["\ucee4\ubc84\uc728"].map(lambda x: round(x, 3))
            allocation_frame["\uc810\uc218"] = allocation_frame["\uc810\uc218"].map(lambda x: round(x, 3))
            st.dataframe(allocation_frame, use_container_width=True, hide_index=True)
        else:
            st.warning("\ud45c\uc2dc\ud560 \ubc30\uc815 \ud6c4\ubcf4\uac00 \uc5c6\uc2b5\ub2c8\ub2e4. \ubd84\uc591\uac00\ud45c\uc640 \uacf5\uaca9\uc801 \uc5c5\uc0ac\uc774\uc988 \uc124\uc815\uc744 \ud655\uc778\ud558\uc138\uc694.")

    with tabs[3]:
        project_frame = pd.DataFrame(
            [
                {"\ud56d\ubaa9": key, "\uae08\uc561": value}
                for key, value in focus_result["project"].items()
            ]
        )
        project_frame["\uae08\uc561"] = project_frame.apply(
            lambda row: f"{row['\uae08\uc561'] * 100:.1f}%" if row["\ud56d\ubaa9"] in {"\uc77c\ubc18\ubd84\uc591 \uc5ec\ub825"} else (fmt_eok(row["\uae08\uc561"]) if isinstance(row["\uae08\uc561"], (int, float)) and row["\ud56d\ubaa9"] not in {"\ucd94\uc815\ube44\ub840\uc728", "\ubcf4\uc815\uacc4\uc218"} else (f"{row['\uae08\uc561']:.2f}%" if row["\ud56d\ubaa9"] == "\ucd94\uc815\ube44\ub840\uc728" else f"{row['\uae08\uc561']:.2f}")),
            axis=1,
        )
        st.dataframe(project_frame, use_container_width=True, hide_index=True)

    with tabs[4]:
        scenario_choice = st.radio("\uc190\uc775 \uc2dc\ub098\ub9ac\uc624", list(SCENARIOS.keys()), horizontal=True, index=list(SCENARIOS.keys()).index(scenario_focus))
        pnl_result = next(item for item in results if item["scenario_name"] == scenario_choice)
        exit_frame = pd.DataFrame(pnl_result["exits"])
        for column in ["\uc790\uc0b0\uac00\uce58", "\uc138\uc804 \uc21c\uc774\uc775", "\uc138\ud6c4 \uc21c\uc774\uc775", "\uc190\uc775\ubd84\uae30 \ub9e4\uc218\uac00", "\uc190\uc775\ubd84\uae30 \ucd94\uac00\ubd84\ub2f4\uae08", "\uc190\uc775\ubd84\uae30 \uc900\uacf5\uc2dc\uc138"]:
            exit_frame[column] = exit_frame[column].map(fmt_eok)
        exit_frame["ROI"] = exit_frame["ROI"].map(lambda x: f"{x * 100:.2f}%")
        exit_frame["IRR"] = exit_frame["IRR"].map(lambda x: "-" if x is None else f"{x * 100:.2f}%")
        exit_frame["\uc608\uc0c1 \uc2dc\uc810(\ub144)"] = exit_frame["\uc608\uc0c1 \uc2dc\uc810(\ub144)"].map(lambda x: round(x, 2))
        exit_frame = exit_frame.rename(columns={"ROI": "\ud22c\uc790\uc218\uc775\ub960", "IRR": "\uc5f0\ud658\uc0b0 IRR"})
        st.dataframe(exit_frame, use_container_width=True, hide_index=True)

    with tabs[5]:
        grid_exit = st.selectbox("\ubbfc\uac10\ub3c4 \uae30\uc900 \uc5d1\uc2dc\ud2b8", list(EXIT_SCENARIOS), index=1)
        grid = sensitivity_grid(inputs, scenario_focus, grid_exit)
        matrix = grid.pivot(index="\ud310\ub9e4\uc728(%)", columns="\uacf5\uc0ac\ube44\ubc30\uc218", values="\uc138\ud6c4 \uc21c\uc774\uc775(\uc5b5)")
        st.markdown("#### \ubbfc\uac10\ub3c4 \ud589\ub82c")
        st.dataframe(matrix, use_container_width=True)
        left, right = st.columns([1.0, 1.2])
        with left:
            st.markdown("#### \ubb38\uc11c \ucd94\ucd9c \uacb0\uacfc")
            if merged_notice:
                st.dataframe(localized_records_frame(merged_notice.extracted_records), use_container_width=True, hide_index=True)
            else:
                st.info("\uc5c5\ub85c\ub4dc\ub41c \ubb38\uc11c\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.")
        with right:
            st.markdown("#### \uacc4\uc0b0 \uadfc\uac70")
            st.dataframe(localized_records_frame(focus_result["source_records"]), use_container_width=True, hide_index=True)
            st.markdown("#### \ucc38\uace0 \ub9c1\ud06c")
            st.markdown(
                "- [\ub3c4\uc2dc \ubc0f \uc8fc\uac70\ud658\uacbd\uc815\ube44\ubc95 \uc81c74\uc870](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1019994219&chrClsCd=010202&ancYnChk=)\n"
                "- [\ubc95\uc81c\ucc98 \ud574\uc11d\ub840 2020-02-26](https://www.law.go.kr/LSW/expcInfoP.do?expcSeq=326815&mode=2)\n"
                "- [\uc11c\uc6b8\uc2dc \uc0ac\uc5c5\ube44 \ubc0f \ubd84\ub2f4\uae08 \ucd94\uc815\ud504\ub85c\uadf8\ub7a8 \ub9e4\ub274\uc5bc](https://cleanup.seoul.go.kr/sures/doc/sures_manual.pdf)\n"
                "- [\uc11c\uc6b8\uc2dc\ubcf4 2023-04-27 \uacf5\uc2dd \uc608\uc2dc](https://event.seoul.go.kr/snews/data/CN_MST/seoulsibo_20230426151204_73863.pdf)\n"
                "- [\uac15\ub0a8\uad6c \uc7ac\uac74\ucd95 \ub2e8\uacc4 \uc124\uba85](https://www.gangnam.go.kr/gangnamlife/2026/html/vol366/sub01_02.html)\n"
                "- [\uc11c\uc6b8 \uc0ac\uc5c5\uc131 \ubcf4\uc815\uacc4\uc218 \uc124\uba85 \uc790\ub8cc](https://ms.smc.seoul.kr/record/appendixDownload.do?key=118e605f12016d435ddd98e70cdefdd7d5ee060b2796116ed8093838d547cf058188275887c9d3b1)"
            )

    st.warning("\ubc30\uc815\ud3c9\ud615, \uc138\uae08, \uc0ac\uc5c5\uc131 \ubcf4\uc815\uacc4\uc218\ub294 \ubc95\uc801 \ud655\uc815\uac12\uc774 \uc544\ub2c8\ub77c \uc758\uc0ac\uacb0\uc815 \ubcf4\uc870\uc6a9 \ucd94\uc815\uce58\uc785\ub2c8\ub2e4.")


if __name__ == "__main__":
    main()
