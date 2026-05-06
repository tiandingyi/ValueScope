#!/usr/bin/env python3
"""
港股/美股提价权分析报告生成器

HTML 渲染、指标解释、估值模块全部复用 core 子包；
本脚本只替换数据获取接口与字段映射。

数据源：
  - 港股财报：AkShare 东方财富港股年报接口
  - 美股财报：AkShare 东方财富美股年报接口
  - 港股行情：腾讯/新浪行情兜底
  - 美股行情：Nasdaq/Yahoo/Stooq/东财兜底

用法（通过 run.py）：
  python3 run.py 00700.HK --years 8
  python3 run.py 3968 --years 8
  python3 run.py AAPL --years 8
  python3 run.py COST.US --years 8
"""

from __future__ import annotations

import re
import statistics
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import akshare as ak
import pandas as pd
import requests

from valuescope.legacy_stock_scripts.core.cache import disk_cache
from valuescope.legacy_stock_scripts.core.config import _dp
from valuescope.legacy_stock_scripts.core.data_a import build_year_data_for_valuation


DEFAULT_OUTPUT_DIR = Path("reports_hk_us_pricing_power")
MARKET: Optional[str] = None
XIAOMI_CAPEX_RELEASE_URL = "https://financialreports.eu/filings/xiaomi-corporation/earnings-release/2026/33021649/"
XIAOMI_2024_ANNUAL_URL = "https://financialreports.eu/filings/xiaomi-corporation/annual-report/2025/29532158/"
JD_2025_RESULTS_URL = "https://ir.jd.com/news-releases/news-release-details/jdcom-announces-fourth-quarter-and-full-year-2025-results-and"
HK_MARKET_PE_SAMPLE = (
    "00700",
    "09988",
    "03690",
    "01810",
    "01211",
    "00981",
    "09999",
    "01024",
    "09618",
    "09888",
    "00005",
    "01299",
    "02318",
    "03988",
    "00388",
    "00001",
    "00016",
    "00027",
    "02020",
    "02313",
)
US_MARKET_PE_SAMPLE = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "JPM",
    "V",
    "UNH",
    "MA",
    "HD",
    "COST",
    "NFLX",
    "AMD",
    "CRM",
    "ORCL",
    "ADBE",
    "KO",
)
SEC_HEADERS = {
    "User-Agent": "stock-scripts financial report research contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}
SEC_TICKERS_HEADERS = {
    "User-Agent": SEC_HEADERS["User-Agent"],
    "Accept-Encoding": "gzip, deflate",
}


def _to_date_key(x) -> Optional[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    try:
        return pd.to_datetime(x).strftime("%Y%m%d")
    except Exception:
        return None


def _to_date_str(x) -> Optional[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    try:
        return pd.to_datetime(x).strftime("%Y-%m-%d")
    except Exception:
        return None


def _normalize_hk_code(raw: str) -> str:
    s = str(raw).strip().upper()
    if s.endswith(".HK"):
        s = s[:-3]
    if s.isdigit() and 1 <= len(s) <= 5:
        return s.zfill(5)
    raise ValueError(f"无法识别港股 ticker：{raw}（期望形如 3968.HK 或 3968）")


def _norm_us(raw: str) -> str:
    s = str(raw).strip().upper()
    if s.endswith(".US"):
        s = s[:-3]
    if not s.isalpha() or not (1 <= len(s) <= 5):
        raise ValueError(f"无法识别美股 ticker：{raw}（期望如 COST、AAPL.US）")
    return s


def _pivot_long_to_wide(
    df_long: pd.DataFrame,
    *,
    report_date_col: str,
    item_col: str,
    value_col: str,
) -> pd.DataFrame:
    if df_long is None or df_long.empty:
        return pd.DataFrame()
    d = df_long.copy()
    d["__date_key"] = d[report_date_col].map(_to_date_key)
    d = d.dropna(subset=["__date_key"])
    wide = d.pivot_table(index="__date_key", columns=item_col, values=value_col, aggfunc="first")
    wide.index = wide.index.map(str)
    return wide.sort_index()


def _fetch_us_indicator_fallback(sym: str) -> pd.DataFrame:
    """Fetch bank/insurance indicator from Eastmoney when the general indicator table is empty."""
    _EM_API = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    secucode_candidates = [f"{sym}.N", f"{sym}.O", f"{sym}.A"]
    for tbl in ("RPT_USF10_FN_BMAININDICATOR", "RPT_USF10_FN_IMAININDICATOR"):
        for sc in secucode_candidates:
            try:
                params = {
                    "reportName": tbl,
                    "columns": "ALL",
                    "pageNumber": "1",
                    "pageSize": "50",
                    "sortTypes": "-1",
                    "sortColumns": "REPORT_DATE",
                    "source": "SECURITIES",
                    "client": "PC",
                    "filter": f'(SECUCODE="{sc}")(DATE_TYPE_CODE="001")',
                }
                r = requests.get(_EM_API, params=params, timeout=15)
                j = r.json()
                data = (j.get("result") or {}).get("data") or []
                if not data:
                    continue
                df = pd.DataFrame(data)
                col_map = {
                    "TOTAL_INCOME": "OPERATE_INCOME",
                    "BASIC_EPS_CS": "BASIC_EPS",
                    "DILUTED_EPS_CS": "DILUTED_EPS",
                    "ROE": "ROE_AVG",
                }
                if "DEBT_RATIO" in df.columns:
                    col_map["DEBT_RATIO"] = "DEBT_ASSET_RATIO"
                df = df.rename(columns=col_map)
                if "NET_PROFIT_RATIO" not in df.columns:
                    try:
                        rev = pd.to_numeric(df["OPERATE_INCOME"], errors="coerce")
                        np_ = pd.to_numeric(df["PARENT_HOLDER_NETPROFIT"], errors="coerce")
                        df["NET_PROFIT_RATIO"] = (np_ / rev * 100).where(rev.abs() > 0)
                    except Exception:
                        pass
                return df
            except Exception:
                continue
    return pd.DataFrame()


def _fetch_us_financials(stock: str) -> Dict[str, pd.DataFrame]:
    sym = _norm_us(stock)
    try:
        ind_df = ak.stock_financial_us_analysis_indicator_em(symbol=sym, indicator="年报")
    except Exception:
        ind_df = None
    if ind_df is None or (hasattr(ind_df, "empty") and ind_df.empty):
        ind_df = _fetch_us_indicator_fallback(sym)
    bal_long = ak.stock_financial_us_report_em(stock=sym, symbol="资产负债表", indicator="年报")
    inc_long = ak.stock_financial_us_report_em(stock=sym, symbol="综合损益表", indicator="年报")
    cf_long = ak.stock_financial_us_report_em(stock=sym, symbol="现金流量表", indicator="年报")
    return {
        "ind_long": ind_df,
        "bal_wide": _pivot_long_to_wide(bal_long, report_date_col="REPORT_DATE", item_col="ITEM_NAME", value_col="AMOUNT"),
        "inc_wide": _pivot_long_to_wide(inc_long, report_date_col="REPORT_DATE", item_col="ITEM_NAME", value_col="AMOUNT"),
        "cf_wide": _pivot_long_to_wide(cf_long, report_date_col="REPORT_DATE", item_col="ITEM_NAME", value_col="AMOUNT"),
    }


def _get_hk_company_name(code_5digits: str) -> str:
    try:
        ind = ak.stock_financial_hk_analysis_indicator_em(symbol=code_5digits, indicator="年度")
        if ind is not None and not ind.empty and "SECURITY_NAME_ABBR" in ind.columns:
            v = ind["SECURITY_NAME_ABBR"].dropna()
            if not v.empty:
                return str(v.iloc[0]).strip()
    except Exception:
        pass
    return code_5digits


def _hk_latest_implied_shares(code_5digits: str) -> Optional[float]:
    try:
        ind = ak.stock_financial_hk_analysis_indicator_em(symbol=code_5digits, indicator="年度")
        if ind is None or ind.empty:
            return None
        ind = ind.copy()
        ind["__date_key"] = ind["REPORT_DATE"].map(_to_date_key)
        ind = ind.dropna(subset=["__date_key"]).sort_values("__date_key", ascending=False)
        for _, row in ind.iterrows():
            profit, eps = row.get("HOLDER_PROFIT"), row.get("BASIC_EPS")
            if profit is None or eps is None or pd.isna(profit) or pd.isna(eps):
                continue
            eps_f = float(eps)
            if abs(eps_f) < 1e-12:
                continue
            return float(profit) / eps_f
    except Exception:
        pass
    return None


def get_company_info_us(code: str) -> Tuple[str, Optional[float], str]:
    sym = _norm_us(code)
    try:
        try:
            ind = ak.stock_financial_us_analysis_indicator_em(symbol=sym, indicator="年报")
        except Exception:
            ind = None
        if ind is None or ind.empty:
            ind = _fetch_us_indicator_fallback(sym)
        if ind is None or ind.empty:
            return sym, None, ""
        name = sym
        if "SECURITY_NAME_ABBR" in ind.columns:
            v = ind["SECURITY_NAME_ABBR"].dropna()
            if not v.empty:
                name = str(v.iloc[0]).strip()
        ind2 = ind.sort_values("REPORT_DATE", ascending=False)
        for _, row in ind2.iterrows():
            p, e = row.get("PARENT_HOLDER_NETPROFIT"), row.get("BASIC_EPS")
            if p is None or e is None or pd.isna(p) or pd.isna(e):
                continue
            ef = float(e)
            if abs(ef) < 1e-12:
                continue
            return name, float(p) / ef, ""
        return name, None, ""
    except Exception:
        return sym, None, ""


def get_current_price_hk(code: str):
    prefix_code = str(code).zfill(5)
    candidates = [prefix_code]
    if prefix_code.startswith("0"):
        candidates.append(prefix_code.lstrip("0"))
    for cc in candidates:
        try:
            r = requests.get(f"https://qt.gtimg.cn/q=hk{cc}", timeout=8, headers={"Referer": "https://gu.qq.com"})
            parts = r.text.split('"')[1].split("~")
            if len(parts) > 3 and parts[3]:
                t_str = None
                if len(parts) > 30 and parts[30]:
                    ts = str(parts[30]).strip()
                    if "/" in ts and " " in ts:
                        d, tm = ts.split(" ", 1)
                        t_str = f"{d.replace('/', '-')} {tm[:5]}"
                return float(parts[3]), "腾讯行情", t_str
        except Exception:
            continue
    for cc in candidates:
        try:
            r = requests.get(f"https://hq.sinajs.cn/list=hk{cc}", timeout=8, headers={"Referer": "https://finance.sina.com.cn"})
            if '"' not in r.text:
                continue
            parts = r.text.split('"')[1].split(",")
            if len(parts) > 3 and parts[3]:
                return float(parts[3]), "新浪行情", None
        except Exception:
            continue
    # ── 最终兜底：从历史日线缓存中读取最近收盘价 ──
    try:
        hist_df = _fetch_hk_daily_hist_tencent(str(code).zfill(5), years_back=1)
        if hist_df is not None and not hist_df.empty and "收盘" in hist_df.columns:
            last = hist_df.iloc[-1]
            return float(last["收盘"]), "历史收盘（兜底）", str(last.get("日期", ""))[:10]
    except Exception:
        pass
    return None, None, None


def _nasdaq_us_last_price(sym: str) -> Tuple[Optional[float], Optional[str]]:
    try:
        r = requests.get(
            f"https://api.nasdaq.com/api/quote/{sym.upper()}/info?assetclass=stocks",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=14,
        )
        pd_ = (r.json().get("data") or {}).get("primaryData") or {}
        raw = pd_.get("lastSalePrice")
        if raw is None:
            return None, None
        px = float(str(raw).replace("$", "").replace(",", "").strip())
        return (px if px > 0 else None), (str(pd_.get("lastTradeTimestamp")).strip() if pd_.get("lastTradeTimestamp") else None)
    except Exception:
        return None, None


def _yahoo_us_last_price(sym: str) -> Tuple[Optional[float], Optional[str]]:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.upper()}",
            params={"interval": "1d", "range": "5d"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
            timeout=14,
        )
        if r.status_code != 200:
            return None, None
        results = (r.json().get("chart") or {}).get("result") or []
        if not results:
            return None, None
        blk = results[0]
        meta = blk.get("meta") or {}
        px = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        if px is None:
            q = (blk.get("indicators") or {}).get("quote") or []
            closes = q[0].get("close") if q else []
            for v in reversed(closes or []):
                if v is not None and float(v) > 0:
                    px = float(v)
                    break
        if px is None or float(px) <= 0:
            return None, None
        return float(px), None
    except Exception:
        return None, None


def _stooq_us_last_price(sym: str) -> Tuple[Optional[float], Optional[str]]:
    try:
        r = requests.get(f"https://stooq.com/q/l/?s={sym.lower()}.us&i=d", headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        text = r.text.strip()
        if not text or "Get your apikey" in text or "Write to www@stooq" in text:
            return None, None
        parts = [p.strip() for p in text.splitlines()[-1].split(",")]
        if len(parts) < 7:
            return None, None
        close = float(parts[6])
        return (close if close > 0 else None), parts[1]
    except Exception:
        return None, None


def get_current_price_us(code: str):
    import os
    import time

    sym = _norm_us(code)
    for fn, label in ((_nasdaq_us_last_price, "Nasdaq行情"), (_yahoo_us_last_price, "Yahoo行情"), (_stooq_us_last_price, "Stooq")):
        px, ts = fn(sym)
        if px is not None:
            return px, label, ts
    poly_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if poly_key:
        try:
            r = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev", params={"adjusted": "true", "apiKey": poly_key}, timeout=12)
            results = r.json().get("results") or []
            if results and float(results[0].get("c", 0)) > 0:
                return float(results[0]["c"]), "Polygon上一日收盘", None
        except Exception:
            pass
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=400)
    for prefix in ("105", "106", "107", "108", "104", "103", "109"):
        try:
            df = ak.stock_us_hist(symbol=f"{prefix}.{sym}", period="daily", start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), adjust="")
            if df is not None and not df.empty and "收盘" in df.columns:
                last = df.iloc[-1]
                return float(last["收盘"]), "东财美股", str(last["日期"])[:10]
        except Exception:
            time.sleep(0.12)
    # ── 最终兜底：调用完整历史日线（含 curl_cffi / Sina 通道），有7天磁盘缓存 ──
    try:
        hist_df = _fetch_us_daily_hist_em_adj_cached(sym, 1)
        if hist_df is not None and not hist_df.empty and "收盘" in hist_df.columns:
            last = hist_df.iloc[-1]
            return float(last["收盘"]), "历史收盘（兜底）", str(last.get("日期", ""))[:10]
    except Exception:
        pass
    return None, None, None


def _build_abs_df_hk(symbol_5digits: str) -> pd.DataFrame:
    ind = ak.stock_financial_hk_analysis_indicator_em(symbol=symbol_5digits, indicator="年度")
    if ind is None or ind.empty:
        return pd.DataFrame()
    cf_long = ak.stock_financial_hk_report_em(stock=symbol_5digits, symbol="现金流量表", indicator="年度")
    bs_long = ak.stock_financial_hk_report_em(stock=symbol_5digits, symbol="资产负债表", indicator="年度")
    cf_wide = _pivot_long_to_wide(cf_long, report_date_col="REPORT_DATE", item_col="STD_ITEM_NAME", value_col="AMOUNT")
    bs_wide = _pivot_long_to_wide(bs_long, report_date_col="REPORT_DATE", item_col="STD_ITEM_NAME", value_col="AMOUNT")

    ind = ind.copy()
    ind["__date_key"] = ind["REPORT_DATE"].map(_to_date_key)
    ind = ind.dropna(subset=["__date_key"])
    date_keys = sorted(ind["__date_key"].unique().tolist())

    def ind_values(col: str) -> List[Optional[float]]:
        if col not in ind.columns:
            return [None] * len(date_keys)
        s = ind.set_index("__date_key")[col]
        return [(v if pd.notna(v) else None) for v in s.reindex(date_keys).tolist()]

    ocf_col = _first_existing_col(cf_wide, ("经营活动产生的现金流量净额", "经营业务现金净额", "经营活动现金流量净额", "经营产生现金净额"))
    ocf_vals = [(v if pd.notna(v) else None) for v in cf_wide[ocf_col].reindex(date_keys).tolist()] if ocf_col and not cf_wide.empty else [None] * len(date_keys)
    eq_col = _first_existing_col(bs_wide, ("股东权益", "净资产", "总权益"))
    eq_vals = [(v if pd.notna(v) else None) for v in bs_wide[eq_col].reindex(date_keys).tolist()] if eq_col and not bs_wide.empty else [None] * len(date_keys)

    holders_profit = ind_values("HOLDER_PROFIT")
    basic_eps = ind_values("BASIC_EPS")
    bps = ind_values("BPS")
    for i in range(len(date_keys)):
        if eq_vals[i] is not None:
            continue
        p, e, b = holders_profit[i], basic_eps[i], bps[i]
        try:
            if p is not None and e is not None and b is not None and abs(float(e)) >= 1e-12:
                eq_vals[i] = float(p) / float(e) * float(b)
        except Exception:
            pass

    metrics = [
        ("营业总收入", ind_values("OPERATE_INCOME")),
        ("归母净利润", holders_profit),
        ("经营现金流量净额", ocf_vals),
        ("股东权益合计(净资产)", eq_vals),
        ("基本每股收益", basic_eps),
        ("稀释每股收益", ind_values("DILUTED_EPS")),
        ("每股净资产", bps),
        ("净资产收益率(ROE)", ind_values("ROE_AVG")),
        ("总资产报酬率(ROA)", ind_values("ROA")),
        ("毛利率", ind_values("GROSS_PROFIT_RATIO")),
        ("销售净利率", ind_values("NET_PROFIT_RATIO")),
        ("资产负债率", ind_values("DEBT_ASSET_RATIO")),
    ]
    rows = [{"指标": name, **{k: vals[i] for i, k in enumerate(date_keys)}} for name, vals in metrics if vals and not all(v is None for v in vals)]
    return pd.DataFrame(rows)[["指标"] + date_keys] if rows else pd.DataFrame()


def _build_abs_df_us(symbol: str) -> pd.DataFrame:
    data = _fetch_us_financials(symbol)
    ind = data["ind_long"]
    if ind is None or ind.empty:
        return pd.DataFrame()
    cf_wide, bal_wide = data["cf_wide"], data["bal_wide"]
    ind = ind.copy()
    ind["__date_key"] = ind["REPORT_DATE"].map(_to_date_key)
    ind = ind.dropna(subset=["__date_key"])
    date_keys = sorted(ind["__date_key"].unique().tolist())

    def ind_values(col: str) -> List[Optional[float]]:
        if col not in ind.columns:
            return [None] * len(date_keys)
        s = ind.set_index("__date_key")[col]
        return [(v if pd.notna(v) else None) for v in s.reindex(date_keys).tolist()]

    ocf_col = _first_existing_col(cf_wide, ("经营活动产生的现金流量净额",))
    ocf_vals = [float(v) if pd.notna(v) else None for v in cf_wide[ocf_col].reindex(date_keys).tolist()] if ocf_col and not cf_wide.empty else [None] * len(date_keys)
    eq_col = _first_existing_col(bal_wide, ("股东权益合计", "归属于母公司股东权益", "净资产"))
    eq_vals = [float(v) if pd.notna(v) else None for v in bal_wide[eq_col].reindex(date_keys).tolist()] if eq_col and not bal_wide.empty else [None] * len(date_keys)

    holders_profit = ind_values("PARENT_HOLDER_NETPROFIT")
    basic_eps = ind_values("BASIC_EPS")
    bps = ind_values("BPS")
    for i in range(len(date_keys)):
        if eq_vals[i] is not None:
            continue
        p, e, b = holders_profit[i], basic_eps[i], bps[i]
        try:
            if p is not None and e is not None and b is not None and abs(float(e)) >= 1e-12:
                eq_vals[i] = float(p) / float(e) * float(b)
        except Exception:
            pass

    bps_out: List[Optional[float]] = list(bps)
    for i in range(len(date_keys)):
        if bps_out[i] is not None or eq_vals[i] is None or holders_profit[i] is None or basic_eps[i] is None:
            continue
        try:
            p, e = float(holders_profit[i]), float(basic_eps[i])
            if abs(e) >= 1e-12 and abs(p) >= 1e-9 and p / e > 0:
                bps_out[i] = float(eq_vals[i]) / (p / e)
        except Exception:
            pass

    metrics = [
        ("营业总收入", ind_values("OPERATE_INCOME")),
        ("归母净利润", holders_profit),
        ("经营现金流量净额", ocf_vals),
        ("股东权益合计(净资产)", eq_vals),
        ("基本每股收益", basic_eps),
        ("稀释每股收益", ind_values("DILUTED_EPS")),
        ("每股净资产", bps_out),
        ("净资产收益率(ROE)", ind_values("ROE_AVG")),
        ("总资产报酬率(ROA)", ind_values("ROA")),
        ("总资产周转率", ind_values("TOTAL_ASSETS_TR")),
        ("毛利率", ind_values("GROSS_PROFIT_RATIO")),
        ("销售净利率", ind_values("NET_PROFIT_RATIO")),
        ("资产负债率", ind_values("DEBT_ASSET_RATIO")),
    ]
    rows = [{"指标": name, **{k: vals[i] for i, k in enumerate(date_keys)}} for name, vals in metrics if vals and not all(v is None for v in vals)]
    return pd.DataFrame(rows)[["指标"] + date_keys] if rows else pd.DataFrame()


def normalize_ticker(raw: str) -> Tuple[str, str]:
    s = str(raw).strip()
    if not s:
        raise ValueError("ticker 不能为空")
    up = s.upper()
    if up.endswith(".HK"):
        return "hk", _normalize_hk_code(up)
    if up.endswith(".US"):
        return "us", _norm_us(up)
    if s.isdigit() and 1 <= len(s) <= 5:
        return "hk", _normalize_hk_code(s)
    return "us", _norm_us(up)


def annual_cols_any_date(abs_df: pd.DataFrame) -> List[str]:
    if abs_df is None or abs_df.empty:
        return []
    out = []
    for col in abs_df.columns:
        s = str(col)
        if s == "指标":
            continue
        if len(s) == 8 and s.isdigit():
            out.append(s)
    return sorted(out)


def _safe_float(x) -> Optional[float]:
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _first_existing_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _pick_col(wide: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    return _first_existing_col(wide, candidates)


def _num_at(wide: pd.DataFrame, date_key: str, col: Optional[str]) -> Optional[float]:
    if col is None or wide is None or wide.empty or date_key not in wide.index or col not in wide.columns:
        return None
    return _safe_float(wide.at[date_key, col])


def _sum_abs_at(wide: pd.DataFrame, date_key: str, cols: Sequence[str]) -> float:
    total = 0.0
    for col in cols:
        v = _num_at(wide, date_key, col)
        if v is not None:
            total += abs(v)
    return total


def _sum_abs_at_optional(wide: pd.DataFrame, date_key: str, cols: Sequence[str]) -> Optional[float]:
    vals = []
    for col in cols:
        v = _num_at(wide, date_key, col)
        if v is not None:
            vals.append(abs(v))
    if not vals:
        return None
    return sum(vals)


def _fetch_xiaomi_capex_fallback() -> Dict[str, float]:
    out: Dict[str, float] = {}
    try:
        r = requests.get(XIAOMI_CAPEX_RELEASE_URL, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        idx = r.text.lower().find("capital expenditures")
        if idx >= 0:
            tables = pd.read_html(StringIO(r.text[idx : idx + 8000]))
            if tables:
                table = tables[0]
                first_col = table.columns[0]
                total_rows = table[table[first_col].astype(str).str.fullmatch("Total", case=False, na=False)]
                if not total_rows.empty:
                    nums = [v for v in pd.to_numeric(total_rows.iloc[0], errors="coerce").dropna().tolist()]
                    if len(nums) >= 4:
                        out["20251231"] = float(nums[-2]) * 1e6
                        out["20241231"] = float(nums[-1]) * 1e6
    except Exception:
        pass

    if "20241231" not in out:
        try:
            r = requests.get(XIAOMI_2024_ANNUAL_URL, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r"\s+", " ", r.text)
            m = re.search(r"capital expenditures of RMB([0-9.]+) billion", text, flags=re.I)
            if m:
                out["20241231"] = float(m.group(1)) * 1e9
        except Exception:
            pass
    return out


def _fetch_jd_capex_fallback() -> Dict[str, float]:
    out: Dict[str, float] = {}
    try:
        r = requests.get(JD_2025_RESULTS_URL, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r"\s+", " ", r.text)
        m = re.search(
            r"Capital expenditures were RMB\s*([0-9.,]+)\s*million.*?for the year of 2025.*?"
            r"RMB\s*([0-9.,]+)\s*million.*?for the year of 2024",
            text,
            flags=re.I,
        )
        if m:
            out["20251231"] = float(m.group(1).replace(",", "")) * 1e6
            out["20241231"] = float(m.group(2).replace(",", "")) * 1e6
    except Exception:
        pass
    out.setdefault("20251231", 12_735_000_000.0)
    out.setdefault("20241231", 14_223_000_000.0)
    return out


def _capex_fallback_for_hk_company(code: str) -> Dict[str, float]:
    normalized = str(code).zfill(5)
    if normalized == "01810":
        return _fetch_xiaomi_capex_fallback()
    if normalized == "09618":
        return _fetch_jd_capex_fallback()
    if normalized == "03690":
        return {
            "20241231": 10_999_490_000.0,
            "20250630": 5_554_202_000.0,
        }
    return {}


def _da_fallback_for_hk_company(code: str) -> Dict[str, float]:
    normalized = str(code).zfill(5)
    if normalized == "03690":
        return {
            "20251231": (9_936_631 + 262_408) * 1_000.0,
            "20241231": (8_181_701 + 239_649) * 1_000.0,
            "20250630": (4_536_656 + 29_768) * 1_000.0,
        }
    if normalized == "01024":
        return {
            "20251231": (3_903 + 3_215 + 77) * 1_000_000.0,
            "20241231": (4_064 + 2_972 + 104) * 1_000_000.0,
        }
    return {}


def _single_asset_at(wide: pd.DataFrame, date_key: str, candidates: Sequence[str]) -> Optional[float]:
    col = _pick_col(wide, candidates)
    v = _num_at(wide, date_key, col)
    return abs(v) if v is not None else None


def _asset_base_at(wide: pd.DataFrame, date_key: str) -> Optional[float]:
    ppe = _single_asset_at(
        wide,
        date_key,
        (
            "物业厂房及设备",
            "固定资产",
            "物业、厂房及设备",
            "物业、厂房及设备净额",
            "不动产、厂场和设备",
        ),
    )
    intangible = _single_asset_at(wide, date_key, ("无形资产", "无形资产净额"))
    vals = [v for v in (ppe, intangible) if v is not None]
    if not vals:
        return None
    return sum(vals)


def _estimate_capex_from_balance(bs_wide: Optional[pd.DataFrame], date_key: str, da: Optional[float]) -> Optional[float]:
    if bs_wide is None or bs_wide.empty or da is None or da <= 0:
        return None
    dates = sorted(str(d) for d in bs_wide.index.map(str).tolist())
    if date_key not in dates:
        return None
    idx = dates.index(date_key)
    if idx == 0:
        return None
    prev_date = dates[idx - 1]
    current_assets = _asset_base_at(bs_wide, date_key)
    previous_assets = _asset_base_at(bs_wide, prev_date)
    if current_assets is None or previous_assets is None:
        return None
    estimated = current_assets - previous_assets + abs(da)
    # 现金流接口缺购建资产明细时，用资产原值/账面值变动 + 折旧摊销做保守兜底。
    return estimated if estimated > 0 else None


def _estimate_da_from_balance(
    bs_wide: Optional[pd.DataFrame],
    cf_wide: Optional[pd.DataFrame],
    date_key: str,
    da_col: Optional[str],
    lookback: int = 4,
) -> Optional[float]:
    if bs_wide is None or bs_wide.empty or cf_wide is None or cf_wide.empty or da_col is None:
        return None
    dates = sorted(str(d) for d in bs_wide.index.map(str).tolist())
    if date_key not in dates:
        return None
    idx = dates.index(date_key)
    if idx <= 0:
        return None

    ratio_samples = []
    last_da = None
    prev_dates = list(reversed(dates[:idx]))
    for prev_date in prev_dates:
        da_v = _num_at(cf_wide, prev_date, da_col)
        asset_base = _asset_base_at(bs_wide, prev_date)
        if da_v is None or da_v <= 0 or asset_base is None or asset_base <= 0:
            continue
        ratio_samples.append(abs(da_v) / asset_base)
        if last_da is None:
            last_da = abs(da_v)
        if len(ratio_samples) >= lookback:
            break
    if not ratio_samples:
        return None

    current_assets = _asset_base_at(bs_wide, date_key)
    previous_assets = _asset_base_at(bs_wide, dates[idx - 1])
    if current_assets is None or current_assets <= 0:
        return None

    asset_anchor = current_assets
    if previous_assets is not None and previous_assets > 0:
        asset_anchor = (current_assets + previous_assets) / 2

    estimated = asset_anchor * statistics.median(ratio_samples)
    if last_da is not None:
        estimated = max(estimated, last_da * 0.85)
    return estimated if estimated > 0 else None


def _wide_to_report_df(wide: pd.DataFrame, aliases: Dict[str, Sequence[str]]) -> pd.DataFrame:
    if wide is None or wide.empty:
        return pd.DataFrame(columns=["报告日"])
    out = wide.copy()
    out.index = out.index.map(str)
    for target, candidates in aliases.items():
        if target in out.columns:
            continue
        src = _first_existing_col(out, candidates)
        if src is not None:
            out[target] = out[src]
    out = out.reset_index().rename(columns={"index": "报告日", "__date_key": "报告日"})
    if "报告日" not in out.columns:
        out = out.rename(columns={out.columns[0]: "报告日"})
    out["报告日"] = out["报告日"].astype(str)
    return out.sort_values("报告日").reset_index(drop=True)


def _derive_income_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in ("营业总收入", "营业收入", "营业成本", "销售费用", "管理费用", "研发费用", "营业费用"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "营业总收入" not in out.columns and "营业收入" in out.columns:
        out["营业总收入"] = out["营业收入"]
    if "营业收入" not in out.columns and "营业总收入" in out.columns:
        out["营业收入"] = out["营业总收入"]

    if "管理费用" not in out.columns and "营业费用" in out.columns:
        if "销售费用" in out.columns or "研发费用" in out.columns:
            selling = out["销售费用"] if "销售费用" in out.columns else 0.0
            rnd = out["研发费用"] if "研发费用" in out.columns else 0.0
            derived = out["营业费用"] - selling - rnd
            out["管理费用"] = derived.where(derived.abs() > 1e-6, 0.0)
        elif "销售费用" not in out.columns:
            out["管理费用"] = out["营业费用"]
    return out


def _normalize_hk_company_income(code: str, income_df: pd.DataFrame) -> pd.DataFrame:
    if income_df is None or income_df.empty:
        return income_df
    out = income_df.copy()
    normalized = str(code).zfill(5)
    if normalized == "09888" and "管理费用" not in out.columns and "销售费用" in out.columns:
        # 百度港股口径把 selling/general/admin 合并放在“销售及分销费用”。
        # 放在销售费用侧、管理费用置 0，避免业务纯度双重扣减同一笔 SG&A。
        out["管理费用"] = 0.0
    return out


def _add_asset_turnover_to_abs(abs_df: pd.DataFrame, income_df: pd.DataFrame, balance_df: pd.DataFrame) -> pd.DataFrame:
    if abs_df is None or abs_df.empty or income_df is None or income_df.empty or balance_df is None or balance_df.empty:
        return abs_df
    if not abs_df[abs_df["指标"] == "总资产周转率"].empty:
        return abs_df
    rev_col = _first_existing_col(income_df, ("营业总收入", "营业收入"))
    asset_col = _first_existing_col(balance_df, ("总资产", "资产总计", "资产合计"))
    if rev_col is None or asset_col is None:
        return abs_df
    inc_map = {str(r["报告日"]): r for _, r in income_df.iterrows()}
    bs_map = {str(r["报告日"]): r for _, r in balance_df.iterrows()}
    cols = annual_cols_any_date(abs_df)
    vals: Dict[str, Optional[float]] = {}
    prev_assets = None
    for col in cols:
        inc_r = inc_map.get(col)
        bs_r = bs_map.get(col)
        rev = _safe_float(inc_r[rev_col]) if inc_r is not None and rev_col in inc_r else None
        assets = _safe_float(bs_r[asset_col]) if bs_r is not None and asset_col in bs_r else None
        at = None
        if rev is not None and assets is not None and assets > 0:
            avg_assets = (prev_assets + assets) / 2 if prev_assets is not None else assets
            at = rev / avg_assets if avg_assets > 0 else None
        vals[col] = at
        if assets is not None:
            prev_assets = assets
    return pd.concat([abs_df, pd.DataFrame([{"指标": "总资产周转率", **vals}])], ignore_index=True)


def _fetch_hk_wides(code: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    inc_long = ak.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
    bs_long = ak.stock_financial_hk_report_em(stock=code, symbol="资产负债表", indicator="年度")
    cf_long = ak.stock_financial_hk_report_em(stock=code, symbol="现金流量表", indicator="年度")
    inc = _pivot_long_to_wide(inc_long, report_date_col="REPORT_DATE", item_col="STD_ITEM_NAME", value_col="AMOUNT")
    bs = _pivot_long_to_wide(bs_long, report_date_col="REPORT_DATE", item_col="STD_ITEM_NAME", value_col="AMOUNT")
    cf = _pivot_long_to_wide(cf_long, report_date_col="REPORT_DATE", item_col="STD_ITEM_NAME", value_col="AMOUNT")
    return inc, bs, cf


def fetch_cashflow_extras_hk_us(
    code: str,
    cf_wide: Optional[pd.DataFrame] = None,
    inc_wide: Optional[pd.DataFrame] = None,
    bs_wide: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    empty = pd.DataFrame(
        columns=[
            "报告日",
            "ocf",
            "capex",
            "dividends_paid",
            "div_reliable",
            "da",
            "buyback_cash",
            "equity_inflow_cash",
            "buyback_col",
            "equity_inflow_col",
            "taxes_paid_cash",
        ]
    )
    try:
        if cf_wide is None:
            if MARKET == "hk":
                _, _, cf_wide = _fetch_hk_wides(code)
            else:
                cf_wide = _fetch_us_financials(_norm_us(code)).get("cf_wide", pd.DataFrame())
    except Exception:
        return empty
    if cf_wide is None or cf_wide.empty:
        return empty

    if MARKET == "hk":
        ocf_candidates = ("经营活动产生的现金流量净额", "经营业务现金净额", "经营活动现金流量净额", "经营产生现金净额")
        capex_candidates = ("购建固定资产", "购建无形资产及其他资产", "购买固定资产", "购买物业厂房及设备")
        da_candidates = ("加:折旧及摊销", "折旧及摊销", "折旧与摊销")
        div_candidates = ("已付股息(融资)", "股息支付", "已付股息")
        tax_candidates = ("已付税项", "支付所得税", "已付所得税")
        buyback_candidates = ("回购股份",)
        equity_candidates = ("发行股份", "吸收投资所得")
    else:
        ocf_candidates = ("经营活动产生的现金流量净额", "经营活动现金净额", "经营活动产生的净现金")
        capex_candidates = ("购买固定资产", "购建无形资产及其他资产", "资本性支出", "购建固定资产")
        da_candidates = ("折旧及摊销", "折旧与摊销")
        div_candidates = ("股息支付", "已付股息(融资)", "现金股利支付")
        tax_candidates = tuple(
            c
            for c in cf_wide.columns
            if "所得税" in str(c) and any(k in str(c) for k in ("支付", "付", "缴", "现金", "已"))
        )
        buyback_candidates = ("回购股份",)
        equity_candidates = ("发行股份", "行使股票期权所得")

    ocf_col = _pick_col(cf_wide, ocf_candidates)
    capex_cols = [c for c in capex_candidates if c in cf_wide.columns]
    da_col = _pick_col(cf_wide, da_candidates)
    div_col = _pick_col(cf_wide, div_candidates)
    buyback_col = _pick_col(cf_wide, buyback_candidates)
    equity_col = _pick_col(cf_wide, equity_candidates)
    tax_cols = [c for c in tax_candidates if c in cf_wide.columns]

    rows = []
    capex_fallback = _capex_fallback_for_hk_company(code) if MARKET == "hk" else {}
    da_fallback = _da_fallback_for_hk_company(code) if MARKET == "hk" else {}
    for d in cf_wide.index.map(str).tolist():
        taxes_paid = _sum_abs_at(cf_wide, d, tax_cols)
        if taxes_paid == 0.0 and MARKET == "us":
            if inc_wide is None:
                try:
                    inc_wide = _fetch_us_financials(_norm_us(code)).get("inc_wide", pd.DataFrame())
                except Exception:
                    inc_wide = pd.DataFrame()
            tax_exp = _num_at(inc_wide, d, _pick_col(inc_wide, ("所得税", "税项")))
            taxes_paid = abs(tax_exp) if tax_exp is not None else 0.0
        div_v = _num_at(cf_wide, d, div_col)
        da = abs(_num_at(cf_wide, d, da_col) or 0.0)
        if da == 0.0:
            da = da_fallback.get(d, 0.0)
        if da == 0.0 and MARKET == "hk":
            estimated_da = _estimate_da_from_balance(bs_wide, cf_wide, d, da_col)
            if estimated_da is not None:
                da = estimated_da
        capex = _sum_abs_at_optional(cf_wide, d, capex_cols) or capex_fallback.get(d)
        if capex is None and MARKET == "hk":
            capex = _estimate_capex_from_balance(bs_wide, d, da)
        if capex is None and MARKET == "us":
            investing_cf = _num_at(cf_wide, d, _pick_col(cf_wide, ("投资活动产生的现金流量净额",)))
            if investing_cf is not None and investing_cf < 0:
                capex = abs(investing_cf)
        rows.append(
            {
                "报告日": d,
                "ocf": _num_at(cf_wide, d, ocf_col),
                "capex": capex,
                "dividends_paid": abs(div_v) if div_v is not None else 0.0,
                "div_reliable": div_v is not None,
                "da": da,
                "buyback_cash": abs(_num_at(cf_wide, d, buyback_col) or 0.0),
                "equity_inflow_cash": abs(_num_at(cf_wide, d, equity_col) or 0.0),
                "buyback_col": buyback_col or "",
                "equity_inflow_col": equity_col or "",
                "taxes_paid_cash": taxes_paid,
            }
        )
    return pd.DataFrame(rows)


def fetch_balance_sheet_extras_hk_us(code: str, bs_wide: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    empty = pd.DataFrame(
        columns=["报告日", "gross_cash", "interest_debt", "due_debt_principal", "net_cash", "goodwill", "equity_net_bs"]
    )
    try:
        if bs_wide is None:
            if MARKET == "hk":
                _, bs_wide, _ = _fetch_hk_wides(code)
            else:
                bs_wide = _fetch_us_financials(_norm_us(code)).get("bal_wide", pd.DataFrame())
    except Exception:
        return empty
    if bs_wide is None or bs_wide.empty:
        return empty

    if MARKET == "hk":
        cash_candidates = (
            "现金及等价物",
            "受限制存款及现金",
            "短期存款",
            "中长期存款",
            "短期投资",
            "交易性金融资产(流动)",
            "指定以公允价值记账之金融资产(流动)",
            "其他金融资产(流动)",
        )
        debt_candidates = (
            "短期贷款",
            "长期贷款",
            "应付债券",
            "应付票据(非流动)",
            "可转换票据及债券",
            "融资租赁负债(流动)",
            "融资租赁负债(非流动)",
        )
        due_candidates = ("短期贷款", "融资租赁负债(流动)")
        equity_candidates = ("股东权益", "净资产", "总权益")
    else:
        cash_candidates = (
            "现金及现金等价物",
            "短期投资",
            "有价证券投资(流动)",
            "有价证券投资(非流动)",
            "可供出售投资(流动)",
        )
        debt_candidates = (
            "短期债务",
            "长期负债",
            "长期负债(本期部分)",
            "资本租赁债务(非流动)",
            "应付票据(流动)",
        )
        due_candidates = ("短期债务", "长期负债(本期部分)", "应付票据(流动)")
        equity_candidates = ("股东权益合计", "归属于母公司股东权益", "净资产")

    cash_cols = [c for c in cash_candidates if c in bs_wide.columns]
    debt_cols = [c for c in debt_candidates if c in bs_wide.columns]
    due_cols = [c for c in due_candidates if c in bs_wide.columns]
    equity_col = _pick_col(bs_wide, equity_candidates)
    goodwill_col = _pick_col(bs_wide, ("商誉",))

    rows = []
    for d in bs_wide.index.map(str).tolist():
        gross_cash = _sum_abs_at(bs_wide, d, cash_cols)
        interest_debt = _sum_abs_at(bs_wide, d, debt_cols)
        due_debt = _sum_abs_at(bs_wide, d, due_cols)
        rows.append(
            {
                "报告日": d,
                "gross_cash": gross_cash,
                "interest_debt": interest_debt,
                "due_debt_principal": due_debt,
                "net_cash": gross_cash - interest_debt,
                "goodwill": abs(_num_at(bs_wide, d, goodwill_col) or 0.0),
                "equity_net_bs": _num_at(bs_wide, d, equity_col),
            }
        )
    return pd.DataFrame(rows)


def fetch_income_extras_hk_us(code: str, inc_wide: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["报告日", "operating_profit", "finance_cost", "pretax_profit", "tax_expense"])
    try:
        if inc_wide is None:
            if MARKET == "hk":
                inc_wide, _, _ = _fetch_hk_wides(code)
            else:
                inc_wide = _fetch_us_financials(_norm_us(code)).get("inc_wide", pd.DataFrame())
    except Exception:
        return empty
    if inc_wide is None or inc_wide.empty:
        return empty

    op_col = _pick_col(inc_wide, ("经营溢利", "营业利润", "经营利润"))
    finance_col = _pick_col(inc_wide, ("融资成本", "利息支出", "财务费用"))
    pretax_col = _pick_col(inc_wide, ("除税前溢利", "持续经营税前利润", "税前利润", "利润总额"))
    tax_col = _pick_col(inc_wide, ("税项", "所得税", "所得税费用"))
    rnd_col = _pick_col(inc_wide, ("研发费用",))
    rows = []
    for d in inc_wide.index.map(str).tolist():
        rows.append(
            {
                "报告日": d,
                "operating_profit": _num_at(inc_wide, d, op_col),
                "finance_cost": _num_at(inc_wide, d, finance_col),
                "pretax_profit": _num_at(inc_wide, d, pretax_col),
                "tax_expense": _num_at(inc_wide, d, tax_col),
                "rnd_expense": _num_at(inc_wide, d, rnd_col),
            }
        )
    return pd.DataFrame(rows)


def _load_data_hk(code: str) -> Dict[str, pd.DataFrame]:
    abs_df = _build_abs_df_hk(code)
    inc_w, bs_w, cf_w = _fetch_hk_wides(code)
    income_df = _normalize_hk_company_income(code, _derive_income_columns(_wide_to_report_df(
        inc_w,
        {
            "营业总收入": ("营业额", "营运收入", "营业收入", "总收入"),
            "营业收入": ("营业额", "营运收入", "营业总收入", "总收入"),
            "营业成本": ("销售成本", "营运支出", "营运成本", "营业成本", "收入成本"),
            "销售费用": ("销售及分销费用", "销售费用", "分销成本"),
            "管理费用": ("行政开支", "行政费用", "管理费用", "一般及行政费用"),
            "研发费用": ("研发费用",),
            "营业费用": ("营业费用",),
            "营业利润": ("经营溢利", "营业利润", "经营利润"),
        },
    )))
    balance_df = _wide_to_report_df(
        bs_w,
        {
            "存货": ("存货", "存货净额"),
            "应收账款": ("应收帐款", "应收账款", "应收票据及应收账款"),
            "应付账款": ("应付帐款", "应付账款", "应付票据及应付账款"),
            "流动资产合计": ("流动资产合计", "流动资产"),
            "负债合计": ("负债合计", "总负债", "负债总计"),
        },
    )
    abs_df = _add_asset_turnover_to_abs(abs_df, income_df, balance_df)
    data: Dict[str, pd.DataFrame] = {
        "abstract": abs_df,
        "income": income_df,
        "balance": balance_df,
        "cashflow_extras": fetch_cashflow_extras_hk_us(code, cf_wide=cf_w, inc_wide=inc_w, bs_wide=bs_w),
        "balance_extras": fetch_balance_sheet_extras_hk_us(code, bs_wide=bs_w),
        "income_extras": fetch_income_extras_hk_us(code, inc_wide=inc_w),
    }
    data["year_data"] = build_year_data_for_valuation(data)
    for _col, _row in (data.get("year_data") or {}).items():
        _raw_shares = _safe_float((_row or {}).get("shares"))
        if _raw_shares is not None and _raw_shares > 0:
            _row["reported_shares"] = _raw_shares
            _row["reported_shares_source"] = "eastmoney_hk_financials"
            _row["reported_shares_semantics"] = "weighted_avg_or_restated"
            _row["share_basis_confidence"] = "medium"
    data["current_price_tuple"] = get_current_price_hk(code)
    return data


def _normalize_us_valuation_shares(
    inc_wide: pd.DataFrame,
    year_data: dict,
    split_threshold: float = 1.5,
) -> Dict[str, float]:
    """归一化美股历史股本到当前拆股口径。

    东方财富的历史 EPS 存在分阶段追溯调整——不同财年可能停留在不同历史拆股基准，
    导致 profit/eps 倒推出的历史股本在调整节点前后跳变（如 AAPL 2011→2012 跳 7×）。

    本函数从综合损益表取"基本加权平均股数-普通股"，逆向扫描年际跳变节点，
    对各跳变节点及其之前所有年份乘以累积跳变因子，使全历史股本归一到最新拆股口径。
    真实回购/增发引起的年度小幅变动（< split_threshold）不会被当作拆股处理。

    返回 {date_col: normalized_shares} 字典，单位与原始报告一致（通常为"股"）。
    """
    if inc_wide is None or inc_wide.empty or not year_data:
        return {}
    shares_col = _pick_col(inc_wide, ("基本加权平均股数-普通股", "摊薄加权平均股数-普通股"))
    if shares_col is None:
        return {}

    sorted_cols = sorted(year_data.keys())
    raw: Dict[str, float] = {}
    for col in sorted_cols:
        v = _num_at(inc_wide, col, shares_col)
        if v is not None and v > 0:
            raw[col] = v
    if not raw:
        return {}

    sorted_raw = sorted(raw.keys())
    corrections: Dict[str, float] = {}
    cumulative = 1.0
    # 从最新年份（索引 len-1）向最旧年份（索引 0）逐年扫描
    for i in range(len(sorted_raw) - 1, -1, -1):
        this_col = sorted_raw[i]
        if i < len(sorted_raw) - 1:
            next_col = sorted_raw[i + 1]      # 时间上晚一年
            next_v = raw.get(next_col)
            this_v = raw.get(this_col)
            if next_v and this_v and this_v > 0:
                ratio = next_v / this_v        # 从 this_col → next_col 的倍数
                if ratio >= split_threshold:   # 疑似拆股追溯调整节点
                    cumulative *= ratio
        corrections[this_col] = cumulative

    vs_dict = {col: raw[col] * corrections.get(col, 1.0) for col in sorted_raw if col in raw}
    return vs_dict, corrections


def _normalize_us_valuation_shares_from_year_data(
    year_data: dict,
    split_threshold: float = 1.5,
) -> Dict[str, float]:
    """缓存命中时的备用归一化：用 year_data['shares']（profit/eps 倒推值）代替 inc_wide。

    与 _normalize_us_valuation_shares() 逻辑相同，但不依赖 inc_wide DataFrame，
    仅作为旧缓存补救手段（新缓存已在写入前注入 valuation_shares，无需此路径）。
    """
    if not year_data:
        return {}
    sorted_cols = sorted(year_data.keys())
    raw: Dict[str, float] = {}
    for col in sorted_cols:
        v = _safe_float(year_data[col].get("shares"))
        if v is not None and v > 0:
            raw[col] = v
    if not raw:
        return {}

    sorted_raw = sorted(raw.keys())
    corrections: Dict[str, float] = {}
    cumulative = 1.0
    for i in range(len(sorted_raw) - 1, -1, -1):
        this_col = sorted_raw[i]
        if i < len(sorted_raw) - 1:
            next_col = sorted_raw[i + 1]
            next_v = raw.get(next_col)
            this_v = raw.get(this_col)
            if next_v and this_v and this_v > 0:
                ratio = next_v / this_v
                if ratio >= split_threshold:
                    cumulative *= ratio
        corrections[this_col] = cumulative

    vs_dict = {col: raw[col] * corrections.get(col, 1.0) for col in sorted_raw if col in raw}
    return vs_dict, corrections


def _parse_share_cell_value(cell: object) -> Optional[float]:
    text = str(cell or "").replace(",", "").strip()
    if not text:
        return None
    m = re.search(r"([-+]?\d+(?:\.\d+)?)", text)
    if not m:
        return None
    return _safe_float(m.group(1))


def _build_us_asof_share_map(code: str, year_data: dict) -> Dict[str, float]:
    if not year_data:
        return {}
    df, status = fetch_us_share_change_history_sec(code)
    if status != "ok" or df is None or df.empty or "变动日期" not in df.columns or "总股本" not in df.columns:
        return {}

    hist = df.copy()
    hist["_dt"] = pd.to_datetime(hist["变动日期"], errors="coerce")
    hist["_shares"] = hist["总股本"].map(_parse_share_cell_value)
    hist = hist[hist["_dt"].notna() & hist["_shares"].notna()].sort_values("_dt")
    if hist.empty:
        return {}

    out: Dict[str, float] = {}
    for col in sorted(year_data.keys()):
        try:
            asof = pd.Timestamp(f"{col[:4]}-{col[4:6]}-{col[6:8]}")
        except Exception:
            continue
        # 严格 as-of：只允许使用该年及以前可观测到的公司行为记录，禁止使用未来日期“最近邻”。
        prior = hist[hist["_dt"] <= asof]
        if prior.empty:
            continue
        nearest = prior.sort_values("_dt").iloc[-1]
        shares = _safe_float(nearest.get("_shares"))
        if shares is not None and shares > 0:
            out[col] = shares
    return out


def _load_data_us(code: str) -> Dict[str, pd.DataFrame]:
    sym = _norm_us(code)
    abs_df = _build_abs_df_us(sym)
    raw = _fetch_us_financials(sym)
    inc_w = raw.get("inc_wide", pd.DataFrame())
    bs_w = raw.get("bal_wide", pd.DataFrame())
    income_df = _derive_income_columns(_wide_to_report_df(
        inc_w,
        {
            "营业总收入": ("营业收入", "主营收入", "总收入", "收入"),
            "营业收入": ("营业收入", "主营收入", "总收入", "收入"),
            "营业成本": ("主营成本", "营业成本", "收入成本", "销售成本", "销货成本"),
            "销售费用": ("销售费用", "营销费用", "销售及营销费用", "销售及分销费用"),
            "管理费用": ("管理费用", "一般及行政费用", "销售、一般和行政费用", "研发、销售及管理费用"),
            "研发费用": ("研发费用",),
            "营业费用": ("营业费用",),
            "营业利润": ("营业利润", "经营利润"),
        },
    ))
    balance_df = _wide_to_report_df(
        bs_w,
        {
            "存货": ("存货", "存货净额"),
            "应收账款": ("应收账款", "应收账款及应收票据", "应收账款净额"),
            "应付账款": ("应付账款", "应付账款及应付票据"),
            "流动资产合计": ("流动资产合计", "总流动资产", "流动资产"),
            "负债合计": ("负债合计", "总负债", "负债总计"),
        },
    )
    data = {
        "abstract": abs_df,
        "income": income_df,
        "balance": balance_df,
        "cashflow_extras": fetch_cashflow_extras_hk_us(
            sym,
            cf_wide=raw.get("cf_wide", pd.DataFrame()),
            inc_wide=inc_w,
            bs_wide=bs_w,
        ),
        "balance_extras": fetch_balance_sheet_extras_hk_us(sym, bs_wide=bs_w),
        "income_extras": fetch_income_extras_hk_us(sym, inc_wide=inc_w),
    }
    data["year_data"] = build_year_data_for_valuation(data)
    for _col, _row in (data.get("year_data") or {}).items():
        _raw_shares = _safe_float((_row or {}).get("shares"))
        if _raw_shares is not None and _raw_shares > 0:
            _row["reported_shares"] = _raw_shares
            _row["reported_shares_source"] = "eastmoney_us_financials"
            _row["reported_shares_semantics"] = "weighted_avg_or_restated"
            _row["share_basis_confidence"] = "medium"
    # 美股拆股口径归一化：修正因东方财富分阶段追溯调整导致的历史股本跳变
    _us_vs_map, _us_sf_map = _normalize_us_valuation_shares(inc_w, data["year_data"])
    for _col, _vs in _us_vs_map.items():
        if _col in data["year_data"]:
            _split_factor = _us_sf_map.get(_col, 1.0)
            data["year_data"][_col]["valuation_shares"] = _vs
            data["year_data"][_col]["split_factor_cumulative"] = _split_factor
            data["year_data"][_col]["asof_shares"] = (_vs / _split_factor) if _split_factor and _split_factor > 0 else _vs
    _us_asof_map = _build_us_asof_share_map(sym, data["year_data"])
    for _col, _shares in _us_asof_map.items():
        if _col in data["year_data"]:
            data["year_data"][_col]["asof_shares"] = _shares
            data["year_data"][_col]["reported_shares"] = _shares
            data["year_data"][_col]["reported_shares_source"] = "sec_share_change_history"
            data["year_data"][_col]["reported_shares_semantics"] = "period_end"
            data["year_data"][_col]["share_basis_confidence"] = "high"
    data["current_price_tuple"] = get_current_price_us(sym)
    return data


def load_data_hk_us(code: str) -> Dict[str, pd.DataFrame]:
    from valuescope.legacy_stock_scripts.core.cache import load_cache, save_cache, cache_age_info

    cached = load_cache(code, market=MARKET)
    if cached is not None:
        ok, info = cache_age_info(code, market=MARKET)
        print(f"  📦 {info}")
        if "year_data" not in cached or not cached["year_data"]:
            cached["year_data"] = build_year_data_for_valuation(cached)
        if MARKET == "hk":
            cached["current_price_tuple"] = get_current_price_hk(code)
        elif MARKET == "us":
            sym = _norm_us(code)
            cached["current_price_tuple"] = get_current_price_us(sym)
            # 旧缓存补救：若 valuation_shares 未注入，用 year_data["shares"] 做启发式归一化
            _yd = cached.get("year_data") or {}
            _has_vs = any(bool(vd.get("valuation_shares")) for vd in _yd.values())
            if not _has_vs and _yd:
                _us_vs_map, _us_sf_map = _normalize_us_valuation_shares_from_year_data(_yd)
                for _col, _vs in _us_vs_map.items():
                    if _col in _yd:
                        _split_factor = _us_sf_map.get(_col, 1.0)
                        _yd[_col]["valuation_shares"] = _vs
                        _yd[_col]["split_factor_cumulative"] = _split_factor
                        _yd[_col]["asof_shares"] = (_vs / _split_factor) if _split_factor and _split_factor > 0 else _vs
            _us_asof_map = _build_us_asof_share_map(sym, _yd)
            for _col, _shares in _us_asof_map.items():
                if _col in _yd:
                    _yd[_col]["asof_shares"] = _shares
                    _yd[_col]["reported_shares"] = _shares
                    _yd[_col]["reported_shares_source"] = "sec_share_change_history"
                    _yd[_col]["reported_shares_semantics"] = "period_end"
                    _yd[_col]["share_basis_confidence"] = "high"
        return cached

    if MARKET == "hk":
        data = _load_data_hk(code)
    elif MARKET == "us":
        data = _load_data_us(code)
    else:
        raise RuntimeError("MARKET 未初始化")

    try:
        save_cache(code, data, market=MARKET)
        print(f"  💾 数据已缓存至 data/raw/{MARKET}_{code}.json")
    except Exception as e:
        print(f"  ⚠️ 缓存写入失败: {e}")

    return data


def get_company_info_hk_us(code: str):
    from valuescope.legacy_stock_scripts.core.config import resolve_hk_us_industry
    if MARKET == "hk":
        name = _get_hk_company_name(code)
        shares = _hk_latest_implied_shares(code)
        industry = resolve_hk_us_industry(code, name) or "港股"
        return name, shares, industry
    if MARKET == "us":
        name, shares, _orig_ind = get_company_info_us(code)
        industry = resolve_hk_us_industry(code, name) or _orig_ind
        return name, shares, industry
    return code, None, ""


def get_current_price_hk_us(code: str):
    if MARKET == "hk":
        return get_current_price_hk(code)
    if MARKET == "us":
        return get_current_price_us(code)
    return None, None, None


def get_historical_price_as_of_hk_us(code: str, asof_date: pd.Timestamp):
    if MARKET == "us":
        return _historical_price_us_yahoo(_norm_us(code), asof_date)
    if MARKET == "hk":
        return _historical_price_hk(code, asof_date)
    return None, None, None


def _historical_price_us_yahoo(sym: str, asof_date: pd.Timestamp):
    asof = pd.Timestamp(asof_date).normalize()
    import requests

    period1 = int((asof - pd.Timedelta(days=10)).timestamp())
    period2 = int((asof + pd.Timedelta(days=3)).timestamp())
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.upper()}",
            params={"period1": period1, "period2": period2, "interval": "1d", "events": "history"},
            timeout=14,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
        )
        j = r.json()
        result = ((j.get("chart") or {}).get("result") or [None])[0] or {}
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        adj = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
        closes = ((indicators.get("quote") or [{}])[0]).get("close") or []
        rows = []
        for i, ts in enumerate(timestamps):
            try:
                dt = pd.to_datetime(int(ts), unit="s", utc=True).tz_convert(None).normalize()
                px = adj[i] if i < len(adj) and adj[i] is not None else (closes[i] if i < len(closes) else None)
                px = float(px) if px is not None else None
            except Exception:
                continue
            if px and px > 0:
                rows.append((dt, px))
        before = [(dt, px) for dt, px in rows if dt <= asof]
        if before:
            dt, px = sorted(before, key=lambda x: x[0])[-1]
            return px, "Yahoo历史复权收盘(as-of)", str(dt.date())
    except Exception:
        pass
    # ---------- fallback: akshare 新浪财经美股日线 ----------
    try:
        df = ak.stock_us_daily(symbol=sym.upper(), adjust="")
        if df is not None and not df.empty and "date" in df.columns and "close" in df.columns:
            d = df.copy()
            d["dt"] = pd.to_datetime(d["date"], errors="coerce")
            d = d.dropna(subset=["dt"])
            d = d[d["dt"] <= asof].sort_values("dt")
            if not d.empty:
                row = d.iloc[-1]
                return float(row["close"]), "新浪财经美股历史收盘(as-of)", str(row["dt"].date())
    except Exception:
        pass
    return None, None, None


def _historical_price_hk(code: str, asof_date: pd.Timestamp):
    asof = pd.Timestamp(asof_date).normalize()
    start = (asof - pd.Timedelta(days=10)).strftime("%Y%m%d")
    end = asof.strftime("%Y%m%d")
    try:
        df = ak.stock_hk_hist(symbol=str(code).zfill(5), period="daily", start_date=start, end_date=end, adjust="")
        if df is not None and not df.empty and "日期" in df.columns and "收盘" in df.columns:
            d = df.copy()
            d["dt"] = pd.to_datetime(d["日期"], errors="coerce")
            d = d.dropna(subset=["dt"])
            d = d[d["dt"] <= asof].sort_values("dt")
            if not d.empty:
                row = d.iloc[-1]
                return float(row["收盘"]), "港股历史收盘(as-of)", str(row["日期"])[:10]
    except Exception:
        pass
    return None, None, None


def _fetch_hk_daily_hist_tencent(code: str, years_back: int = 12) -> pd.DataFrame:
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.DateOffset(years=int(max(1, years_back)))
    symbol = f"hk{str(code).zfill(5)}"
    rows = []
    seg_end = end_ts
    hard_stop = 200
    while seg_end >= start_ts and hard_stop > 0:
        hard_stop -= 1
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{symbol},day,{start_ts.strftime('%Y-%m-%d')},{seg_end.strftime('%Y-%m-%d')},640,nfq"
        }
        try:
            response = requests.get(url, params=params, timeout=12, headers={"Referer": "https://gu.qq.com"})
            payload = response.json()
        except Exception:
            break
        blob = (payload.get("data") or {}).get(symbol) or {}
        got = blob.get("day") or []
        if not got:
            break
        rows.extend(got)
        try:
            seg_end = pd.Timestamp(str(got[0][0])).normalize() - pd.Timedelta(days=1)
        except Exception:
            break
        if len(got) < 5:
            break
    if not rows:
        return pd.DataFrame()
    by_date = {}
    for row in rows:
        if not row or len(row) < 3:
            continue
        try:
            by_date[str(row[0])] = float(row[2])
        except (TypeError, ValueError):
            continue
    if not by_date:
        return pd.DataFrame()
    out = pd.DataFrame([{"日期": d, "收盘": v} for d, v in sorted(by_date.items(), key=lambda x: x[0])])
    out["dt"] = pd.to_datetime(out["日期"], errors="coerce")
    out = out.dropna(subset=["dt"])
    out = out[(out["dt"] >= start_ts) & (out["dt"] <= end_ts)]
    return out.sort_values("dt").reset_index(drop=True)


def _fetch_us_daily_hist_nasdaq(code: str, years_back: int = 12) -> pd.DataFrame:
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.DateOffset(years=int(max(1, years_back)))
    symbol = _norm_us(code)
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical"
    params = {
        "assetclass": "stocks",
        "fromdate": start_ts.strftime("%Y-%m-%d"),
        "limit": "9999",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=16)
        payload = response.json()
    except Exception:
        return pd.DataFrame()
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    if not rows:
        return pd.DataFrame()

    parsed = []
    for row in rows:
        date_raw = str(row.get("date") or "").strip()
        close_raw = str(row.get("close") or "").replace("$", "").replace(",", "").strip()
        if not date_raw or not close_raw:
            continue
        try:
            dt = pd.to_datetime(date_raw, format="%m/%d/%Y", errors="raise")
            close = float(close_raw)
        except Exception:
            continue
        parsed.append({"日期": dt.strftime("%Y-%m-%d"), "收盘": close, "dt": dt.normalize()})
    if not parsed:
        return pd.DataFrame()
    out = pd.DataFrame(parsed)
    out = out[(out["dt"] >= start_ts) & (out["dt"] <= end_ts)]
    out = out.drop_duplicates(subset=["日期"], keep="last")
    return out.sort_values("dt").reset_index(drop=True)


@disk_cache(ttl_days=7)
def _fetch_us_daily_hist_em_adj_cached(sym: str, years_back: int) -> pd.DataFrame:
    """东方财富美股日线（前复权 fqt=1），磁盘缓存 7 天。

    使用前复权（fqt=1）价格：历史价格已还原到当前拆股口径，
    与 current-split-basis 的 valuation_shares 一致，保证 OE yield 分母正确。
    优先用 curl_cffi Chrome 指纹绕过服务器的 UA 封锁（能获取约 20 年数据）；
    失败时回退到标准 AKShare 请求。返回含「日期」「收盘」列的 DataFrame。
    """
    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(years=int(max(1, years_back)))
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    # ── 方法1：curl_cffi Chrome 指纹，绕过普通 requests 被 push2his 拒绝的问题 ──
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[import]
        for server_id in range(58, 70):
            url = f"https://{server_id}.push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                "secid": f"105.{sym}",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",  # 前复权：历史价格归一到当前拆股口径，与 valuation_shares 同基准
                "beg": start_s,
                "end": "20500000",
            }
            try:
                r = cffi_requests.get(
                    url, params=params, impersonate="chrome110", timeout=30
                )
                klines = (r.json().get("data") or {}).get("klines") or []
                if len(klines) > 500:  # 至少 2 年才认为成功
                    parsed = []
                    for line in klines:
                        parts = line.split(",")
                        if len(parts) >= 3:
                            try:
                                dt = pd.to_datetime(parts[0])
                                parsed.append(
                                    {
                                        "日期": parts[0],
                                        "收盘": float(parts[2]),
                                        "dt": dt.normalize(),
                                    }
                                )
                            except (ValueError, IndexError):
                                continue
                    if len(parsed) > 200:
                        df = pd.DataFrame(parsed)
                        return df.sort_values("dt").reset_index(drop=True)
            except Exception:
                continue
    except ImportError:
        pass

    # ── 方法2：ak.stock_us_daily（Sina Finance，约40年数据，列名 date/close） ──
    try:
        got = ak.stock_us_daily(symbol=sym, adjust="")
        if got is not None and not got.empty and "date" in got.columns and "close" in got.columns:
            got["date"] = pd.to_datetime(got["date"])
            got = got[got["date"] >= start].copy()
            if len(got) > 200:
                got = got.rename(columns={"date": "日期", "close": "收盘"})
                got["dt"] = pd.to_datetime(got["日期"]).dt.normalize()
                return got.sort_values("dt").reset_index(drop=True)
    except Exception:
        pass

    # ── 方法3：标准 AKShare stock_us_hist（多 prefix 尝试） ──
    for prefix in ("105", "106", "107", "108", "104", "103", "109"):
        for _attempt in range(2):
            try:
                got = ak.stock_us_hist(
                    symbol=f"{prefix}.{sym}",
                    period="daily",
                    start_date=start_s,
                    end_date=end_s,
                    adjust="",
                )
                if got is not None and not got.empty:
                    return got
            except Exception:
                continue
    return pd.DataFrame()


def fetch_daily_hist_hk_us(code: str, years_back: int = 12) -> pd.DataFrame:
    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(years=int(max(1, years_back)))
    try:
        if MARKET == "hk":
            df = _fetch_hk_daily_hist_tencent(code, years_back)
            if df is None or df.empty:
                df = ak.stock_hk_hist(
                    symbol=str(code).zfill(5),
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="",
                )
        else:
            # AKShare/Eastmoney 优先（约20年数），带7天磁盘缓存；NASDAQ兜底（约10年）
            sym = _norm_us(code)
            df = _fetch_us_daily_hist_em_adj_cached(sym, int(max(1, years_back)))
            if df is None or df.empty:
                df = _fetch_us_daily_hist_nasdaq(code, years_back)
        if df is None or df.empty or "日期" not in df.columns:
            return pd.DataFrame()
        out = df.copy()
        out["dt"] = pd.to_datetime(out["日期"], errors="coerce")
        return out.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def fetch_market_pe_anchor_hk_us() -> Tuple[Optional[float], Optional[str]]:
    if MARKET == "hk":
        symbols = [f"hk{str(code).zfill(5)}" for code in HK_MARKET_PE_SAMPLE]
        label = f"港股代表样本PE中位数（腾讯行情，n={len(symbols)}）"
    elif MARKET == "us":
        symbols = [f"us{_norm_us(code)}" for code in US_MARKET_PE_SAMPLE]
        label = f"美股代表样本PE中位数（腾讯行情，n={len(symbols)}）"
    else:
        return None, None

    vals = []
    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={','.join(symbols)}",
            timeout=8,
            headers={"Referer": "https://gu.qq.com"},
        )
        quote_texts = [chunk for chunk in r.text.split(";") if "~" in chunk]
    except Exception:
        quote_texts = []

    for quote in quote_texts:
        try:
            parts = quote.split('"')[1].split("~")
            pe = _safe_float(parts[39]) if len(parts) > 39 else None
            if pe is not None and 0 < pe < 500:
                vals.append(pe)
        except Exception:
            continue

    if len(vals) >= 5:
        return float(pd.Series(vals).median()), label.replace(f"n={len(symbols)}", f"n={len(vals)}")

    # ── 兜底：腾讯样本不足时，尝试 Yahoo Finance 批量接口 ──
    if MARKET == "us":
        us_raw_syms = list(US_MARKET_PE_SAMPLE)[:10]
        yf_vals: List[float] = []
        try:
            r2 = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": ",".join(us_raw_syms), "fields": "trailingPE,forwardPE"},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
                timeout=12,
            )
            if r2.status_code == 200:
                result_list = ((r2.json().get("quoteResponse") or {}).get("result") or [])
                for item in result_list:
                    pe = _safe_float(item.get("trailingPE")) or _safe_float(item.get("forwardPE"))
                    if pe is not None and 0 < pe < 500:
                        yf_vals.append(pe)
        except Exception:
            pass
        if len(yf_vals) >= 3:
            return float(pd.Series(yf_vals).median()), (
                f"美股代表样本PE中位数（Yahoo Finance兜底，n={len(yf_vals)}/{len(us_raw_syms)}）"
            )

        # ── 第三层兜底：直接获取 S&P 500 指数 PE（Yahoo Finance）──
        try:
            r3 = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": "^GSPC,^SPX,SPY", "fields": "trailingPE,forwardPE"},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
                timeout=10,
            )
            if r3.status_code == 200:
                idx_list = ((r3.json().get("quoteResponse") or {}).get("result") or [])
                for item in idx_list:
                    pe = _safe_float(item.get("trailingPE")) or _safe_float(item.get("forwardPE"))
                    if pe is not None and 10 < pe < 60:   # 指数PE合理范围
                        return pe, f"美股市场PE近似参考值（S&P500指数PE，{item.get('symbol', '^GSPC')}）"
        except Exception:
            pass

    return None, None


@lru_cache(maxsize=1)
@disk_cache(ttl_days=1)
def _bond_zh_us_rate_cached(start_date: str = "20160101") -> Optional[pd.DataFrame]:
    """获取国债收益率历史序列，带1天磁盘缓存，与 technicals 模块共享数据源。"""
    try:
        return ak.bond_zh_us_rate(start_date=start_date)
    except Exception:
        try:
            return ak.bond_zh_us_rate()
        except Exception:
            return None


def fetch_risk_free_yield_hk_us() -> Tuple[Optional[float], Optional[str]]:
    # 优先使用 technicals 模块共享的带磁盘缓存历史序列，确保与市场环境模块口径一致
    df = None
    try:
        from valuescope.legacy_stock_scripts.core.technicals import _bond_zh_us_rate_hist_cached
        df = _bond_zh_us_rate_hist_cached("20160101")
    except Exception:
        pass
    if df is None:
        # 兜底：使用本模块自带的缓存版本
        df = _bond_zh_us_rate_cached("20160101")
    if df is None:
        return None, None
    if df.empty or "美国国债收益率10年" not in df.columns or "日期" not in df.columns:
        return None, None
    for i in range(len(df) - 1, -1, -1):
        row = df.iloc[i]
        y = _safe_float(row.get("美国国债收益率10年"))
        if y is None:
            continue
        try:
            dt = str(pd.Timestamp(row["日期"]).date())
        except Exception:
            dt = str(row.get("日期") or "")
        if MARKET == "hk":
            return y, f"美国10年期国债收益率（港币联系汇率近似，{dt}）"
        return y, f"美国10年期国债收益率（{dt}）"
    return None, None


def fetch_pledge_snapshot_not_applicable(code: str):
    return None, "not_applicable"


def _share_cell(shares: Optional[float]) -> Optional[str]:
    if shares is None or shares <= 0:
        return None
    return f"{float(shares):.0f}股"


def _tencent_current_share_pair(code: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    if MARKET == "hk":
        symbol = f"hk{str(code).zfill(5)}"
        total_idx, listed_idx = 69, 70
    elif MARKET == "us":
        symbol = f"us{_norm_us(code)}"
        total_idx, listed_idx = 62, 63
    else:
        return None, None, None
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={symbol}", timeout=8, headers={"Referer": "https://gu.qq.com"})
        parts = r.text.split('"')[1].split("~")
        total = _safe_float(parts[total_idx]) if len(parts) > total_idx else None
        listed = _safe_float(parts[listed_idx]) if len(parts) > listed_idx else None
        dt = None
        if len(parts) > 30 and parts[30]:
            dt = str(parts[30]).split(" ")[0].replace("/", "-")
        return total, listed, dt
    except Exception:
        return None, None, None


@lru_cache(maxsize=1)
def _sec_ticker_cik_map() -> Dict[str, int]:
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            timeout=20,
            headers=SEC_TICKERS_HEADERS,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
    except Exception:
        return {}

    out: Dict[str, int] = {}
    values = data.values() if isinstance(data, dict) else data
    for item in values:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        cik = _safe_float(item.get("cik_str"))
        if ticker and cik is not None and cik > 0:
            out[ticker] = int(cik)
    return out


def _sec_cik_for_us_symbol(sym: str) -> Optional[int]:
    return _sec_ticker_cik_map().get(_norm_us(sym).upper())


@lru_cache(maxsize=128)
def _sec_companyfacts(cik: int) -> Dict:
    try:
        cik10 = str(int(cik)).zfill(10)
        r = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
            timeout=24,
            headers=SEC_HEADERS,
        )
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


def fetch_us_share_change_history_sec(code: str) -> Tuple[pd.DataFrame, str]:
    cik = _sec_cik_for_us_symbol(code)
    if cik is None:
        return pd.DataFrame(), "not_found"
    facts = _sec_companyfacts(cik)
    dei = (facts.get("facts") or {}).get("dei") or {}
    shares_fact = dei.get("EntityCommonStockSharesOutstanding") or {}
    share_rows = ((shares_fact.get("units") or {}).get("shares")) or []
    rows: List[Dict[str, object]] = []
    for item in share_rows:
        if not isinstance(item, dict):
            continue
        val = _safe_float(item.get("val"))
        end = item.get("end")
        if val is None or val <= 0 or not end:
            continue
        try:
            dt = pd.to_datetime(end)
        except Exception:
            continue
        # 美股没有 A 股“限售/流通 A 股”同款口径；这里用 SEC 披露的普通股 outstanding
        # 作为股本质量模块的可交易股本近似，避免错误地沿用 A 股股本接口。
        rows.append(
            {
                "变动日期": dt.strftime("%Y-%m-%d"),
                "总股本": _share_cell(val),
                "已流通股份": _share_cell(val),
                "_filed": item.get("filed") or "",
                "_form": item.get("form") or "",
            }
        )
    if not rows:
        return pd.DataFrame(), "not_found"
    out = pd.DataFrame(rows)
    out["_dt"] = pd.to_datetime(out["变动日期"], errors="coerce")
    out = out.dropna(subset=["_dt"]).sort_values(["_dt", "_filed", "_form"])
    out = out.drop_duplicates(subset=["_dt"], keep="last")
    return out.drop(columns=["_dt", "_filed", "_form"]).reset_index(drop=True), "ok"


def _ths_hk_symbol(code: str) -> str:
    return f"HK{int(str(code).strip()):04d}"


def fetch_hk_share_change_history_ths(code: str) -> Tuple[pd.DataFrame, str]:
    rows: List[Dict[str, object]] = []
    try:
        url = f"https://basic.10jqka.com.cn/176/{_ths_hk_symbol(code)}/equity.html"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        r.encoding = "utf-8"
        tables = pd.read_html(StringIO(r.text))
    except Exception:
        tables = []

    try:
        if tables:
            t0 = tables[0].copy()
            first_col = t0.columns[0]
            labels = t0[first_col].astype(str)
            has_a_share_row = labels.str.contains("A股总股本", na=False).any()
            total_row = t0[labels.str.contains("总股本", na=False) & ~labels.str.contains("港股|A股|优先", na=False)]
            hk_row = t0[labels.str.contains("港股总股本", na=False)]
            change_row = t0[labels.str.contains("变动日期", na=False)]
            for col in t0.columns[1:]:
                total = _safe_float(total_row.iloc[0][col]) * 1e6 if not total_row.empty and _safe_float(total_row.iloc[0][col]) is not None else None
                hk_float = _safe_float(hk_row.iloc[0][col]) * 1e6 if not hk_row.empty and _safe_float(hk_row.iloc[0][col]) is not None else None
                dt = str(change_row.iloc[0][col]) if not change_row.empty else str(col)
                rows.append({"变动日期": dt, "总股本": _share_cell(total), "已流通股份": _share_cell(hk_float)})

        if len(tables) > 1:
            t1 = tables[1].copy()
            date_col = next((c for c in t1.columns if "变动" in str(c) and "日期" in str(c)), None)
            shares_col = next((c for c in t1.columns if "普通股" in str(c)), None)
            if date_col is not None and shares_col is not None:
                for _, row in t1.iterrows():
                    shares_m = _safe_float(row.get(shares_col))
                    if shares_m is None:
                        continue
                    shares = shares_m * 1e6
                    rows.append(
                        {
                            "变动日期": str(row.get(date_col)),
                            "总股本": None if has_a_share_row else _share_cell(shares),
                            "已流通股份": _share_cell(shares),
                        }
                    )
    except Exception:
        pass

    total_now, listed_now, dt_now = _tencent_current_share_pair(code)
    if total_now is not None or listed_now is not None:
        rows.append(
            {
                "变动日期": dt_now or pd.Timestamp.now().strftime("%Y-%m-%d"),
                "总股本": _share_cell(total_now),
                "已流通股份": _share_cell(listed_now or total_now),
            }
        )

    if not rows:
        return pd.DataFrame(), "not_found"
    out = pd.DataFrame(rows)
    out["_dt"] = pd.to_datetime(out["变动日期"], errors="coerce")
    out = out.dropna(subset=["_dt"]).sort_values("_dt").drop_duplicates(subset=["_dt"], keep="last")
    return out.drop(columns=["_dt"]).reset_index(drop=True), "ok"


def fetch_share_change_history_hk_us(code: str) -> Tuple[pd.DataFrame, str]:
    if MARKET == "hk":
        return fetch_hk_share_change_history_ths(code)
    if MARKET == "us":
        sec_df, sec_status = fetch_us_share_change_history_sec(code)
        if sec_status == "ok" and not sec_df.empty:
            return sec_df, "ok"
        total, listed, dt = _tencent_current_share_pair(code)
        if total is None and listed is None:
            return pd.DataFrame(), sec_status
        return (
            pd.DataFrame(
                [
                    {
                        "变动日期": dt or pd.Timestamp.now().strftime("%Y-%m-%d"),
                        "总股本": _share_cell(total),
                        "已流通股份": _share_cell(listed or total),
                    }
                ]
            ),
            "ok_current_only",
        )
    return pd.DataFrame(), "not_found"


def fetch_restricted_release_not_applicable(code: str) -> Tuple[pd.DataFrame, str]:
    return pd.DataFrame(), "not_applicable"


def patch_pricing_power_for_hk_us(market: str, output_dir: Path) -> None:
    global MARKET
    MARKET = market
    dp = _dp
    dp.output_dir = output_dir
    dp.load_data = load_data_hk_us
    dp.get_company_info = get_company_info_hk_us
    dp.get_current_price = get_current_price_hk_us
    dp.get_historical_price_as_of = get_historical_price_as_of_hk_us
    dp.fetch_stock_daily_hist_long = fetch_daily_hist_hk_us
    dp.fetch_market_pe_anchor = fetch_market_pe_anchor_hk_us
    dp.fetch_risk_free_yield = fetch_risk_free_yield_hk_us
    dp.fetch_pledge_snapshot = fetch_pledge_snapshot_not_applicable
    dp.fetch_share_change_history = fetch_share_change_history_hk_us
    dp.fetch_restricted_release_queue = fetch_restricted_release_not_applicable
    dp.annual_cols_from_abstract = annual_cols_any_date
