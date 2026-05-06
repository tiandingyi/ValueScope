# core/data_a.py — auto-extracted
from __future__ import annotations

import json
import math
import multiprocessing as mp
from queue import Empty
import statistics
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import akshare as ak
import pandas as pd
import requests

from valuescope.legacy_stock_scripts.core.config import (
    REPORTS_DIR, OUTPUT_DIR, DISCOUNT_RATE, TERMINAL_GROWTH,
    PROJECTION_YEARS, MARGIN_OF_SAFETY, FADE_RATE, OE_HAIRCUT,
    G_MAX_CAP, LAST_PROFILE,
    INDUSTRY_DISCOUNT_MAP, INDUSTRY_EXIT_PE, DEFAULT_EXIT_PE,
    _get_industry_discount, _get_industry_exit_pes,
    _compute_dynamic_mos,
    PLEDGE_PROFILE_TIMEOUT_SEC, PLEDGE_RATIO_TIMEOUT_SEC,
    PLEDGE_MAX_DATES, PLEDGE_TOTAL_TIMEOUT_SEC,
    BOND_ZH_US_RATE_TIMEOUT_SEC,
    A_MARKET_PE_SAMPLE, MARKET_PE_ANCHOR_CACHE,
    TimeoutAbort, DataProvider, _dp,
    _DEDUCT_PARENT_NET_PROFIT_NAMES, _REAL_EPS_ROW_NAMES,
    MAINT_CAPEX_FLOOR_RATIO, MetricAssessment, ValuationAssessment,
)
from valuescope.legacy_stock_scripts.core.cache import disk_cache
from valuescope.legacy_stock_scripts.core.utils import (
    get_metric, get_metric_first, get_deduct_parent_net_profit,
    get_real_eps, _parse_share_count, is_bank, _tencent_symbol_prefix,
    safe_float, fmt_pct, fmt_days, fmt_ratio, fmt_num, fmt_yi, fmt_shares,
    pick_first_column, annualize, series_values, trend_text,
    _parse_cninfo_share_count, _parse_restricted_release_share_count,
    _equity_denom, _trend_arrow,
)


@lru_cache(maxsize=32)
@disk_cache(ttl_days=7)
def _stock_individual_info_em_cached(code: str) -> pd.DataFrame:
    return ak.stock_individual_info_em(symbol=code, timeout=5)

@lru_cache(maxsize=1)
@disk_cache(ttl_days=7)
def _stock_info_a_code_name_cached() -> pd.DataFrame:
    return ak.stock_info_a_code_name()

@lru_cache(maxsize=32)
def _stock_financial_abstract_cached(code: str) -> pd.DataFrame:
    return ak.stock_financial_abstract(symbol=code)

@lru_cache(maxsize=96)
@disk_cache(ttl_days=7)
def _stock_financial_report_sina_cached(code: str, symbol: str) -> pd.DataFrame:
    return ak.stock_financial_report_sina(stock=code, symbol=symbol)

@lru_cache(maxsize=32)
@disk_cache(ttl_days=7)
def _stock_financial_cash_ths_cached(code: str) -> pd.DataFrame:
    return ak.stock_financial_cash_ths(symbol=code, indicator="按报告期")

def _bond_zh_us_rate_worker(result_holder: list) -> None:
    """在后台线程内获取 10Y 国债收益率。"""
    try:
        df = ak.bond_zh_us_rate()
        result_holder.append(("ok", _cn_10y_yield_from_bond_zh_us_rate_df(df)))
    except Exception as exc:
        result_holder.append(("error", repr(exc)))

@lru_cache(maxsize=1)
@disk_cache(ttl_days=1)
def _bond_zh_us_rate_cached() -> Tuple[Optional[float], Optional[str]]:
    """用后台线程 + 超时获取国债收益率，避免 fork 导致的 SIGSEGV。"""
    import threading
    result_holder: list = []
    t = threading.Thread(target=_bond_zh_us_rate_worker, args=(result_holder,), daemon=True)
    t.start()
    t.join(BOND_ZH_US_RATE_TIMEOUT_SEC)
    if t.is_alive():
        raise TimeoutError("ak.bond_zh_us_rate exceeded %ss" % BOND_ZH_US_RATE_TIMEOUT_SEC) from None
    if not result_holder:
        raise RuntimeError("ak.bond_zh_us_rate returned no data") from None
    status, payload = result_holder[0]
    if status != "ok":
        raise RuntimeError(str(payload))
    return payload

@lru_cache(maxsize=1)
def _stock_zh_a_spot_em_cached() -> pd.DataFrame:
    return ak.stock_zh_a_spot_em()

@lru_cache(maxsize=1)
@disk_cache(ttl_days=1)
def _stock_gpzy_profile_em_cached() -> pd.DataFrame:
    return ak.stock_gpzy_profile_em()

@lru_cache(maxsize=32)
def _stock_gpzy_pledge_ratio_em_cached(date: str) -> pd.DataFrame:
    return ak.stock_gpzy_pledge_ratio_em(date=date)

@lru_cache(maxsize=32)
@disk_cache(ttl_days=7)
def _stock_share_change_cninfo_cached(code: str) -> pd.DataFrame:
    return ak.stock_share_change_cninfo(symbol=str(code).zfill(6))

@lru_cache(maxsize=32)
@disk_cache(ttl_days=7)
def _stock_restricted_release_queue_em_cached(code: str) -> pd.DataFrame:
    return ak.stock_restricted_release_queue_em(symbol=str(code).zfill(6))

def get_company_info(code):
    if _dp.get_company_info is not None:
        return _dp.get_company_info(code)
    name: Optional[str] = None
    total_shares: Optional[float] = None
    industry_em = ""
    try:
        info = _stock_individual_info_em_cached(code).copy()
        for name_field in ["股票简称", "股票名称", "名称", "公司简称"]:
            name_row = info[info["item"] == name_field]
            if not name_row.empty:
                name = str(name_row.iloc[0]["value"]).strip()
                break
        shares_row = info[info["item"] == "总股本"]
        total_shares = _parse_share_count(shares_row.iloc[0]["value"]) if not shares_row.empty else None
        for ind_field in ("所属行业", "行业", "申万行业", "证监会行业"):
            row = info[info["item"] == ind_field]
            if not row.empty:
                industry_em = str(row.iloc[0]["value"]).strip()
                break
    except Exception:
        pass
    if not name or name == code:
        try:
            cn_df = _stock_info_a_code_name_cached().copy()
            matched = cn_df[cn_df["code"] == code]
            if not matched.empty:
                name = str(matched.iloc[0]["name"]).strip()
        except Exception:
            pass
    return name or code, total_shares, industry_em

@lru_cache(maxsize=32)
def _get_current_price_cached(code: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    return _get_current_price_uncached(code)

def _get_current_price_uncached(code: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    获取最新股价，三级降级：
    ① 腾讯行情
    ② 新浪行情
    ③ AkShare 历史收盘兜底
    """
    import requests

    prefix = _tencent_symbol_prefix(str(code).zfill(6))

    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={prefix}{str(code).zfill(6)}",
            timeout=5,
            headers={"Referer": "https://gu.qq.com"},
        )
        parts = r.text.split('"')[1].split("~")
        if len(parts) > 3 and parts[3]:
            price = float(parts[3])
            ts = parts[30].strip() if len(parts) > 30 else ""
            if len(ts) == 14:
                t_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}"
            else:
                t_str = pd.Timestamp.now().strftime("%Y-%m-%d")
            return price, "腾讯行情", t_str
    except Exception:
        pass

    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={prefix}{str(code).zfill(6)}",
            timeout=5,
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        parts = r.text.split('"')[1].split(",")
        if len(parts) > 3 and parts[3]:
            price = float(parts[3])
            if len(parts) > 31:
                t_str = f"{parts[30].strip()} {parts[31].strip()[:5]}"
            else:
                t_str = pd.Timestamp.now().strftime("%Y-%m-%d")
            return price, "新浪行情", t_str
    except Exception:
        pass

    try:
        end = pd.Timestamp.now().strftime("%Y%m%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=15)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=str(code).zfill(6), period="daily", start_date=start, end_date=end, adjust="")
        if not df.empty:
            last = df.iloc[-1]
            return float(last["收盘"]), "历史收盘", str(last["日期"])[:10]
    except Exception:
        pass

    return None, None, None

def get_current_price(code):
    if _dp.get_current_price is not None:
        return _dp.get_current_price(code)
    return _get_current_price_cached(str(code).zfill(6))

def _parse_ths_money(val) -> float:
    if val is False or val is None:
        return 0.0
    try:
        if pd.isna(val):
            return 0.0
    except (TypeError, ValueError):
        pass
    s = str(val).strip().replace(",", "").replace(" ", "")
    try:
        if "亿" in s:
            return float(s.replace("亿", "")) * 1e8
        if "万" in s:
            return float(s.replace("万", "")) * 1e4
        return float(s)
    except (ValueError, TypeError):
        return 0.0

def _fetch_da_ths(code) -> dict:
    try:
        df = _stock_financial_cash_ths_cached(code).copy()
    except Exception:
        return {}

    if df is None or df.empty or "报告期" not in df.columns:
        return {}

    df["报告期"] = df["报告期"].astype(str)
    annual = df[df["报告期"].str.endswith("12-31")].copy()
    if annual.empty:
        return {}

    da_ths_l1 = [
        "固定资产折旧、油气资产折耗、生产性生物资产折旧",
        "固定资产折旧和摊销",
        "折旧与摊销",
    ]
    da_ths_amort = ["无形资产摊销", "长期待摊费用摊销", "使用权资产折旧"]
    da_excl = frozenset(["减值", "处置", "报废", "出售", "转让", "冲回", "损失", "收益", "准备"])

    result = {}
    for _, row in annual.iterrows():
        date_key = row["报告期"].replace("-", "")
        da = 0.0
        l1_hit = False
        for col in da_ths_l1:
            if col in df.columns:
                da += _parse_ths_money(row.get(col, False))
                l1_hit = True
                break
        if not l1_hit:
            for col in ["固定资产折旧", "计提的固定资产折旧"]:
                if col in df.columns:
                    da += _parse_ths_money(row.get(col, False))
                    break
        for col in da_ths_amort:
            if col in df.columns:
                da += _parse_ths_money(row.get(col, False))
        if da == 0.0:
            known = set(da_ths_l1 + ["固定资产折旧", "计提的固定资产折旧"] + da_ths_amort)
            for col in df.columns:
                if col in known:
                    continue
                s = str(col)
                if ("折旧" in s or "摊销" in s) and not any(ex in s for ex in da_excl):
                    da += _parse_ths_money(row.get(col, False))
        result[date_key] = da
    return result

def _cf_outflow_as_positive_yuan(val) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(x):
        return 0.0
    return abs(x)

def _buyback_cash_series(annual: pd.DataFrame, cf_columns) -> Tuple[pd.Series, Optional[str]]:
    for col in (
        "回购股份支付的现金",
        "回购本公司股份支付的现金",
        "回购股票支付的现金",
    ):
        if col in cf_columns:
            s = pd.to_numeric(annual[col], errors="coerce").fillna(0).map(_cf_outflow_as_positive_yuan)
            return s, col
    picked = None
    for col in cf_columns:
        sname = str(col)
        if "回购" not in sname:
            continue
        if "金融资产" in sname or "卖出回购" in sname or "业务资金" in sname:
            continue
        if ("股份" in sname or "股票" in sname) and ("支付" in sname or "付" in sname):
            picked = col
            break
    if picked:
        s = pd.to_numeric(annual[picked], errors="coerce").fillna(0).map(_cf_outflow_as_positive_yuan)
        return s, picked
    return pd.Series([0.0] * len(annual), index=annual.index), None

def _equity_inflow_series(annual: pd.DataFrame, cf_columns) -> Tuple[pd.Series, Optional[str]]:
    main = "吸收投资收到的现金"
    sub = "子公司吸收少数股东投资收到的现金"
    if main not in cf_columns:
        return pd.Series([0.0] * len(annual), index=annual.index), None
    absorb = pd.to_numeric(annual[main], errors="coerce").fillna(0).map(_cf_outflow_as_positive_yuan)
    if sub in cf_columns:
        minority = pd.to_numeric(annual[sub], errors="coerce").fillna(0).map(_cf_outflow_as_positive_yuan)
        return (absorb - minority).clip(lower=0.0), f"{main}−{sub}"
    return absorb, main

def fetch_cashflow_extras(code, cf: Optional[pd.DataFrame] = None):
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
    if cf is None:
        try:
            cf = _stock_financial_report_sina_cached(code, "现金流量表").copy()
        except Exception:
            return empty
    capex_col_candidates = [
        "购建固定资产、无形资产和其他长期资产所支付的现金",
        "购建固定资产、无形资产和其他长期资产支付的现金",
    ]
    capex_col = next((c for c in capex_col_candidates if c in cf.columns), None)
    div_col_pure_candidates = (
        "支付给股东的股利",
        "支付的现金股利",
        "分配普通股股利支付的现金",
    )
    div_col_combined_candidates = (
        "分配股利、利润或偿付利息所支付的现金",
        "分配股利、利润或偿付利息支付的现金",
    )
    div_col_pure = next((c for c in div_col_pure_candidates if c in cf.columns), None)
    div_col_combined = next((c for c in div_col_combined_candidates if c in cf.columns), None)
    da_l1 = [
        "固定资产折旧、油气资产折耗、生产性生物资产折旧",
        "固定资产折旧和摊销",
        "折旧与摊销",
        "折旧、耗竭及摊销",
        "计提的折旧摊销费用",
        "折旧摊销",
    ]
    da_l2 = [
        "固定资产折旧",
        "计提的固定资产折旧",
        "提取的固定资产折旧",
        "固定资产折旧费",
    ]
    da_l3 = [
        "无形资产摊销",
        "长期待摊费用摊销",
        "使用权资产折旧",
        "投资性房地产折旧",
        "生产性生物资产折旧",
        "油气资产折耗",
    ]
    da_excl = frozenset(["减值", "处置", "报废", "出售", "转让", "冲回", "损失", "收益", "准备"])

    cf["报告日"] = cf["报告日"].astype(str)
    annual = cf[cf["报告日"].str.endswith("1231")].copy()
    if annual.empty:
        return empty

    result = pd.DataFrame()
    result["报告日"] = annual["报告日"].values
    ocf_col_candidates = [
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "经营活动现金净额",
        "经营业务现金净额",
        "经营活动产生的净现金",
    ]
    ocf_col = next((c for c in ocf_col_candidates if c in cf.columns), None)
    if ocf_col is not None:
        result["ocf"] = pd.to_numeric(annual[ocf_col], errors="coerce").values
    else:
        inflow_col = "经营活动现金流入小计" if "经营活动现金流入小计" in cf.columns else None
        outflow_col = "经营活动现金流出小计" if "经营活动现金流出小计" in cf.columns else None
        if inflow_col is not None and outflow_col is not None:
            result["ocf"] = (
                pd.to_numeric(annual[inflow_col], errors="coerce")
                - pd.to_numeric(annual[outflow_col], errors="coerce")
            ).values
        else:
            result["ocf"] = [None] * len(annual)
    if capex_col is not None:
        result["capex"] = pd.to_numeric(annual[capex_col], errors="coerce").values
    else:
        result["capex"] = [None] * len(annual)

    if div_col_pure is not None:
        result["dividends_paid"] = pd.to_numeric(annual[div_col_pure], errors="coerce").fillna(0).values
        result["div_reliable"] = True
    elif div_col_combined is not None:
        result["dividends_paid"] = pd.to_numeric(annual[div_col_combined], errors="coerce").fillna(0).values
        result["div_reliable"] = False
    else:
        result["dividends_paid"] = [0.0] * len(annual)
        result["div_reliable"] = False

    da_series = pd.Series([0.0] * len(annual), index=annual.index)
    l1_found = False
    for col in da_l1:
        if col in cf.columns:
            da_series += pd.to_numeric(annual[col], errors="coerce").fillna(0)
            l1_found = True
            break
    if not l1_found:
        for col in da_l2:
            if col in cf.columns:
                da_series += pd.to_numeric(annual[col], errors="coerce").fillna(0)
                break
    for col in da_l3:
        if col in cf.columns:
            da_series += pd.to_numeric(annual[col], errors="coerce").fillna(0)
    if da_series.abs().sum() == 0:
        known = set(da_l1 + da_l2 + da_l3)
        for col in cf.columns:
            if col in known:
                continue
            s = str(col)
            if ("折旧" in s or "摊销" in s) and not any(ex in s for ex in da_excl):
                da_series += pd.to_numeric(annual[col], errors="coerce").fillna(0)
    result["da"] = da_series.values

    bb_s, bb_col = _buyback_cash_series(annual, cf.columns)
    eq_s, eq_col = _equity_inflow_series(annual, cf.columns)
    result["buyback_cash"] = bb_s.values
    result["equity_inflow_cash"] = eq_s.values
    result["buyback_col"] = bb_col or ""
    result["equity_inflow_col"] = eq_col or ""

    if "支付的各项税费" in cf.columns:
        result["taxes_paid_cash"] = (
            pd.to_numeric(annual["支付的各项税费"], errors="coerce").fillna(0).map(_cf_outflow_as_positive_yuan).values
        )
    else:
        result["taxes_paid_cash"] = [0.0] * len(annual)

    if da_series.abs().sum() == 0:
        ths_da = _fetch_da_ths(code)
        if ths_da:
            result["da"] = result["报告日"].map(lambda d: ths_da.get(str(d), 0.0)).values

    return result.reset_index(drop=True)

def fetch_balance_sheet_extras(code, bs: Optional[pd.DataFrame] = None):
    empty = pd.DataFrame(columns=["报告日", "gross_cash", "interest_debt", "due_debt_principal", "net_cash", "goodwill", "equity_net_bs"])
    if bs is None:
        try:
            bs = _stock_financial_report_sina_cached(code, "资产负债表").copy()
        except Exception:
            return empty
    cash_col_candidates = ["货币资金", "交易性金融资产"]
    debt_col_candidates = [
        "短期借款",
        "交易性金融负债",
        "一年内到期的非流动负债",
        "长期借款",
        "应付债券",
        "租赁负债",
    ]

    bs["报告日"] = bs["报告日"].astype(str)
    annual = bs[bs["报告日"].str.endswith("1231")].copy()
    if annual.empty:
        return empty

    gross_cash = pd.Series([0.0] * len(annual), index=annual.index)
    interest_debt = pd.Series([0.0] * len(annual), index=annual.index)
    due_debt_principal = pd.Series([0.0] * len(annual), index=annual.index)

    for col in cash_col_candidates:
        if col in bs.columns:
            gross_cash += pd.to_numeric(annual[col], errors="coerce").fillna(0)
    for col in debt_col_candidates:
        if col in bs.columns:
            interest_debt += pd.to_numeric(annual[col], errors="coerce").fillna(0)
    for col in ("短期借款", "一年内到期的非流动负债"):
        if col in bs.columns:
            due_debt_principal += pd.to_numeric(annual[col], errors="coerce").fillna(0)

    if "商誉" in bs.columns:
        goodwill_s = pd.to_numeric(annual["商誉"], errors="coerce").fillna(0)
    else:
        goodwill_s = pd.Series([0.0] * len(annual), index=annual.index)

    equity_bs = None
    for eq_col in ("归属于母公司股东权益合计", "所有者权益(或股东权益)合计", "所有者权益"):
        if eq_col in bs.columns:
            equity_bs = pd.to_numeric(annual[eq_col], errors="coerce")
            break
    if equity_bs is None:
        equity_bs = pd.Series([None] * len(annual), index=annual.index)

    result = pd.DataFrame()
    result["报告日"] = annual["报告日"].values
    result["gross_cash"] = gross_cash.values
    result["interest_debt"] = interest_debt.values
    result["due_debt_principal"] = due_debt_principal.values
    result["net_cash"] = gross_cash.values - interest_debt.values
    result["goodwill"] = goodwill_s.values
    result["equity_net_bs"] = equity_bs.values
    return result.reset_index(drop=True)

def fetch_income_extras(code, pl: Optional[pd.DataFrame] = None):
    empty = pd.DataFrame(columns=["报告日", "revenue", "operating_profit", "finance_cost", "pretax_profit", "tax_expense"])
    if pl is None:
        try:
            pl = _stock_financial_report_sina_cached(code, "利润表").copy()
        except Exception:
            return empty
    col_map = {
        "营业利润": "operating_profit",
        "财务费用": "finance_cost",
        "利润总额": "pretax_profit",
        "所得税费用": "tax_expense",
        "减:所得税费用": "tax_expense",
        "减:所得税": "tax_expense",
    }
    if "营业利润" not in pl.columns or "利润总额" not in pl.columns:
        return empty

    pl["报告日"] = pl["报告日"].astype(str)
    annual = pl[pl["报告日"].str.endswith("1231")].copy()
    if annual.empty:
        return empty

    result = pd.DataFrame()
    result["报告日"] = annual["报告日"].values
    for src, dst in col_map.items():
        if src in pl.columns:
            result[dst] = pd.to_numeric(annual[src], errors="coerce").values
        elif dst not in result.columns:
            result[dst] = [None] * len(annual)

    # Revenue with fallback: 营业总收入 → 营业收入
    _rev_src = "营业总收入" if "营业总收入" in pl.columns else ("营业收入" if "营业收入" in pl.columns else None)
    if _rev_src:
        result["revenue"] = pd.to_numeric(annual[_rev_src], errors="coerce").values
    else:
        result["revenue"] = [None] * len(annual)

    if "finance_cost" in result.columns and "利息净收入" in pl.columns:
        fc_raw = pd.to_numeric(result["finance_cost"], errors="coerce")
        ni_as_fc = -pd.to_numeric(annual["利息净收入"], errors="coerce")
        n = len(result)
        if len(fc_raw) == n and len(ni_as_fc) == n:
            result["finance_cost"] = [
                float(fc_raw.iloc[i]) if pd.notna(fc_raw.iloc[i]) else float(ni_as_fc.iloc[i])
                for i in range(n)
            ]

    # 研发费用
    _rnd_src = "研发费用" if "研发费用" in pl.columns else ("研发支出" if "研发支出" in pl.columns else None)
    if _rnd_src:
        result["rnd_expense"] = pd.to_numeric(annual[_rnd_src], errors="coerce").values
    else:
        result["rnd_expense"] = [None] * len(annual)

    return result.reset_index(drop=True)

@lru_cache(maxsize=32)
@disk_cache(ttl_days=1)
def _fetch_stock_daily_hist_long_cached(code: str, years_back: int = 12) -> pd.DataFrame:
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.DateOffset(years=int(max(1, years_back)))
    try:
        import requests

        sym = f"{_tencent_symbol_prefix(str(code).zfill(6))}{str(code).zfill(6)}"
        all_rows = []
        seg_end = end_ts
        hard_stop = 200
        while seg_end >= start_ts and hard_stop > 0:
            hard_stop -= 1
            url = (
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
                f"param={sym},day,{start_ts.strftime('%Y-%m-%d')},{seg_end.strftime('%Y-%m-%d')},640,nfq"
            )
            try:
                r = requests.get(url, timeout=12, headers={"Referer": "https://gu.qq.com"})
                j = r.json()
            except Exception:
                break
            blob = (j.get("data") or {}).get(sym) or {}
            rows = blob.get("day") or []
            if not rows:
                break
            all_rows.extend(rows)
            try:
                seg_end = pd.Timestamp(str(rows[0][0])).normalize() - pd.Timedelta(days=1)
            except Exception:
                break
            if len(rows) < 5:
                break
        if all_rows:
            by_date = {}
            for row in all_rows:
                if not row or len(row) < 3:
                    continue
                try:
                    by_date[str(row[0])] = float(row[2])
                except (TypeError, ValueError):
                    continue
            if by_date:
                out = pd.DataFrame([{"日期": d, "收盘": v} for d, v in sorted(by_date.items(), key=lambda x: x[0])])
                out["dt"] = pd.to_datetime(out["日期"], errors="coerce")
                out = out.dropna(subset=["dt"])
                out = out[(out["dt"] >= start_ts) & (out["dt"] <= end_ts)]
                if not out.empty:
                    return out.sort_values("dt").reset_index(drop=True)
    except Exception:
        pass

    window = pd.Timedelta(days=800)
    parts = []
    seg_end = end_ts
    while seg_end > start_ts:
        seg_start = max(start_ts, seg_end - window)
        got = pd.DataFrame()
        for attempt in range(5):
            try:
                got = ak.stock_zh_a_hist(
                    symbol=str(code).zfill(6),
                    period="daily",
                    start_date=seg_start.strftime("%Y%m%d"),
                    end_date=seg_end.strftime("%Y%m%d"),
                    adjust="",
                )
                if got is not None and not got.empty:
                    break
            except Exception:
                got = pd.DataFrame()
            time.sleep(0.45 + attempt * 0.35)
        if got is not None and not got.empty:
            parts.append(got)
        seg_end = seg_start - pd.Timedelta(days=1)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    if "日期" not in out.columns:
        return pd.DataFrame()
    out = out.drop_duplicates(subset=["日期"], keep="last")
    out["dt"] = pd.to_datetime(out["日期"], errors="coerce")
    return out.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)

def fetch_stock_daily_hist_long(code: str, years_back: int = 12) -> pd.DataFrame:
    if _dp.fetch_stock_daily_hist_long is not None:
        return _dp.fetch_stock_daily_hist_long(code, years_back)
    result = _fetch_stock_daily_hist_long_cached(str(code).zfill(6), int(max(1, years_back))).copy()
    # 磁盘缓存反序列化后 dt 列可能变为字符串，需重新转为 datetime
    if not result.empty and "dt" in result.columns:
        result["dt"] = pd.to_datetime(result["dt"], errors="coerce")
    return result

def _close_column(daily: pd.DataFrame) -> Optional[str]:
    for c in ("收盘", "close", "Close"):
        if c in daily.columns:
            return c
    return None

def _first_close_on_or_after(daily: pd.DataFrame, y: int, m: int, d: int) -> Optional[float]:
    if daily.empty or "dt" not in daily.columns:
        return None
    col = _close_column(daily)
    if not col:
        return None
    target = pd.Timestamp(year=y, month=m, day=d)
    sub = daily[daily["dt"] >= target]
    if sub.empty:
        return None
    try:
        return float(sub.iloc[0][col])
    except Exception:
        return None

def _first_close_record_on_or_after(daily: pd.DataFrame, y: int, m: int, d: int) -> Optional[Tuple[str, float]]:
    if daily.empty or "dt" not in daily.columns:
        return None
    col = _close_column(daily)
    if not col:
        return None
    target = pd.Timestamp(year=y, month=m, day=d)
    sub = daily[daily["dt"] >= target]
    if sub.empty:
        return None
    try:
        row = sub.iloc[0]
        return str(pd.Timestamp(row["dt"]).date()), float(row[col])
    except Exception:
        return None

def _pe_percentile_cheap_score(current_pe: float, hist_pe: list[float]) -> Optional[float]:
    h = [float(x) for x in hist_pe if x is not None and 0 < float(x) < 5000]
    if len(h) < 3 or current_pe is None or current_pe <= 0:
        return None
    return 100.0 * sum(1 for v in h if v <= float(current_pe)) / len(h)

def _low_value_percentile_score(current_value: float, hist_values: list[float]) -> Optional[float]:
    vals = [float(x) for x in hist_values if x is not None and 0 < float(x) < 5000]
    if len(vals) < 3 or current_value is None or current_value <= 0:
        return None
    return 100.0 * sum(1 for v in vals if v <= float(current_value)) / len(vals)

def _high_value_percentile_score(current_value: float, hist_values: list[float]) -> Optional[float]:
    vals = [float(x) for x in hist_values if x is not None and 0 < float(x) < 5000]
    if len(vals) < 3 or current_value is None or current_value <= 0:
        return None
    return 100.0 * sum(1 for v in vals if v <= float(current_value)) / len(vals)

def build_dual_pe_history_post_may(code: str, abs_df: pd.DataFrame, max_fiscal_years: int = 10, daily_years_back: int = 12) -> Tuple[list[float], list[float], int, str]:
    note = "历史样本：各年 EPS 来自财务摘要；股价取次年5月1日起首笔收盘。"
    daily = fetch_stock_daily_hist_long(code, years_back=daily_years_back)
    if daily.empty:
        return [], [], 0, note + " 日线获取失败。"
    cols_desc = sorted(annual_cols_from_abstract(abs_df), reverse=True)[: max(1, int(max_fiscal_years))]
    hist_real, hist_basic = [], []
    last_dt = daily["dt"].max()
    for col in cols_desc:
        fy = int(str(col)[:4])
        if pd.Timestamp(year=fy + 1, month=5, day=1) > last_dt:
            continue
        px = _first_close_on_or_after(daily, fy + 1, 5, 1)
        re_t, _ = get_real_eps(abs_df, col)
        be_v = get_metric(abs_df, "基本每股收益", col)
        if px is None or re_t is None or be_v is None or re_t <= 0 or be_v <= 0:
            continue
        hist_real.append(px / re_t)
        hist_basic.append(px / be_v)
    return hist_real, hist_basic, len(cols_desc), note

def build_pe_percentile_history_post_may(
    code: str,
    abs_df: pd.DataFrame,
    current_pe: Optional[float],
    max_fiscal_years: int = 10,
    daily_years_back: int = 12,
) -> Dict[str, object]:
    note = "历史样本：各年 EPS 来自财务摘要；股价取次年5月1日起首笔收盘；当前PE使用最新股价 ÷ 最新EPS。"
    payload: Dict[str, object] = {
        "note": note,
        "points": [],
        "current_pe": current_pe,
        "percentile": None,
        "sample_count": 0,
        "hist_min": None,
        "hist_median": None,
        "hist_max": None,
        "hist_mean": None,
        "current_vs_median_pct": None,
        "method": "post_may_anchor",
    }
    if abs_df is None or abs_df.empty or current_pe is None or current_pe <= 0:
        return payload

    daily = fetch_stock_daily_hist_long(code, years_back=daily_years_back)
    if daily.empty:
        payload["note"] = note + " 日线获取失败。"
        return payload

    cols = annual_cols_from_abstract(abs_df)[-max(1, int(max_fiscal_years)):]
    if not cols:
        payload["note"] = note + " 财务摘要年报列缺失。"
        return payload

    last_dt = daily["dt"].max()
    points: List[Dict[str, object]] = []
    hist_real: List[float] = []
    hist_basic: List[float] = []
    for col in cols:
        fy = int(str(col)[:4])
        if pd.Timestamp(year=fy + 1, month=5, day=1) > last_dt:
            continue
        record = _first_close_record_on_or_after(daily, fy + 1, 5, 1)
        if record is None:
            continue
        price_date, px = record
        real_eps, real_src = get_real_eps(abs_df, col)
        basic_eps = get_metric(abs_df, "基本每股收益", col)
        real_pe = (px / real_eps) if real_eps is not None and real_eps > 0 else None
        basic_pe = (px / basic_eps) if basic_eps is not None and basic_eps > 0 else None
        if real_pe is not None:
            hist_real.append(float(real_pe))
        if basic_pe is not None:
            hist_basic.append(float(basic_pe))
        points.append(
            {
                "fiscal_year": str(fy),
                "anchor_date": price_date,
                "anchor_price": px,
                "real_eps": real_eps,
                "real_eps_src": real_src,
                "basic_eps": basic_eps,
                "real_pe": real_pe,
                "basic_pe": basic_pe,
            }
        )

    payload["points"] = points
    payload["sample_count"] = len(hist_real)
    if len(hist_real) < 3:
        payload["note"] = note + " 有效PE样本不足3个。"
        return payload

    hist_real = [float(x) for x in hist_real if x is not None and 0 < float(x) < 5000]
    if len(hist_real) < 3:
        payload["note"] = note + " 有效PE样本不足3个。"
        payload["sample_count"] = len(hist_real)
        return payload

    hist_median = float(statistics.median(hist_real))
    payload["percentile"] = _pe_percentile_cheap_score(float(current_pe), hist_real)
    payload["hist_min"] = min(hist_real)
    payload["hist_median"] = hist_median
    payload["hist_max"] = max(hist_real)
    payload["hist_mean"] = float(sum(hist_real) / len(hist_real))
    payload["hist_real"] = hist_real
    payload["hist_basic"] = hist_basic
    if hist_median > 0:
        payload["current_vs_median_pct"] = (float(current_pe) / hist_median - 1.0) * 100.0
    return payload

def build_eps_percentile_history(
    abs_df: pd.DataFrame,
    max_fiscal_years: int = 10,
) -> Dict[str, object]:
    note = "历史样本：各年 E 使用财务摘要中的 EPS（优先扣非/真实EPS，其次基本EPS）；当前E使用最新财年的同口径EPS。"
    payload: Dict[str, object] = {
        "note": note,
        "points": [],
        "current_value": None,
        "current_fiscal_year": None,
        "current_value_src": None,
        "percentile": None,
        "sample_count": 0,
        "hist_min": None,
        "hist_median": None,
        "hist_max": None,
        "hist_mean": None,
        "current_vs_median_pct": None,
        "method": "annual_eps_history",
    }
    if abs_df is None or abs_df.empty:
        return payload

    cols = annual_cols_from_abstract(abs_df)[-max(1, int(max_fiscal_years)):]
    if not cols:
        payload["note"] = note + " 财务摘要年报列缺失。"
        return payload

    points: List[Dict[str, object]] = []
    hist_values: List[float] = []
    for col in cols:
        fiscal_year = str(col)[:4]
        real_eps, real_src = get_real_eps(abs_df, col)
        basic_eps = safe_float(get_metric(abs_df, "基本每股收益", col))
        eps_value = real_eps if real_eps is not None else basic_eps
        if eps_value is not None:
            hist_values.append(float(eps_value))
        points.append(
            {
                "fiscal_year": fiscal_year,
                "value": eps_value,
                "real_eps": real_eps,
                "real_eps_src": real_src,
                "basic_eps": basic_eps,
            }
        )

    payload["points"] = points
    if points:
        latest_point = points[-1]
        payload["current_fiscal_year"] = latest_point.get("fiscal_year")
        payload["current_value"] = latest_point.get("value")
        payload["current_value_src"] = latest_point.get("real_eps_src") if latest_point.get("real_eps") is not None else "基本每股收益"

    valid_values = [float(x) for x in hist_values if x is not None and abs(float(x)) < 5000]
    payload["sample_count"] = len(valid_values)
    current_eps = safe_float(payload.get("current_value"))
    if len(valid_values) < 3 or current_eps is None:
        payload["note"] = note + f" 有效E样本仅 {len(valid_values)} 个。"
        return payload

    hist_median = float(statistics.median(valid_values))
    payload["percentile"] = _high_value_percentile_score(float(current_eps), valid_values)
    payload["hist_min"] = min(valid_values)
    payload["hist_median"] = hist_median
    payload["hist_max"] = max(valid_values)
    payload["hist_mean"] = float(sum(valid_values) / len(valid_values))
    payload["hist_values"] = valid_values
    if hist_median != 0:
        payload["current_vs_median_pct"] = (float(current_eps) / hist_median - 1.0) * 100.0
    return payload

def _cn_10y_yield_from_bond_zh_us_rate_df(df: pd.DataFrame) -> Tuple[Optional[float], Optional[str]]:
    col = "中国国债收益率10年"
    if df is None or df.empty or col not in df.columns or "日期" not in df.columns:
        return None, None
    for i in range(len(df) - 1, -1, -1):
        row = df.iloc[i]
        y_raw = row[col]
        if y_raw is None or pd.isna(y_raw):
            continue
        try:
            return float(y_raw), str(pd.Timestamp(row["日期"]).date())
        except Exception:
            continue
    return None, None

def fetch_cn_10y_government_bond_yield_pct() -> Tuple[Optional[float], Optional[str]]:
    if _dp.fetch_risk_free_yield is not None:
        return _dp.fetch_risk_free_yield()
    try:
        return _bond_zh_us_rate_cached()
    except Exception:
        return None, None

def _fetch_pledge_via_eastmoney_api(code_s: str, trade_dates: List[str]) -> Tuple[Optional[dict], str]:
    """直接请求东方财富 API 获取质押数据（绕过 akshare SSL 兼容问题）。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    for ds in trade_dates[:PLEDGE_MAX_DATES]:
        ds_fmt = f"{ds[:4]}-{ds[4:6]}-{ds[6:]}"
        params = {
            "sortColumns": "PLEDGE_RATIO",
            "sortTypes": "-1",
            "pageSize": "10",
            "pageNumber": "1",
            "reportName": "RPT_CSDC_LIST",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(TRADE_DATE='{ds_fmt}')(SECURITY_CODE=\"{code_s}\")",
        }
        try:
            r = requests.get(url, params=params, timeout=10, verify=False)
            data = r.json()
            if data.get("result") and data["result"].get("data"):
                item = data["result"]["data"][0]
                return {
                    "trade_date": ds_fmt,
                    "pledge_ratio_pct": float(item.get("PLEDGE_RATIO", 0)),
                    "pledge_shares_wan": float(item.get("REPURCHASE_BALANCE", 0)),
                    "pledge_mv_wan": float(item.get("PLEDGE_MARKET_CAP", 0)),
                    "pledge_n": int(item.get("PLEDGE_DEAL_NUM", 0)),
                    "industry": str(item.get("INDUSTRY", "")),
                }, "ok"
        except Exception:
            continue
    return None, "not_found"

def _fetch_listed_pledge_snapshot_inner(code: str) -> Tuple[Optional[dict], str]:
    code_raw = str(code).strip()
    if not code_raw.isdigit() or len(code_raw) <= 5:
        return None, "invalid_code"
    code_s = code_raw.zfill(6)
    trade_dates = []
    try:
        prof = _stock_gpzy_profile_em_cached().copy()
        if prof is not None and not prof.empty and "交易日期" in prof.columns:
            extra = [pd.Timestamp(v).strftime("%Y%m%d") for v in prof["交易日期"].tail(12).tolist()]
            for ds in reversed(extra):
                if ds not in trade_dates:
                    trade_dates.append(ds)
    except Exception:
        pass
    if not trade_dates:
        trade_dates = [pd.Timestamp.now().strftime("%Y%m%d")]
    # 优先用直接 API（快且绕过 SSL 兼容问题），失败再试 akshare
    result, status = _fetch_pledge_via_eastmoney_api(code_s, trade_dates)
    if result is not None:
        return result, status
    # 直接 API 失败，回退到 akshare
    for ds in trade_dates[:PLEDGE_MAX_DATES]:
        df = None
        for attempt in range(2):
            try:
                df = _stock_gpzy_pledge_ratio_em_cached(ds).copy()
                if df is not None and not df.empty:
                    break
            except Exception:
                df = None
                time.sleep(0.4 + 0.3 * attempt)
        if df is None or df.empty or "股票代码" not in df.columns:
            continue
        sub = df[df["股票代码"].astype(str).str.strip().str.zfill(6) == code_s]
        if not sub.empty:
            r = sub.iloc[0]
            return {
                "trade_date": r["交易日期"],
                "pledge_ratio_pct": float(r["质押比例"]),
                "pledge_shares_wan": float(r["质押股数"]),
                "pledge_mv_wan": float(r["质押市值"]),
                "pledge_n": int(r["质押笔数"]) if pd.notna(r["质押笔数"]) else 0,
                "industry": str(r.get("所属行业", "")) if pd.notna(r.get("所属行业")) else "",
            }, "ok"
    return None, "not_found"

def _fetch_listed_pledge_snapshot_worker(code: str, result_holder: list) -> None:
    try:
        result_holder.append(("ok", _fetch_listed_pledge_snapshot_inner(code)))
    except Exception as exc:
        result_holder.append(("error", repr(exc)))

def fetch_listed_pledge_snapshot_safe(code: str) -> Tuple[Optional[dict], str]:
    if _dp.fetch_pledge_snapshot is not None:
        return _dp.fetch_pledge_snapshot(code)
    import threading
    result_holder: list = []
    t = threading.Thread(target=_fetch_listed_pledge_snapshot_worker, args=(str(code), result_holder), daemon=True)
    t.start()
    t.join(PLEDGE_TOTAL_TIMEOUT_SEC)
    if t.is_alive():
        return None, "timeout"
    if not result_holder:
        return None, "error"
    status, payload = result_holder[0]
    if status != "ok":
        return None, "error"
    return payload

def fetch_listed_pledge_snapshot_em(code: str) -> Optional[dict]:
    pledge, _status = fetch_listed_pledge_snapshot_safe(code)
    return pledge

def annual_cols_from_abstract(abs_df: pd.DataFrame) -> List[str]:
    if _dp.annual_cols_from_abstract is not None:
        return _dp.annual_cols_from_abstract(abs_df)
    cols = [str(c) for c in abs_df.columns if str(c).endswith("1231")]
    return sorted(cols)

def load_data(code: str) -> Dict[str, pd.DataFrame]:
    if _dp.load_data is not None:
        return _dp.load_data(code)

    # ── 尝试从缓存加载 ──
    from valuescope.legacy_stock_scripts.core.cache import load_cache, save_cache, cache_age_info
    cached = load_cache(code, market="a")
    if cached is not None:
        ok, info = cache_age_info(code, market="a")
        print(f"  📦 {info}")
        # year_data 从缓存重建（如果缺失）
        if "year_data" not in cached or not cached["year_data"]:
            cached["year_data"] = build_year_data_for_valuation(cached)
        if (
            "cashflow_extras" not in cached
            or cached.get("cashflow_extras") is None
            or getattr(cached.get("cashflow_extras"), "empty", True)
            or "ocf" not in getattr(cached.get("cashflow_extras"), "columns", [])
        ):
            cached["cashflow_extras"] = fetch_cashflow_extras(code)
            cached["year_data"] = build_year_data_for_valuation(cached)
        # 缓存命中时也重建 valuation_shares（巨潮股本数据独立缓存，成本低）
        _a_vs_map = _normalize_a_valuation_shares(code, cached["year_data"])
        for _col, _vs in _a_vs_map.items():
            if _col in cached["year_data"]:
                cached["year_data"][_col]["valuation_shares"] = _vs
                cached["year_data"][_col]["asof_shares"] = _vs
                cached["year_data"][_col]["reported_shares"] = _vs
                cached["year_data"][_col]["reported_shares_source"] = "cninfo_share_change"
                cached["year_data"][_col]["reported_shares_semantics"] = "period_end"
                cached["year_data"][_col]["share_basis_confidence"] = "high"
        cached["current_price_tuple"] = get_current_price(code)
        try:
            save_cache(code, cached, market="a")
        except Exception:
            pass
        return cached

    abs_df = _stock_financial_abstract_cached(code).copy()
    try:
        income_raw = _stock_financial_report_sina_cached(code, "利润表").copy()
    except Exception:
        income_raw = pd.DataFrame()
    try:
        balance_raw = _stock_financial_report_sina_cached(code, "资产负债表").copy()
    except Exception:
        balance_raw = pd.DataFrame()
    try:
        cashflow_raw = _stock_financial_report_sina_cached(code, "现金流量表").copy()
    except Exception:
        cashflow_raw = pd.DataFrame()

    income_df = annualize(income_raw)
    balance_df = annualize(balance_raw)
    cashflow_extras = fetch_cashflow_extras(code, cashflow_raw)
    balance_extras = fetch_balance_sheet_extras(code, balance_raw)
    income_extras = fetch_income_extras(code, income_raw)

    data = {
        "abstract": abs_df,
        "income": income_df,
        "balance": balance_df,
        "income_raw": income_raw,
        "balance_raw": balance_raw,
        "cashflow_extras": cashflow_extras,
        "balance_extras": balance_extras,
        "income_extras": income_extras,
    }
    data["year_data"] = build_year_data_for_valuation(data)
    # A 股历史股本口径修复：用巨潮实际期末总股本替代 profit/eps 倒推值
    _a_vs_map = _normalize_a_valuation_shares(code, data["year_data"])
    for _col, _vs in _a_vs_map.items():
        if _col in data["year_data"]:
            data["year_data"][_col]["valuation_shares"] = _vs
            data["year_data"][_col]["asof_shares"] = _vs
            data["year_data"][_col]["reported_shares"] = _vs
            data["year_data"][_col]["reported_shares_source"] = "cninfo_share_change"
            data["year_data"][_col]["reported_shares_semantics"] = "period_end"
            data["year_data"][_col]["share_basis_confidence"] = "high"
    data["current_price_tuple"] = get_current_price(code)

    # ── 写入缓存 ──
    try:
        save_cache(code, data, market="a")
        print(f"  💾 数据已缓存至 data/raw/a_{code}.json")
    except Exception as e:
        print(f"  ⚠️ 缓存写入失败: {e}")

    return data

def _filter_data_as_of_year(data: Dict[str, pd.DataFrame], asof_year: Optional[int]) -> Dict[str, pd.DataFrame]:
    if asof_year is None:
        return data
    cutoff = f"{int(asof_year):04d}1231"
    out: Dict[str, pd.DataFrame] = {}
    source_year_data = data.get("year_data") if isinstance(data.get("year_data"), dict) else {}
    for key, df in data.items():
        if key == "year_data":
            continue
        if not isinstance(df, pd.DataFrame):
            out[key] = df
            continue
        if df.empty:
            out[key] = df.copy()
            continue
        d = df.copy()
        if "报告日" in d.columns:
            mask = d["报告日"].astype(str) <= cutoff
            out[key] = d[mask].reset_index(drop=True)
            continue
        keep_cols = []
        for col in d.columns:
            s = str(col)
            if s == "指标" or not (len(s) == 8 and s.isdigit()):
                keep_cols.append(col)
            elif s <= cutoff:
                keep_cols.append(col)
        out[key] = d[keep_cols].copy()
    out["year_data"] = build_year_data_for_valuation(out)
    if source_year_data:
        for _col, _dest in out["year_data"].items():
            _src = source_year_data.get(_col)
            if not isinstance(_src, dict):
                continue
            for _field in (
                "asof_shares",
                "valuation_shares",
                "reported_shares",
                "reported_shares_source",
                "reported_shares_semantics",
                "share_basis_confidence",
                "split_factor_cumulative",
            ):
                _value = _src.get(_field)
                if _value is not None:
                    _dest[_field] = _value
    out["_share_basis_mode"] = "asof"
    return out

def _historical_price_as_of_a(code: str, asof_date: pd.Timestamp) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    years_back = max(1, int(pd.Timestamp.now().year - asof_date.year + 2))
    daily = fetch_stock_daily_hist_long(code, years_back=years_back)
    if daily is None or daily.empty or "dt" not in daily.columns:
        return None, None, None
    close_col = _close_column(daily)
    if not close_col:
        return None, None, None
    asof = pd.Timestamp(asof_date).normalize()
    sub = daily[daily["dt"] <= asof].sort_values("dt")
    if sub.empty:
        sub = daily[daily["dt"] >= asof].sort_values("dt")
    if sub.empty:
        return None, None, None
    row = sub.iloc[-1] if sub.iloc[-1]["dt"] <= asof else sub.iloc[0]
    px = safe_float(row.get(close_col))
    if px is None or px <= 0:
        return None, None, None
    return px, "历史收盘(as-of)", str(pd.Timestamp(row["dt"]).date())

def get_historical_price_as_of(code: str, asof_date: pd.Timestamp) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    if _dp.get_historical_price_as_of is not None:
        try:
            px = _dp.get_historical_price_as_of(code, asof_date)
            if px and px[0] is not None:
                return px
        except Exception:
            pass
    return _historical_price_as_of_a(code, asof_date)

# --------------- Bank KPI extraction from existing statements ---------------

def _get_bank_col(df: pd.DataFrame, col_name: str, report_col: str) -> Optional[float]:
    """Get a single value from a statement DataFrame for banks (columns = fields, rows = periods)."""
    if df is None or df.empty or col_name not in df.columns:
        return None
    # For Sina format: first column is 报告日, other columns are metric names
    # Each row is a reporting period
    row = df[df[df.columns[0]] == report_col]
    if row.empty:
        return None
    v = row[col_name].values[0]
    try:
        return float(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None

def _get_sina_val(df: pd.DataFrame, col_name: str, report_date: str) -> Optional[float]:
    """Get value from Sina-format statement: rows = periods (报告日), columns = indicators."""
    if df is None or df.empty:
        return None
    date_col = df.columns[0]  # 报告日
    row = df[df[date_col].astype(str) == report_date]
    if row.empty:
        return None
    if col_name not in df.columns:
        return None
    v = row[col_name].values[0]
    try:
        return float(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None


def fetch_eastmoney_bank_data(code: str) -> Dict[str, Dict]:
    """Fetch official bank regulatory indicators from EastMoney F10 API.

    Returns {year_col: {nim, npl_ratio, provision_loan_ratio,
    provision_coverage_ratio, capital_adequacy_ratio, cost_income_ratio, ...}}.
    """
    secucode = code + ".SH" if code.startswith("6") else code + ".SZ"
    url = "https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": (
            "REPORT_DATE,REPORT_TYPE,"
            "NET_INTEREST_MARGIN,NET_INTEREST_SPREAD,"
            "NEWCAPITALADER,HXYJBCZL,FIRST_ADEQUACY_RATIO,"
            "NONPERLOAN,NON_PERFORMING_LOAN,LOAN_PROVISION_RATIO,BLDKBBL,"
            "REVENUE_RATIO,GROSSLOANS,TOTAL_ASSETS_PK"
        ),
        "filter": f'(SECUCODE="{secucode}")(REPORT_TYPE="年报")',
        "p": 1,
        "ps": 30,
        "sr": -1,
        "st": "REPORT_DATE",
    }
    try:
        import requests as _req
        r = _req.get(url, params=params, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
    except Exception:
        return {}
    rows = (d.get("result") or {}).get("data") or []
    result: Dict[str, Dict] = {}
    for row in rows:
        rd = str(row.get("REPORT_DATE", ""))[:10]  # "2024-12-31"
        if len(rd) < 10:
            continue
        year_col = rd[:4] + "1231"
        entry: Dict[str, Optional[float]] = {}
        entry["nim"] = row.get("NET_INTEREST_MARGIN")
        entry["npl_ratio"] = row.get("NONPERLOAN")
        entry["provision_loan_ratio"] = row.get("LOAN_PROVISION_RATIO")
        entry["provision_coverage_ratio"] = row.get("BLDKBBL")
        entry["capital_adequacy_ratio"] = row.get("HXYJBCZL")
        entry["tier1_adequacy_ratio"] = row.get("FIRST_ADEQUACY_RATIO")
        entry["cost_income_ratio"] = row.get("REVENUE_RATIO")
        entry["net_interest_spread"] = row.get("NET_INTEREST_SPREAD")
        # Derived: loan loss allowance = PCR × NPL amount / 100
        _pcr = row.get("BLDKBBL")
        _npl_amt = row.get("NON_PERFORMING_LOAN")
        entry["loan_loss_allowance"] = (_pcr * _npl_amt / 100) if _pcr and _npl_amt else None
        entry["total_loans"] = row.get("GROSSLOANS")
        entry["npl_amount"] = _npl_amt
        entry["em_total_assets"] = row.get("TOTAL_ASSETS_PK")
        result[year_col] = entry
    return result


def fetch_bank_kpi(data: Dict[str, pd.DataFrame], annual_cols: List[str]) -> Dict[str, Dict]:
    """
    Compute bank-specific KPIs per year from existing Sina financial statements.
    Returns {year_col: {nim, cost_income_ratio, npl_ratio, provision_coverage, ...}}.
    """
    income_raw = data.get("income_raw")
    balance_raw = data.get("balance_raw")
    abs_df = data.get("abstract")
    result: Dict[str, Dict] = {}

    for col in annual_cols:
        kpi: Dict[str, Optional[float]] = {}

        # --- From income statement ---
        revenue = _get_sina_val(income_raw, "营业收入", col)
        net_interest_income = _get_sina_val(income_raw, "净利息收入", col)
        interest_income = _get_sina_val(income_raw, "利息收入", col)
        interest_expense = _get_sina_val(income_raw, "利息支出", col)
        biz_admin_expense = _get_sina_val(income_raw, "业务及管理费用", col)
        credit_impairment = _get_sina_val(income_raw, "信用减值损失", col)
        pretax = _get_sina_val(income_raw, "利润总额", col)
        tax = _get_sina_val(income_raw, "减:所得税", col)
        if tax is None:
            tax = _get_sina_val(income_raw, "所得税", col)
        net_profit_parent = _get_sina_val(income_raw, "归属于母公司的净利润", col)

        # Cost-Income Ratio = 业务及管理费用 / 营业收入 × 100%
        if biz_admin_expense is not None and revenue and revenue > 0:
            kpi["cost_income_ratio"] = biz_admin_expense / revenue * 100
        else:
            kpi["cost_income_ratio"] = None

        # --- From balance sheet ---
        total_assets = _get_sina_val(balance_raw, "资产总计", col)
        gross_loans = _get_sina_val(balance_raw, "发放贷款及垫款", col)
        loan_provisions = _get_sina_val(balance_raw, "减:贷款损失准备", col)
        net_loans = _get_sina_val(balance_raw, "发放贷款及垫款净额", col)
        deposits = _get_sina_val(balance_raw, "客户存款(吸收存款)", col)
        parent_equity = _get_sina_val(balance_raw, "归属于母公司股东的权益", col)
        total_liabilities = _get_sina_val(balance_raw, "负债合计", col)

        # NIM proxy: 净利息收入 / 总资产 × 100% (simplified; true NIM uses avg earning assets)
        if net_interest_income is not None and total_assets and total_assets > 0:
            kpi["nim"] = net_interest_income / total_assets * 100
        else:
            kpi["nim"] = None

        # NPL ratio proxy: (gross_loans - net_loans) / gross_loans is NOT NPL.
        # loan_provisions / gross_loans = provision ratio (拨贷比)
        # For NPL, we need "不良贷款" which isn't directly in statements.
        # Use provision_coverage as a safer single metric.
        kpi["npl_ratio"] = None  # Not available from statements alone

        # Provision-to-Loan ratio (拨贷比) = 贷款损失准备 / 发放贷款及垫款 × 100%
        if loan_provisions is not None and gross_loans and gross_loans > 0:
            kpi["provision_loan_ratio"] = loan_provisions / gross_loans * 100
        else:
            kpi["provision_loan_ratio"] = None

        # Loan-to-Deposit ratio = 发放贷款 / 客户存款 × 100%
        if gross_loans is not None and deposits and deposits > 0:
            kpi["loan_deposit_ratio"] = gross_loans / deposits * 100
        else:
            kpi["loan_deposit_ratio"] = None

        # ROA (from abstract is more accurate, but we store total_assets for reference)
        kpi["total_assets"] = total_assets
        kpi["parent_equity"] = parent_equity
        kpi["gross_loans"] = gross_loans
        kpi["deposits"] = deposits
        kpi["net_interest_income"] = net_interest_income
        kpi["interest_income"] = interest_income
        kpi["interest_expense"] = interest_expense
        kpi["biz_admin_expense"] = biz_admin_expense
        kpi["credit_impairment"] = credit_impairment
        kpi["loan_provisions"] = loan_provisions
        kpi["revenue"] = revenue
        kpi["pretax_profit"] = pretax
        kpi["net_profit_parent"] = net_profit_parent

        # --- ROTCE components from balance sheet ---
        goodwill = _get_sina_val(balance_raw, "商誉", col)
        intangible_assets = _get_sina_val(balance_raw, "无形资产", col)
        kpi["goodwill"] = goodwill
        kpi["intangible_assets"] = intangible_assets

        # Effective tax rate
        if pretax and pretax > 0 and tax is not None:
            kpi["eff_tax_rate"] = tax / pretax * 100
        else:
            kpi["eff_tax_rate"] = None

        # Leverage ratio = total_assets / parent_equity
        if total_assets and parent_equity and parent_equity > 0:
            kpi["leverage_ratio"] = total_assets / parent_equity
            kpi["capital_buffer_ratio"] = parent_equity / total_assets * 100
        else:
            kpi["leverage_ratio"] = None
            kpi["capital_buffer_ratio"] = None

        kpi["provision_coverage_ratio"] = get_metric_first(
            abs_df,
            col,
            "拨备覆盖率",
            "拨备覆盖率(%)",
            "贷款拨备覆盖率",
            "贷款损失准备覆盖率",
        ) if abs_df is not None else None
        kpi["capital_adequacy_ratio"] = get_metric_first(
            abs_df,
            col,
            "资本充足率",
            "资本充足率(%)",
            "资本充足率CAP",
            "一级资本充足率",
            "一级资本充足率(%)",
            "核心一级资本充足率",
            "核心一级资本充足率(%)",
            "普通股一级资本充足率",
            "普通股一级资本充足率(%)",
        ) if abs_df is not None else None

        result[col] = kpi

    return result

def build_year_data_for_valuation(data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
    cached = data.get("year_data")
    if isinstance(cached, dict) and cached:
        return cached
    abs_df = data["abstract"]
    cf_extras = data["cashflow_extras"]
    bs_extras = data["balance_extras"]
    inc_extras = data["income_extras"]

    cf_map = {}
    if cf_extras is not None and not cf_extras.empty:
        tmp = cf_extras.copy()
        tmp["报告日"] = tmp["报告日"].astype(str)
        cf_map = {str(row["报告日"]): row for _, row in tmp.iterrows()}

    bs_map = {}
    if bs_extras is not None and not bs_extras.empty:
        tmp = bs_extras.copy()
        tmp["报告日"] = tmp["报告日"].astype(str)
        bs_map = {str(row["报告日"]): row for _, row in tmp.iterrows()}

    inc_map = {}
    if inc_extras is not None and not inc_extras.empty:
        tmp = inc_extras.copy()
        tmp["报告日"] = tmp["报告日"].astype(str)
        inc_map = {str(row["报告日"]): row for _, row in tmp.iterrows()}

    out: Dict[str, Dict] = {}
    for c in annual_cols_from_abstract(abs_df):
        cf_r = cf_map.get(c)
        ocf_v = safe_float(get_metric(abs_df, "经营现金流量净额", c))
        if ocf_v is None and cf_r is not None and "ocf" in cf_r:
            ocf_v = safe_float(cf_r["ocf"])
        profit_v = safe_float(get_metric(abs_df, "归母净利润", c))
        eps_v = safe_float(get_metric(abs_df, "基本每股收益", c))
        roe_v = safe_float(get_metric_first(abs_df, c, "净资产收益率(ROE)", "净资产收益率_平均"))
        equity_v = safe_float(get_metric(abs_df, "股东权益合计(净资产)", c))
        if profit_v is None or eps_v is None or abs(profit_v) < 1e6 or abs(eps_v) < 1e-6:
            continue
        raw_shares = (profit_v / eps_v) if eps_v else None
        bs_r = bs_map.get(c)
        inc_r = inc_map.get(c)
        out[c] = {
            "ocf": ocf_v,
            "capex": safe_float(cf_r["capex"]) if cf_r is not None and "capex" in cf_r else None,
            "shares": raw_shares,
            "reported_shares": raw_shares,
            "reported_shares_source": "profit_over_eps_derived",
            "reported_shares_semantics": "derived_from_eps",
            "share_basis_confidence": "low",
            "profit": profit_v,
            "roe": roe_v,
            "roa": safe_float(get_metric_first(abs_df, c, "总资产报酬率(ROA)", "总资产报酬率", "总资产净利率_平均")),
            "revenue": safe_float(inc_r["revenue"]) if inc_r is not None and "revenue" in inc_r.index else None,
            "dividends_paid": safe_float(cf_r["dividends_paid"]) if cf_r is not None and "dividends_paid" in cf_r else None,
            "div_reliable": bool(cf_r["div_reliable"]) if cf_r is not None and "div_reliable" in cf_r else False,
            "da": safe_float(cf_r["da"]) if cf_r is not None and "da" in cf_r else 0.0,
            "buyback_cash": safe_float(cf_r["buyback_cash"]) if cf_r is not None and "buyback_cash" in cf_r else 0.0,
            "equity_inflow_cash": safe_float(cf_r["equity_inflow_cash"]) if cf_r is not None and "equity_inflow_cash" in cf_r else 0.0,
            "taxes_paid_cash": safe_float(cf_r["taxes_paid_cash"]) if cf_r is not None and "taxes_paid_cash" in cf_r else 0.0,
            "net_cash": safe_float(bs_r["net_cash"]) if bs_r is not None and "net_cash" in bs_r else None,
            "due_debt_principal": safe_float(bs_r["due_debt_principal"]) if bs_r is not None and "due_debt_principal" in bs_r else 0.0,
            "goodwill": safe_float(bs_r["goodwill"]) if bs_r is not None and "goodwill" in bs_r else 0.0,
            "equity_net_bs": safe_float(bs_r["equity_net_bs"]) if bs_r is not None and "equity_net_bs" in bs_r else None,
            "equity_total": equity_v,
            "int_debt": safe_float(bs_r["interest_debt"]) if bs_r is not None and "interest_debt" in bs_r else 0.0,
            "op_profit": safe_float(inc_r["operating_profit"]) if inc_r is not None and "operating_profit" in inc_r else None,
            "fin_cost": safe_float(inc_r["finance_cost"]) if inc_r is not None and "finance_cost" in inc_r else None,
            "pretax": safe_float(inc_r["pretax_profit"]) if inc_r is not None and "pretax_profit" in inc_r else None,
            "tax": safe_float(inc_r["tax_expense"]) if inc_r is not None and "tax_expense" in inc_r else None,
            "rnd_expense": safe_float(inc_r["rnd_expense"]) if inc_r is not None and "rnd_expense" in inc_r else 0.0,
        }
    if data.get("is_bank") and out:
        bank_kpi_map = fetch_bank_kpi(data, [c for c in annual_cols_from_abstract(abs_df) if c in out])
        for col, bank_extra in bank_kpi_map.items():
            if col not in out:
                continue
            out[col].update(
                {
                    "nim": bank_extra.get("nim"),
                    "cost_income_ratio": bank_extra.get("cost_income_ratio"),
                    "provision_loan_ratio": bank_extra.get("provision_loan_ratio"),
                    "provision_coverage_ratio": bank_extra.get("provision_coverage_ratio"),
                    "loan_deposit_ratio": bank_extra.get("loan_deposit_ratio"),
                    "leverage_ratio": bank_extra.get("leverage_ratio"),
                    "capital_adequacy_ratio": bank_extra.get("capital_adequacy_ratio"),
                    "capital_buffer_ratio": bank_extra.get("capital_buffer_ratio"),
                    "total_assets": bank_extra.get("total_assets"),
                    "parent_equity": bank_extra.get("parent_equity"),
                }
            )
    # ── D&A 零值插值修复 ─────────────────────────────────
    # 部分数据源对特定年份的折旧摊销返回 0（实为未报告），
    # 当前后年份均有正值时，用线性插值填补，避免 OE 计算失真。
    sorted_cols = sorted(out.keys())
    for i, col in enumerate(sorted_cols):
        if out[col].get("da") not in (0.0, 0, None):
            continue
        # 向前找最近的正 DA
        prev_da, prev_idx = None, None
        for j in range(i - 1, -1, -1):
            v = out[sorted_cols[j]].get("da")
            if v is not None and v > 0:
                prev_da, prev_idx = v, j
                break
        # 向后找最近的正 DA
        next_da, next_idx = None, None
        for j in range(i + 1, len(sorted_cols)):
            v = out[sorted_cols[j]].get("da")
            if v is not None and v > 0:
                next_da, next_idx = v, j
                break
        if prev_da is not None and next_da is not None:
            span = next_idx - prev_idx
            frac = (i - prev_idx) / span
            out[col]["da"] = prev_da + (next_da - prev_da) * frac
        elif prev_da is not None:
            out[col]["da"] = prev_da
        elif next_da is not None:
            out[col]["da"] = next_da
    data["year_data"] = out
    return out

def build_pb_history_post_may(code: str, abs_df: pd.DataFrame, max_fiscal_years: int = 10, daily_years_back: int = 12) -> List[float]:
    daily = fetch_stock_daily_hist_long(code, years_back=daily_years_back)
    if daily.empty:
        return []
    hist_pb: List[float] = []
    cols_desc = sorted(annual_cols_from_abstract(abs_df), reverse=True)[: max(1, int(max_fiscal_years))]
    for col in cols_desc:
        fy = int(str(col)[:4])
        px = _first_close_on_or_after(daily, fy + 1, 5, 1)
        bps = safe_float(get_metric_first(abs_df, col, "每股净资产", "每股净资产_最新股数"))
        if px is None or px <= 0 or bps is None or bps <= 0:
            continue
        pb = px / bps
        if 0 < pb < 500:
            hist_pb.append(pb)
    return hist_pb

def build_pb_percentile_history_post_may(
    code: str,
    abs_df: pd.DataFrame,
    current_pb: Optional[float],
    max_fiscal_years: int = 10,
    daily_years_back: int = 12,
) -> Dict[str, object]:
    note = "历史样本：各年 BPS 来自财务摘要；股价取次年5月1日起首笔收盘；当前PB使用最新股价 ÷ 最新BPS。"
    payload: Dict[str, object] = {
        "note": note,
        "points": [],
        "current_value": current_pb,
        "percentile": None,
        "sample_count": 0,
        "hist_min": None,
        "hist_median": None,
        "hist_max": None,
        "current_vs_median_pct": None,
        "method": "post_may_anchor",
    }
    if abs_df is None or abs_df.empty or current_pb is None or current_pb <= 0:
        return payload

    daily = fetch_stock_daily_hist_long(code, years_back=daily_years_back)
    if daily.empty:
        payload["note"] = note + " 日线获取失败。"
        return payload

    points: List[Dict[str, object]] = []
    hist_pb: List[float] = []
    last_dt = daily["dt"].max()
    cols = annual_cols_from_abstract(abs_df)[-max(1, int(max_fiscal_years)):]
    for col in cols:
        fy = int(str(col)[:4])
        if pd.Timestamp(year=fy + 1, month=5, day=1) > last_dt:
            continue
        record = _first_close_record_on_or_after(daily, fy + 1, 5, 1)
        if record is None:
            continue
        price_date, px = record
        bps = safe_float(get_metric_first(abs_df, col, "每股净资产", "每股净资产_最新股数"))
        pb = (px / bps) if px is not None and px > 0 and bps is not None and bps > 0 else None
        if pb is not None and 0 < pb < 500:
            hist_pb.append(float(pb))
        points.append(
            {
                "fiscal_year": str(fy),
                "anchor_date": price_date,
                "anchor_price": px,
                "bps": bps,
                "value": pb,
            }
        )

    payload["points"] = points
    payload["sample_count"] = len(hist_pb)
    if len(hist_pb) < 3:
        payload["note"] = note + f" 有效PB样本不足{len(hist_pb)}个。"
        return payload

    hist_median = float(statistics.median(hist_pb))
    payload["percentile"] = _low_value_percentile_score(float(current_pb), hist_pb)
    payload["hist_min"] = min(hist_pb)
    payload["hist_median"] = hist_median
    payload["hist_max"] = max(hist_pb)
    if hist_median > 0:
        payload["current_vs_median_pct"] = (float(current_pb) / hist_median - 1.0) * 100.0
    return payload

def build_dividend_yield_percentile_history_post_may(
    code: str,
    year_data: Dict[str, Dict],
    current_dividend_yield_pct: Optional[float],
    max_fiscal_years: int = 10,
    daily_years_back: int = 12,
) -> Dict[str, object]:
    note = "历史样本：股息取当年现金分红；股价取次年5月1日起首笔收盘；当前股息率使用最新年度现金分红 ÷ 最新市值。"
    payload: Dict[str, object] = {
        "note": note,
        "points": [],
        "current_value": current_dividend_yield_pct,
        "percentile": None,
        "sample_count": 0,
        "hist_min": None,
        "hist_median": None,
        "hist_max": None,
        "current_vs_median_pct": None,
        "method": "post_may_anchor",
    }
    if not year_data or current_dividend_yield_pct is None or current_dividend_yield_pct <= 0:
        return payload

    daily = fetch_stock_daily_hist_long(code, years_back=daily_years_back)
    if daily.empty:
        payload["note"] = note + " 日线获取失败。"
        return payload

    points: List[Dict[str, object]] = []
    hist_yield: List[float] = []
    last_dt = daily["dt"].max()
    cols = sorted(year_data.keys())[-max(1, int(max_fiscal_years)):]
    for col in cols:
        fy = int(str(col)[:4])
        if pd.Timestamp(year=fy + 1, month=5, day=1) > last_dt:
            continue
        record = _first_close_record_on_or_after(daily, fy + 1, 5, 1)
        if record is None:
            continue
        price_date, px = record
        row = year_data.get(col) or {}
        div_paid = safe_float(row.get("dividends_paid"))
        shares = safe_float(row.get("shares"))
        market_cap = (px * shares) if px is not None and px > 0 and shares is not None and shares > 0 else None
        dy = (div_paid / market_cap * 100) if div_paid is not None and div_paid > 0 and market_cap is not None and market_cap > 0 else None
        if dy is not None and 0 < dy < 100:
            hist_yield.append(float(dy))
        points.append(
            {
                "fiscal_year": str(fy),
                "anchor_date": price_date,
                "anchor_price": px,
                "dividends_paid": div_paid,
                "shares": shares,
                "value": dy,
            }
        )

    payload["points"] = points
    payload["sample_count"] = len(hist_yield)
    if len(hist_yield) < 3:
        payload["note"] = note + f" 有效股息率样本不足{len(hist_yield)}个。"
        return payload

    hist_median = float(statistics.median(hist_yield))
    payload["percentile"] = _high_value_percentile_score(float(current_dividend_yield_pct), hist_yield)
    payload["hist_min"] = min(hist_yield)
    payload["hist_median"] = hist_median
    payload["hist_max"] = max(hist_yield)
    if hist_median > 0:
        payload["current_vs_median_pct"] = (float(current_dividend_yield_pct) / hist_median - 1.0) * 100.0
    return payload

def infer_asset_style(industry_text: str) -> str:
    heavy_keywords = ("银行", "保险", "煤炭", "钢铁", "有色", "石油", "化工", "电力", "交运", "建筑", "地产", "机械", "制造", "资源")
    text = (industry_text or "").strip()
    return "heavy" if any(k in text for k in heavy_keywords) else "light"

def fetch_market_pe_anchor() -> Tuple[Optional[float], Optional[str]]:
    if _dp.fetch_market_pe_anchor is not None:
        return _dp.fetch_market_pe_anchor()
    def remember(value: float, label: str) -> Tuple[float, str]:
        try:
            MARKET_PE_ANCHOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
            MARKET_PE_ANCHOR_CACHE.write_text(
                json.dumps(
                    {
                        "value": float(value),
                        "label": label,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        return float(value), label

    for _ in range(3):
        try:
            r = requests.get(
                f"https://qt.gtimg.cn/q={','.join(A_MARKET_PE_SAMPLE)}",
                timeout=8,
                headers={"Referer": "https://gu.qq.com"},
            )
            vals = []
            for quote in [chunk for chunk in r.text.split(";") if "~" in chunk]:
                try:
                    parts = quote.split('"')[1].split("~")
                    pe = safe_float(parts[39]) if len(parts) > 39 else None
                    if pe is not None and 0 < pe < 200:
                        vals.append(pe)
                except Exception:
                    continue
            if len(vals) >= 5:
                return remember(float(pd.Series(vals).median()), f"A股代表样本PE中位数（腾讯行情，n={len(vals)}）")
        except Exception:
            time.sleep(0.3)

    try:
        df = _stock_zh_a_spot_em_cached().copy()
        if df is None or df.empty:
            raise ValueError("empty spot")
        pe_col = None
        for cand in ("市盈率-动态", "市盈率", "市盈率动态"):
            if cand in df.columns:
                pe_col = cand
                break
        if pe_col is None:
            raise ValueError("missing pe column")
        vals = pd.to_numeric(df[pe_col], errors="coerce")
        vals = vals[(vals > 0) & (vals < 200)]
        if len(vals) >= 100:
            return remember(float(vals.median()), "A股全市场动态PE中位数")
    except Exception:
        pass
    try:
        cached = json.loads(MARKET_PE_ANCHOR_CACHE.read_text(encoding="utf-8"))
        value = safe_float(cached.get("value"))
        if value is not None and value > 0:
            label = str(cached.get("label") or "A股市场PE锚点")
            updated_at = str(cached.get("updated_at") or "")
            suffix = f"，缓存于{updated_at}" if updated_at else "，缓存值"
            return value, f"{label}{suffix}"
    except Exception:
        pass
    return None, None

def current_assets_and_liabilities(balance_df: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    if balance_df is None or balance_df.empty:
        return None, None
    latest = balance_df.sort_values("报告日").iloc[-1]
    ca = None
    tl = None
    for col in ("流动资产合计", "流动资产"):
        if col in balance_df.columns:
            ca = safe_float(latest[col])
            if ca is not None:
                break
    for col in ("负债合计", "总负债", "负债总计"):
        if col in balance_df.columns:
            tl = safe_float(latest[col])
            if tl is not None:
                break
    return ca, tl

def _normalize_a_valuation_shares(code: str, year_data: Dict[str, Dict]) -> Dict[str, float]:
    """
    A 股历史估值分母修复：从巨潮股本变动接口获取逐年实际期末总股本，
    替代原 profit/eps 倒推法，避免高送转/EPS 追溯调整导致的虚假断点。

    A 股每日行情使用不复权收盘价（nfq），因此估值分母应与之配套使用
    「实际历史总股本」，而非追溯调整后的 EPS 导出股本。

    返回 {年度列: 实际总股本（股）} 字典；
    若接口异常或数据不足，返回空字典，下游保留 shares=profit/eps 兜底。
    """
    if not year_data:
        return {}
    try:
        df = _stock_share_change_cninfo_cached(str(code).zfill(6))
    except Exception:
        return {}
    if df is None or df.empty or "变动日期" not in df.columns or "总股本" not in df.columns:
        return {}
    dfc = df.copy()
    dfc["_dt"] = pd.to_datetime(dfc["变动日期"], errors="coerce")
    dfc = dfc[dfc["_dt"].notna()].sort_values("_dt")
    if dfc.empty:
        return {}
    result: Dict[str, float] = {}
    for col in year_data:
        as_of = pd.Timestamp(f"{col[:4]}-12-31")
        rows_before = dfc[dfc["_dt"] <= as_of]
        if rows_before.empty:
            continue
        latest_row = rows_before.iloc[-1]
        shares = _parse_cninfo_share_count(latest_row.get("总股本"))
        if shares is not None and shares > 0:
            result[col] = shares
    return result


def fetch_share_change_history_safe(code: str) -> Tuple[pd.DataFrame, str]:
    if _dp.fetch_share_change_history is not None:
        return _dp.fetch_share_change_history(code)
    try:
        df = _stock_share_change_cninfo_cached(str(code).zfill(6)).copy()
        if df is None or df.empty:
            return pd.DataFrame(), "not_found"
        return df, "ok"
    except Exception:
        return pd.DataFrame(), "error"

def fetch_restricted_release_queue_safe(code: str) -> Tuple[pd.DataFrame, str]:
    if _dp.fetch_restricted_release_queue is not None:
        return _dp.fetch_restricted_release_queue(code)
    try:
        df = _stock_restricted_release_queue_em_cached(str(code).zfill(6)).copy()
        if df is None or df.empty:
            return pd.DataFrame(), "not_found"
        return df, "ok"
    except Exception:
        return pd.DataFrame(), "error"
