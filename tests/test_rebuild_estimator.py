from __future__ import annotations

import unittest
from datetime import date

from rebuild_estimator.engine import analyze_investment, build_context
from rebuild_estimator.models import ProjectInput, PropertyInput, TaxProfile


class RebuildEstimatorTests(unittest.TestCase):
    def _context(self):
        property_input = PropertyInput(
            complex_name="Sample Complex",
            address="Seoul Gangnam-gu",
            current_stage="Association Approval",
            purchase_price=3_500_000_000,
            purchase_date=date(2026, 3, 26),
            current_unit_supply_area=107.7,
            current_unit_exclusive_area=84.0,
            floor_no=10,
            comparison_new_apt_price=4_800_000_000,
            recent_same_complex_trade_price=3_400_000_000,
            public_price=2_500_000_000,
        )
        project_input = ProjectInput(
            land_share=25.0,
            current_households=480,
            planned_households=620,
            current_far=180.0,
            target_far=260.0,
            construction_cost_per_pyeong=9_000_000.0,
            pf_rate=0.085,
            move_loan_rate=0.05,
            general_sale_price=1_400_000_000,
            sale_rate=0.97,
            cash_settlement_rate=0.03,
        )
        tax_profile = TaxProfile(label="Base")
        return build_context(property_input, project_input, tax_profile)

    def test_analyze_returns_three_scenarios(self):
        results = analyze_investment(self._context())
        self.assertEqual([item.scenario_name for item in results], ["Optimistic", "Base", "Conservative"])

    def test_floor_adjustment_changes_old_asset_estimate(self):
        low = self._context()
        high = self._context()
        low.property_input.floor_no = 2
        high.property_input.floor_no = 15
        low_base = next(item for item in analyze_investment(low) if item.scenario_name == "Base")
        high_base = next(item for item in analyze_investment(high) if item.scenario_name == "Base")
        diff_ratio = high_base.valuation.old_asset_estimate / low_base.valuation.old_asset_estimate - 1
        self.assertAlmostEqual(diff_ratio, 0.0408163265, places=3)

    def test_lower_sale_rate_reduces_profit(self):
        context = self._context()
        base_profit = next(item for item in analyze_investment(context) if item.scenario_name == "Base").exit_outcomes[1].after_tax_profit
        context.project_input.sale_rate = 0.92
        lower_profit = next(item for item in analyze_investment(context) if item.scenario_name == "Base").exit_outcomes[1].after_tax_profit
        self.assertLess(lower_profit, base_profit)


if __name__ == "__main__":
    unittest.main()
