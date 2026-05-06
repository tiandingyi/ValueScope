from __future__ import annotations

import copy
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from valuescope.legacy_stock_scripts.core import orchestrator
from valuescope.legacy_stock_scripts.core.assessment import build_quality_year_snapshots

SCHEMA_VERSION = "0.3.0"
DEFAULT_OUTPUT_DIR = Path("data/report_snapshots")
ALL_ANNUAL_HISTORY_YEARS = 80


class ReportSnapshotError(RuntimeError):
    """Raised when a report snapshot cannot be generated safely."""


def generate_report_snapshot(
    ticker: str,
    years: int = 8,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    asof_year: Optional[int] = None,
    asof_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate a ValueScope company report snapshot.

    The legacy engine is copied whole for speed. This facade captures the rich
    payload immediately before the old HTML renderer and serializes a
    ValueScope-owned JSON contract.
    """

    captured: Dict[str, Any] = {}
    original_render_html = orchestrator.render_html

    def capture_render_html(*args: Any, **kwargs: Any) -> str:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "<html><body>ValueScope snapshot generated; legacy HTML rendering skipped.</body></html>"

    orchestrator.render_html = capture_render_html
    try:
        html_path = orchestrator.generate_report(
            ticker,
            max(ALL_ANNUAL_HISTORY_YEARS, int(years)),
            asof_year=asof_year,
            asof_price=asof_price,
        )
    except Exception as exc:  # legacy engine has mixed provider exceptions
        raise ReportSnapshotError(f"Failed to generate report snapshot for {ticker}: {exc}") from exc
    finally:
        orchestrator.render_html = original_render_html

    if "args" not in captured:
        raise ReportSnapshotError("Legacy report engine did not reach the render boundary.")

    snapshot = _snapshot_from_render_payload(
        ticker=ticker,
        html_path=Path(html_path),
        args=captured["args"],
        kwargs=captured["kwargs"],
        years=years,
        asof_year=asof_year,
        asof_price=asof_price,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "company_report_snapshot.json"
    file_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot["snapshot_path"] = str(file_path)
    return snapshot


def _snapshot_from_render_payload(
    ticker: str,
    html_path: Path,
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    years: int,
    asof_year: Optional[int],
    asof_price: Optional[float],
) -> Dict[str, Any]:
    (
        code,
        company_name,
        rows,
        metrics,
        conclusions,
        ses_metrics,
        ses_conclusions,
        valuation_metrics,
        valuation_conclusions,
        valuation_details,
        valuation_history,
        diagnostics,
    ) = args[:12]

    is_bank = bool(kwargs.get("is_bank", False))
    data_quality = kwargs.get("data_quality") or {}
    rows, annual_warnings = _annual_report_rows(rows)
    valuation_history = _filter_rows_to_annual_years(valuation_history, rows)
    oe_yield_history = _filter_rows_to_annual_years(kwargs.get("oe_yield_history") or [], rows)
    dollar_retention = _filter_dollar_retention_to_annual_years(kwargs.get("dollar_retention"), rows)
    current_price = _current_price(asof_price=asof_price, diagnostics=diagnostics)
    market_context = _market_context(kwargs.get("market_env_data"))
    pe_percentile = _percentile_context((valuation_details or {}).get("pe_percentile_history"), "pe")
    eps_percentile = _percentile_context((valuation_details or {}).get("eps_percentile_history"), "eps")
    wr_data = _williams_r_context(kwargs.get("wr_data"))

    coverage_years = [str(row.get("year")) for row in rows if row.get("year") is not None]
    company_market = "CN-A"
    if str(ticker).upper().endswith(".HK"):
        company_market = "HK"
    elif str(ticker).upper().endswith(".US") or str(ticker).isalpha():
        company_market = "US"

    warnings = _warnings_from_quality(data_quality) + annual_warnings
    quality_snapshots = build_quality_year_snapshots(
        diagnostics.get("abs_df") if isinstance(diagnostics, dict) else None,
        diagnostics.get("annual_cols") if isinstance(diagnostics, dict) else [],
        diagnostics.get("year_data") if isinstance(diagnostics, dict) else {},
        diagnostics.get("market_cap") if isinstance(diagnostics, dict) else None,
    )
    sections = [
        _overview_section(conclusions, data_quality),
        _metric_section("quality", "Quality", metrics),
        _metric_section("pricing_power", "Pricing Power", ses_metrics),
        _radar_modules_section(metrics, ses_metrics, valuation_metrics, diagnostics, dollar_retention),
        _metric_section("valuation", "Valuation", valuation_metrics),
        _valuation_scenarios_section(valuation_details),
        _percentile_section("pe_percentile", "PE Percentile", pe_percentile),
        _percentile_section("eps_percentile", "EPS Percentile", eps_percentile),
        _cash_flow_section(rows),
        _capital_safety_section(diagnostics, quality_snapshots, rows),
        _share_basis_section(diagnostics, data_quality, rows),
        _shareholder_returns_section(dollar_retention),
        _table_section("annual_rows", "Annual Rows", rows),
        _table_section("valuation_history", "Valuation History", valuation_history),
        _table_section("owner_earnings_yield", "Owner Earnings Yield", oe_yield_history),
        _technicals_section(wr_data),
        _market_context_section(market_context),
        _data_quality_section(data_quality, warnings),
        _machine_summary_section(ticker, company_name, rows, data_quality, warnings, valuation_metrics),
        _valuation_formulas_section(valuation_metrics),
        _diagnostics_section(diagnostics),
        _raw_section("dollar_retention", "Dollar Retention", dollar_retention),
        _metric_explanations_section(metrics, ses_metrics, valuation_metrics),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "name": "valuescope-python-report",
            "provider": "legacy_stock_scripts",
            "mode": "as_of" if asof_year is not None else "current",
            "html_debug_path": str(html_path),
            "notes": "stock-scripts copied under valuescope.legacy_stock_scripts; JSON emitted by ValueScope facade",
        },
        "company": {
            "ticker": str(code),
            "name": str(company_name),
            "market": company_market,
            "currency": "CNY" if company_market == "CN-A" else None,
            "accounting_unit": "CNY" if company_market == "CN-A" else None,
            "is_bank": is_bank,
        },
        "current_price": current_price,
        "market_context": market_context,
        "pe_percentile": pe_percentile,
        "eps_percentile": eps_percentile,
        "coverage": {
            "period_type": "annual",
            "years": coverage_years,
            "requested_years": years,
            "asof_year": asof_year,
            "asof_price": asof_price,
        },
        "metric_definitions": _metric_definitions(metrics, ses_metrics, valuation_metrics),
        "sections": [section for section in sections if section is not None],
        "warnings": warnings,
    }


def _metric_section(section_id: str, title: str, assessments: Any) -> Dict[str, Any]:
    items = []
    for assessment in assessments or []:
        data = _assessment_to_item(assessment)
        items.append(data)
    return {
        "id": section_id,
        "title": title,
        "summary": None,
        "items": items,
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _current_price(*, asof_price: Optional[float], diagnostics: Any) -> Optional[float]:
    if asof_price is not None:
        return float(asof_price)
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("price"), (int, float)):
        return float(diagnostics["price"])
    return None


def _market_context(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    dates = value.get("bond_dates") or []
    yields = value.get("bond_values") or []
    series = []
    for date, yield_pct in zip(dates, yields):
        if yield_pct is None:
            continue
        series.append({"date": str(date)[:10], "yield_pct": float(yield_pct)})
    series = _monthly_series(series)

    latest = _safe_float(value.get("bond_latest"))
    csi300_pe = _safe_float(value.get("csi300_pe"))
    csi300_ey = _safe_float(value.get("csi300_ey"))
    erp_stock = _safe_float(value.get("erp_stock"))
    return {
        "bond_label": value.get("bond_label") or "中国十年期国债收益率",
        "bond_latest": latest,
        "bond_latest_date": value.get("bond_latest_date"),
        "bond_percentile": _safe_float(value.get("bond_pctile")),
        "bond_min": _safe_float(value.get("bond_min")),
        "bond_max": _safe_float(value.get("bond_max")),
        "bond_mean": _safe_float(value.get("bond_mean")),
        "csi300_pe_ttm": csi300_pe,
        "csi300_earnings_yield": csi300_ey,
        "market_equity_risk_premium": _safe_float(value.get("erp")),
        "stock_equity_risk_premium": erp_stock,
        "stock_erp_status": _erp_status(erp_stock),
        "summary": value.get("env_label"),
        "bond_yield_series": series,
    }


def _monthly_series(series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    monthly: Dict[str, Dict[str, Any]] = {}
    for point in series:
        date = str(point.get("date") or "")
        if len(date) < 7:
            continue
        monthly[date[:7]] = point
    compact = [monthly[key] for key in sorted(monthly)]
    if series and (not compact or compact[-1].get("date") != series[-1].get("date")):
        compact.append(series[-1])
    return compact


def _market_context_section(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not context:
        return {
            "id": "market_context",
            "title": "Market Context",
            "summary": "市场环境数据缺失。",
            "items": [],
            "details": {"status": "missing", "message": "数据缺失"},
            "rows": [],
            "warnings": [{"code": "market_context_missing", "message": "市场环境数据缺失。", "severity": "warning"}],
        }
    return {
        "id": "market_context",
        "title": "Market Context",
        "summary": context.get("summary"),
        "items": [
            _display_item("bond_latest", "中国10Y国债", context.get("bond_latest"), "十年期国债收益率最新值。", unit="percent"),
            _display_item("bond_percentile", "历史分位", context.get("bond_percentile"), "近十年国债收益率历史分位。", unit="percent"),
            _display_item("csi300_pe_ttm", "沪深300 PE", context.get("csi300_pe_ttm"), "沪深300滚动市盈率。", unit="multiple"),
            _display_item("market_equity_risk_premium", "股债风险溢价", context.get("market_equity_risk_premium"), "沪深300盈利率减十年期国债收益率。", unit="percent"),
        ],
        "details": context,
        "rows": context.get("bond_yield_series") or [],
        "warnings": [],
    }


def _erp_status(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value >= 3:
        return "sufficient"
    if value >= 0:
        return "thin"
    return "negative"


def _percentile_context(value: Any, kind: str) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    clean = _jsonable(value)
    if not isinstance(clean, dict):
        return None
    points = clean.get("points") or []
    series = []
    if kind == "pe":
        current = clean.get("current_pe")
        for point in points:
            if not isinstance(point, dict):
                continue
            series.append({
                "year": str(point.get("fiscal_year") or point.get("year") or ""),
                "price": point.get("anchor_price"),
                "eps": point.get("real_eps") if point.get("real_eps") is not None else point.get("basic_eps"),
                "pe": point.get("real_pe") if point.get("real_pe") is not None else point.get("basic_pe"),
                "anchor_date": point.get("anchor_date"),
            })
    else:
        current = clean.get("current_value")
        for point in points:
            if not isinstance(point, dict):
                continue
            series.append({
                "year": str(point.get("fiscal_year") or point.get("year") or ""),
                "eps": point.get("value"),
                "real_eps": point.get("real_eps"),
                "basic_eps": point.get("basic_eps"),
                "basis": point.get("real_eps_src"),
            })
    return {
        "kind": kind,
        "current": current,
        "percentile": clean.get("percentile"),
        "hist_min": clean.get("hist_min"),
        "hist_median": clean.get("hist_median"),
        "hist_max": clean.get("hist_max"),
        "hist_mean": clean.get("hist_mean"),
        "current_vs_median_pct": clean.get("current_vs_median_pct"),
        "sample_count": clean.get("sample_count"),
        "method": clean.get("method"),
        "note": clean.get("note"),
        "series": series,
        "raw": clean,
    }


def _percentile_section(section_id: str, title: str, context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if context is None:
        return None
    label = "PE 近十年历史分位" if context.get("kind") == "pe" else "E（EPS）近十年历史分位"
    items = [
        _display_item("current", "当前值", context.get("current"), "当前估值或盈利口径。", unit="multiple" if context.get("kind") == "pe" else None),
        _display_item("percentile", "近十年分位", context.get("percentile"), "当前值在历史样本中的位置。", unit="percent"),
        _display_item("history_range", "历史区间", _range_display(context.get("hist_min"), context.get("hist_max")), "历史样本最小值到最大值。"),
        _display_item("current_vs_median_pct", "相对中位数", context.get("current_vs_median_pct"), "当前值相对历史中位数的偏离。", unit="percent"),
    ]
    return {
        "id": section_id,
        "title": title,
        "summary": context.get("note") or label,
        "items": items,
        "details": context,
        "rows": context.get("series") or [],
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _overview_section(conclusions: Any, data_quality: Any) -> Dict[str, Any]:
    items = []
    for index, conclusion in enumerate(conclusions or []):
        items.append({
            "metric": f"conclusion_{index + 1}",
            "label": "Conclusion",
            "value": str(conclusion),
            "status": "ok",
            "basis": "Legacy stock-scripts business quality conclusion.",
            "warning": None,
        })
    return {
        "id": "overview",
        "title": "Overview",
        "summary": "Generated from the copied stock-scripts report engine.",
        "items": items,
        "data_quality": _jsonable(data_quality),
        "warnings": _warnings_from_quality(data_quality),
    }


def _data_quality_section(data_quality: Any, warnings: List[Dict[str, Any]]) -> Dict[str, Any]:
    clean = _jsonable(data_quality) if isinstance(data_quality, dict) else {}
    field_stats = clean.get("field_stats") if isinstance(clean, dict) else []
    model_results = clean.get("model_results") if isinstance(clean, dict) else []
    items = [
        _display_item("confidence", "整体置信度", clean.get("confidence"), "由字段覆盖、估值模型可用性、股本口径和缺失警告共同给出。"),
        _display_item("n_years", "历史样本", clean.get("n_years"), "进入快照的年度历史样本数量。", unit="number"),
        _display_item("models_available", "可用模型", clean.get("n_models_available"), "当前快照中可计算的估值模型数量。", unit="number"),
        _display_item("model_coverage", "模型覆盖", _safe_percent(clean.get("n_models_available"), clean.get("n_models_total")), "可用估值模型 / 总估值模型。", unit="percent"),
    ]
    return {
        "id": "data_quality",
        "title": "Data Quality",
        "summary": "把字段覆盖、模型可用性、股本口径和排除年度拆成可核查状态，避免把数据问题藏在总览警告里。",
        "items": items,
        "details": {
            "confidence": clean.get("confidence"),
            "confidence_score": clean.get("confidence_score"),
            "year_range": clean.get("year_range"),
            "industry_matched": clean.get("industry_matched"),
            "discount_key": clean.get("discount_key"),
            "exit_pe_key": clean.get("exit_pe_key"),
            "share_basis": clean.get("share_basis"),
            "model_results": model_results,
        },
        "rows": field_stats or [],
        "warnings": warnings,
    }


def _machine_summary_section(
    ticker: str,
    company_name: Any,
    rows: List[Dict[str, Any]],
    data_quality: Any,
    warnings: List[Dict[str, Any]],
    valuation_metrics: Any,
) -> Dict[str, Any]:
    latest = _latest_annual_row(rows) or {}
    quality = _jsonable(data_quality) if isinstance(data_quality, dict) else {}
    valuation_items = [_assessment_to_item(item) for item in valuation_metrics or []]
    warning_labels = [item.get("label") for item in valuation_items if item.get("status") in {"warning", "error", "missing"}]
    summary = {
        "ticker": str(ticker),
        "company_name": str(company_name),
        "latest_annual_year": latest.get("year"),
        "confidence": quality.get("confidence"),
        "warning_count": len(warnings),
        "valuation_warning_labels": warning_labels,
        "research_only": True,
        "advice_policy": "研究辅助，不构成买入、卖出或持有建议。",
    }
    rows_out = [
        {"key": "ticker", "value": summary["ticker"], "basis": "报告快照 company.ticker"},
        {"key": "latest_annual_year", "value": summary["latest_annual_year"], "basis": "已确认年度历史的最后一年"},
        {"key": "confidence", "value": summary["confidence"], "basis": "数据质量综合评分"},
        {"key": "warning_count", "value": summary["warning_count"], "basis": "顶层警告数量"},
        {"key": "research_only", "value": "true", "basis": summary["advice_policy"]},
    ]
    return {
        "id": "machine_summary",
        "title": "Machine Summary",
        "summary": "面向后续自动解析的低噪声摘要；只表达数据事实和研究辅助状态，不输出买卖建议。",
        "items": [
            _display_item("latest_annual_year", "最新年报", latest.get("year"), "已确认年度历史的最后一年。"),
            _display_item("warning_count", "警告数量", len(warnings), "快照顶层数据警告数量。", unit="number"),
        ],
        "details": summary,
        "rows": rows_out,
        "warnings": warnings,
    }


def _table_section(section_id: str, title: str, rows: Any) -> Dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "summary": None,
        "items": [],
        "rows": _jsonable(rows or []),
        "warnings": [],
    }


def _display_item(
    metric: str,
    label: str,
    value: Any,
    basis: str,
    *,
    unit: Optional[str] = None,
    status: Optional[str] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    item_status = status or ("missing" if value is None else "ok")
    display_value = _display_number(value, unit) if item_status != "missing" else None
    return {
        "metric": metric,
        "label": label,
        "value": display_value,
        "status": item_status,
        "basis": basis,
        "warning": warning or ("源数据缺失，未按 0 处理。" if item_status == "missing" else None),
    }


def _display_number(value: Any, unit: Optional[str] = None) -> Any:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return value
    if unit == "money":
        return f"{value / 100000000:.2f} 亿"
    if unit == "percent":
        return f"{value:.2f}%"
    if unit == "days":
        return f"{value:.2f} 天"
    if unit == "multiple":
        return f"{value:.2f} 倍"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        if value is not None:
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _range_display(low: Any, high: Any) -> Optional[str]:
    low_num = _safe_float(low)
    high_num = _safe_float(high)
    if low_num is None or high_num is None:
        return None
    return f"{low_num:.2f} - {high_num:.2f}"


def _latest_annual_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return rows[-1] if rows else None


def _cash_flow_section(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest = _latest_annual_row(rows) or {}
    items = [
        _display_item("ocf", "经营现金流", latest.get("ocf"), "年度现金流量表经营活动现金流量净额。", unit="money"),
        _display_item("net_income", "净利润", latest.get("net_income"), "年度利润表净利润。", unit="money"),
        _display_item("capex", "资本开支", latest.get("capex"), "现金流量表构建长期资产相关支出。", unit="money"),
        _display_item(
            "capex_net_income",
            "资本开支/净利润",
            latest.get("capex_net_income"),
            "资本开支占净利润比例，用来观察维护性资本开支压力。",
            unit="percent",
            status=_capex_intensity_status(latest.get("capex_net_income")),
        ),
    ]
    table_rows = [
        {
            "year": row.get("year"),
            "ocf": row.get("ocf"),
            "net_income": row.get("net_income"),
            "capex": row.get("capex"),
            "capex_net_income": row.get("capex_net_income"),
            "report_provenance": row.get("report_provenance"),
        }
        for row in rows
    ]
    return {
        "id": "cash_flow",
        "title": "Cash Flow",
        "summary": "现金流章节只使用已纳入年度历史的年报行；缺失值保留为缺失。",
        "items": items,
        "rows": table_rows,
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _capex_intensity_status(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "missing"
    if number <= 25:
        return "ok"
    if number <= 60:
        return "warning"
    return "error"


def _capital_safety_section(diagnostics: Any, quality_snapshots: Any = None, annual_rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return _raw_section("capital_safety", "Capital Safety", diagnostics)
    share_capital = diagnostics.get("share_capital")
    cards = share_capital.get("cards") if isinstance(share_capital, dict) else []
    items = [_assessment_to_item(card) for card in cards or []]
    selected = {
        "price": diagnostics.get("price"),
        "market_cap": diagnostics.get("market_cap"),
        "shares": diagnostics.get("shares"),
        "pledge_fetch_status": diagnostics.get("pledge_fetch_status"),
    }
    return {
        "id": "capital_safety",
        "title": "Capital Safety",
        "summary": "资本安全先披露价格、市值、股本口径和稀释/回购真实性，不输出投资建议。",
        "items": items,
        "details": _jsonable(selected),
        "rows": _jsonable(_capital_safety_rows(quality_snapshots, annual_rows or [])),
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _capital_safety_rows(quality_snapshots: Any, annual_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    annual_years = {str(row.get("year")) for row in annual_rows}
    rows = []
    for row in _jsonable(quality_snapshots or []):
        if not isinstance(row, dict):
            continue
        if annual_years and str(row.get("year")) not in annual_years:
            continue
        rows.append({
            "year": row.get("year"),
            "roic": row.get("roic"),
            "interest_coverage": row.get("icr"),
            "interest_tag": row.get("icr_tag"),
            "ocf_ratio": row.get("ocf_ratio"),
            "eps_quality": row.get("eps_quality"),
            "goodwill_ratio": row.get("gw_pct"),
            "payout": row.get("payout"),
            "total_yield": row.get("total_yield"),
        })
    return sorted(rows, key=lambda item: str(item.get("year") or ""))


def _share_basis_section(diagnostics: Any, data_quality: Any, annual_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(diagnostics, dict):
        return None
    share_capital = diagnostics.get("share_capital")
    if not isinstance(share_capital, dict):
        return None
    annual_years = {str(row.get("year")) for row in annual_rows}
    rows = [
        row
        for row in _jsonable(share_capital.get("rows") or [])
        if isinstance(row, dict) and str(row.get("year")) in annual_years
    ]
    cards = share_capital.get("cards") or []
    items = [_assessment_to_item(card) for card in cards]
    clean_quality = _jsonable(data_quality) if isinstance(data_quality, dict) else {}
    share_basis = clean_quality.get("share_basis") if isinstance(clean_quality, dict) else {}
    details = {
        "price": diagnostics.get("price"),
        "market_cap": diagnostics.get("market_cap"),
        "shares": diagnostics.get("shares"),
        "confidence": share_basis.get("confidence") if isinstance(share_basis, dict) else None,
        "coverage_ratio": share_basis.get("coverage_ratio") if isinstance(share_basis, dict) else None,
        "valuation_count": share_basis.get("valuation_count") if isinstance(share_basis, dict) else None,
        "eps_derived_years": share_basis.get("eps_derived_years") if isinstance(share_basis, dict) else [],
        "legacy_fallback_years": share_basis.get("legacy_fallback_years") if isinstance(share_basis, dict) else [],
        "reported_semantics": share_basis.get("reported_semantics") if isinstance(share_basis, dict) else [],
        "source_policy": "优先财报披露股本；缺失时可记录 EPS 推导隐含股本；legacy shares 只能作为最后回退并必须警告。",
    }
    warnings = [item for item in items if item.get("status") in {"missing", "warning", "error"}]
    if isinstance(share_basis, dict) and share_basis.get("eps_derived_count"):
        warnings.append({
            "code": "eps_derived_share_basis",
            "message": f"历史股本有 {share_basis.get('eps_derived_count')} 年使用归母净利润/EPS推导的隐含股本。",
            "severity": "warning",
        })
    return {
        "id": "share_basis",
        "title": "Share Basis Diagnostics",
        "summary": "单独披露估值使用的股本来源、推导年份和稀释/回购判断，避免把股本口径误读成 legacy 回退。",
        "items": items,
        "details": _jsonable(details),
        "rows": rows,
        "warnings": warnings,
    }


def _shareholder_returns_section(dollar_retention: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(dollar_retention, dict):
        return _raw_section("shareholder_returns", "Shareholder Returns", dollar_retention)
    items = [
        _display_item("total_div", "累计分红", dollar_retention.get("total_div"), "纳入年报窗口内的现金分红合计。", unit="money"),
        _display_item("total_buyback", "累计回购", dollar_retention.get("total_buyback"), "纳入年报窗口内的回购现金合计。", unit="money"),
        _display_item("retained_oe", "留存所有者收益", dollar_retention.get("retained_oe"), "累计所有者收益扣除分红和回购后的留存部分。", unit="money"),
        _display_item("ratio_oe", "OE留存回报", dollar_retention.get("ratio_oe"), "市值增加额相对留存所有者收益的倍数。", unit="multiple"),
    ]
    rows = _jsonable(dollar_retention.get("rows") or [])
    enriched_rows = []
    cumulative_retained = 0.0
    cumulative_mva = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        retained = (float(row.get("oe") or 0) - float(row.get("div") or 0) - float(row.get("buyback") or 0))
        cumulative_retained += retained
        if isinstance(dollar_retention.get("mcap_start"), (int, float)) and isinstance(row.get("price_ma200"), (int, float)) and isinstance(dollar_retention.get("shares_yi"), (int, float)):
            current_mcap = row["price_ma200"] * dollar_retention["shares_yi"]
            cumulative_mva = current_mcap - dollar_retention["mcap_start"]
        enriched["retained_oe"] = retained
        enriched["one_dollar_return"] = _safe_divide(cumulative_mva, cumulative_retained) if cumulative_mva is not None else None
        enriched_rows.append(enriched)
    return {
        "id": "shareholder_returns",
        "title": "Shareholder Returns",
        "summary": "股东回报按已确认年报窗口重算，并用巴菲特“一美元留存收益至少创造一美元市值”的口径观察管理层资本配置。",
        "items": items,
        "rows": enriched_rows,
        "details": _jsonable({key: value for key, value in dollar_retention.items() if key != "rows"}),
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _valuation_formulas_section(valuation_metrics: Any) -> Dict[str, Any]:
    rows = []
    for item in [_assessment_to_item(metric) for metric in valuation_metrics or []]:
        rows.append({
            "model": item.get("label"),
            "value": item.get("value"),
            "formula": item.get("basis"),
            "direction": "contextual",
            "meaning": item.get("what_it_measures") or item.get("meaning"),
            "caveat": item.get("implication"),
            "status": item.get("status"),
        })
    return {
        "id": "valuation_formulas",
        "title": "Valuation Formulas",
        "summary": "把估值公式、方向和限制条件独立成表，便于和原 HTML 的公式附录核对。",
        "items": [],
        "rows": rows,
        "warnings": [row for row in rows if row.get("status") in {"missing", "warning", "error"}],
    }


def _valuation_scenarios_section(valuation_details: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(valuation_details, dict):
        return None
    scenarios = valuation_details.get("scenario_analysis")
    if not isinstance(scenarios, dict):
        return None
    dcf_iv = scenarios.get("dcf_iv") or {}
    munger_tables = scenarios.get("munger_tables") or {}
    rows = []
    for oe_label, oe_value in scenarios.get("oe_levels") or []:
        for g_label, g_value in scenarios.get("g_levels") or []:
            key = (oe_label, g_label)
            row = {
                "owner_earnings_case": oe_label,
                "owner_earnings_ps": oe_value,
                "growth_case": g_label,
                "growth": _safe_percent(g_value, 1),
                "dcf_iv": dcf_iv.get(key),
            }
            for exit_pe in scenarios.get("exit_pes") or []:
                table = munger_tables.get(exit_pe) or {}
                row[f"munger_{exit_pe}x"] = table.get(key)
            rows.append(row)
    resonances = valuation_details.get("resonances") or []
    sensitivity = valuation_details.get("dcf_sensitivity") if isinstance(valuation_details.get("dcf_sensitivity"), dict) else {}
    items = [
        _display_item("resonance_count", "共振信号", len(resonances), "多个估值模型同时支持或反对低估判断的数量。", unit="number"),
        _display_item("mos_ratio", "安全边际", _safe_percent(valuation_details.get("mos_ratio"), 1), "估值模型采用的安全边际比例。", unit="percent"),
        _display_item("discount_rate", "折现率", _safe_percent(valuation_details.get("discount_rate"), 1), "行业适配后的折现率。", unit="percent"),
    ]
    return {
        "id": "valuation_scenarios",
        "title": "Valuation Scenarios",
        "summary": "三档所有者收益、增长率与退出市盈率组合，配合低估共振和 DCF 敏感性复核估值结构。",
        "items": items,
        "details": _jsonable({
            "resonances": resonances,
            "dcf_sensitivity": sensitivity,
            "exit_pes": valuation_details.get("exit_pes"),
            "mos_grade": valuation_details.get("mos_grade"),
            "discount_rate_key": valuation_details.get("discount_rate_key"),
            "exit_pe_key": valuation_details.get("exit_pe_key"),
        }),
        "rows": _jsonable(rows),
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _radar_modules_section(
    metrics: Any,
    ses_metrics: Any,
    valuation_metrics: Any,
    diagnostics: Any,
    dollar_retention: Any,
) -> Dict[str, Any]:
    rows = []

    def add_row(module: str, source: str, item: Dict[str, Any]) -> None:
        rows.append({
            "module": module,
            "signal": item.get("label"),
            "value": item.get("value"),
            "status": item.get("status"),
            "basis": item.get("basis"),
            "source": source,
            "warning": item.get("warning"),
        })

    for item in [_assessment_to_item(value) for value in metrics or []]:
        label = str(item.get("label") or "")
        if any(token in label for token in ["毛利", "纯度", "现金", "资本", "ROE", "EPS", "税", "商誉", "净现"]):
            add_row("经营质量雷达", "quality", item)
    for item in [_assessment_to_item(value) for value in ses_metrics or []]:
        label = str(item.get("label") or "")
        if any(token in label for token in ["营收", "毛利", "费用", "周转", "ROE", "现金"]):
            add_row("提价权与效率雷达", "pricing_power", item)
    for item in [_assessment_to_item(value) for value in valuation_metrics or []]:
        add_row("估值雷达", "valuation", item)
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("share_capital"), dict):
        for card in diagnostics["share_capital"].get("cards") or []:
            add_row("股本质量雷达", "share_capital", _assessment_to_item(card))
    if isinstance(dollar_retention, dict):
        ratio = dollar_retention.get("ratio_oe")
        status = "ok" if isinstance(ratio, (int, float)) and ratio >= 1 else "warning"
        rows.append({
            "module": "股东回报雷达",
            "signal": "OE留存回报",
            "value": ratio,
            "status": status,
            "basis": "市值增加额 / 留存所有者收益。",
            "source": "dollar_retention",
            "warning": None if status == "ok" else "留存收益未被市值充分确认。",
        })
    return {
        "id": "radar_modules",
        "title": "Focused Radar Modules",
        "summary": "把经营、估值、股本和股东回报信号拆成可扫描模块，减少宽泛章节里的信息压缩。",
        "items": [],
        "rows": rows,
        "warnings": [row for row in rows if row.get("status") in {"missing", "warning", "error"}],
    }


def _williams_r_context(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    clean = _jsonable(value)
    if not isinstance(clean, dict):
        return None
    periods = [int(period) for period in clean.get("periods") or []]
    dates = clean.get("dates") or []
    wr = clean.get("wr") or {}
    rows = []
    for index, date in enumerate(dates):
        row: Dict[str, Any] = {"date": date}
        for period in periods:
            series = wr.get(str(period)) or wr.get(period) or []
            row[f"wr_{period}"] = series[index] if index < len(series) else None
        rows.append(row)
    latest = {}
    raw_latest = clean.get("latest") or {}
    for period in periods:
        latest[f"wr_{period}"] = raw_latest.get(str(period)) if str(period) in raw_latest else raw_latest.get(period)
    return {
        "asof": clean.get("asof"),
        "periods": periods,
        "latest": latest,
        "rows": rows,
        "crossings": clean.get("crossings") or [],
    }


def _technicals_section(context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if context is None:
        return None
    latest = context.get("latest") or {}
    items = []
    for period in context.get("periods") or []:
        value = latest.get(f"wr_{period}")
        label, status = _williams_status(value)
        items.append(_display_item(f"wr_{period}", f"Williams %R {period}日", value, f"{period}日 Williams %R，{label}。", status=status))
    return {
        "id": "technicals",
        "title": "Williams %R Technicals",
        "summary": "技术面只作为价格位置辅助，不参与买卖建议；展示 14/28/60 日 %R、阈值状态和交叉事件。",
        "items": items,
        "details": {
            "asof": context.get("asof"),
            "periods": context.get("periods"),
            "latest": latest,
            "crossings": context.get("crossings") or [],
        },
        "rows": context.get("rows") or [],
        "crossings": context.get("crossings") or [],
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


def _williams_status(value: Any) -> tuple[str, str]:
    number = _safe_float(value)
    if number is None:
        return "数据缺失", "missing"
    if number <= -80:
        return "超卖区", "warning"
    if number >= -20:
        return "超买区", "warning"
    return "中性区", "ok"


def _annual_report_rows(rows: Any) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep only annual-report rows, preserving the full available history.

    The report UI must not silently use quarterly rows as the latest year. A
    row is annual only when its report date key ends in 1231. If the source has
    no current-year annual report, the latest available full annual report
    remains the latest row, e.g. 2024 instead of quarterly 2025 data.
    """

    candidates: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for row in _jsonable(rows or []):
        if not isinstance(row, dict):
            continue
        date_key = str(row.get("date_key") or "")
        year = str(row.get("year") or "")
        if date_key:
            if not date_key.endswith("1231"):
                continue
            normalized = dict(row)
            normalized["year"] = date_key[:4]
            candidates.append(normalized)
        elif year.isdigit() and len(year) == 4:
            candidates.append(dict(row))

    sorted_candidates = sorted(candidates, key=lambda item: str(item.get("year") or ""))
    if not sorted_candidates:
        return [], []

    # A-share annual reports are published by April 30 each year for the prior fiscal year.
    # By mid-year, last year's annual data is confirmed. Use year-1 so FY(current-1) is accepted.
    conservative_latest_year = datetime.now(timezone.utc).year - 1
    annual_rows: List[Dict[str, Any]] = []
    excluded_years: List[str] = []
    for row in sorted_candidates:
        normalized = dict(row)
        year_text = str(normalized.get("year") or "")
        year_num = int(year_text) if year_text.isdigit() else None
        has_provider_provenance = str(normalized.get("report_provenance") or "") == "confirmed_annual"
        if has_provider_provenance or (year_num is not None and year_num <= conservative_latest_year):
            normalized["report_type"] = "annual"
            normalized["report_source"] = str(normalized.get("report_source") or "legacy_stock_scripts:render_payload")
            normalized["report_provenance"] = "confirmed_annual" if has_provider_provenance else "confirmed_annual_by_conservative_cutoff"
            annual_rows.append(normalized)
        else:
            excluded_years.append(year_text or str(normalized.get("date_key") or "unknown"))

    if excluded_years:
        warnings.append({
            "code": "unconfirmed_annual_rows_excluded",
            "message": f"以下年度缺少可验证年报来源，已从年度历史中排除：{'、'.join(excluded_years)}。",
            "severity": "warning",
        })
    return annual_rows, warnings


def _filter_rows_to_annual_years(rows: Any, annual_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    annual_years = {str(row.get("year")) for row in annual_rows if row.get("year") is not None}
    filtered = []
    for row in _jsonable(rows or []):
        if isinstance(row, dict) and str(row.get("year")) in annual_years:
            filtered.append(row)
    return sorted(filtered, key=lambda item: str(item.get("year") or ""))


def _filter_dollar_retention_to_annual_years(value: Any, annual_rows: List[Dict[str, Any]]) -> Any:
    if not isinstance(value, dict):
        return _jsonable(value)

    annual_years = {str(row.get("year")) for row in annual_rows if row.get("year") is not None}
    clean = _jsonable(value)
    if not isinstance(clean, dict):
        return clean

    rows = [
        row
        for row in clean.get("rows") or []
        if isinstance(row, dict) and str(row.get("year")) in annual_years
    ]
    rows = sorted(rows, key=lambda item: str(item.get("year") or ""))
    clean["rows"] = rows
    if not rows:
        return clean

    clean["window_start"] = str(rows[0].get("year"))
    clean["window_end"] = str(rows[-1].get("year"))
    for source_key, total_key in [
        ("ni", "total_ni"),
        ("oe", "total_oe"),
        ("div", "total_div"),
        ("buyback", "total_buyback"),
    ]:
        clean[total_key] = sum(float(row.get(source_key) or 0) for row in rows)

    clean["retained_strict"] = clean["total_ni"] - clean["total_div"] - clean["total_buyback"]
    clean["retained_oe"] = clean["total_oe"] - clean["total_div"] - clean["total_buyback"]
    clean["real_retained"] = clean["retained_oe"]
    last_price = rows[-1].get("price_ma200")
    if last_price is not None:
        clean["price_end"] = last_price
    shares = clean.get("shares_yi")
    if isinstance(shares, (int, float)) and isinstance(last_price, (int, float)):
        clean["mcap_end"] = shares * last_price
    if isinstance(clean.get("mcap_start"), (int, float)) and isinstance(clean.get("mcap_end"), (int, float)):
        clean["mva"] = clean["mcap_end"] - clean["mcap_start"]
    if isinstance(clean.get("mva"), (int, float)):
        clean["ratio_strict"] = _safe_divide(clean["mva"], clean["retained_strict"])
        clean["ratio_oe"] = _safe_divide(clean["mva"], clean["retained_oe"])
    clean["passed_strict"] = isinstance(clean.get("ratio_strict"), (int, float)) and clean["ratio_strict"] >= 1
    return clean


def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def _safe_percent(numerator: Any, denominator: Any) -> Optional[float]:
    n = _safe_float(numerator)
    d = _safe_float(denominator)
    if n is None or d in (None, 0):
        return None
    return n / d * 100


def _diagnostics_section(diagnostics: Any) -> Dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return _raw_section("diagnostics", "Diagnostics", diagnostics)
    selected = {
        "price": diagnostics.get("price"),
        "market_cap": diagnostics.get("market_cap"),
        "shares": diagnostics.get("shares"),
        "share_capital": diagnostics.get("share_capital"),
        "pledge": diagnostics.get("pledge"),
        "pledge_fetch_status": diagnostics.get("pledge_fetch_status"),
    }
    return {
        "id": "diagnostics",
        "title": "Diagnostics",
        "summary": "Selected diagnostics from the legacy engine.",
        "items": [],
        "details": _jsonable(selected),
        "warnings": [],
    }


def _raw_section(section_id: str, title: str, value: Any) -> Dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "summary": None,
        "items": [],
        "details": _jsonable(value),
        "warnings": [],
    }


def _metric_explanations_section(*groups: Any) -> Dict[str, Any]:
    items = []
    for group in groups:
        for assessment in group or []:
            item = _assessment_to_item(assessment)
            items.append({
                "metric": item["metric"],
                "label": item["label"],
                "value": item.get("meaning") or item.get("basis"),
                "status": item["status"],
                "basis": item.get("basis"),
                "warning": item.get("warning"),
            })
    return {
        "id": "metric_explanations",
        "title": "Metric Explanations",
        "summary": "Metric formulas, meanings, and implications copied from the report engine.",
        "items": items,
        "warnings": [],
    }


def _assessment_to_item(assessment: Any) -> Dict[str, Any]:
    data = dataclasses.asdict(assessment) if dataclasses.is_dataclass(assessment) else dict(assessment)
    label = str(data.get("label") or "Metric")
    tone = str(data.get("tone") or "muted")
    status = _status_from_tone_and_text(tone, data.get("value_display"), data.get("status_text"))
    warning = data.get("status_text") if status in {"missing", "warning", "error"} else None
    return {
        "metric": _metric_id(label),
        "label": label,
        "value": data.get("value_display"),
        "status": status,
        "tone": tone,
        "badge": _badge_label(label, status, data.get("status_text"), data.get("value_display")),
        "badge_color": _badge_color(status, tone),
        "what_it_measures": data.get("meaning"),
        "basis": data.get("formula") or data.get("rule_display") or data.get("meaning"),
        "meaning": data.get("meaning"),
        "implication": data.get("implication"),
        "warning": warning,
    }


def _badge_color(status: str, tone: str) -> Optional[str]:
    if status in {"missing", "not_applicable"}:
        return None
    if status == "error" or tone == "bad":
        return "red"
    if status == "warning" or tone == "warn":
        return "yellow"
    if status == "ok" and tone == "good":
        return "green"
    return None


def _badge_label(label: str, status: str, status_text: Any, value_display: Any) -> Optional[str]:
    if status == "missing":
        return "数据缺失"
    if status == "not_applicable":
        return "不适用"
    text = str(status_text or value_display or "")
    if status == "ok":
        if label == "OE-DCF":
            return "满足安全边际"
        if "芒格" in label:
            return "25x场景显著高于现价"
        if "国债" in label:
            return "风险溢价通过"
        return text[:18] or "通过"
    if status == "warning":
        return text[:18] or "需关注"
    if status == "error":
        return "计算失败"
    return None


def _status_from_tone_and_text(tone: str, value_display: Any, status_text: Any) -> str:
    text = f"{value_display or ''} {status_text or ''}".lower()
    if "error" in text or "失败" in text:
        return "error"
    if "n/a" in text or "na" == text.strip() or "缺" in text:
        return "missing"
    if "不适用" in text:
        return "not_applicable"
    if tone in {"bad", "warn"}:
        return "warning"
    return "ok"


def _metric_definitions(*groups: Any) -> Dict[str, Any]:
    definitions: Dict[str, Any] = {}
    for group in groups:
        for assessment in group or []:
            item = _assessment_to_item(assessment)
            definitions[item["metric"]] = {
                "label": item["label"],
                "unit": _infer_unit(item["value"]),
                "value_type": "display_string",
                "direction": "contextual",
                "description": item.get("meaning") or item.get("basis"),
                "source_reference": "valuescope.legacy_stock_scripts",
            }
    return definitions


def _infer_unit(value: Any) -> Optional[str]:
    text = str(value or "")
    if "%" in text:
        return "percent"
    if "倍" in text or "x" in text.lower():
        return "multiple"
    if "亿" in text:
        return "CNY 100M"
    return None


def _warnings_from_quality(data_quality: Any) -> List[Dict[str, Any]]:
    if not isinstance(data_quality, dict):
        return []
    warnings: List[Dict[str, Any]] = []
    for key, value in data_quality.items():
        if value in (None, "", [], {}):
            continue
        if "warning" in key.lower() or "missing" in key.lower() or "缺" in key:
            message_value = _jsonable(value)
            if isinstance(message_value, list):
                message = "；".join(str(item) for item in message_value)
            else:
                message = str(message_value)
            warnings.append({
                "code": str(key),
                "message": message,
                "severity": "warning",
            })
    return warnings


def _metric_id(label: str) -> str:
    normalized = []
    for ch in label.lower().strip():
        if ch.isalnum():
            normalized.append(ch)
        elif normalized and normalized[-1] != "_":
            normalized.append("_")
    return "".join(normalized).strip("_") or "metric"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
        return frame.where(pd.notnull(frame), None).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items() if key not in {"abs_df"}}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return copy.deepcopy(str(value))
