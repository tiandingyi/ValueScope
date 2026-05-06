from __future__ import annotations

import copy
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from valuescope.legacy_stock_scripts.core import orchestrator

SCHEMA_VERSION = "0.1.0"
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

    coverage_years = [str(row.get("year")) for row in rows if row.get("year") is not None]
    company_market = "CN-A"
    if str(ticker).upper().endswith(".HK"):
        company_market = "HK"
    elif str(ticker).upper().endswith(".US") or str(ticker).isalpha():
        company_market = "US"

    warnings = _warnings_from_quality(data_quality) + annual_warnings
    sections = [
        _overview_section(conclusions, data_quality),
        _metric_section("quality", "Quality", metrics),
        _metric_section("pricing_power", "Pricing Power", ses_metrics),
        _metric_section("valuation", "Valuation", valuation_metrics),
        _cash_flow_section(rows),
        _capital_safety_section(diagnostics),
        _shareholder_returns_section(dollar_retention),
        _table_section("annual_rows", "Annual Rows", rows),
        _table_section("valuation_history", "Valuation History", valuation_history),
        _diagnostics_section(diagnostics),
        _table_section("owner_earnings_yield", "Owner Earnings Yield", oe_yield_history),
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


def _capital_safety_section(diagnostics: Any) -> Dict[str, Any]:
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
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
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
    return {
        "id": "shareholder_returns",
        "title": "Shareholder Returns",
        "summary": "股东回报章节按已确认年报窗口重算，避免把未确认年度混入留存收益检验。",
        "items": items,
        "rows": _jsonable(dollar_retention.get("rows") or []),
        "details": _jsonable({key: value for key, value in dollar_retention.items() if key != "rows"}),
        "warnings": [item for item in items if item.get("status") in {"missing", "warning", "error"}],
    }


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

    conservative_latest_year = datetime.now(timezone.utc).year - 2
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
        "basis": data.get("formula") or data.get("rule_display") or data.get("meaning"),
        "meaning": data.get("meaning"),
        "implication": data.get("implication"),
        "warning": warning,
    }


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
