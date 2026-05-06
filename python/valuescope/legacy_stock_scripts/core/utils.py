# core/utils.py — auto-extracted
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import _DEDUCT_PARENT_NET_PROFIT_NAMES, _REAL_EPS_ROW_NAMES


def get_metric(df, metric, col):
    rows = df[df["指标"] == metric]
    if rows.empty or col not in df.columns:
        return None
    for v in rows[col].values:
        if pd.notna(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None

def get_metric_first(abs_df: pd.DataFrame, col: str, *names: str) -> Optional[float]:
    if abs_df is None or abs_df.empty or col not in abs_df.columns:
        return None
    for name in names:
        rows = abs_df[abs_df["指标"] == name]
        if rows.empty:
            continue
        v = rows[col].values[0]
        if pd.notna(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None

def get_deduct_parent_net_profit(abs_df: pd.DataFrame, col: str) -> Optional[float]:
    return get_metric_first(abs_df, col, *_DEDUCT_PARENT_NET_PROFIT_NAMES)

def get_real_eps(abs_df: pd.DataFrame, col: str) -> Tuple[Optional[float], str]:
    if abs_df is None or abs_df.empty or col not in abs_df.columns:
        return (None, "")
    for name in _REAL_EPS_ROW_NAMES:
        rows = abs_df[abs_df["指标"] == name]
        if rows.empty:
            continue
        v = rows[col].values[0]
        if pd.notna(v):
            try:
                return float(v), f"摘要·{name}"
            except (TypeError, ValueError):
                pass
    kr = get_deduct_parent_net_profit(abs_df, col)
    ni = get_metric(abs_df, "归母净利润", col)
    be = get_metric(abs_df, "基本每股收益", col)
    if kr is not None and ni is not None and be is not None and abs(ni) >= 1e-9:
        return float(kr) * float(be) / float(ni), "推算·扣非归母净利÷隐含加权平均股本"
    if be is not None:
        return float(be), "回退·基本每股收益（缺扣非归母净利）"
    return None, ""

def _parse_share_count(val) -> Optional[float]:
    s = str(val).strip().replace(",", "").replace(" ", "")
    try:
        if "亿" in s:
            return float(s.replace("亿", "").replace("股", "")) * 1e8
        if "万" in s:
            return float(s.replace("万", "").replace("股", "")) * 1e4
        return float(s.replace("股", ""))
    except (ValueError, TypeError):
        return None

def is_bank(industry_text: str, company_name: str = "") -> bool:
    """Detect whether the stock is a bank based on industry text or company name."""
    combined = (industry_text or "") + "|" + (company_name or "")
    return "银行" in combined

def _tencent_symbol_prefix(code: str) -> str:
    return "sh" if code.startswith("6") else ("bj" if code[:1] in ("4", "8", "9") else "sz")

def _trend_arrow(values: Sequence[Optional[float]], higher_is_better: bool = True) -> str:
    """Return a trend arrow symbol based on the last 3 values."""
    nums = [v for v in values[-3:] if v is not None]
    if len(nums) < 2:
        return ""
    delta = nums[-1] - nums[0]
    pct = abs(delta / nums[0]) * 100 if nums[0] != 0 else (100 if delta != 0 else 0)
    if pct < 3:
        return "→"
    improving = (delta > 0) == higher_is_better
    if pct >= 15:
        return "↑" if improving else "↓"
    return "↗" if improving else "↘"

def safe_float(val) -> Optional[float]:
    try:
        if val is None or pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None

def fmt_pct(val: Optional[float], digits: int = 1) -> str:
    if val is None:
        return "N/A"
    use_digits = digits
    if abs(val) < 1 and digits < 2:
        use_digits = 2
    return f"{val:.{use_digits}f}%"

def fmt_days(val: Optional[float], digits: int = 1) -> str:
    return "N/A" if val is None else f"{val:.{digits}f} 天"

def fmt_ratio(val: Optional[float], digits: int = 1) -> str:
    return "N/A" if val is None else f"{val:.{digits}f}%"

def fmt_num(val: Optional[float], digits: int = 2) -> str:
    return "N/A" if val is None else f"{val:.{digits}f}"

def fmt_yi(val: Optional[float], digits: int = 2) -> str:
    return "N/A" if val is None else f"{val / 1e8:,.{digits}f} 亿"

def fmt_shares(val: Optional[float], digits: int = 2) -> str:
    return "N/A" if val is None else f"{val / 1e8:,.{digits}f} 亿股"

def pick_first_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for col in candidates:
        if col in df.columns:
            return col
    return None

def annualize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "报告日" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["报告日"] = out["报告日"].astype(str)
    out = out[out["报告日"].str.endswith("1231")].copy()
    return out.sort_values("报告日")

def series_values(rows: Sequence[Dict], key: str) -> List[float]:
    vals = []
    for row in rows:
        val = row.get(key)
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            vals.append(float(val))
    return vals

def trend_text(values: Sequence[float]) -> str:
    if len(values) < 3:
        return "样本不足"
    start = statistics.mean(values[: min(2, len(values))])
    end = statistics.mean(values[-min(2, len(values)) :])
    delta = end - start
    if delta >= 2:
        return "改善"
    if delta <= -2:
        return "走弱"
    return "平稳"

def _equity_denom(d: Dict[str, object]) -> Optional[float]:
    eq = safe_float(d.get("equity_total"))
    if eq is not None and eq > 0:
        return eq
    eqb = safe_float(d.get("equity_net_bs"))
    if eqb is not None and eqb > 0:
        return eqb
    return None

def _parse_cninfo_share_count(val) -> Optional[float]:
    """
    巨潮股本变动接口的数值列通常以“万股”为单位；带单位字符串则按单位解析。
    """
    if val is None or pd.isna(val):
        return None
    raw = str(val).strip()
    if "亿" in raw or "万" in raw or "股" in raw:
        return _parse_share_count(raw)
    num = safe_float(raw.replace(",", ""))
    return num * 1e4 if num is not None else None

def _parse_restricted_release_share_count(val) -> Optional[float]:
    """
    东方财富解禁队列的“解禁数量/实际解禁数量”数值列已经是股，不是万股。
    带中文单位的字符串仍按单位解析。
    """
    if val is None or pd.isna(val):
        return None
    raw = str(val).strip()
    if "亿" in raw or "万" in raw or "股" in raw:
        return _parse_share_count(raw)
    return safe_float(raw.replace(",", ""))



# --- Moved from render.py to break circular dependency ---
import html

def tone_class(tone: str) -> str:
    return {"good": "good", "warn": "warn", "bad": "bad", "muted": "muted"}.get(tone, "muted")

def wrap_value(text: str, tone: str) -> str:
    return f'<span class="value-chip {tone_class(tone)}">{html.escape(text)}</span>'
