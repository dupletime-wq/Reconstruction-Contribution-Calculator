from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .engine import analyze_investment, build_context
from .models import MemberPriceRecord, ParsedProjectNotice, ProjectInput, PropertyInput, ScenarioResult, STAGE_OPTIONS, TaxProfile
from .parsers import member_price_table_to_frame, parse_uploaded_notice, parsed_notice_to_rows


def _money_from_eok(value: float) -> float:
    return float(value) * 100_000_000.0


def _money_to_eok(value: float | None) -> float:
    return 0.0 if value is None else float(value) / 100_000_000.0


def _format_eok(value: float) -> str:
    return f"{value / 100_000_000.0:,.2f} eok"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #132238;
            --muted: #5d6b7a;
            --surface: rgba(255, 255, 255, 0.86);
            --border: rgba(60, 79, 101, 0.16);
        }
        .stApp {
            color: var(--ink);
            background:
                radial-gradient(circle at top left, rgba(227, 202, 165, 0.33), transparent 26%),
                radial-gradient(circle at top right, rgba(183, 224, 207, 0.42), transparent 24%),
                linear-gradient(180deg, #fcfaf6 0%, #f3ede2 100%);
        }
        .block-container {
            max-width: 1480px;
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }
        .hero {
            background: linear-gradient(135deg, #132238 0%, #345f6d 52%, #c96b2c 100%);
            color: #fdfaf6;
            padding: 1.8rem 2rem;
            border-radius: 28px;
            margin-bottom: 1rem;
            box-shadow: 0 18px 52px rgba(20, 34, 56, 0.16);
        }
        .hero h1 { margin: 0; font-size: 2.1rem; letter-spacing: -0.03em; }
        .hero p { margin: 0.5rem 0 0; max-width: 60rem; color: rgba(255,255,255,0.92); line-height: 1.6; }
        .metric-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 22px;
            padding: 0.95rem 1.05rem;
            min-height: 8.1rem;
            box-shadow: 0 10px 30px rgba(20, 34, 56, 0.06);
            backdrop-filter: blur(10px);
        }
        .metric-label { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.4rem; }
        .metric-value { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 0.25rem; }
        .metric-note { color: var(--muted); font-size: 0.87rem; line-height: 1.45; }
        .section-note { color: var(--muted); font-size: 0.94rem; line-height: 1.55; margin-bottom: 0.75rem; }
        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.25rem 0.65rem;
            background: rgba(19, 34, 56, 0.06);
            border: 1px solid rgba(19, 34, 56, 0.08);
            margin-right: 0.35rem;
            color: var(--muted);
            font-size: 0.82rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_card(title: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _merge_notices(notices: Iterable[ParsedProjectNotice]) -> ParsedProjectNotice | None:
    notices = list(notices)
    if not notices:
        return None
    merged = ParsedProjectNotice(
        source_url=", ".join(filter(None, [notice.source_url for notice in notices])),
        summary=" / ".join(filter(None, [notice.summary for notice in notices])),
    )
    for notice in notices:
        if merged.proportional_ratio is None and notice.proportional_ratio is not None:
            merged.proportional_ratio = notice.proportional_ratio
        if merged.old_asset_formula is None and notice.old_asset_formula:
            merged.old_asset_formula = notice.old_asset_formula
        if not merged.member_price_table and notice.member_price_table:
            merged.member_price_table = list(notice.member_price_table)
        merged.revenue_items.update(notice.revenue_items)
        merged.cost_items.update(notice.cost_items)
        merged.extracted_records.extend(notice.extracted_records)
    return merged


def _member_price_editor(default_table: list[MemberPriceRecord]) -> list[MemberPriceRecord]:
    if default_table:
        frame = member_price_table_to_frame(default_table)
        frame["member_sale_price_eok"] = frame["member_sale_price"].map(_money_to_eok)
        frame = frame.drop(columns=["member_sale_price"])
    else:
        frame = pd.DataFrame(
            [
                {"label": "59sqm", "exclusive_area_sqm": 59.0, "supply_area_sqm": 75.6, "member_sale_price_eok": 8.5},
                {"label": "84sqm", "exclusive_area_sqm": 84.0, "supply_area_sqm": 107.7, "member_sale_price_eok": 12.0},
                {"label": "101sqm", "exclusive_area_sqm": 101.0, "supply_area_sqm": 129.5, "member_sale_price_eok": 15.0},
            ]
        )
    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="member_price_editor",
    )
    records: list[MemberPriceRecord] = []
    for _, row in edited.iterrows():
        label = str(row.get("label", "")).strip()
        exclusive = pd.to_numeric(row.get("exclusive_area_sqm"), errors="coerce")
        supply = pd.to_numeric(row.get("supply_area_sqm"), errors="coerce")
        price_eok = pd.to_numeric(row.get("member_sale_price_eok"), errors="coerce")
        if not label or pd.isna(exclusive) or pd.isna(supply) or pd.isna(price_eok):
            continue
        records.append(
            MemberPriceRecord(
                label=label,
                exclusive_area_sqm=float(exclusive),
                supply_area_sqm=float(supply),
                member_sale_price=_money_from_eok(float(price_eok)),
            )
        )
    return records


def _scenario_lookup(results: list[ScenarioResult], scenario_name: str) -> ScenarioResult:
    return next(result for result in results if result.scenario_name == scenario_name)


def _project_breakdown_chart(results: list[ScenarioResult]) -> go.Figure:
    fig = go.Figure()
    colors = {"Total revenue": "#0d7a5f", "Total cost": "#b14e2f", "Legacy asset total": "#486482"}
    for label, extractor in [
        ("Total revenue", lambda r: r.project.total_revenue),
        ("Total cost", lambda r: r.project.total_cost),
        ("Legacy asset total", lambda r: r.project.total_old_asset_value),
    ]:
        fig.add_bar(
            name=label,
            x=[item.scenario_name for item in results],
            y=[extractor(item) / 100_000_000 for item in results],
            marker_color=colors[label],
        )
    fig.update_layout(
        barmode="group",
        height=400,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_title="eok",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.55)",
    )
    return fig


def _exit_chart(result: ScenarioResult) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name="After-tax profit",
        x=[item.exit_name for item in result.exit_outcomes],
        y=[item.after_tax_profit / 100_000_000 for item in result.exit_outcomes],
        marker_color=["#cc6b2c", "#2c7a7b", "#355c7d"],
    )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_title="eok",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.55)",
    )
    return fig


def _sensitivity_grid(context, selected_scenario: str, selected_exit: str) -> pd.DataFrame:
    sale_rates = [0.92, 0.95, 0.97, 1.00]
    cost_multipliers = [0.95, 1.00, 1.05, 1.10]
    rows: list[dict[str, float]] = []
    for sale_rate in sale_rates:
        for cost_multiplier in cost_multipliers:
            modified_project = replace(
                context.project_input,
                sale_rate=sale_rate,
                construction_cost_per_pyeong=context.project_input.construction_cost_per_pyeong * cost_multiplier,
            )
            modified_context = build_context(
                property_input=context.property_input,
                project_input=modified_project,
                tax_profile=context.tax_profile,
                parsed_notice=context.parsed_notice,
                applied_document_fields=context.applied_document_fields,
                applied_document_price_table=context.applied_document_price_table,
                aggressive_upsize=context.aggressive_upsize,
            )
            scenario_result = _scenario_lookup(analyze_investment(modified_context), selected_scenario)
            exit_outcome = next(item for item in scenario_result.exit_outcomes if item.exit_name == selected_exit)
            rows.append(
                {
                    "sale_rate_pct": round(sale_rate * 100, 1),
                    "cost_multiplier": cost_multiplier,
                    "after_tax_profit_eok": exit_outcome.after_tax_profit / 100_000_000,
                }
            )
    return pd.DataFrame(rows)


def _sensitivity_heatmap(grid_frame: pd.DataFrame) -> go.Figure:
    pivot = grid_frame.pivot(index="sale_rate_pct", columns="cost_multiplier", values="after_tax_profit_eok")
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{value:.2f}x" for value in pivot.columns],
            y=[f"{value:.1f}%" for value in pivot.index],
            colorscale="BrBG",
            colorbar_title="eok",
            text=[[f"{cell:.2f}" for cell in row] for row in pivot.values],
            texttemplate="%{text}",
        )
    )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title="Construction cost multiplier",
        yaxis_title="General sale rate",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.55)",
    )
    return fig


def render_app() -> None:
    st.set_page_config(page_title="Rebuild Profit Estimator", page_icon="R", layout="wide", initial_sidebar_state="expanded")
    _apply_style()

    for key, default in [
        ("quick_estimate", {}),
        ("detailed_inputs", {}),
        ("source_records", []),
        ("scenario_results", []),
        ("sensitivity_grid", []),
    ]:
        st.session_state.setdefault(key, default)

    st.markdown(
        """
        <div class="hero">
            <h1>Apartment Rebuild Profit Estimator</h1>
            <p>
                This Streamlit app estimates legacy asset value, rights value, member allocation fit,
                project feasibility, and personal after-tax outcomes under Optimistic, Base, and Conservative scenarios.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.title("Controls")
    st.sidebar.caption("Document values are never auto-applied. Review them first, then opt in.")
    aggressive_upsize = st.sidebar.checkbox("Allow aggressive upsizing", value=False)
    scenario_focus = st.sidebar.selectbox("Default scenario", ["Base", "Optimistic", "Conservative"], index=0)
    uploaded_files = st.sidebar.file_uploader("Upload estimate notice / CSV", type=["pdf", "csv"], accept_multiple_files=True)

    parsed_notices: list[ParsedProjectNotice] = []
    if uploaded_files:
        for file in uploaded_files:
            parsed_notices.append(parse_uploaded_notice(file.name, file.getvalue()))
    merged_notice = _merge_notices(parsed_notices)
    extracted_field_options: list[str] = []
    if merged_notice:
        extracted_field_options = sorted({row["field"] for row in parsed_notice_to_rows(merged_notice) if row["field"] not in {"member_price_table_count", "parser_status"}})
        st.sidebar.caption(f"Parsed files: {merged_notice.source_url}")
    applied_document_fields = set(st.sidebar.multiselect("Apply extracted fields", options=extracted_field_options, default=[]))
    apply_document_price_table = st.sidebar.checkbox("Apply document price table", value=False, disabled=not (merged_notice and merged_notice.member_price_table))

    tabs = st.tabs(["Quick Input", "Project Inputs", "Legacy Asset / Allocation", "Project Economics", "Personal PnL", "Sensitivity / Sources"])

    with tabs[0]:
        st.markdown('<div class="section-note">Only the minimum deal inputs are required. Missing values fall back to heuristics and lower the confidence score.</div>', unsafe_allow_html=True)
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            complex_name = st.text_input("Complex name", value="Apgujeong Sample Complex")
            address = st.text_input("Address", value="Seoul Gangnam-gu Apgujeong-dong")
            current_stage = st.selectbox("Current stage", options=list(STAGE_OPTIONS), index=3)
        with col_b:
            current_unit_supply_area = st.number_input("Current supply area (sqm)", min_value=20.0, value=107.7, step=1.0)
            current_unit_exclusive_area = st.number_input("Current exclusive area (sqm)", min_value=20.0, value=84.0, step=1.0)
            floor_no = st.number_input("Floor", min_value=1, value=10, step=1)
        with col_c:
            purchase_price_eok = st.number_input("Purchase price (eok)", min_value=0.0, value=35.0, step=0.1)
            purchase_date = st.date_input("Purchase date", value=date.today())
            comparison_new_price_eok = st.number_input("Comparable new-build price (eok)", min_value=0.0, value=48.0, step=0.1)
            expected_new_exclusive_area = st.number_input("Expected new exclusive area (sqm)", min_value=0.0, value=84.0, step=1.0)

    with tabs[1]:
        st.markdown('<div class="section-note">Lock project scale, revenue assumptions, financing, risk, and manual overrides here.</div>', unsafe_allow_html=True)
        with st.expander("Project scope", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                building_no = st.text_input("Building", value="101")
                land_share = st.number_input("Land share (sqm)", min_value=0.0, value=25.0, step=0.1)
                current_households = st.number_input("Current households", min_value=1, value=480, step=1)
                planned_households = st.number_input("Planned households", min_value=1, value=620, step=1)
            with col2:
                current_far = st.number_input("Current FAR (%)", min_value=0.0, value=180.0, step=1.0)
                target_far = st.number_input("Target FAR (%)", min_value=0.0, value=260.0, step=1.0)
                general_sale_ratio_pct = st.number_input("General sale ratio (%)", min_value=0.0, max_value=100.0, value=22.0, step=1.0)
                public_land_price_avg = st.number_input("Public land price avg (KRW/sqm)", min_value=0.0, value=32_000_000.0, step=100_000.0)
            with col3:
                construction_cost_per_pyeong_man = st.number_input("Construction cost (manwon/pyeong)", min_value=0.0, value=900.0, step=10.0)
                general_sale_price_eok = st.number_input("General sale avg price (eok)", min_value=0.0, value=14.0, step=0.1)
                recent_trade_price_eok = st.number_input("Recent same-complex trade (eok)", min_value=0.0, value=34.0, step=0.1)
                public_price_eok = st.number_input("Public price (eok)", min_value=0.0, value=25.0, step=0.1)

        with st.expander("Financing and risk", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                pf_rate_pct = st.number_input("PF rate (%)", min_value=0.0, max_value=30.0, value=8.5, step=0.1)
                move_loan_rate_pct = st.number_input("Move-loan rate (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.1)
                sale_rate_pct = st.number_input("General sale rate (%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0)
            with col2:
                cash_settlement_rate_pct = st.number_input("Cash-settlement rate (%)", min_value=0.0, max_value=100.0, value=3.0, step=1.0)
                delay_one_year = st.checkbox("Add 1-year delay", value=False)
                apply_seoul_business_boost = st.checkbox("Apply Seoul business boost", value=False)
            with col3:
                seoul_avg_public_land_price = st.number_input("Seoul avg public land price", min_value=0.0, value=43_000_000.0, step=100_000.0)
                alpha = st.number_input("Boost alpha", value=0.0, step=0.01, format="%.2f")
                beta = st.number_input("Boost beta", value=0.0, step=0.01, format="%.2f")

        with st.expander("Manual overrides", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                appraised_old_asset_eok = st.number_input("My appraised old asset (eok)", min_value=0.0, value=0.0, step=0.1)
                total_old_asset_value_eok = st.number_input("Complex total old asset (eok)", min_value=0.0, value=0.0, step=1.0)
                total_market_value_eok = st.number_input("Complex market cap override (eok)", min_value=0.0, value=0.0, step=1.0)
            with col2:
                adjustment_factor_override = st.number_input("Adjustment factor override", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                reconstruction_levy_eok = st.number_input("Reconstruction levy (eok)", min_value=0.0, value=0.0, step=0.1)
                liquidation_cost_eok = st.number_input("Settlement / litigation cost (eok)", min_value=0.0, value=0.0, step=0.1)
            with col3:
                ancillary_revenue_eok = st.number_input("Ancillary revenue (eok)", min_value=0.0, value=0.0, step=0.1)
                other_disposal_revenue_eok = st.number_input("Other disposal revenue (eok)", min_value=0.0, value=0.0, step=0.1)

        with st.expander("Member sale price table", expanded=True):
            base_table = merged_notice.member_price_table if merged_notice and apply_document_price_table else []
            member_price_table = _member_price_editor(base_table)

        with st.expander("Tax profile", expanded=True):
            tax_preset = st.selectbox("Tax preset", ["Base", "Low", "High"], index=0)
            preset_map = {
                "Low": (1.2, 0.2, 10.0, 0.4),
                "Base": (1.5, 0.3, 20.0, 0.4),
                "High": (3.5, 0.5, 35.0, 0.4),
            }
            default_tax = preset_map[tax_preset]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                acquisition_rate_pct = st.number_input("Acquisition rate (%)", min_value=0.0, max_value=100.0, value=float(default_tax[0]), step=0.1)
            with col2:
                annual_holding_rate_pct = st.number_input("Annual holding rate (%)", min_value=0.0, max_value=100.0, value=float(default_tax[1]), step=0.1)
            with col3:
                capital_gains_rate_pct = st.number_input("Capital gains effective rate (%)", min_value=0.0, max_value=100.0, value=float(default_tax[2]), step=0.5)
            with col4:
                brokerage_rate_pct = st.number_input("Brokerage/disposal rate (%)", min_value=0.0, max_value=100.0, value=float(default_tax[3]), step=0.1)

    property_input = PropertyInput(
        complex_name=complex_name,
        address=address,
        current_stage=current_stage,
        purchase_price=_money_from_eok(purchase_price_eok),
        purchase_date=purchase_date,
        current_unit_supply_area=current_unit_supply_area,
        current_unit_exclusive_area=current_unit_exclusive_area,
        building_no=building_no,
        floor_no=int(floor_no),
        expected_new_exclusive_area=expected_new_exclusive_area or None,
        comparison_new_apt_price=_money_from_eok(comparison_new_price_eok) if comparison_new_price_eok else None,
        recent_same_complex_trade_price=_money_from_eok(recent_trade_price_eok) if recent_trade_price_eok else None,
        public_price=_money_from_eok(public_price_eok) if public_price_eok else None,
        appraised_old_asset_value=_money_from_eok(appraised_old_asset_eok) if appraised_old_asset_eok else None,
    )
    project_input = ProjectInput(
        land_share=land_share or None,
        current_households=int(current_households),
        planned_households=int(planned_households),
        current_far=current_far or None,
        target_far=target_far or None,
        construction_cost_per_pyeong=construction_cost_per_pyeong_man * 10_000,
        pf_rate=pf_rate_pct / 100.0,
        move_loan_rate=move_loan_rate_pct / 100.0,
        general_sale_price=_money_from_eok(general_sale_price_eok) if general_sale_price_eok else None,
        general_sale_ratio=general_sale_ratio_pct / 100.0,
        member_sale_price_table=member_price_table,
        sale_rate=sale_rate_pct / 100.0,
        cash_settlement_rate=cash_settlement_rate_pct / 100.0,
        delay_one_year=delay_one_year,
        apply_seoul_business_boost=apply_seoul_business_boost,
        public_land_price_avg=public_land_price_avg or None,
        seoul_average_public_land_price=seoul_avg_public_land_price,
        alpha=alpha,
        beta=beta,
        reconstruction_levy=_money_from_eok(reconstruction_levy_eok),
        ancillary_revenue=_money_from_eok(ancillary_revenue_eok),
        other_disposal_revenue=_money_from_eok(other_disposal_revenue_eok),
        existing_total_old_asset_value=_money_from_eok(total_old_asset_value_eok) if total_old_asset_value_eok else None,
        existing_total_market_value=_money_from_eok(total_market_value_eok) if total_market_value_eok else None,
        adjustment_factor_override=adjustment_factor_override or None,
        liquidation_cost_override=_money_from_eok(liquidation_cost_eok) if liquidation_cost_eok else None,
        parsed_notice=merged_notice,
    )
    tax_profile = TaxProfile(
        label=tax_preset,
        acquisition_rate=acquisition_rate_pct / 100.0,
        annual_holding_rate=annual_holding_rate_pct / 100.0,
        capital_gains_effective_rate=capital_gains_rate_pct / 100.0,
        brokerage_rate=brokerage_rate_pct / 100.0,
    )
    context = build_context(
        property_input=property_input,
        project_input=project_input,
        tax_profile=tax_profile,
        parsed_notice=merged_notice,
        applied_document_fields=applied_document_fields,
        applied_document_price_table=apply_document_price_table,
        aggressive_upsize=aggressive_upsize,
    )
    results = analyze_investment(context)
    focus_result = _scenario_lookup(results, scenario_focus)
    focus_exit = next(item for item in focus_result.exit_outcomes if item.exit_name == "Sell at Completion")

    st.session_state["quick_estimate"] = {
        "complex_name": complex_name,
        "address": address,
        "current_stage": current_stage,
        "purchase_price": property_input.purchase_price,
    }
    st.session_state["detailed_inputs"] = {
        "current_households": current_households,
        "planned_households": planned_households,
        "pf_rate": project_input.pf_rate,
        "sale_rate": project_input.sale_rate,
    }
    st.session_state["source_records"] = [
        {
            "field": record.key,
            "value": record.value,
            "source": record.source,
            "retrieved_at": record.retrieved_at,
            "confidence": round(record.confidence * 100, 1),
            "notes": record.notes,
        }
        for record in focus_result.source_records
    ]
    st.session_state["scenario_results"] = results

    with tabs[0]:
        cards = st.columns(4)
        with cards[0]:
            _render_metric_card("Rights value", _format_eok(focus_result.valuation.rights_value), f"Proportional ratio {_format_percent(focus_result.project.proportional_ratio)}")
        with cards[1]:
            _render_metric_card("Recommended size", focus_result.selected_candidate.label, f"Addl contribution {_format_eok(focus_result.selected_candidate.additional_contribution)}")
        with cards[2]:
            _render_metric_card("After-tax profit at completion", _format_eok(focus_exit.after_tax_profit), f"ROI {focus_exit.roi * 100:.1f}%")
        with cards[3]:
            _render_metric_card("Confidence", focus_result.confidence_label, f"{focus_result.confidence_score:.1f} pts")
        st.markdown(
            f"""
            <div class="section-note">
                <span class="pill">{property_input.complex_name}</span>
                <span class="pill">{property_input.address}</span>
                <span class="pill">{property_input.current_stage}</span>
                <span class="pill">{scenario_focus}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with tabs[2]:
        metric_cols = st.columns(4)
        with metric_cols[0]:
            _render_metric_card("Legacy asset estimate", _format_eok(focus_result.valuation.old_asset_estimate), focus_result.valuation.old_asset_source)
        with metric_cols[1]:
            _render_metric_card("Complex legacy asset total", _format_eok(focus_result.valuation.total_old_asset_value), focus_result.valuation.total_old_asset_source)
        with metric_cols[2]:
            _render_metric_card("Adjustment factor", f"{focus_result.valuation.adjustment_factor:.3f}", f"Floor factor {focus_result.valuation.floor_adjustment_factor:.2f}x")
        with metric_cols[3]:
            _render_metric_card("Rights value", _format_eok(focus_result.valuation.rights_value), "Legacy asset x proportional ratio")
        candidate_frame = pd.DataFrame(
            [
                {
                    "Type": item.label,
                    "Exclusive sqm": item.exclusive_area_sqm,
                    "Supply sqm": item.supply_area_sqm,
                    "Member sale price (eok)": round(_money_to_eok(item.member_sale_price), 2),
                    "Addl contribution (eok)": round(_money_to_eok(item.additional_contribution), 2),
                    "Cover ratio": round(item.cover_ratio, 3),
                    "Score": round(item.score, 3),
                    "Signal": item.feasibility_label,
                }
                for item in focus_result.allocation_candidates
            ]
        )
        st.markdown("#### Allocation candidates")
        st.dataframe(candidate_frame, use_container_width=True, hide_index=True)
        if focus_result.valuation.notes:
            st.warning(" | ".join(focus_result.valuation.notes))
        st.caption("Allocation ranking is a heuristic for investment analysis, not a legal allocation confirmation.")

    with tabs[3]:
        metric_cols = st.columns(4)
        with metric_cols[0]:
            _render_metric_card("Total revenue", _format_eok(focus_result.project.total_revenue), "Member sale + general sale + ancillary")
        with metric_cols[1]:
            _render_metric_card("Total cost", _format_eok(focus_result.project.total_cost), "Construction + financing + levy + reserve")
        with metric_cols[2]:
            _render_metric_card("Avg contribution / member", _format_eok(focus_result.project.average_contribution_per_member), f"Remaining months {focus_result.project.remaining_months:.0f}")
        with metric_cols[3]:
            _render_metric_card("General sale capacity", f"{focus_result.project.general_sale_capacity * 100:.1f}%", f"Boost factor {focus_result.project.business_correction_after:.2f}")
        st.plotly_chart(_project_breakdown_chart(results), use_container_width=True)
        breakdown_frame = pd.DataFrame(
            [
                {"Item": "Direct construction", "Value (eok)": round(focus_result.project.direct_construction_cost / 100_000_000, 2)},
                {"Item": "Demolition / site prep", "Value (eok)": round(focus_result.project.demolition_cost / 100_000_000, 2)},
                {"Item": "Design / PM", "Value (eok)": round(focus_result.project.design_and_pm_cost / 100_000_000, 2)},
                {"Item": "Reserve", "Value (eok)": round(focus_result.project.reserve_cost / 100_000_000, 2)},
                {"Item": "PF financing", "Value (eok)": round(focus_result.project.financing_cost / 100_000_000, 2)},
                {"Item": "Move-loan interest", "Value (eok)": round(focus_result.project.move_loan_interest_cost / 100_000_000, 2)},
                {"Item": "Sales expense", "Value (eok)": round(focus_result.project.sales_expense / 100_000_000, 2)},
                {"Item": "Taxes / charges", "Value (eok)": round(focus_result.project.tax_and_charge_cost / 100_000_000, 2)},
                {"Item": "Settlement / litigation", "Value (eok)": round(focus_result.project.settlement_and_litigation_cost / 100_000_000, 2)},
            ]
        )
        st.dataframe(breakdown_frame, use_container_width=True, hide_index=True)

    with tabs[4]:
        scenario_choice = st.radio("PnL scenario", ["Base", "Optimistic", "Conservative"], horizontal=True, index=["Base", "Optimistic", "Conservative"].index(scenario_focus))
        profit_result = _scenario_lookup(results, scenario_choice)
        st.plotly_chart(_exit_chart(profit_result), use_container_width=True)
        exit_table = pd.DataFrame(
            [
                {
                    "Exit": item.exit_name,
                    "Years": round(item.years_to_exit, 2),
                    "Asset value (eok)": round(item.gross_exit_value / 100_000_000, 2),
                    "Pretax profit (eok)": round(item.pretax_profit / 100_000_000, 2),
                    "After-tax profit (eok)": round(item.after_tax_profit / 100_000_000, 2),
                    "ROI (%)": round(item.roi * 100, 2),
                    "IRR (%)": round((item.annualized_irr or 0.0) * 100, 2) if item.annualized_irr is not None else None,
                    "Breakeven purchase (eok)": round(item.break_even_purchase_price / 100_000_000, 2),
                    "Breakeven addl contrib (eok)": round(item.break_even_additional_contribution / 100_000_000, 2),
                    "Breakeven exit value (eok)": round(item.break_even_exit_value / 100_000_000, 2),
                }
                for item in profit_result.exit_outcomes
            ]
        )
        st.dataframe(exit_table, use_container_width=True, hide_index=True)
        st.caption("Taxes use an effective-rate profile, not a full legal tax engine.")

    with tabs[5]:
        exit_option = st.selectbox("Sensitivity exit", ["Sell at Completion", "Rights Sale", "Hold 3Y After Completion"], index=0)
        grid = _sensitivity_grid(context, scenario_focus, exit_option)
        st.session_state["sensitivity_grid"] = grid.to_dict("records")
        st.plotly_chart(_sensitivity_heatmap(grid), use_container_width=True)
        left, right = st.columns([1.0, 1.2])
        with left:
            st.markdown("#### Parsed document rows")
            if merged_notice:
                st.dataframe(pd.DataFrame(parsed_notice_to_rows(merged_notice)), use_container_width=True, hide_index=True)
            else:
                st.info("No uploaded notice.")
        with right:
            st.markdown("#### Source records")
            st.dataframe(pd.DataFrame(st.session_state["source_records"]), use_container_width=True, hide_index=True)
            st.markdown("#### References")
            st.markdown(
                "- [Urban and Residential Environment Improvement Act, Article 74](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1019994219&chrClsCd=010202&ancYnChk=)\n"
                "- [Ministry interpretation note, 2020-02-26](https://www.law.go.kr/LSW/expcInfoP.do?expcSeq=326815&mode=2)\n"
                "- [Seoul cost/share estimate manual](https://cleanup.seoul.go.kr/sures/doc/sures_manual.pdf)\n"
                "- [Seoul gazette example, 2023-04-27](https://event.seoul.go.kr/snews/data/CN_MST/seoulsibo_20230426151204_73863.pdf)\n"
                "- [Gangnam district rebuild stages](https://www.gangnam.go.kr/gangnamlife/2026/html/vol366/sub01_02.html)\n"
                "- [Seoul business boost coefficient](https://ms.smc.seoul.kr/record/appendixDownload.do?key=118e605f12016d435ddd98e70cdefdd7d5ee060b2796116ed8093838d547cf058188275887c9d3b1)"
            )

    st.caption("This estimator targets apartment rebuild deals only. Allocation logic, cost heuristics, and tax presets are decision-support rules, not legal determinations.")
