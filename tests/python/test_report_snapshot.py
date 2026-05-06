from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from valuescope.report_snapshot import generate_report_snapshot


def test_generate_report_snapshot_captures_render_payload(tmp_path: Path) -> None:
    rows = [
        {
            "year": "2022",
            "date_key": "20221231",
            "revenue": 0.8,
        },
        {
            "year": "2023",
            "date_key": "20230930",
            "revenue": 0.9,
        },
        {
            "year": "2024",
            "date_key": "20241231",
            "revenue": 1.0,
            "net_income": None,
        },
        {
            "year": str(datetime.now(timezone.utc).year - 1),
            "date_key": f"{datetime.now(timezone.utc).year - 1}1231",
            "revenue": 1.1,
        }
    ]
    payload_args = (
        "000858",
        "五粮液",
        rows,
        [],
        ["sample conclusion"],
        [],
        [],
        [],
        [],
        {
            "pe_percentile_history": {
                "current_pe": 12.0,
                "percentile": 40.0,
                "hist_min": 8.0,
                "hist_median": 11.0,
                "hist_max": 18.0,
                "points": [{"fiscal_year": "2024", "anchor_price": 100.0, "real_eps": 8.0, "real_pe": 12.5}],
            },
            "eps_percentile_history": {
                "current_value": 8.0,
                "percentile": 80.0,
                "hist_min": 4.0,
                "hist_median": 7.0,
                "hist_max": 9.0,
                "points": [{"fiscal_year": "2024", "value": 8.0, "real_eps": 8.0, "basic_eps": 7.8}],
            },
            "resonances": ["sample resonance"],
            "scenario_analysis": {
                "g_levels": [("基准G", 0.03)],
                "oe_levels": [("基准OE", 5.0)],
                "exit_pes": (20,),
                "dcf_iv": {("基准OE", "基准G"): 100.0},
                "munger_tables": {20: {("基准OE", "基准G"): 110.0}},
            },
        },
        [],
        {"price": 100.0, "share_capital": {"rows": []}},
    )

    def fake_generate_report(*_args, **_kwargs):
        # The facade monkeypatches orchestrator.render_html. Calling it here
        # proves we capture the legacy render boundary without hitting network.
        from valuescope.legacy_stock_scripts.core import orchestrator

        orchestrator.render_html(*payload_args)
        html_path = tmp_path / "debug.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return html_path

    with patch("valuescope.legacy_stock_scripts.core.orchestrator.generate_report", side_effect=fake_generate_report):
        snapshot = generate_report_snapshot("000858", output_dir=tmp_path)

    assert snapshot["company"]["ticker"] == "000858"
    assert snapshot["schema_version"] == "0.3.0"
    assert snapshot["current_price"] == 100.0
    assert snapshot["coverage"]["years"] == ["2022", "2024"]
    annual_rows = next(section for section in snapshot["sections"] if section["id"] == "annual_rows")
    assert [row["year"] for row in annual_rows["rows"]] == ["2022", "2024"]
    assert all(row["report_type"] == "annual" for row in annual_rows["rows"])
    assert all(row["report_provenance"].startswith("confirmed_annual") for row in annual_rows["rows"])
    section_ids = [section["id"] for section in snapshot["sections"]]
    assert "market_context" in section_ids
    assert "data_quality" in section_ids
    assert "machine_summary" in section_ids
    assert "pe_percentile" in section_ids
    assert "eps_percentile" in section_ids
    assert "radar_modules" in section_ids
    assert "valuation_scenarios" in section_ids
    assert "cash_flow" in section_ids
    assert "capital_safety" in section_ids
    assert "share_basis" in section_ids
    assert "valuation_formulas" in section_ids
    assert "shareholder_returns" in section_ids
    assert any(warning["code"] == "unconfirmed_annual_rows_excluded" for warning in snapshot["warnings"])
    assert snapshot["sections"][0]["id"] == "overview"
    assert snapshot["pe_percentile"]["series"][0]["pe"] == 12.5
    assert snapshot["eps_percentile"]["series"][0]["eps"] == 8.0
    assert (tmp_path / "company_report_snapshot.json").exists()
