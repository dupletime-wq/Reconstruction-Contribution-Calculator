from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import pandas as pd

from .models import MemberPriceRecord, ParsedProjectNotice, SourceRecord, now_timestamp

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


MONEY_TOKEN_PATTERN = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(jo|eok|cheonman|baekman|manwon|\uc870|\uc5b5|\ucc9c\ub9cc|\ub9cc\uc6d0|\uc6d0)?", re.IGNORECASE)
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


def _source_record(key: str, value: str, source: str, confidence: float, notes: str = "") -> SourceRecord:
    return SourceRecord(
        key=key,
        value=value,
        source=source,
        retrieved_at=now_timestamp(),
        confidence=confidence,
        notes=notes,
    )


def parse_korean_money(text: str) -> float | None:
    if not text:
        return None
    compact = text.replace(" ", "")
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


def _normalize_key(raw: str) -> str:
    compact = re.sub(r"\s+", "", str(raw))
    return KEY_ALIASES.get(compact, compact)


def _parse_member_price_table_from_frame(frame: pd.DataFrame) -> list[MemberPriceRecord]:
    label_col = next((col for col in frame.columns if str(col).lower() in {"label", "type"} or "\ud615" in str(col)), None)
    exclusive_col = next((col for col in frame.columns if "exclusive" in str(col).lower() or "\uc804\uc6a9" in str(col)), None)
    supply_col = next((col for col in frame.columns if "supply" in str(col).lower() or "\uacf5\uae09" in str(col)), None)
    price_col = next((col for col in frame.columns if "price" in str(col).lower() or "\ubd84\uc591\uac00" in str(col)), None)
    if not all([label_col, exclusive_col, supply_col, price_col]):
        return []

    records: list[MemberPriceRecord] = []
    for _, row in frame.iterrows():
        label = str(row[label_col]).strip()
        exclusive = pd.to_numeric(row[exclusive_col], errors="coerce")
        supply = pd.to_numeric(row[supply_col], errors="coerce")
        price = parse_korean_money(str(row[price_col]))
        if not label or pd.isna(exclusive) or pd.isna(supply) or price is None:
            continue
        records.append(
            MemberPriceRecord(
                label=label,
                exclusive_area_sqm=float(exclusive),
                supply_area_sqm=float(supply),
                member_sale_price=float(price),
            )
        )
    return records


def parse_csv_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    frame = pd.read_csv(BytesIO(file_bytes))
    notice = ParsedProjectNotice(source_url=file_name, summary="csv_parsed")
    lower_cols = {str(col).lower() for col in frame.columns}
    if {"key", "value"}.issubset(lower_cols):
        key_col = next(col for col in frame.columns if str(col).lower() == "key")
        value_col = next(col for col in frame.columns if str(col).lower() == "value")
        for _, row in frame.iterrows():
            key = _normalize_key(row[key_col])
            raw_value = str(row[value_col]).strip()
            if not raw_value:
                continue
            if key == "proportional_ratio":
                pct_match = PERCENT_PATTERN.search(raw_value)
                notice.proportional_ratio = float(pct_match.group(1)) if pct_match else float(raw_value)
                notice.extracted_records.append(_source_record("proportional_ratio", f"{notice.proportional_ratio:.2f}", f"csv:{file_name}", 0.86))
            elif key in {"member_sale_revenue", "general_sale_revenue", "total_revenue"}:
                amount = parse_korean_money(raw_value)
                if amount is not None:
                    notice.revenue_items[key] = amount
                    notice.extracted_records.append(_source_record(key, f"{amount:,.0f}", f"csv:{file_name}", 0.78))
            elif key in {"total_cost", "reconstruction_levy", "total_old_asset_value"}:
                amount = parse_korean_money(raw_value)
                if amount is not None:
                    notice.cost_items[key] = amount
                    notice.extracted_records.append(_source_record(key, f"{amount:,.0f}", f"csv:{file_name}", 0.78))
            elif key == "old_asset_formula":
                notice.old_asset_formula = raw_value
                notice.extracted_records.append(_source_record("old_asset_formula", raw_value, f"csv:{file_name}", 0.72))
        return notice

    price_table = _parse_member_price_table_from_frame(frame)
    if price_table:
        notice.member_price_table = price_table
        notice.summary = "csv_price_table"
        notice.extracted_records.append(_source_record("member_price_table_count", str(len(price_table)), f"csv:{file_name}", 0.90))
    return notice


def _extract_amounts_from_text(text: str) -> tuple[dict[str, float], dict[str, float], list[SourceRecord], float | None, str | None]:
    revenue_items: dict[str, float] = {}
    cost_items: dict[str, float] = {}
    records: list[SourceRecord] = []
    proportional_ratio: float | None = None
    old_asset_formula: str | None = None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    formula_markers = ["\uacf5\ub3d9\uc8fc\ud0dd", "\uacf5\uc2dc\uac00\uaca9", "x", "\u00d7"]

    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if "\ube44\ub840\uc728" in compact and proportional_ratio is None:
            pct_match = PERCENT_PATTERN.search(line)
            if pct_match:
                proportional_ratio = float(pct_match.group(1))
                records.append(_source_record("proportional_ratio", f"{proportional_ratio:.2f}", "pdf_extract", 0.74))
        if old_asset_formula is None and all(marker in compact.lower() if marker == "x" else marker in compact for marker in formula_markers):
            old_asset_formula = line[:200]
            records.append(_source_record("old_asset_formula", old_asset_formula, "pdf_extract", 0.68))
        for label, key in KEY_ALIASES.items():
            if label in compact:
                amount = parse_korean_money(line)
                if amount is None:
                    continue
                if key in {"member_sale_revenue", "general_sale_revenue", "total_revenue"}:
                    revenue_items[key] = amount
                else:
                    cost_items[key] = amount
                records.append(_source_record(key, f"{amount:,.0f}", "pdf_extract", 0.70))
    return revenue_items, cost_items, records, proportional_ratio, old_asset_formula


def _parse_member_price_table_from_text(text: str) -> list[MemberPriceRecord]:
    pattern = re.compile(
        r"(?P<label>\d+\s*[A-Za-z\uac00-\ud7a3]+)\s+"
        r"(?P<exclusive>\d+(?:\.\d+)?)\s+"
        r"(?P<supply>\d+(?:\.\d+)?)\s+"
        r"(?P<price>\d[\d,]*(?:\.\d+)?\s*(?:\uc5b5|\ub9cc\uc6d0|\uc6d0)?)"
    )
    records: list[MemberPriceRecord] = []
    for match in pattern.finditer(text):
        price = parse_korean_money(match.group("price"))
        if price is None:
            continue
        records.append(
            MemberPriceRecord(
                label=match.group("label").strip(),
                exclusive_area_sqm=float(match.group("exclusive")),
                supply_area_sqm=float(match.group("supply")),
                member_sale_price=float(price),
            )
        )
    deduped: list[MemberPriceRecord] = []
    seen: set[tuple[str, float, float]] = set()
    for item in records:
        key = (item.label, item.exclusive_area_sqm, item.supply_area_sqm)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:12]


def parse_pdf_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    if PdfReader is None:
        return ParsedProjectNotice(
            source_url=file_name,
            summary="pypdf_missing",
            extracted_records=[_source_record("parser_status", "pypdf_missing", f"pdf:{file_name}", 0.15, "install pypdf")],
        )
    reader = PdfReader(BytesIO(file_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    revenue_items, cost_items, extracted_records, proportional_ratio, old_asset_formula = _extract_amounts_from_text(text)
    member_table = _parse_member_price_table_from_text(text)
    if member_table:
        extracted_records.append(_source_record("member_price_table_count", str(len(member_table)), f"pdf:{file_name}", 0.64))
    return ParsedProjectNotice(
        proportional_ratio=proportional_ratio,
        old_asset_formula=old_asset_formula,
        member_price_table=member_table,
        revenue_items=revenue_items,
        cost_items=cost_items,
        source_url=file_name,
        extracted_records=extracted_records,
        summary="pdf_parsed",
    )


def parse_uploaded_notice(file_name: str, file_bytes: bytes) -> ParsedProjectNotice:
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        return parse_csv_notice(file_name, file_bytes)
    if lower_name.endswith(".pdf"):
        return parse_pdf_notice(file_name, file_bytes)
    return ParsedProjectNotice(
        source_url=file_name,
        summary="unsupported_format",
        extracted_records=[_source_record("parser_status", "unsupported", file_name, 0.10, "only csv/pdf supported")],
    )


def parsed_notice_to_rows(parsed_notice: ParsedProjectNotice) -> list[dict[str, Any]]:
    return [
        {
            "field": record.key,
            "value": record.value,
            "source": record.source,
            "confidence": round(record.confidence * 100, 1),
            "notes": record.notes,
        }
        for record in parsed_notice.extracted_records
    ]


def member_price_table_to_frame(price_table: list[MemberPriceRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "label": item.label,
                "exclusive_area_sqm": item.exclusive_area_sqm,
                "supply_area_sqm": item.supply_area_sqm,
                "member_sale_price": item.member_sale_price,
            }
            for item in price_table
        ]
    )
