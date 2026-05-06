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
        {},
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
    assert snapshot["coverage"]["years"] == ["2022", "2024"]
    annual_rows = next(section for section in snapshot["sections"] if section["id"] == "annual_rows")
    assert [row["year"] for row in annual_rows["rows"]] == ["2022", "2024"]
    assert all(row["report_type"] == "annual" for row in annual_rows["rows"])
    assert all(row["report_provenance"].startswith("confirmed_annual") for row in annual_rows["rows"])
    section_ids = [section["id"] for section in snapshot["sections"]]
    assert "cash_flow" in section_ids
    assert "capital_safety" in section_ids
    assert "shareholder_returns" in section_ids
    assert any(warning["code"] == "unconfirmed_annual_rows_excluded" for warning in snapshot["warnings"])
    assert snapshot["sections"][0]["id"] == "overview"
    assert (tmp_path / "company_report_snapshot.json").exists()
