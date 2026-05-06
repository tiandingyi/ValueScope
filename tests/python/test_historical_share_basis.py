import copy
import unittest
from unittest.mock import patch

import pandas as pd

from valuescope.legacy_stock_scripts.core.data_a import _filter_data_as_of_year
from valuescope.legacy_stock_scripts.core.valuation import build_oe_yield_history, build_valuation_assessments, build_valuation_history


class HistoricalShareBasisRegressionTests(unittest.TestCase):
    def _make_history_data(self):
        abstract = pd.DataFrame(
            [
                {"指标": "归母净利润", "20161231": 120000000.0, "20171231": 140000000.0},
                {"指标": "基本每股收益", "20161231": 12.0, "20171231": 14.0},
            ]
        )
        year_data = {
            "20161231": {
                "profit": 120000000.0,
                "shares": 10.0,
                "asof_shares": 10.0,
                "valuation_shares": 40.0,
                "dividends_paid": 0.0,
            },
            "20171231": {
                "profit": 140000000.0,
                "shares": 20.0,
                "asof_shares": 20.0,
                "valuation_shares": 80.0,
                "dividends_paid": 0.0,
            },
        }
        return {
            "abstract": abstract,
            "balance": pd.DataFrame(),
            "year_data": year_data,
            "current_price_tuple": (10.0, "test", "2026-04-25"),
        }

    def _make_filter_data(self):
        abstract = pd.DataFrame(
            [
                {
                    "指标": "归母净利润",
                    "20101231": 100000000.0,
                    "20111231": 110000000.0,
                    "20121231": 120000000.0,
                },
                {
                    "指标": "基本每股收益",
                    "20101231": 10.0,
                    "20111231": 11.0,
                    "20121231": 12.0,
                },
            ]
        )
        year_data = {
            "20101231": {"asof_shares": 10.0, "valuation_shares": 10.0, "split_factor_cumulative": 1.0},
            "20111231": {"asof_shares": 11.0, "valuation_shares": 44.0, "split_factor_cumulative": 4.0},
            "20121231": {"asof_shares": 12.0, "valuation_shares": 48.0, "split_factor_cumulative": 4.0},
        }
        report_dates = pd.DataFrame({"报告日": ["20101231", "20111231", "20121231"]})
        return {
            "abstract": abstract,
            "income": report_dates.copy(),
            "balance": report_dates.copy(),
            "cashflow_extras": pd.DataFrame(),
            "balance_extras": pd.DataFrame(),
            "income_extras": pd.DataFrame(),
            "year_data": year_data,
        }

    def test_build_valuation_history_uses_asof_shares_for_historical_rows(self):
        data = self._make_history_data()
        calls = []

        def fake_snapshot(col, year_data, annual_cols, abs_df, discount_rate, terminal_growth, projection_years, shares_for_ps=None, **kwargs):
            calls.append((col, shares_for_ps))
            return {
                "avg_oe_ps": 1.0,
                "g_bm": 0.1,
                "buf_total": 1.0,
                "raw_buf_total": 1.0,
                "buf_dcf": 1.0,
                "nc_iv": 0.0,
                "munger": {15: 1.0, 20: 1.0, 25: 1.0},
                "raw_munger": {15: 1.0, 20: 1.0, 25: 1.0},
                "diag_dcf": {},
                "diag_munger": {},
                "payout": 0.0,
            }

        with patch("valuescope.legacy_stock_scripts.core.valuation.compute_buffett_munger_snapshot", side_effect=fake_snapshot):
            build_valuation_history(data, total_shares=None, history_years=2)

        self.assertEqual(calls[0], ("20161231", 10.0))
        self.assertEqual(calls[1], ("20171231", 20.0))

    def test_filter_data_as_of_year_preserves_share_basis_fields(self):
        data = self._make_filter_data()

        filtered = _filter_data_as_of_year(copy.deepcopy(data), 2011)
        filtered_year_data = filtered["year_data"]

        self.assertIn("20111231", filtered_year_data)
        self.assertNotIn("20121231", filtered_year_data)
        self.assertEqual(filtered_year_data["20111231"]["asof_shares"], 11.0)
        self.assertEqual(filtered_year_data["20111231"]["valuation_shares"], 44.0)
        self.assertEqual(filtered_year_data["20111231"]["split_factor_cumulative"], 4.0)
        self.assertEqual(filtered.get("_share_basis_mode"), "asof")

    def test_build_valuation_assessments_prefers_asof_shares_in_asof_mode(self):
        data = self._make_history_data()
        data["_share_basis_mode"] = "asof"
        calls = []

        def fake_snapshot(col, year_data, annual_cols, abs_df, discount_rate, terminal_growth, projection_years, shares_for_ps=None, **kwargs):
            calls.append((col, shares_for_ps))
            return {
                "avg_oe_ps": 1.0,
                "g_bm": 0.1,
                "buf_total": 1.0,
                "raw_buf_total": 1.0,
                "buf_dcf": 1.0,
                "nc_iv": 0.0,
                "munger": {15: 1.0, 20: 1.0, 25: 1.0},
                "raw_munger": {15: 1.0, 20: 1.0, 25: 1.0},
                "diag_dcf": {},
                "diag_munger": {},
                "payout": 0.0,
                "g_note": "",
            }

        with patch("valuescope.legacy_stock_scripts.core.valuation.compute_buffett_munger_snapshot", side_effect=fake_snapshot), \
             patch("valuescope.legacy_stock_scripts.core.valuation.fetch_market_pe_anchor", return_value=(None, None)), \
             patch("valuescope.legacy_stock_scripts.core.valuation.fetch_cn_10y_government_bond_yield_pct", return_value=(None, None)), \
             patch("valuescope.legacy_stock_scripts.core.valuation.build_pe_percentile_history_post_may", return_value={}), \
             patch("valuescope.legacy_stock_scripts.core.valuation.build_eps_percentile_history", return_value={}):
            _, details = build_valuation_assessments(
                code="AAPL",
                company_name="Apple",
                industry_text="",
                total_shares=None,
                data=data,
            )

        self.assertEqual(calls[0], ("20171231", 20.0))
        self.assertEqual(details.get("latest_share_source"), "asof_shares")

    def test_build_oe_yield_history_prefers_asof_shares(self):
        year_data = {
            "20161231": {
                "asof_shares": 10.0,
                "valuation_shares": 40.0,
                "profit": 100.0,
                "da": 0.0,
                "capex": 0.0,
            }
        }
        daily = pd.DataFrame(
            {
                "dt": pd.date_range("2016-01-01", periods=250, freq="D"),
                "close": [10.0] * 250,
            }
        )

        with patch("valuescope.legacy_stock_scripts.core.valuation.fetch_stock_daily_hist_long", return_value=daily), \
             patch("valuescope.legacy_stock_scripts.core.valuation._close_column", return_value="close"), \
             patch("valuescope.legacy_stock_scripts.core.valuation._owner_earnings_three_caliber", return_value=(100.0, 100.0, 100.0)):
            result = build_oe_yield_history(
                code="AAPL",
                year_data=year_data,
                all_annual_cols_sorted=["20161231"],
                shares_for_ps=40.0,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["base_oe_ps"], 10.0)
        self.assertEqual(result[0]["base_yield"], 100.0)


if __name__ == "__main__":
    unittest.main()
