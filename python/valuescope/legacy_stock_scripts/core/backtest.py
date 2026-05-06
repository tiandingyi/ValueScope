# core/backtest.py — As-of backtest: 多年时点回放估值 vs 实际回报
"""
对指定股票在 [start_year, end_year] 范围内逐年做 as-of 估值回放，
提取 OE-DCF 内在价值 / 芒格远景 / 低估共振等核心信号，
并对比 1Y / 3Y 后的实际股价变化，生成回测汇总表。

用法：
  python3 run.py 000858 --backtest
  python3 run.py 000858 --backtest --bt-start 2016 --bt-end 2023
"""
from __future__ import annotations

import copy
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import (
    DISCOUNT_RATE, TERMINAL_GROWTH, PROJECTION_YEARS,
    _compute_dynamic_mos, _get_industry_discount, _get_industry_exit_pes,
    _get_maint_capex_floor_ratio, DataProvider, _dp,
)
from valuescope.legacy_stock_scripts.core.utils import (
    safe_float, is_bank,
)
from valuescope.legacy_stock_scripts.core.data_a import (
    get_company_info, load_data,
    fetch_bank_kpi, fetch_eastmoney_bank_data,
    annual_cols_from_abstract,
    _filter_data_as_of_year, get_historical_price_as_of,
)
from valuescope.legacy_stock_scripts.core.orchestrator import build_year_rows
from valuescope.legacy_stock_scripts.core.assessment import (
    build_summary_metrics, build_bank_summary_metrics,
    build_extended_diagnostics,
)
from valuescope.legacy_stock_scripts.core.valuation import (
    build_valuation_assessments, build_valuation_conclusion,
)


def _get_future_price(code: str, base_year: int, delta_years: int) -> Optional[float]:
    """获取 base_year + delta_years 年末的股价。"""
    target_year = base_year + delta_years
    now_year = pd.Timestamp.now().year
    if target_year > now_year:
        return None
    target_date = pd.Timestamp(f"{target_year}-12-31")
    result = get_historical_price_as_of(code, target_date)
    if result is None:
        return None
    px = result[0] if isinstance(result, tuple) else result
    return safe_float(px)


def _determine_backtest_range(
    data: Dict, start_year: Optional[int], end_year: Optional[int],
) -> Tuple[int, int]:
    """从数据中推断可用的回测年份范围。"""
    abs_df = data.get("abstract")
    if abs_df is None or abs_df.empty:
        raise RuntimeError("无法获取年报数据")
    annual_cols = annual_cols_from_abstract(abs_df)
    if not annual_cols:
        raise RuntimeError("无可用年度列")
    available_years = sorted(int(c[:4]) for c in annual_cols if len(c) >= 4 and c[:4].isdigit())
    if not available_years:
        raise RuntimeError("无可用年份")
    # 至少需要 5 年历史数据才能做有意义的估值
    min_year = available_years[0] + 4
    max_year = available_years[-1]
    # end_year 默认到最近可用年份（但留出至少 1 年验证期）
    now_year = pd.Timestamp.now().year
    default_end = min(max_year, now_year - 1)
    s = start_year if start_year is not None else min_year
    e = end_year if end_year is not None else default_end
    s = max(s, min_year)
    e = min(e, max_year)
    if s > e:
        raise RuntimeError(f"回测范围无效: {s}–{e}（可用: {min_year}–{max_year}）")
    return s, e


def _run_single_year(
    code: str,
    name: str,
    total_shares: Optional[float],
    industry_text: str,
    data_orig: Dict,
    asof_year: int,
    years: int = 20,
) -> Dict:
    """对单个 as-of 年份执行估值，返回摘要 dict。"""
    data = _filter_data_as_of_year(data_orig, asof_year)
    asof_date = pd.Timestamp(f"{asof_year:04d}-12-31")
    price_result = get_historical_price_as_of(code, asof_date)
    if price_result is None or price_result[0] is None:
        return {"year": asof_year, "error": "无法获取历史股价"}
    price, price_src, price_dt = price_result
    data["current_price_tuple"] = (float(price), price_src, price_dt)

    bank_flag = is_bank(industry_text, name)
    data["is_bank"] = bank_flag
    if bank_flag:
        yd = data.get("year_data")
        if isinstance(yd, dict) and yd:
            bank_kpi_map = fetch_bank_kpi(data, list(yd.keys()))
            data["_bank_kpi_map"] = bank_kpi_map
            for _col, _bk in bank_kpi_map.items():
                if _col in yd:
                    yd[_col].update({k: _bk.get(k) for k in (
                        "nim", "cost_income_ratio", "provision_loan_ratio",
                        "provision_coverage_ratio", "loan_deposit_ratio",
                        "leverage_ratio", "capital_adequacy_ratio",
                        "capital_buffer_ratio", "total_assets", "parent_equity",
                    )})
            em_bank = fetch_eastmoney_bank_data(code)
            for _col, _em in em_bank.items():
                if _col in yd:
                    for _k, _v in _em.items():
                        if _v is not None:
                            yd[_col][_k] = _v
            data["_em_bank"] = em_bank

    rows = build_year_rows(data, years)
    if not rows:
        return {"year": asof_year, "error": "年报数据不足"}

    # 估值参数
    maint_capex_ratio, _ = _get_maint_capex_floor_ratio(industry_text, name)
    diagnostics = build_extended_diagnostics(code, data, total_shares, max(4, years), maint_capex_ratio=maint_capex_ratio)

    valuation_shares = total_shares
    diag_year_data = diagnostics.get("year_data") or {}
    diag_annual_cols = diagnostics.get("annual_cols") or []
    preferred_share_key = "asof_shares" if data.get("_share_basis_mode") == "asof" else "valuation_shares"
    if valuation_shares is None and diag_annual_cols:
        latest_diag = diag_year_data.get(diag_annual_cols[-1]) or {}
        valuation_shares = safe_float(latest_diag.get(preferred_share_key))
        if valuation_shares is None:
            valuation_shares = safe_float(latest_diag.get("reported_shares"))
    if valuation_shares is None:
        share_capital_diag = diagnostics.get("share_capital") if isinstance(diagnostics, dict) else None
        if isinstance(share_capital_diag, dict):
            share_rows = share_capital_diag.get("rows") or []
            if isinstance(share_rows, list) and share_rows:
                latest_share_row = share_rows[-1]
                total_diag_shares = safe_float(latest_share_row.get("total_shares")) if isinstance(latest_share_row, dict) else None
                if total_diag_shares is not None and total_diag_shares > 0:
                    valuation_shares = total_diag_shares
    if valuation_shares is None:
        valuation_shares = safe_float(diagnostics.get("shares")) if isinstance(diagnostics, dict) else None

    if bank_flag:
        metrics, stats = build_bank_summary_metrics(rows, data)
    else:
        metrics, stats = build_summary_metrics(rows)

    dynamic_mos, mos_grade = _compute_dynamic_mos(metrics)
    ind_discount, _ = _get_industry_discount(industry_text)
    ind_exit_pes, _ = _get_industry_exit_pes(industry_text)
    valuation_metrics, valuation_details = build_valuation_assessments(
        code, name, industry_text, valuation_shares, data,
        mos=dynamic_mos, discount_rate=ind_discount, exit_pes=ind_exit_pes,
    )

    # 提取关键估值数据
    snap = valuation_details.get("snap")
    resonances = valuation_details.get("resonances") or []

    dcf_iv = None
    munger_iv = None
    if snap is not None:
        dcf_iv = safe_float(snap.get("buf_total"))
        # 芒格远景取中档 PE
        mid_pe = ind_exit_pes[1]
        munger_dict = snap.get("munger") or {}
        munger_iv = safe_float(munger_dict.get(mid_pe))

    gordon_iv = safe_float(valuation_details.get("gordon_iv"))

    # 判定信号
    n_resonances = len(resonances)
    if dcf_iv is not None and price > 0:
        mos_price = dcf_iv * (1 - dynamic_mos)
        if price < mos_price:
            dcf_signal = "低估(安全边际内)"
        elif price < dcf_iv:
            dcf_signal = "合理偏低"
        else:
            dcf_signal = "高估"
    else:
        dcf_signal = "N/A"

    return {
        "year": asof_year,
        "price": round(price, 2),
        "price_dt": price_dt,
        "dcf_iv": round(dcf_iv, 2) if dcf_iv else None,
        "munger_iv": round(munger_iv, 2) if munger_iv else None,
        "gordon_iv": round(gordon_iv, 2) if gordon_iv else None,
        "dcf_signal": dcf_signal,
        "n_resonances": n_resonances,
        "mos": round(dynamic_mos * 100, 1),
        "is_bank": bank_flag,
    }


def run_backtest(
    code: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    years: int = 20,
) -> Dict:
    """
    主入口：对 code 在 [start_year, end_year] 逐年执行 as-of 估值并收集实际回报。

    返回::

        {
            "code": "000858",
            "name": "五粮液",
            "industry": "白酒",
            "results": [ { year, price, dcf_iv, ..., ret_1y, ret_3y }, ... ],
        }
    """
    t0 = time.perf_counter()
    name, total_shares, industry_text = get_company_info(code)
    data_orig = load_data(code)
    s, e = _determine_backtest_range(data_orig, start_year, end_year)

    results: List[Dict] = []
    for yr in range(s, e + 1):
        print(f"  回测 {yr} ...", end=" ", flush=True)
        try:
            row = _run_single_year(code, name, total_shares, industry_text, data_orig, yr, years)
        except Exception as ex:
            row = {"year": yr, "error": str(ex)}
        # 获取未来实际价格
        if "error" not in row:
            px = row["price"]
            for delta, key in ((1, "ret_1y"), (3, "ret_3y")):
                future_px = _get_future_price(code, yr, delta)
                if future_px is not None and px > 0:
                    row[f"px_{delta}y"] = round(future_px, 2)
                    row[key] = round((future_px / px - 1) * 100, 1)
                else:
                    row[f"px_{delta}y"] = None
                    row[key] = None
        results.append(row)
        status = row.get("error") or row.get("dcf_signal", "")
        print(status)

    elapsed = time.perf_counter() - t0
    return {
        "code": code,
        "name": name,
        "industry": industry_text,
        "start_year": s,
        "end_year": e,
        "elapsed": round(elapsed, 1),
        "results": results,
    }


# ──────────────────── 输出格式化 ────────────────────


def _fmt(v, suffix="", width=8):
    if v is None:
        return "—".center(width)
    return f"{v}{suffix}".rjust(width)


def print_backtest_table(bt: Dict) -> None:
    """将回测结果以紧凑 ASCII 表格输出到 stdout。"""
    print(f"\n{'=' * 80}")
    print(f"  回测汇总: {bt['name']}({bt['code']})  行业: {bt['industry']}")
    print(f"  范围: {bt['start_year']}–{bt['end_year']}  耗时: {bt['elapsed']}s")
    print(f"{'=' * 80}")

    # Header
    hdr = (
        f"{'年份':>6}  {'股价':>8}  {'DCF-IV':>8}  "
        f"{'芒格-IV':>8}  {'信号':>14}  {'共振':>4}  "
        f"{'1Y回报':>8}  {'3Y回报':>8}"
    )
    print(hdr)
    print("-" * len(hdr))

    ok_rows = []
    for r in bt["results"]:
        if "error" in r:
            print(f"{r['year']:>6}  *** {r['error']}")
            continue
        iv_key = "gordon_iv" if r.get("is_bank") else "dcf_iv"
        iv_val = r.get(iv_key)
        munger_val = r.get("munger_iv")
        print(
            f"{r['year']:>6}  "
            f"{_fmt(r.get('price'), width=8)}  "
            f"{_fmt(iv_val, width=8)}  "
            f"{_fmt(munger_val, width=8)}  "
            f"{str(r.get('dcf_signal', '')):>14}  "
            f"{_fmt(r.get('n_resonances'), width=4)}  "
            f"{_fmt(r.get('ret_1y'), '%', 8)}  "
            f"{_fmt(r.get('ret_3y'), '%', 8)}"
        )
        ok_rows.append(r)

    # 汇总统计
    if ok_rows:
        print("-" * len(hdr))
        under = [r for r in ok_rows if r.get("dcf_signal") in ("低估(安全边际内)",)]
        fair_low = [r for r in ok_rows if r.get("dcf_signal") == "合理偏低"]
        over = [r for r in ok_rows if r.get("dcf_signal") == "高估"]

        def _avg_ret(subset, key):
            vals = [r[key] for r in subset if r.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        print(f"  低估信号 {len(under)} 次 | 合理偏低 {len(fair_low)} 次 | 高估 {len(over)} 次 | N/A {len(ok_rows) - len(under) - len(fair_low) - len(over)} 次")
        if under:
            a1 = _avg_ret(under, "ret_1y")
            a3 = _avg_ret(under, "ret_3y")
            print(f"  低估年份平均回报: 1Y={_fmt(a1, '%')}  3Y={_fmt(a3, '%')}")
        if over:
            a1 = _avg_ret(over, "ret_1y")
            a3 = _avg_ret(over, "ret_3y")
            print(f"  高估年份平均回报: 1Y={_fmt(a1, '%')}  3Y={_fmt(a3, '%')}")
    print()
