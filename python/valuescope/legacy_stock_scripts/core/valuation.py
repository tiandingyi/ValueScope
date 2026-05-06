# core/valuation.py — auto-extracted
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import (
    DISCOUNT_RATE, TERMINAL_GROWTH, PROJECTION_YEARS, MARGIN_OF_SAFETY,
    FADE_RATE, OE_HAIRCUT, G_MAX_CAP, LAST_PROFILE, DEFAULT_EXIT_PE,
    _compute_dynamic_mos, _get_industry_discount, _get_industry_exit_pes,
    MAINT_CAPEX_FLOOR_RATIO, MetricAssessment, ValuationAssessment,
    _dp, _get_rd_capitalization_ratio, _get_maint_capex_floor_ratio,
)
from valuescope.legacy_stock_scripts.core.utils import (
    get_metric, get_metric_first, get_deduct_parent_net_profit,
    get_real_eps, safe_float, fmt_pct, fmt_num, fmt_yi,
    series_values, trend_text, _trend_arrow,
)
from valuescope.legacy_stock_scripts.core.data_a import (
    get_company_info, get_current_price, load_data,
    fetch_cn_10y_government_bond_yield_pct,
    annual_cols_from_abstract, build_year_data_for_valuation,
    fetch_market_pe_anchor, _filter_data_as_of_year,
    build_pe_percentile_history_post_may, build_eps_percentile_history,
    build_pb_percentile_history_post_may,
    build_dividend_yield_percentile_history_post_may,
    current_assets_and_liabilities,
    fetch_stock_daily_hist_long, _close_column,
)


def dcf_two_stage(fcf_per_share, growth_rate, r, g_tv, n):
    if fcf_per_share <= 0 or r <= g_tv:
        return 0.0
    pv1 = sum(fcf_per_share * (1 + growth_rate) ** t / (1 + r) ** t for t in range(1, n + 1))
    fcf_n = fcf_per_share * (1 + growth_rate) ** n
    pv2 = (fcf_n * (1 + g_tv) / (r - g_tv)) / (1 + r) ** n
    return pv1 + pv2

def dcf_zero_growth_perpetuity(oe_per_share: float, r: float) -> Optional[float]:
    if oe_per_share <= 0 or r <= 0:
        return None
    return oe_per_share / r

def dcf_fade(fcf, g_init, r, g_tv, n, fade_rate=FADE_RATE):
    """增长衰减 DCF：g 从 g_init 指数衰减至 g_tv。

    巴菲特假设：竞争优势会逐年削弱，高增长不可能持续 n 年不变。
    fade_rate=0.80 → 每年增长率中"高于终值"的部分衰减 20%。

    同时返回第 n 年末 FCF 和中间派息 PV（供芒格估值复用）。
    """
    if fcf <= 0 or r <= g_tv:
        return 0.0, 0.0, 0.0  # total, oe_n, pv_interim_factor=0
    pv = 0.0
    oe_t = fcf
    pv_div = 0.0  # 中间 OE 折现和（不含 payout，调用者自乘）
    for t in range(1, n + 1):
        blend = fade_rate ** t
        g_t = g_init * blend + g_tv * (1 - blend)
        oe_t *= (1 + g_t)
        disc = (1 + r) ** t
        pv += oe_t / disc
        pv_div += oe_t / disc
    tv = oe_t * (1 + g_tv) / (r - g_tv)
    pv += tv / (1 + r) ** n
    return pv, oe_t, pv_div

def estimate_growth_rate(
    abs_df,
    target_col,
    roe_raw,
    dividends_paid,
    profit,
    div_reliable=True,
    custom_series=None,
    series_label="净利润",
    roic_raw=None,
):
    all_annual = sorted(str(c) for c in abs_df.columns if str(c).endswith("1231"))
    if custom_series is not None:
        profit_seq = [v for v in custom_series if v is not None and v > 0]
    else:
        if target_col not in all_annual:
            return 0.08, "默认8%（未找到列）"
        idx = all_annual.index(target_col)
        window = all_annual[max(0, idx - 6): idx + 1]
        profit_seq = []
        for col in window:
            p = get_metric(abs_df, "归母净利润", col)
            if p is not None and p > 0:
                profit_seq.append(p)
    if len(profit_seq) < 2:
        return 0.08, "数据不足，默认8%"
    yoy = [(profit_seq[i] - profit_seq[i - 1]) / profit_seq[i - 1] for i in range(1, len(profit_seq))]
    median_g = statistics.median(yoy)
    hist_cagr = None
    if len(profit_seq) >= 2 and profit_seq[0] > 0 and profit_seq[-1] > 0:
        periods = len(profit_seq) - 1
        hist_cagr = (profit_seq[-1] / profit_seq[0]) ** (1 / periods) - 1
    # C级：工程上限，避免极端增长率导致估值失真。
    g_ceiling = 0.25
    sgr_cap = None
    quality_anchor = None
    retention = 0.60
    if roe_raw is not None:
        # A级：SGR = ROE * retention（可持续增长约束）。
        roe = roe_raw / 100 if roe_raw > 1 else roe_raw
        if profit and profit > 0 and dividends_paid and dividends_paid > 0:
            payout = min(dividends_paid / profit, 1.0)
            if not div_reliable:
                payout = min(payout, 0.80)
            retention = max(0.40, 1.0 - payout)
        sgr_cap = max(0.0, roe) * retention
        g_ceiling = min(sgr_cap, 0.25)
    if roic_raw is not None:
        # B级：质量锚（ROIC*再投资率）用于交叉校验历史外推。
        roic = roic_raw / 100 if roic_raw > 1 else roic_raw
        quality_anchor = max(0.0, roic) * retention

    # --- 巴菲特-芒格保守交叉法 ---
    # 历史锚 = min(YoY中位数, 历史CAGR)：取历史证据中更保守的那个
    hist_anchors = [median_g]
    if hist_cagr is not None:
        hist_anchors.append(hist_cagr)
    conservative_hist = min(hist_anchors)

    # 质量锚 = min(quality_anchor, sgr_cap)：取资本回报能支撑的更低增速
    qual_anchors = []
    if quality_anchor is not None:
        qual_anchors.append(quality_anchor)
    if sgr_cap is not None:
        qual_anchors.append(sgr_cap)
    conservative_qual = min(qual_anchors) if qual_anchors else None

    # g = min(保守历史, 保守质量)：只为两端都能验证的增速付钱
    if conservative_qual is not None:
        g_base = min(conservative_hist, conservative_qual)
    else:
        g_base = conservative_hist

    # C级：下限保护，避免单年异常把增长率压得过低。
    g = max(-0.05, min(g_base, g_ceiling))
    sgr_note = ""
    if sgr_cap is not None and median_g > sgr_cap:
        sgr_note = f"，受SGR上限{sgr_cap*100:.1f}%截断"
    parts = [f"{series_label}YoY中位数={median_g*100:.1f}%"]
    if hist_cagr is not None:
        parts.append(f"CAGR={hist_cagr*100:.1f}%")
    if conservative_qual is not None:
        parts.append(f"质量锚={conservative_qual*100:.1f}%")
    parts.append(f"保守交叉={g_base*100:.1f}%")
    extra_note = f"，{'，'.join(parts[1:])}"
    return round(g, 4), f"{parts[0]}{extra_note}{sgr_note}"

def compute_cagr(begin_value: Optional[float], end_value: Optional[float], periods: int) -> Optional[float]:
    if begin_value is None or end_value is None or periods <= 0:
        return None
    if begin_value <= 0 or end_value <= 0:
        return None
    try:
        return ((float(end_value) / float(begin_value)) ** (1.0 / float(periods)) - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def _eps_at(abs_df: pd.DataFrame, col: str) -> Tuple[Optional[float], Optional[str]]:
    eps, src = get_real_eps(abs_df, col)
    if eps is None:
        eps = safe_float(get_metric(abs_df, "基本每股收益", col))
        src = src or "基本EPS"
    return eps, src

def build_eps_cagr_snapshot(abs_df: pd.DataFrame, annual_cols: Sequence[str], target_col: str, preferred_years: int = 3) -> Dict[str, object]:
    if abs_df is None or abs_df.empty or target_col not in annual_cols:
        return {}
    idx = annual_cols.index(target_col)
    if idx <= 0:
        return {}
    end_col = target_col
    end_eps, end_src = _eps_at(abs_df, end_col)
    if end_eps is None or end_eps <= 0:
        return {"end_col": end_col, "end_eps": end_eps, "end_src": end_src, "cagr_pct": None, "reason": "end_eps_non_positive"}

    preferred_start_idx = max(0, idx - preferred_years)
    lookback_start_idx = max(0, idx - max(preferred_years * 2, preferred_years))
    candidates = list(range(lookback_start_idx, idx))
    preferred = [i for i in candidates if i == preferred_start_idx]
    others = [i for i in candidates if i != preferred_start_idx]
    ordered = preferred + others

    best = None
    for start_idx in ordered:
        start_col = annual_cols[start_idx]
        begin_eps, begin_src = _eps_at(abs_df, start_col)
        periods = int(end_col[:4]) - int(start_col[:4])
        cagr_pct = compute_cagr(begin_eps, end_eps, periods)
        if cagr_pct is not None:
            best = (start_col, begin_eps, begin_src, periods, cagr_pct)
            break

    if best is None:
        return {"end_col": end_col, "end_eps": end_eps, "end_src": end_src, "cagr_pct": None, "reason": "no_positive_start_eps"}
    start_col, begin_eps, begin_src, periods, cagr_pct = best
    return {
        "start_col": start_col,
        "end_col": end_col,
        "start_eps": begin_eps,
        "end_eps": end_eps,
        "periods": periods,
        "cagr_pct": cagr_pct,
        "start_src": begin_src,
        "end_src": end_src,
    }

def _owner_earnings_company(dc: dict, rd_cap_ratio: float = 0.0, maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO) -> Optional[float]:
    profit = safe_float(dc.get("profit"))
    da_c = safe_float(dc.get("da"))
    cap_c = safe_float(dc.get("capex"))
    if profit is None or da_c is None or cap_c is None:
        return None
    # 研发资本化调节：将扩张性研发加回净利润
    rnd = safe_float(dc.get("rnd_expense")) or 0.0
    adjusted_profit = profit + rnd * rd_cap_ratio
    # C级：维持性Capex工程代理 = max(min(Capex,D&A), maint_capex_ratio*Capex)
    maint_da = min(cap_c, da_c) if da_c > 0 else cap_c
    maint_floor = cap_c * maint_capex_ratio
    maint = max(maint_da, maint_floor)
    return float(adjusted_profit + da_c - maint)

def _owner_earnings_three_caliber(dc: dict, rd_cap_ratio: float = 0.0, maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO):
    """Return (pessimistic, base, lenient) company-level OE, or None if data missing."""
    profit = safe_float(dc.get("profit"))
    da = safe_float(dc.get("da"))
    capex = safe_float(dc.get("capex"))
    if profit is None or da is None or capex is None:
        return None
    # 研发资本化调节：将扩张性研发加回净利润
    rnd = safe_float(dc.get("rnd_expense")) or 0.0
    adjusted_profit = profit + rnd * rd_cap_ratio
    # 悲观OE: NI_adj + D&A - Capex (全部资本开支视为维持性)
    pess = float(adjusted_profit + da - capex)
    # 基准OE: NI_adj + D&A - max(min(Capex, D&A), maint_capex_ratio*Capex)
    maint_da = min(capex, da) if da > 0 else capex
    maint_floor = capex * maint_capex_ratio
    maint_base = max(maint_da, maint_floor)
    base = float(adjusted_profit + da - maint_base)
    # 宽松OE: NI_adj + D&A - min(Capex, D&A)
    maint_len = min(capex, da) if da > 0 else capex
    leni = float(adjusted_profit + da - maint_len)
    return (pess, base, leni)

def compute_buffett_munger_snapshot(col: str, year_data: dict, all_annual_cols_sorted: list, abs_df: pd.DataFrame, r: float, g_tv: float, n: int, shares_for_ps: Optional[float] = None, *, g_fin_cap: Optional[float] = None, include_net_cash_in_iv: bool = True, exit_pes: Tuple[int, int, int] = (15, 20, 25), rd_cap_ratio: float = 0.0, rd_cap_industry: str = "默认", maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO):
    if col not in year_data:
        return None
    idx = all_annual_cols_sorted.index(col)
    w3 = [c for c in all_annual_cols_sorted[max(0, idx - 4): idx + 1] if c in year_data]
    if not w3:
        return None
    sh = float(shares_for_ps) if shares_for_ps is not None else float(year_data[col]["shares"])
    if sh <= 0:
        return None

    # ── OE 三口径体系 (§1.1) ──────────────────────────
    oe_three_vals = [_owner_earnings_three_caliber(year_data[c], rd_cap_ratio, maint_capex_ratio) for c in w3]
    if any(v is None for v in oe_three_vals):
        _null_oe_three = {"pessimistic": None, "base": None, "lenient": None}
        _null_g_three = {"bear": None, "base": None, "bull": None}
        return {
            "w3_len": len(w3),
            "avg_oe_ps": None,
            "oe_three": _null_oe_three,
            "g_bm": None,
            "g_three": _null_g_three,
            "g_hist": None, "g_quality": None,
            "g_note": "Capex缺失，OE-DCF不适用",
            "nc_ps": None,
            "nc_iv": None,
            "include_net_cash_in_iv": include_net_cash_in_iv,
            "g_fin_cap_applied": None,
            "payout": None,
            "payout_src": "Capex缺失",
            "buf_dcf": None,
            "buf_total": None,
            "zero_g_core": None,
            "zero_g_total": None,
            "munger": {exit_pes[0]: None, exit_pes[1]: None, exit_pes[2]: None},
            "pv_interim": None,
            "avg_profit": None,
            "avg_da": None,
            "avg_maint": None,
            "exit_pes": exit_pes,
            "diag_dcf": None, "diag_munger": None,
            "rd_cap_ratio": rd_cap_ratio,
            "rd_cap_adj_total": 0.0,
            "rd_cap_industry": rd_cap_industry,
        }
    # 三口径分别取均值，乘以 OE_HAIRCUT
    avg_oe_pess = sum(v[0] for v in oe_three_vals) / len(w3) * OE_HAIRCUT
    avg_oe_base = sum(v[1] for v in oe_three_vals) / len(w3) * OE_HAIRCUT
    avg_oe_leni = sum(v[2] for v in oe_three_vals) / len(w3) * OE_HAIRCUT
    avg_oe = avg_oe_base  # backward compat
    avg_oe_ps = avg_oe / sh
    pess_oe_ps = avg_oe_pess / sh
    base_oe_ps = avg_oe_ps
    leni_oe_ps = avg_oe_leni / sh
    oe_three = {"pessimistic": pess_oe_ps, "base": base_oe_ps, "lenient": leni_oe_ps}

    nc_raw = year_data[col].get("net_cash")
    nc_ps = (float(nc_raw) / sh) if nc_raw is not None else None
    nc_iv = nc_ps if (nc_ps is not None and include_net_cash_in_iv) else 0.0

    # ── Payout (可用年份均值，先于G计算) ────────────────────
    payout_vals = []
    for c in w3:
        dc = year_data[c]
        if dc["dividends_paid"] and dc["profit"] > 0 and dc["dividends_paid"] > 0:
            p = min(dc["dividends_paid"] / dc["profit"], 1.0)
            p = min(p, 0.80) if not dc["div_reliable"] else p
            payout_vals.append(p)
    payout = sum(payout_vals) / len(payout_vals) if payout_vals else 0.0
    payout = max(0.0, min(payout, 1.0))
    retention = max(0.0, 1.0 - payout)

    # ── 三档增长率 G — 双锚法 (§1.4b) ─────────────────
    d_latest = year_data[col]
    oe_hist_cols = [c for c in all_annual_cols_sorted if c in year_data and c <= col]

    # 历史组: median(营收CAGR, 净利润CAGR, OE CAGR)
    _hist_cagrs = []
    _g_note_parts = []
    # 营收 CAGR
    rev_series = [(c, safe_float(year_data[c].get("revenue"))) for c in oe_hist_cols if c in year_data]
    rev_series = [(c, v) for c, v in rev_series if v is not None and v > 0]
    rev_series = rev_series[-7:]
    if len(rev_series) >= 2:
        _rc = (rev_series[-1][1] / rev_series[0][1]) ** (1 / (len(rev_series) - 1)) - 1
        _hist_cagrs.append(_rc)
        _g_note_parts.append(f"营收CAGR={_rc*100:.1f}%")
    # 净利润 CAGR
    ni_series = [(c, safe_float(year_data[c].get("profit"))) for c in oe_hist_cols if c in year_data]
    ni_series = [(c, v) for c, v in ni_series if v is not None and v > 0]
    ni_series = ni_series[-7:]
    if len(ni_series) >= 2:
        _nc_ = (ni_series[-1][1] / ni_series[0][1]) ** (1 / (len(ni_series) - 1)) - 1
        _hist_cagrs.append(_nc_)
        _g_note_parts.append(f"净利润CAGR={_nc_*100:.1f}%")
    # OE CAGR (基准口径)
    oe_full_series = [v for v in (_owner_earnings_company(year_data[_c], rd_cap_ratio, maint_capex_ratio) for _c in oe_hist_cols) if v is not None]
    oe_trim = oe_full_series[-7:]
    if len(oe_trim) >= 2 and oe_trim[0] > 0 and oe_trim[-1] > 0:
        _oc = (oe_trim[-1] / oe_trim[0]) ** (1 / (len(oe_trim) - 1)) - 1
        _hist_cagrs.append(_oc)
        _g_note_parts.append(f"OE-CAGR={_oc*100:.1f}%")
    g_hist = statistics.median(_hist_cagrs) if _hist_cagrs else None

    # 质量组: avg(ROE×留存, ROIC×留存)
    _qual_vals = []
    roe_raw = d_latest.get("roe")
    roe_dec = roe_raw / 100 if roe_raw is not None and abs(roe_raw) > 1 else roe_raw
    roic_pct = roic_percent_from_year_data(d_latest)
    roic_dec = roic_pct / 100 if roic_pct is not None and abs(roic_pct) > 1 else roic_pct
    if roe_dec is not None:
        _qual_vals.append(max(0.0, roe_dec) * retention)
    if roic_dec is not None:
        _qual_vals.append(max(0.0, roic_dec) * retention)
    g_quality = sum(_qual_vals) / len(_qual_vals) if _qual_vals else None
    if g_quality is not None:
        _g_note_parts.append(f"质量组={g_quality*100:.1f}%")

    # 三档
    if g_hist is not None and g_quality is not None:
        g_bear = min(g_hist, g_quality)
        g_base_3 = g_quality
        g_bull = max(g_hist, g_quality)
    elif g_quality is not None:
        g_bear = g_base_3 = g_bull = g_quality
    elif g_hist is not None:
        g_bear = g_base_3 = g_bull = g_hist
    else:
        g_bear = g_base_3 = g_bull = 0.08  # fallback

    # g_fin_cap 约束
    g_fin_cap_applied = None
    if g_fin_cap is not None and g_fin_cap >= 0:
        if g_base_3 > g_fin_cap:
            g_fin_cap_applied = g_fin_cap
            _g_note_parts.append(f"金融类g封顶{g_fin_cap*100:.1f}%")
        g_bear = min(g_bear, g_fin_cap)
        g_base_3 = min(g_base_3, g_fin_cap)
        g_bull = min(g_bull, g_fin_cap)

    # 硬上限 + 下限（-5%为工程约束：即使企业处于衰退期，仍假设长期不会持续萎缩超过5%/年）
    _cap_note = ""
    if g_base_3 > G_MAX_CAP:
        _cap_note = f"G上限{G_MAX_CAP*100:.0f}%"
    g_bear = max(-0.05, min(g_bear, G_MAX_CAP))
    g_base_3 = max(-0.05, min(g_base_3, G_MAX_CAP))
    g_bull = max(-0.05, min(g_bull, G_MAX_CAP))

    g_bm = g_base_3  # 基准G = 质量组锚
    g_note = "双锚法: " + "，".join(_g_note_parts)
    if _cap_note:
        g_note += f" → {_cap_note}"
    g_three = {"bear": g_bear, "base": g_base_3, "bull": g_bull}

    avg_profit = sum(year_data[c]["profit"] for c in w3) / len(w3)
    avg_da = sum(year_data[c]["da"] for c in w3) / len(w3)
    avg_capex3 = sum(float(year_data[c]["capex"]) for c in w3) / len(w3)
    _avg_maint_da = min(avg_capex3, avg_da) if avg_da > 0 else avg_capex3
    avg_maint = max(_avg_maint_da, avg_capex3 * maint_capex_ratio)
    # A级：DCF/Gordon约束，要求 r > g_t。
    valid_oe = avg_oe_ps > 0 and r > g_tv
    # ── 增长衰减 DCF：假设竞争优势逐年削弱 ──────────────
    buf_dcf_val, oe_year_n, pv_div_factor = dcf_fade(avg_oe_ps, g_bm, r, g_tv, n) if valid_oe else (None, 0.0, 0.0)
    buf_dcf = buf_dcf_val if buf_dcf_val and buf_dcf_val > 0 else None
    raw_buf_total = (buf_dcf + nc_iv) if buf_dcf is not None else None
    buf_total = raw_buf_total if raw_buf_total is not None and raw_buf_total > 0 else None
    munger = {exit_pes[0]: None, exit_pes[1]: None, exit_pes[2]: None}
    raw_munger = {exit_pes[0]: None, exit_pes[1]: None, exit_pes[2]: None}
    pv_interim = None
    if valid_oe:
        # 芒格估值也使用衰减增长，oe_year_n 是第 n 年末的 OE/股
        pv_interim = pv_div_factor * payout
        for pe in exit_pes:
            exit_pv = (oe_year_n * pe) / (1 + r) ** n
            raw_munger[pe] = pv_interim + exit_pv + nc_iv
            munger[pe] = raw_munger[pe] if raw_munger[pe] is not None and raw_munger[pe] > 0 else None

    # ── 对角线值 (§1.5 §2.1): 保守/基准/宽松 ─────────────
    diag_dcf = {"conservative": None, "base": None, "lenient": None}
    diag_munger = {"conservative": None, "base": None, "lenient": None}
    if valid_oe:
        # DCF 对角线
        for _key, _oe_val, _g_val in [("conservative", pess_oe_ps, g_bear), ("base", base_oe_ps, g_base_3), ("lenient", leni_oe_ps, g_bull)]:
            if _oe_val > 0:
                _dv = dcf_fade(_oe_val, _g_val, r, g_tv, n)[0] + nc_iv
                diag_dcf[_key] = _dv if _dv > 0 else None
        # 芒格对角线: 保守=悲观OE×悲观G×低PE, 基准=基准OE×基准G×中PE, 宽松=宽松OE×乐观G×高PE
        _diag_pe = [exit_pes[0], exit_pes[1], exit_pes[2]]
        for _ix, (_key, _oe_val, _g_val) in enumerate([("conservative", pess_oe_ps, g_bear), ("base", base_oe_ps, g_base_3), ("lenient", leni_oe_ps, g_bull)]):
            if _oe_val > 0:
                _ft, _oen, _pvd = dcf_fade(_oe_val, _g_val, r, g_tv, n)
                _pvi = _pvd * payout
                _epv = (_oen * _diag_pe[_ix]) / (1 + r) ** n
                _mv = _pvi + _epv + nc_iv
                diag_munger[_key] = _mv if _mv > 0 else None

    zg_core = dcf_zero_growth_perpetuity(avg_oe_ps, r)
    raw_zg_total = (zg_core + nc_iv) if zg_core is not None else None
    zg_total = raw_zg_total if raw_zg_total is not None and raw_zg_total > 0 else None

    # ── 研发资本化调节诊断 ──────────────────────────────
    rd_adj_total = 0.0
    if rd_cap_ratio > 0:
        rd_adj_total = sum((safe_float(year_data[c].get("rnd_expense")) or 0.0) * rd_cap_ratio for c in w3) / len(w3)

    # ── OE 年度构成透视 ──────────────────────────────────
    oe_yearly_detail = []
    for c in w3:
        dc = year_data[c]
        _profit = safe_float(dc.get("profit"))
        _da = safe_float(dc.get("da"))
        _capex = safe_float(dc.get("capex"))
        _rnd = safe_float(dc.get("rnd_expense"))
        _rnd_adj = (_rnd or 0.0) * rd_cap_ratio if rd_cap_ratio > 0 else 0.0
        _oe_vals = _owner_earnings_three_caliber(dc, rd_cap_ratio, maint_capex_ratio)
        oe_yearly_detail.append({
            "year": c[:4],
            "profit": _profit,
            "da": _da,
            "capex": _capex,
            "rnd_expense": _rnd,
            "rnd_adj": _rnd_adj,
            "oe_base": _oe_vals[1] if _oe_vals else None,
        })

    return {
        "w3_len": len(w3), "avg_oe_ps": avg_oe_ps, "oe_three": oe_three,
        "g_bm": g_bm, "g_three": g_three, "g_hist": g_hist, "g_quality": g_quality, "g_note": g_note,
        "nc_ps": nc_ps, "nc_iv": nc_iv, "include_net_cash_in_iv": include_net_cash_in_iv,
        "g_fin_cap_applied": g_fin_cap_applied,
        "payout": payout, "payout_src": f"实际均值（{len(payout_vals)}年）" if payout_vals else "无可靠分红数据，默认0%",
        "buf_dcf": buf_dcf, "buf_total": buf_total, "raw_buf_total": raw_buf_total,
        "zero_g_core": zg_core, "zero_g_total": zg_total, "raw_zero_g_total": raw_zg_total,
        "munger": munger, "raw_munger": raw_munger, "pv_interim": pv_interim,
        "avg_profit": avg_profit, "avg_da": avg_da, "avg_maint": avg_maint, "exit_pes": exit_pes,
        "diag_dcf": diag_dcf, "diag_munger": diag_munger,
        "rd_cap_ratio": rd_cap_ratio,
        "rd_cap_adj_total": rd_adj_total,
        "rd_cap_industry": rd_cap_industry,
        "oe_yearly_detail": oe_yearly_detail,
    }

def roic_percent_from_year_data(d: dict) -> Optional[float]:
    op = d.get("op_profit")
    fc = d.get("fin_cost") or 0.0
    pt = d.get("pretax")
    tx = d.get("tax")
    eq = d.get("equity_total")
    id_ = d.get("int_debt") or 0.0
    if op is None or eq is None or eq <= 0:
        return None
    ebit = op + max(fc, 0.0)
    tr = max(0.0, min(tx / pt, 0.50)) if pt and pt > 0 and tx is not None else 0.25
    nopat = ebit * (1 - tr)
    ic = eq + id_
    if ic <= 0:
        return None
    return nopat / ic * 100.0

def interest_coverage_ratio_tag_value(d: dict) -> Tuple[str, Optional[float]]:
    op = d.get("op_profit")
    fc = d.get("fin_cost")
    if op is None or fc is None:
        return "na", None
    fc_f = float(fc)
    if fc_f <= 0:
        return "surplus", None
    ebit = float(op) + fc_f
    return "ok", float(ebit / fc_f)

def _bank_threshold_tone(value: Optional[float], good_floor: float, warn_floor: float) -> str:
    if value is None:
        return "muted"
    if value >= good_floor:
        return "good"
    if value >= warn_floor:
        return "warn"
    return "bad"

def _build_bank_quality_filter(latest_col: str, year_data: Dict[str, Dict]) -> Dict[str, object]:
    latest = year_data.get(latest_col) or {}
    roa = safe_float(latest.get("roa"))
    provision_cov = safe_float(latest.get("provision_coverage_ratio"))
    provision_loan = safe_float(latest.get("provision_loan_ratio"))
    capital_ratio = safe_float(latest.get("capital_adequacy_ratio"))
    capital_buffer = safe_float(latest.get("capital_buffer_ratio"))

    roa_tone = _bank_threshold_tone(roa, 1.0, 0.7)
    if provision_cov is not None:
        provision_label = "拨备覆盖率"
        provision_value = provision_cov
        provision_tone = _bank_threshold_tone(provision_cov, 180.0, 150.0)
        provision_rule = ">=180% 优秀；>=150% 达标"
    else:
        provision_label = "拨贷比"
        provision_value = provision_loan
        provision_tone = _bank_threshold_tone(provision_loan, 3.0, 2.0)
        provision_rule = ">=3.0% 优秀；>=2.0% 达标"

    if capital_ratio is not None:
        capital_label = "资本充足率"
        capital_value = capital_ratio
        capital_tone = _bank_threshold_tone(capital_ratio, 12.0, 10.5)
        capital_rule = ">=12% 稳健；>=10.5% 及格"
        capital_mode = "regulatory"
    else:
        capital_label = "资本缓冲率"
        capital_value = capital_buffer
        capital_tone = _bank_threshold_tone(capital_buffer, 8.0, 6.0)
        capital_rule = "权益/总资产 >=8% 稳健；>=6% 及格"
        capital_mode = "proxy"

    checks = [
        {
            "label": "ROA",
            "value": roa,
            "tone": roa_tone,
            "rule": ">=1.0% 优秀；>=0.7% 稳健",
        },
        {
            "label": provision_label,
            "value": provision_value,
            "tone": provision_tone,
            "rule": provision_rule,
        },
        {
            "label": capital_label,
            "value": capital_value,
            "tone": capital_tone,
            "rule": capital_rule,
            "mode": capital_mode,
        },
    ]
    available = [item for item in checks if item.get("tone") != "muted"]
    bad_count = sum(1 for item in available if item.get("tone") == "bad")
    good_count = sum(1 for item in available if item.get("tone") == "good")
    passed = bool(available) and bad_count == 0 and len(available) >= 2
    if passed and good_count >= 2:
        status = "质量过滤通过"
        tone = "good"
    elif passed:
        status = "质量过滤勉强通过"
        tone = "warn"
    elif available:
        status = "质量过滤未通过"
        tone = "bad"
    else:
        status = "质量过滤缺少关键数据"
        tone = "muted"
    return {
        "checks": checks,
        "passed": passed,
        "status": status,
        "tone": tone,
        "available_count": len(available),
        "good_count": good_count,
        "bad_count": bad_count,
    }

def _build_bank_margin_of_safety_summary(
    pb_tone: str,
    gordon_tone: str,
    pb_history: Dict[str, object],
    dividend_history: Dict[str, object],
    quality_filter: Dict[str, object],
) -> Dict[str, object]:
    reasons: List[str] = []
    pb_percentile = safe_float(pb_history.get("percentile"))
    dividend_percentile = safe_float(dividend_history.get("percentile"))
    quality_passed = bool(quality_filter.get("passed"))

    if pb_tone == "good":
        reasons.append("当前PB低于合理PB区间。")
    elif pb_percentile is not None and pb_percentile <= 30:
        reasons.append("当前PB位于近十年低分位。")
    if gordon_tone == "good":
        reasons.append("超额收益模型已达到安全边际。")
    elif gordon_tone == "warn":
        reasons.append("超额收益模型显示低于内在价值，但折价还不够厚。")
    if dividend_percentile is not None and dividend_percentile >= 70:
        reasons.append("当前股息率处于历史高位区间。")
    elif dividend_percentile is not None and dividend_percentile < 40:
        reasons.append("当前股息率没有给出明显高位补偿。")
    if quality_passed:
        reasons.append("ROA、拨备和资本缓冲至少有两项达到达标线。")
    elif quality_filter.get("available_count"):
        reasons.append("质量过滤未过，便宜不等于安全。")
    else:
        reasons.append("质量过滤关键数据不足，结论置信度有限。")

    if quality_passed and (gordon_tone == "good" or (pb_tone == "good" and pb_percentile is not None and pb_percentile <= 35)):
        status = "存在安全边际"
        tone = "good"
    elif quality_passed and (gordon_tone == "warn" or pb_tone == "good" or (pb_percentile is not None and pb_percentile <= 35)):
        status = "可能存在安全边际，但证据还不够厚"
        tone = "warn"
    elif not quality_passed and (gordon_tone in {"good", "warn"} or pb_tone == "good"):
        status = "估值看似不贵，但质量过滤未过，暂不认定存在安全边际"
        tone = "bad"
    else:
        status = "暂不存在安全边际"
        tone = "bad"
    return {
        "status": status,
        "tone": tone,
        "reasons": reasons,
        "pb_percentile": pb_percentile,
        "dividend_percentile": dividend_percentile,
        "quality_passed": quality_passed,
    }

def build_valuation_assessments(code: str, company_name: str, industry_text: str, total_shares: Optional[float], data: Dict[str, pd.DataFrame], mos: float = MARGIN_OF_SAFETY, discount_rate: float = DISCOUNT_RATE, exit_pes: Tuple[int, int, int] = DEFAULT_EXIT_PE) -> Tuple[List[ValuationAssessment], Dict[str, object]]:
    abs_df = data["abstract"]
    balance_df = data["balance"]
    bank_flag = bool(data.get("is_bank"))
    year_data = build_year_data_for_valuation(data)
    annual_cols = [c for c in annual_cols_from_abstract(abs_df) if c in year_data]
    if not annual_cols:
        return [], {}

    latest_col = annual_cols[-1]
    price, price_source, price_time = data.get("current_price_tuple") or get_current_price(code)
    real_eps, real_eps_src = get_real_eps(abs_df, latest_col)
    basic_eps = safe_float(get_metric(abs_df, "基本每股收益", latest_col))
    pe_current = None
    if price and price > 0:
        eps_for_pe = real_eps if real_eps is not None and real_eps > 0 else basic_eps
        if eps_for_pe is not None and eps_for_pe > 0:
            pe_current = float(price) / float(eps_for_pe)

    latest_shares = total_shares
    latest_share_source = "explicit_total_shares" if latest_shares is not None else "missing"
    share_basis_mode = data.get("_share_basis_mode")
    if latest_shares is None and latest_col in year_data:
        preferred_key = "asof_shares" if share_basis_mode == "asof" else "valuation_shares"
        latest_shares = safe_float(year_data[latest_col].get(preferred_key))
        if latest_shares is not None and latest_shares > 0:
            latest_share_source = preferred_key
        else:
            latest_shares = safe_float(year_data[latest_col].get("reported_shares"))
            if latest_shares is not None and latest_shares > 0:
                latest_share_source = "reported_shares"
            else:
                latest_shares = safe_float(year_data[latest_col].get("shares"))
                if latest_shares is not None and latest_shares > 0:
                    latest_share_source = "legacy_shares"

    # --- Bank PB valuation ---
    bps = safe_float(get_metric_first(abs_df, latest_col, "每股净资产", "每股净资产_最新股数"))
    pb_current = None
    if price and price > 0 and bps and bps > 0:
        pb_current = float(price) / float(bps)

    nc_pct = None
    rd_cap_ratio, rd_cap_industry = _get_rd_capitalization_ratio(industry_text, company_name)
    maint_capex_ratio, maint_capex_key = _get_maint_capex_floor_ratio(industry_text, company_name)

    if bank_flag:
        # Skip OE-DCF/Munger for banks — capex/OE meaningless
        snap = None
        oe_tone, oe_status = "muted", "不适用于银行"
        mos_value = None
        munger_base = None
        munger_tone, munger_status = "muted", "不适用于银行"
    else:
        snap = compute_buffett_munger_snapshot(
            latest_col,
            year_data,
            annual_cols,
            abs_df,
            discount_rate,
            TERMINAL_GROWTH,
            PROJECTION_YEARS,
            shares_for_ps=latest_shares,
            g_fin_cap=None,
            include_net_cash_in_iv=True,
            exit_pes=exit_pes,
            rd_cap_ratio=rd_cap_ratio,
            rd_cap_industry=rd_cap_industry,
            maint_capex_ratio=maint_capex_ratio,
        )

        mos_value = None
        oe_tone = "muted"
        oe_status = "缺数据"
        if snap is not None:
            avg_oe_ps = snap.get("avg_oe_ps")
            if avg_oe_ps is not None and avg_oe_ps <= 0:
                oe_status = "OE为负，DCF不适用"
            elif snap.get("g_note") and "Capex缺失" in snap["g_note"]:
                oe_status = "Capex缺失，DCF不适用"
            elif snap.get("raw_buf_total") is not None and snap.get("buf_total") is None:
                raw_total = safe_float(snap.get("raw_buf_total"))
                raw_core = safe_float(snap.get("buf_dcf"))
                raw_nc = safe_float(snap.get("nc_iv"))
                if raw_total is not None and raw_total <= 0:
                    if raw_core is not None and raw_core > 0 and raw_nc is not None and raw_nc < 0:
                        oe_status = "净负债较高，股权价值<=0"
                    else:
                        oe_status = "经营现金流折现后价值<=0"
        if snap is not None and snap.get("buf_total") is not None:
            mos_value = float(snap["buf_total"]) * (1 - mos)
            if price and price > 0:
                if price < mos_value:
                    oe_tone, oe_status = "good", "满足安全边际"
                elif price < float(snap["buf_total"]):
                    oe_tone, oe_status = "warn", "高于安全边际但低于内在价值"
                else:
                    oe_tone, oe_status = "bad", "未满足低估"
            else:
                # 模型已计算内在价值，但股价缺失无法比较
                oe_tone, oe_status = "warn", f"内在价值已计算（IV={snap['buf_total']:.1f}），股价缺失无法比较"

        _mid_pe = exit_pes[1]
        munger_base = snap["munger"].get(_mid_pe) if snap is not None and snap.get("munger") else None
        munger_tone = "muted"
        munger_status = "缺数据"
        if snap is not None and munger_base is None:
            avg_oe_ps = snap.get("avg_oe_ps")
            if avg_oe_ps is not None and avg_oe_ps <= 0:
                munger_status = "OE为负，远景估值不适用"
            elif snap.get("g_note") and "Capex缺失" in snap["g_note"]:
                munger_status = "Capex缺失，不适用"
            else:
                raw_munger_mid = safe_float((snap.get("raw_munger") or {}).get(_mid_pe)) if snap is not None else None
                if raw_munger_mid is not None and raw_munger_mid <= 0:
                    raw_nc = safe_float(snap.get("nc_iv"))
                    if raw_nc is not None and raw_nc < 0:
                        munger_status = "净负债较高，远景股权价值<=0"
                    else:
                        munger_status = "远景股权价值<=0"
        _mid_pe_label = f"{_mid_pe}x"
        if price and price > 0 and munger_base is not None:
            if munger_base >= price * 1.3:
                munger_tone, munger_status = "good", f"{_mid_pe_label}场景显著高于现价"
            elif munger_base >= price:
                munger_tone, munger_status = "warn", f"{_mid_pe_label}场景略高于现价"
            else:
                munger_tone, munger_status = "bad", f"{_mid_pe_label}场景不支持低估"
        elif munger_base is not None:
            # 远景价値已计算，但股价缺失无法比较
            munger_tone, munger_status = "warn", f"{_mid_pe_label}远景内在价値已计算，股价缺失"

    # --- DCF sensitivity analysis ---
    dcf_sensitivity = None
    if snap is not None and snap.get("buf_total") is not None and snap.get("avg_oe_ps") is not None:
        _s_oe = float(snap["avg_oe_ps"])
        _s_g = float(snap["g_bm"]) if snap.get("g_bm") is not None else 0.0
        _s_nc = float(snap.get("nc_ps") or 0)
        _s_base = float(snap["buf_total"])
        if _s_oe > 0 and _s_base > 0:
            _s_core = _s_base - _s_nc
            _s_tv_pct = None
            # Compute terminal value share (using fade model)
            _, _, _pv1_div = dcf_fade(_s_oe, _s_g, discount_rate, TERMINAL_GROWTH, PROJECTION_YEARS)
            _pv1 = _pv1_div  # undiscounted OE PV stream
            if _pv1 > 0 and _s_core > 0:
                _s_tv_pct = max(0.0, min(100.0, (1 - _pv1 / _s_core) * 100))
            # g ± 1pp (using fade DCF)
            _iv_g_up = dcf_fade(_s_oe, _s_g + 0.01, discount_rate, TERMINAL_GROWTH, PROJECTION_YEARS)[0] + _s_nc
            _iv_g_dn = dcf_fade(_s_oe, max(-0.05, _s_g - 0.01), discount_rate, TERMINAL_GROWTH, PROJECTION_YEARS)[0] + _s_nc
            # terminal growth ± 1pp
            _iv_tv_up = dcf_fade(_s_oe, _s_g, discount_rate, min(TERMINAL_GROWTH + 0.01, discount_rate - 0.01), PROJECTION_YEARS)[0] + _s_nc
            _iv_tv_dn = dcf_fade(_s_oe, _s_g, discount_rate, max(0.0, TERMINAL_GROWTH - 0.01), PROJECTION_YEARS)[0] + _s_nc
            dcf_sensitivity = {
                "tv_pct": _s_tv_pct,
                "g_up": _iv_g_up,
                "g_dn": _iv_g_dn,
                "g_base": _s_base,
                "tv_up": _iv_tv_up,
                "tv_dn": _iv_tv_dn,
            }

    # --- 三档情景分析 (OE三口径 × G三档) — 1 DCF + 3 芒格矩阵 ---
    scenario_analysis = None
    if snap is not None and snap.get("buf_total") is not None and snap.get("oe_three") is not None:
        _oe3 = snap["oe_three"]
        _g3 = snap["g_three"]
        _sc_nc = float(snap.get("nc_iv") or 0)
        _sc_payout = float(snap.get("payout") or 0.40)
        _sc_exit_pes = snap.get("exit_pes", exit_pes)
        if _oe3.get("base") is not None and _oe3["base"] > 0 and _g3.get("base") is not None:
            _oe_levels = [
                ("悲观OE", float(_oe3["pessimistic"])),
                ("基准OE", float(_oe3["base"])),
                ("宽松OE", float(_oe3["lenient"])),
            ]
            _g_levels = [
                ("悲观G", float(_g3["bear"])),
                ("基准G", float(_g3["base"])),
                ("乐观G", float(_g3["bull"])),
            ]
            # ── OE-DCF 3×3: rows=OE口径, cols=G三档 ──
            _dcf_iv = {}
            for oe_label, oe_val in _oe_levels:
                for g_label, g_val in _g_levels:
                    if oe_val > 0:
                        _iv = dcf_fade(oe_val, g_val, discount_rate, TERMINAL_GROWTH, PROJECTION_YEARS)[0] + _sc_nc
                        _dcf_iv[(oe_label, g_label)] = _iv if _iv > 0 else None
                    else:
                        _dcf_iv[(oe_label, g_label)] = None
            # ── 芒格远景: 每个退出PE一个3×3 (rows=OE口径, cols=G三档) ──
            _munger_tables = {}
            for pe in _sc_exit_pes:
                _mt = {}
                for oe_label, oe_val in _oe_levels:
                    for g_label, g_val in _g_levels:
                        if oe_val > 0:
                            _ft, _oen, _pvd = dcf_fade(oe_val, g_val, discount_rate, TERMINAL_GROWTH, PROJECTION_YEARS)
                            _pvi = _pvd * _sc_payout
                            _epv = (_oen * pe) / (1 + discount_rate) ** PROJECTION_YEARS
                            _iv = _pvi + _epv + _sc_nc
                            _mt[(oe_label, g_label)] = _iv if _iv > 0 else None
                        else:
                            _mt[(oe_label, g_label)] = None
                _munger_tables[pe] = _mt
            scenario_analysis = {
                "g_levels": _g_levels,
                "oe_levels": _oe_levels,
                "exit_pes": _sc_exit_pes,
                "mos_ratio": mos,
                "dcf_iv": _dcf_iv,
                "munger_tables": _munger_tables,
                "diag_dcf": snap.get("diag_dcf"),
                "diag_munger": snap.get("diag_munger"),
            }

    payout = None
    if snap is not None and snap.get("payout") is not None:
        payout = float(snap["payout"])
    latest_roe = safe_float(year_data[latest_col].get("roe")) if latest_col in year_data else None
    sgr_pct = latest_roe * max(0.0, 1 - payout) if latest_roe is not None and payout is not None else None
    cagr_info = build_eps_cagr_snapshot(abs_df, annual_cols, latest_col, preferred_years=3)
    cagr_pct = safe_float(cagr_info.get("cagr_pct"))
    growth_for_peg_pct = cagr_pct if cagr_pct is not None else sgr_pct
    latest_div = safe_float(year_data[latest_col].get("dividends_paid")) if latest_col in year_data else None
    dividend_yield_pct = (latest_div / (float(price) * float(latest_shares)) * 100) if latest_div is not None and price and latest_shares and latest_shares > 0 else None
    peg = None
    peg_display = "N/A"
    peg_reason = ""
    peg_tone = "muted"
    peg_status = "缺数据"
    if pe_current is None and growth_for_peg_pct is None:
        peg_status = "PE与增长率均缺失，PEG不适用"
    elif pe_current is None:
        peg_status = "PE为负或缺失，PEG不适用"
    elif growth_for_peg_pct is None:
        peg_status = "增长率缺失，PEG不适用"
    if pe_current is not None and growth_for_peg_pct is not None:
        if growth_for_peg_pct <= 0:
            peg_tone, peg_status = "muted", "负增长，不加分"
            peg_reason = f"EPS CAGR 为 {fmt_pct(growth_for_peg_pct)}，增长率小于等于 0，PEG 没有经济意义"
            peg_display = f"不适用：{peg_reason}"
        else:
            peg = pe_current / growth_for_peg_pct
            peg_display = f"PE {fmt_num(pe_current)}x / CAGR {fmt_pct(growth_for_peg_pct)} / PEG {fmt_num(peg)}"
            if growth_for_peg_pct > 50:
                peg_tone, peg_status = "warn", "增速过高，PEG参考性弱"
            elif peg < 1:
                peg_tone, peg_status = "good", "PEG<1"
            elif peg <= 2:
                peg_tone, peg_status = "warn", "PEG一般"
            else:
                peg_tone, peg_status = "muted", "PEG未加分"

    pegy = None
    pegy_display = "N/A"
    pegy_reason = ""
    pegy_tone = "muted"
    pegy_status = "缺数据"
    if pe_current is None:
        pegy_status = "PE为负或缺失，PEGY不适用"
    elif growth_for_peg_pct is None:
        pegy_status = "增长率缺失，PEGY不适用"
    elif dividend_yield_pct is None:
        pegy_status = "股息率缺失，PEGY不适用"
    if pe_current is not None and growth_for_peg_pct is not None and dividend_yield_pct is not None:
        combo_growth = growth_for_peg_pct + dividend_yield_pct
        if combo_growth <= 0:
            pegy_tone, pegy_status = "muted", "增长+股息不加分"
            pegy_reason = (
                f"EPS CAGR {fmt_pct(growth_for_peg_pct)} + 股息率 {fmt_pct(dividend_yield_pct)}"
                f" = {fmt_pct(combo_growth)}，分母小于等于 0"
            )
            pegy_display = f"不适用：{pegy_reason}"
        else:
            pegy = pe_current / combo_growth
            pegy_display = f"PEGY {fmt_num(pegy)} / 股息率 {fmt_pct(dividend_yield_pct)}"
            if pegy < 1:
                pegy_tone, pegy_status = "good", "PEGY<1"
            elif pegy <= 2:
                pegy_tone, pegy_status = "warn", "PEGY一般"
            else:
                pegy_tone, pegy_status = "muted", "PEGY未加分"

    _mid_pe2 = exit_pes[1]
    munger_base = snap["munger"].get(_mid_pe2) if snap is not None and snap.get("munger") else None
    if not bank_flag:
        pass  # munger_tone/munger_status already set above
    # For banks, munger_tone/munger_status already set to "muted"/"不适用于银行"

    market_pe, market_pe_label = fetch_market_pe_anchor()
    rel_tone = "muted"
    rel_status = "缺数据"
    if pe_current is not None and market_pe is not None:
        if pe_current < market_pe:
            rel_tone, rel_status = "good", "低于全市场锚点"
        elif pe_current <= market_pe * 1.15:
            rel_tone, rel_status = "warn", "接近全市场锚点"
        else:
            rel_tone, rel_status = "bad", "高于全市场锚点"
    elif market_pe is not None and pe_current is None:
        rel_status = "个股PE为负或缺失，不适用"
    elif market_pe is None and pe_current is not None:
        rel_status = "全市场PE未取到"
    elif market_pe is None and pe_current is None:
        rel_status = "个股PE与市场PE均缺失"

    rf_pct, rf_dt = fetch_cn_10y_government_bond_yield_pct()
    earnings_yield = (1 / pe_current * 100) if pe_current and pe_current > 0 else None
    spread = (earnings_yield - rf_pct) if earnings_yield is not None and rf_pct is not None else None
    cost_tone = "muted"
    cost_status = "缺数据"
    if spread is None:
        if earnings_yield is None and rf_pct is None:
            cost_status = "PE与国债数据均缺失"
        elif earnings_yield is None:
            cost_status = "PE为负或缺失，盈利率不适用"
        elif rf_pct is None:
            cost_status = "国债收益率未取到"
    if spread is not None:
        if spread >= 5:
            cost_tone, cost_status = "good", "显著跑赢国债"
        elif spread >= 3:
            cost_tone, cost_status = "good", "达到风险溢价要求"
        elif spread >= 0:
            cost_tone, cost_status = "warn", "利差偏薄"
        else:
            cost_tone, cost_status = "bad", "不如国债"

    oe_yield_pct = None
    oe_spread = None
    oe_yield_tone = "muted"
    oe_yield_status = "缺数据"
    avg_oe_ps = snap.get("avg_oe_ps") if snap is not None else None
    if avg_oe_ps is not None and price and price > 0:
        oe_yield_pct = avg_oe_ps / float(price) * 100
    if oe_yield_pct is None:
        if avg_oe_ps is None and rf_pct is None:
            oe_yield_status = "OE与国债数据均缺失"
        elif avg_oe_ps is None:
            oe_yield_status = "OE为负或缺失，OE收益率不适用"
        elif rf_pct is None:
            oe_yield_status = "国债收益率未取到"
        elif price is None or price <= 0:
            oe_yield_status = "股价缺失，OE收益率不适用"
    if oe_yield_pct is not None and rf_pct is not None:
        oe_spread = oe_yield_pct - rf_pct
        if oe_spread >= 5:
            oe_yield_tone, oe_yield_status = "good", "OE收益率显著跑赢国债"
        elif oe_spread >= 3:
            oe_yield_tone, oe_yield_status = "good", "OE达到风险溢价要求"
        elif oe_spread >= 0:
            oe_yield_tone, oe_yield_status = "warn", "OE利差偏薄"
        else:
            oe_yield_tone, oe_yield_status = "bad", "OE收益率不如国债"

    ca, tl = current_assets_and_liabilities(balance_df)
    nwc = (ca - tl) if ca is not None and tl is not None else None
    market_cap = (float(price) * float(latest_shares)) if price and latest_shares and latest_shares > 0 else None
    netnet_threshold = nwc * (2 / 3) if nwc is not None else None
    nn_tone = "muted"
    nn_status = "样本多半不适用"
    if market_cap is not None and netnet_threshold is not None:
        if market_cap < netnet_threshold:
            nn_tone, nn_status = "good", "达到烟屁股低估"
        elif nwc is not None and nwc > 0 and market_cap < nwc:
            nn_tone, nn_status = "warn", "接近净营运资本保护"
        else:
            nn_tone, nn_status = "bad", "未达到Net-Net"

    if pe_current is not None and market_pe is not None:
        rel_value_display = f"个股PE {fmt_num(pe_current)}x / 市场锚 {fmt_num(market_pe)}x"
    elif market_pe is not None:
        rel_value_display = f"个股PE N/A / 市场锚 {fmt_num(market_pe)}x"
    elif pe_current is not None:
        rel_value_display = f"个股PE {fmt_num(pe_current)}x / 市场锚 N/A"
    else:
        rel_value_display = "N/A"

    # --- PB assessment (primarily for banks but available for all) ---
    pb_tone = "muted"
    pb_status = "缺数据"
    fair_pb = None
    if pb_current is not None:
        if bank_flag:
            # Dynamic fair PB: fair_pb = (ROE - g) / (ke - g)
            # Compute using latest ROE and Gordon g; fallback to static thresholds
            _pb_roe = None
            _pb_g = None
            # Try to get ROE for fair_pb (weighted-average will be computed later, use simple latest here)
            if latest_col in year_data:
                _pb_roe_raw = safe_float(year_data[latest_col].get("roe"))
                if _pb_roe_raw is not None and _pb_roe_raw > 0:
                    _pb_roe = _pb_roe_raw / 100  # convert percentage to decimal
            _pb_payout = safe_float(year_data[latest_col].get("payout_ratio")) if latest_col in year_data else None
            # Fallback: compute from dividends_paid / profit (needed when payout_ratio not in year_data)
            if _pb_payout is None and latest_col in year_data:
                _pb_div = safe_float(year_data[latest_col].get("dividends_paid"))
                _pb_pft = safe_float(year_data[latest_col].get("profit"))
                if _pb_div is not None and _pb_div > 0 and _pb_pft is not None and _pb_pft > 0:
                    _pb_payout = min(_pb_div / _pb_pft, 1.0)
            if _pb_roe is not None and _pb_payout is not None:
                _pb_g = _pb_roe * max(0.0, 1 - _pb_payout)
                _pb_g = min(_pb_g, TERMINAL_GROWTH)  # banks: perpetual growth ≤ GDP
            if _pb_roe is not None and _pb_g is not None and discount_rate > _pb_g:
                fair_pb = (_pb_roe - _pb_g) / (discount_rate - _pb_g)
                # Assess relative to fair_pb
                if pb_current < fair_pb * 0.6:
                    pb_tone, pb_status = "good", f"深度低估（合理PB {fair_pb:.2f}x）"
                elif pb_current < fair_pb * 0.85:
                    pb_tone, pb_status = "good", f"低估（合理PB {fair_pb:.2f}x）"
                elif pb_current < fair_pb * 1.1:
                    pb_tone, pb_status = "warn", f"合理（合理PB {fair_pb:.2f}x）"
                else:
                    pb_tone, pb_status = "bad", f"偏高（合理PB {fair_pb:.2f}x）"
            else:
                # Fallback to static thresholds when ROE/payout unavailable
                if pb_current < 0.7:
                    pb_tone, pb_status = "good", "深度低估"
                elif pb_current < 1.0:
                    pb_tone, pb_status = "good", "破净低估"
                elif pb_current < 1.3:
                    pb_tone, pb_status = "warn", "合理偏低"
                else:
                    pb_tone, pb_status = "bad", "估值偏高"
        else:
            if pb_current < 1.0:
                pb_tone, pb_status = "good", "破净"
            elif pb_current < 2.0:
                pb_tone, pb_status = "warn", "PB适中"
            else:
                pb_tone, pb_status = "muted", "PB偏高"

    # --- Excess Return Model (Residual Income) for banks ---
    gordon_iv = None
    gordon_tone = "muted"
    gordon_status = "缺数据"
    gordon_g_raw = None
    gordon_g_capped = False
    if bank_flag:
        # Weighted-average ROE (3:2:1) for stability
        roe_weights = [(3, 0), (2, 1), (1, 2)]  # (weight, offset from latest)
        roe_vals_w = []
        for w, offset in roe_weights:
            idx = len(annual_cols) - 1 - offset
            if 0 <= idx < len(annual_cols):
                c = annual_cols[idx]
                rv = safe_float(year_data[c].get("roe")) if c in year_data else None
                if rv is not None:
                    roe_vals_w.append((rv, w))
        if roe_vals_w:
            latest_roe_val = sum(v * w for v, w in roe_vals_w) / sum(w for _, w in roe_vals_w)
        else:
            latest_roe_val = None
        payout_val = safe_float(year_data[latest_col].get("payout_ratio")) if latest_col in year_data else None
        if payout_val is None and snap is not None and snap.get("payout") is not None:
            payout_val = float(snap["payout"])
        # Fallback: compute from dividends_paid / profit (needed for banks where snap=None)
        if payout_val is None and latest_col in year_data:
            _div_p = safe_float(year_data[latest_col].get("dividends_paid"))
            _pft_p = safe_float(year_data[latest_col].get("profit"))
            if _div_p is not None and _div_p > 0 and _pft_p is not None and _pft_p > 0:
                payout_val = min(_div_p / _pft_p, 1.0)
        if latest_roe_val is not None and bps and bps > 0 and payout_val is not None:
            roe_decimal = latest_roe_val / 100
            gordon_g_raw = roe_decimal * max(0.0, 1 - payout_val)
            g_gordon_cap = TERMINAL_GROWTH  # banks: perpetual growth ≤ GDP
            if gordon_g_raw > g_gordon_cap:
                g_gordon = g_gordon_cap
                gordon_g_capped = True
            else:
                g_gordon = gordon_g_raw
            cost_of_equity = discount_rate
            if cost_of_equity > g_gordon and roe_decimal > g_gordon:
                # Excess Return Model: V = BPS × (ROE - g) / (Ke - g)
                gordon_iv = bps * (roe_decimal - g_gordon) / (cost_of_equity - g_gordon)
                if price and price > 0:
                    if price < gordon_iv * (1 - mos):
                        gordon_tone, gordon_status = "good", "满足安全边际"
                    elif price < gordon_iv:
                        gordon_tone, gordon_status = "warn", "低于内在价值但未达安全边际"
                    else:
                        gordon_tone, gordon_status = "bad", "高于内在价值"

    assessments: List[ValuationAssessment] = []
    _mos_pct_label = f"{mos*100:.0f}%"
    _mos_keep_pct = f"{(1-mos)*100:.0f}%"

    # PB (first card for banks)
    if bank_flag:
        _pb_rule = f"合理PB = (ROE-g)/(ke-g) = {fair_pb:.2f}x；低估: PB < {fair_pb*0.85:.2f}x；深度低估: PB < {fair_pb*0.6:.2f}x" if fair_pb is not None else "银行低估: PB < 1.0；深度低估: PB < 0.7"
        assessments.append(ValuationAssessment(
            label="PB(市净率)",
            value_display=f"PB {fmt_num(pb_current)}x / BPS {fmt_num(bps)} 元" if pb_current is not None else "N/A",
            rule_display=_pb_rule,
            status_text=pb_status,
            tone=pb_tone,
            meaning="银行最核心的估值锚点，直接衡量市场对银行净资产的定价倍数。",
            implication="银行资产以贷款为主体，净资产是安全垫；长期低于1倍PB可能意味着市场担忧资产质量。",
            formula=f"PB = 股价/BPS；合理PB = (ROE - g) / (ke - g)，g上限 = {fmt_pct(TERMINAL_GROWTH * 100)}",
        ))
        gordon_cap_note = ""
        if gordon_g_capped and gordon_g_raw is not None:
            gordon_cap_note = f"（原始g={fmt_pct(gordon_g_raw * 100)}被截断至{fmt_pct(TERMINAL_GROWTH * 100)}）"
        assessments.append(ValuationAssessment(
            label="超额收益模型",
            value_display=f"内在价值 {fmt_num(gordon_iv)} 元{gordon_cap_note}" if gordon_iv is not None else "N/A",
            rule_display=f"低估标准: 现价 < 内在价值 × {_mos_keep_pct}（安全边际{_mos_pct_label}）",
            status_text=gordon_status,
            tone=gordon_tone,
            meaning="用超额收益模型（Residual Income）估算银行内在价值，同时捕获股息和留存再投资的价值。ROE使用近3年加权平均(3:2:1)以平滑波动。",
            implication="当ROE>折现率时银行创造超额价值；PB与本模型数学等价，结论一致。",
            formula=f"V = BPS × (ROE - g) / (Ke - g)，g = ROE × (1 - 派息率)，g上限 = {fmt_pct(TERMINAL_GROWTH * 100)}(GDP终端增长率)",
        ))
    else:
        _sens_note = ""
        if dcf_sensitivity is not None:
            tv_p = dcf_sensitivity["tv_pct"]
            g_up_chg = (dcf_sensitivity["g_up"] / dcf_sensitivity["g_base"] - 1) * 100 if dcf_sensitivity["g_base"] > 0 else 0
            g_dn_chg = (dcf_sensitivity["g_dn"] / dcf_sensitivity["g_base"] - 1) * 100 if dcf_sensitivity["g_base"] > 0 else 0
            tv_up_chg = (dcf_sensitivity["tv_up"] / dcf_sensitivity["g_base"] - 1) * 100 if dcf_sensitivity["g_base"] > 0 else 0
            tv_dn_chg = (dcf_sensitivity["tv_dn"] / dcf_sensitivity["g_base"] - 1) * 100 if dcf_sensitivity["g_base"] > 0 else 0
            _sens_note = f"终值占比{fmt_num(tv_p)}% | g±1pp影响{g_dn_chg:+.0f}%~{g_up_chg:+.0f}% | 永续增长率±1pp影响{tv_dn_chg:+.0f}%~{tv_up_chg:+.0f}%" if tv_p is not None else f"g±1pp影响{g_dn_chg:+.0f}%~{g_up_chg:+.0f}%"
        # --- 净现金占比警告 ---
        _nc_warn_note = ""
        nc_pct = None
        if snap is not None and snap.get("buf_total") is not None and snap.get("buf_dcf") is not None:
            _nc_val = float(snap.get("nc_iv") or 0)
            _buf_total_val = float(snap["buf_total"])
            if _buf_total_val > 0 and _nc_val > 0:
                nc_pct = _nc_val / _buf_total_val * 100
                if nc_pct > 50:
                    _nc_warn_note = f" | \u26a0\ufe0f 净现金占内在价值{nc_pct:.0f}%，估值依赖资产而非盈利能力"
        assessments.append(ValuationAssessment(
            label="OE-DCF",
            value_display=(
                f"内在价值 {fmt_num(snap['buf_total'])} 元 / 安全边际价 {fmt_num(mos_value)} 元"
                if snap is not None and snap.get("buf_total") is not None
                else (
                    f"内在价值 {fmt_num(safe_float(snap.get('raw_buf_total')))} 元（<=0）"
                    if snap is not None and safe_float(snap.get("raw_buf_total")) is not None
                    else "N/A"
                )
            ),
            rule_display=f"低估标准: 现价 < 内在价值 × {_mos_keep_pct}（安全边际{_mos_pct_label}）",
            status_text=oe_status,
            tone=oe_tone,
            meaning="用所有者盈余折现来估算企业长期可提取现金流的现值。",
            implication=f"它回答的是：按保守折现后，这家公司今天到底值多少钱。{_sens_note}{_nc_warn_note}",
        ))
        _pe_lo, _pe_mid, _pe_hi = exit_pes
        _munger_label = f"{_pe_mid}x"
        _raw_munger_mid = safe_float((snap.get("raw_munger") or {}).get(_pe_mid)) if snap is not None else None
        assessments.append(ValuationAssessment(
            label="芒格远景估值",
            value_display=(
                f"{_munger_label}场景 {fmt_num(munger_base)} 元"
                if munger_base is not None
                else (
                    f"{_munger_label}场景 {fmt_num(_raw_munger_mid)} 元（<=0）"
                    if _raw_munger_mid is not None
                    else "N/A"
                )
            ),
            rule_display=f"退出PE {_pe_lo}x/{_pe_mid}x/{_pe_hi}x（行业适配），基准{_munger_label}场景明显高于现价即低估",
            status_text=munger_status,
            tone=munger_tone,
            meaning="把未来十年的分红现值和期末卖出价格折现回今天。",
            implication="它更像真实持有场景，能直观看长期持有后是否值得。",
        ))

    # Common cards for both banks and industrial
    assessments.extend([
        ValuationAssessment(
            label="PEG × CAGR",
            value_display=peg_display,
            rule_display="低估标准: PEG < 1；>2 常见高估/泡沫",
            status_text=peg_status,
            tone=peg_tone,
            meaning="用 EPS 的年复合增长率去校准市盈率，过滤掉单一年份的增速抖动。",
            implication="如果 CAGR 为负，PEG 在经济意义上就不再适用；如果 PEG 太高，说明看似便宜的 PE 其实没有被长期增长支撑。",
            formula="PEG = PE / CAGR",
        ),
        ValuationAssessment(
            label="PEGY",
            value_display=pegy_display,
            rule_display="成熟现金奶牛更适合看 PEGY < 1",
            status_text=pegy_status,
            tone=pegy_tone,
            meaning="把股息率加回增长率后，再看 PE 是否仍然匹配。",
            implication="如果增长率和股息率加总后仍然不为正，PEGY 也没有可比意义；对高分红成熟股，PEGY 往往比 PEG 更接近真实股东回报。",
            formula="PEGY = PE / (CAGR + Dividend Yield)",
        ),
        ValuationAssessment(
            label="全市场锚点",
            value_display=rel_value_display,
            rule_display="低估标准: 个股 PE < 全市场中位 PE",
            status_text=rel_status,
            tone=rel_tone,
            meaning="把个股放回整个市场资金池里比较其单位盈利定价。",
            implication="低于全市场锚点，说明同一元盈利在市场里被给了更便宜的价格。",
        ),
        ValuationAssessment(
            label="盈利率 vs 国债",
            value_display=f"E/P {fmt_pct(earnings_yield)} / 利差 {fmt_num(spread)} pp" if earnings_yield is not None and spread is not None else "N/A",
            rule_display="低估标准: 盈利率 > 10Y国债 + 3%~5%",
            status_text=cost_status,
            tone=cost_tone,
            meaning="用股票盈利回报率和无风险国债收益率做机会成本比较。",
            implication="如果盈利率连国债都赢不了，这笔风险资产就谈不上有吸引力。",
        ),
    ])

    if not bank_flag:
        assessments.append(ValuationAssessment(
            label="OE收益率 vs 国债",
            value_display=f"OE Yield {fmt_pct(oe_yield_pct)} / 利差 {fmt_num(oe_spread)} pp" if oe_yield_pct is not None and oe_spread is not None else "N/A",
            rule_display="低估标准: OE/股价 > 10Y国债 + 3%~5%",
            status_text=oe_yield_status,
            tone=oe_yield_tone,
            meaning="用所有者盈余收益率代替会计EPS做机会成本比较，排除了折旧/资本开支扭曲。",
            implication="OE收益率比E/P更接近股东真实可提取回报，是巴菲特视角下的机会成本检验。",
            formula="OE Yield = OE每股 / 股价 × 100%",
        ))
        assessments.append(ValuationAssessment(
            label="Net-Net",
            value_display=f"市值 {fmt_yi(market_cap)} / 2/3×NWC {fmt_yi(netnet_threshold)}" if market_cap is not None and netnet_threshold is not None else "N/A",
            rule_display="低估标准: 市值 < 净营运资本 × 2/3",
            status_text=nn_status,
            tone=nn_tone,
            meaning="用格雷厄姆的极端清算视角看市场价格是否低到离谱。",
            implication="它寻找的是市场极端恐慌时的物理底部，通常只在很少数公司上触发。",
        ))

    resonances = []
    if bank_flag:
        if pb_tone == "good":
            resonances.append("PB低估，市场对银行净资产给予了折价。")
        if gordon_tone == "good":
            resonances.append("超额收益模型提供安全边际，ROE超越资本成本支持低估。")
    else:
        if oe_tone == "good":
            resonances.append("OE-DCF 已经提供 30% 安全边际。")
    if peg_tone == "good":
        resonances.append("PEG 基于 CAGR 小于 1，增长与估值匹配。")
    if pegy_tone == "good":
        resonances.append("PEGY 也小于 1，分红把成熟股东回报进一步抬高。")
    if cost_tone == "good":
        resonances.append("盈利率对十年国债的利差达到或超过风险补偿要求。")
    if not bank_flag and oe_yield_tone == "good":
        resonances.append("OE收益率对十年国债的利差达到风险补偿要求，巴菲特视角下的机会成本检验通过。")
    if rel_tone == "good":
        resonances.append("当前 PE 低于全市场动态 PE 中位锚点。")

    bank_pb_history = None
    bank_dividend_history = None
    bank_quality_filter = None
    bank_margin_of_safety = None
    if bank_flag:
        bank_pb_history = build_pb_percentile_history_post_may(
            code,
            abs_df,
            pb_current,
            max_fiscal_years=10,
            daily_years_back=12,
        )
        bank_dividend_history = build_dividend_yield_percentile_history_post_may(
            code,
            year_data,
            dividend_yield_pct,
            max_fiscal_years=10,
            daily_years_back=12,
        )
        bank_quality_filter = _build_bank_quality_filter(latest_col, year_data)
        bank_margin_of_safety = _build_bank_margin_of_safety_summary(
            pb_tone,
            gordon_tone,
            bank_pb_history,
            bank_dividend_history,
            bank_quality_filter,
        )

    details = {
        "price": price,
        "price_source": price_source,
        "price_time": price_time,
        "real_eps": real_eps,
        "real_eps_src": real_eps_src,
        "pe_current": pe_current,
        "market_pe": market_pe,
        "market_pe_label": market_pe_label,
        "rf_pct": rf_pct,
        "rf_dt": rf_dt,
        "earnings_yield": earnings_yield,
        "spread": spread,
        "sgr_pct": sgr_pct,
        "cagr_info": cagr_info,
        "growth_for_peg_pct": growth_for_peg_pct,
        "peg": peg,
        "pegy": pegy,
        "peg_reason": peg_reason,
        "pegy_reason": pegy_reason,
        "dividend_yield_pct": dividend_yield_pct,
        "market_cap": market_cap,
        "latest_share_source": latest_share_source,
        "nwc": nwc,
        "netnet_threshold": netnet_threshold,
        "snap": snap,
        "resonances": resonances,
        "latest_year": latest_col[:4],
        "pb_current": pb_current,
        "fair_pb": fair_pb,
        "bps": bps,
        "gordon_iv": gordon_iv if bank_flag else None,
        "gordon_g_raw": gordon_g_raw,
        "gordon_g_capped": gordon_g_capped,
        "dcf_sensitivity": dcf_sensitivity,
        "scenario_analysis": scenario_analysis,
        "nc_pct": nc_pct,
        "is_bank": bank_flag,
        "bank_pb_percentile_history": bank_pb_history,
        "bank_dividend_yield_percentile_history": bank_dividend_history,
        "bank_quality_filter": bank_quality_filter,
        "bank_margin_of_safety": bank_margin_of_safety,
    }
    if not bank_flag:
        details["pe_percentile_history"] = build_pe_percentile_history_post_may(
            code,
            abs_df,
            pe_current,
            max_fiscal_years=10,
            daily_years_back=12,
        )
        details["eps_percentile_history"] = build_eps_percentile_history(
            abs_df,
            max_fiscal_years=10,
        )
    return assessments, details

def build_valuation_conclusion(details: Dict[str, object]) -> List[str]:
    lines: List[str] = []
    if details.get("is_bank"):
        bank_mos = details.get("bank_margin_of_safety") or {}
        bank_quality = details.get("bank_quality_filter") or {}
        status = str(bank_mos.get("status") or "暂不存在安全边际")
        lines.append(f"银行安全边际结论: {status}。")
        if bank_quality.get("status"):
            lines.append(f"质量过滤: {bank_quality.get('status')}。")
        for reason in bank_mos.get("reasons") or []:
            lines.append(str(reason))

    resonances = details.get("resonances") or []
    if resonances:
        lines.append(f"低估共振信号数量: {len(resonances)} 项。")
        lines.extend(str(x) for x in resonances)
    else:
        lines.append("当前没有形成你定义的低估共振，价格与价值之间还缺少足够多的交叉验证。")

    pe_current = details.get("pe_current")
    market_pe = details.get("market_pe")
    spread = details.get("spread")
    if pe_current is not None and market_pe is not None:
        if float(pe_current) < float(market_pe):
            lines.append("相对全市场锚点看，当前 PE 具备统计上的价格优势。")
        else:
            lines.append("相对全市场锚点看，当前 PE 并不便宜。")
    if spread is not None:
        if float(spread) >= 3:
            lines.append("机会成本维度过关，股票盈利率相对国债留出了像样的风险溢价。")
        else:
            lines.append("机会成本维度偏弱，和国债相比的额外回报还不够厚。")
    return lines

def build_valuation_history(data: Dict[str, pd.DataFrame], total_shares: Optional[float], is_bank: bool = False, mos: float = MARGIN_OF_SAFETY, discount_rate: float = DISCOUNT_RATE, exit_pes: Tuple[int, int, int] = DEFAULT_EXIT_PE, industry_text: str = "", company_name: str = "", history_years: int = 5) -> List[Dict[str, object]]:
    abs_df = data["abstract"]
    year_data = build_year_data_for_valuation(data)
    annual_cols = [c for c in annual_cols_from_abstract(abs_df) if c in year_data]
    current_price = safe_float((data.get("current_price_tuple") or (None, None, None))[0])
    rd_cap_ratio, rd_cap_industry = _get_rd_capitalization_ratio(industry_text, company_name)
    maint_capex_ratio, _ = _get_maint_capex_floor_ratio(industry_text, company_name)
    history: List[Dict[str, object]] = []
    share_basis_mode = data.get("_share_basis_mode")
    primary_basis = "asof_shares"
    # ── 巴菲特公司级算法：用当年股本基准重现历史定价 ──────────────────────
    # 每一年用该年自己的股数计算每股OE，以准确重现历史时点的内在价值。
    # PE 和利润 CAGR 直接用公司级指标计算，不依赖 EPS。
    for col in annual_cols[-history_years:]:
        shares_for_ps = total_shares  # fallback: caller传入的当前股数
        share_basis_used = "explicit_total_shares"
        if col in year_data:
            valuation_shares = safe_float(year_data[col].get("valuation_shares"))
            asof_shares = safe_float(year_data[col].get("asof_shares"))
            if primary_basis == "asof_shares" and asof_shares and asof_shares > 0:
                shares_for_ps = asof_shares
                share_basis_used = "asof_shares"
            elif primary_basis == "valuation_shares" and valuation_shares and valuation_shares > 0:
                shares_for_ps = valuation_shares
                share_basis_used = "valuation_shares"
            else:
                secondary = asof_shares if primary_basis == "valuation_shares" else valuation_shares
                secondary_key = "asof_shares" if primary_basis == "valuation_shares" else "valuation_shares"
                if secondary and secondary > 0:
                    shares_for_ps = secondary
                    share_basis_used = secondary_key
                else:
                    yr_shares = safe_float(year_data[col].get("reported_shares"))
                    if yr_shares and yr_shares > 0:
                        shares_for_ps = yr_shares
                        share_basis_used = "reported_shares"
                    else:
                        yr_shares = safe_float(year_data[col].get("shares"))
                    if yr_shares and yr_shares > 0:
                        shares_for_ps = yr_shares  # legacy fallback（A股/港股）
                        share_basis_used = "legacy_shares"
        snap = compute_buffett_munger_snapshot(
            col,
            year_data,
            annual_cols,
            abs_df,
            discount_rate,
            TERMINAL_GROWTH,
            PROJECTION_YEARS,
            shares_for_ps=shares_for_ps,
            g_fin_cap=None,
            include_net_cash_in_iv=True,
            exit_pes=exit_pes,
            rd_cap_ratio=rd_cap_ratio,
            rd_cap_industry=rd_cap_industry,
            maint_capex_ratio=maint_capex_ratio,
        )
        if snap is None:
            continue
        # ── 公司级 PE：总市值 ÷ 归母净利润 ─────────────────
        total_profit = safe_float(year_data[col].get("profit"))
        market_cap = (current_price * shares_for_ps) if current_price and shares_for_ps and shares_for_ps > 0 else None
        pe_anchor = (market_cap / total_profit) if market_cap and total_profit and total_profit > 0 else None
        # ── 公司级利润 CAGR ──────────────────────────────
        # 直接用归母净利润序列计算 CAGR，跟股数完全无关。
        col_idx = annual_cols.index(col) if col in annual_cols else -1
        cagr_pct = None
        cagr_start_year = None
        cagr_end_year = None
        cagr_reason = None
        if total_profit is not None and total_profit > 0 and col_idx > 0:
            for yb in [3, 4, 5, 6]:
                si = col_idx - yb
                if si < 0:
                    continue
                sc = annual_cols[si]
                sp = safe_float(year_data[sc].get("profit")) if sc in year_data else None
                periods = int(col[:4]) - int(sc[:4])
                if sp and sp > 0 and periods > 0:
                    cagr_pct = compute_cagr(sp, total_profit, periods)
                    if cagr_pct is not None:
                        cagr_start_year = sc[:4]
                        cagr_end_year = col[:4]
                        break
            if cagr_pct is None:
                cagr_reason = "no_positive_start"
        elif total_profit is not None and total_profit <= 0:
            cagr_reason = "end_profit_non_positive"
        # ── 股息率（公司级：总分红 ÷ 总市值）──────────────
        div_paid = safe_float(year_data[col].get("dividends_paid"))
        div_yield = (div_paid / market_cap * 100) if div_paid is not None and market_cap and market_cap > 0 else None
        peg = (pe_anchor / cagr_pct) if pe_anchor is not None and cagr_pct is not None and cagr_pct > 0 else None
        pegy = (pe_anchor / (cagr_pct + div_yield)) if pe_anchor is not None and cagr_pct is not None and div_yield is not None and (cagr_pct + div_yield) > 0 else None
        peg_reason = ""
        if peg is None:
            if cagr_pct is not None and cagr_pct <= 0:
                peg_reason = f"CAGR {fmt_pct(cagr_pct)}≤0"
            elif pe_anchor is None:
                peg_reason = "PE缺失"
            elif cagr_pct is None:
                peg_reason = "CAGR缺失"
        pegy_reason = ""
        if pegy is None:
            if cagr_pct is not None and div_yield is not None and (cagr_pct + div_yield) <= 0:
                pegy_reason = f"CAGR+股息率 {fmt_pct(cagr_pct + div_yield)}≤0"
            elif pe_anchor is None:
                pegy_reason = "PE缺失"
            elif cagr_pct is None:
                pegy_reason = "CAGR缺失"
            elif div_yield is None:
                pegy_reason = "股息率缺失"
        history.append(
            {
                "year": col[:4],
                "oe_ps": snap.get("avg_oe_ps"),
                "g_bm": (float(snap["g_bm"]) * 100) if snap.get("g_bm") is not None else None,
                "eps_cagr": cagr_pct,
                "eps_cagr_reason": cagr_reason,
                "eps_cagr_start_year": cagr_start_year,
                "eps_cagr_end_year": cagr_end_year,
                "div_yield": div_yield,
                "peg": peg,
                "pegy": pegy,
                "peg_reason": peg_reason,
                "pegy_reason": pegy_reason,
                "oe_dcf": snap.get("buf_total"),
                "oe_dcf_raw": snap.get("raw_buf_total"),
                "oe_dcf_reason": (
                    "OE<=0，DCF不适用"
                    if safe_float(snap.get("avg_oe_ps")) is not None and safe_float(snap.get("avg_oe_ps")) <= 0
                    else (
                    "净负债较高，股权价值<=0"
                    if safe_float(snap.get("raw_buf_total")) is not None
                    and safe_float(snap.get("raw_buf_total")) <= 0
                    and safe_float(snap.get("buf_dcf")) is not None
                    and safe_float(snap.get("buf_dcf")) > 0
                    and safe_float(snap.get("nc_iv")) is not None
                    and safe_float(snap.get("nc_iv")) < 0
                    else (
                        "经营现金流折现后价值<=0"
                        if safe_float(snap.get("raw_buf_total")) is not None and safe_float(snap.get("raw_buf_total")) <= 0
                        else ""
                    )
                    )
                ),
                "oe_mos": (float(snap["buf_total"]) * (1 - mos)) if snap.get("buf_total") is not None else None,
                "munger_lo": snap.get("munger", {}).get(exit_pes[0]) if snap.get("munger") else None,
                "munger_lo_raw": (snap.get("raw_munger") or {}).get(exit_pes[0]) if snap.get("raw_munger") else None,
                "munger_lo_mos": (float(snap["munger"][exit_pes[0]]) * (1 - mos)) if snap.get("munger") and snap["munger"].get(exit_pes[0]) is not None else None,
                "munger_mid": snap.get("munger", {}).get(exit_pes[1]) if snap.get("munger") else None,
                "munger_mid_raw": (snap.get("raw_munger") or {}).get(exit_pes[1]) if snap.get("raw_munger") else None,
                "munger_mid_reason": (
                    "OE<=0，远景估值不适用"
                    if safe_float(snap.get("avg_oe_ps")) is not None and safe_float(snap.get("avg_oe_ps")) <= 0
                    else (
                    "净负债较高，远景股权价值<=0"
                    if safe_float((snap.get("raw_munger") or {}).get(exit_pes[1])) is not None
                    and safe_float((snap.get("raw_munger") or {}).get(exit_pes[1])) <= 0
                    and safe_float(snap.get("nc_iv")) is not None
                    and safe_float(snap.get("nc_iv")) < 0
                    else (
                        "远景股权价值<=0"
                        if safe_float((snap.get("raw_munger") or {}).get(exit_pes[1])) is not None and safe_float((snap.get("raw_munger") or {}).get(exit_pes[1])) <= 0
                        else ""
                    )
                    )
                ),
                "munger_mid_mos": (float(snap["munger"][exit_pes[1]]) * (1 - mos)) if snap.get("munger") and snap["munger"].get(exit_pes[1]) is not None else None,
                "munger_hi": snap.get("munger", {}).get(exit_pes[2]) if snap.get("munger") else None,
                "munger_hi_raw": (snap.get("raw_munger") or {}).get(exit_pes[2]) if snap.get("raw_munger") else None,
                "munger_hi_mos": (float(snap["munger"][exit_pes[2]]) * (1 - mos)) if snap.get("munger") and snap["munger"].get(exit_pes[2]) is not None else None,
                "exit_pes": exit_pes,
                "payout": (float(snap["payout"]) * 100) if snap.get("payout") is not None else None,
                "diag_dcf": snap.get("diag_dcf"),
                "diag_munger": snap.get("diag_munger"),
                "share_basis_used": share_basis_used,
                "primary_basis": primary_basis,
                "strict_primary": (share_basis_used == primary_basis),
                "strict_asof": (share_basis_used == "asof_shares"),
            }
        )
        # Add bank-specific fields
        if is_bank and history:
            entry = history[-1]
            bps_val = safe_float(get_metric_first(abs_df, col, "每股净资产", "每股净资产_最新股数"))
            entry["bps"] = bps_val
            entry["pb"] = (current_price / bps_val) if current_price and current_price > 0 and bps_val and bps_val > 0 else None
            # Gordon DDM per year — weighted-average ROE (3:2:1) + g cap
            col_idx = annual_cols.index(col) if col in annual_cols else -1
            roe_wv = []
            for w, off in [(3, 0), (2, 1), (1, 2)]:
                ci = col_idx - off
                if 0 <= ci < len(annual_cols):
                    rv = safe_float(year_data[annual_cols[ci]].get("roe")) if annual_cols[ci] in year_data else None
                    if rv is not None:
                        roe_wv.append((rv, w))
            roe_val = sum(v * w for v, w in roe_wv) / sum(w for _, w in roe_wv) if roe_wv else None
            payout_v = safe_float(year_data[col].get("payout_ratio")) if col in year_data else None
            if payout_v is None and snap is not None and snap.get("payout") is not None:
                payout_v = float(snap["payout"])
            # --- payout fallback: dividends_paid / profit ---
            if payout_v is None and col in year_data:
                _dp = safe_float(year_data[col].get("dividends_paid"))
                _pr = safe_float(year_data[col].get("profit"))
                if _dp is not None and _pr is not None and _pr > 0:
                    payout_v = min(_dp / _pr, 1.0)
            gordon_val = None  # variable name kept for backward compat (now Excess Return)
            if roe_val is not None and bps_val and bps_val > 0 and payout_v is not None:
                g_g = roe_val / 100 * max(0.0, 1 - payout_v)
                g_g = min(g_g, TERMINAL_GROWTH)  # banks: perpetual growth ≤ GDP
                roe_dec = roe_val / 100
                if discount_rate > g_g and roe_dec > g_g:
                    gordon_val = bps_val * (roe_dec - g_g) / (discount_rate - g_g)
            entry["gordon_ddm"] = gordon_val
            entry["gordon_mos"] = (gordon_val * (1 - mos)) if gordon_val is not None else None
    return list(reversed(history))


def _detect_cumulative_price_split_factor_after(
    daily_df: "pd.DataFrame",
    close_col: str,
    after_dt: "pd.Timestamp",
    split_threshold: float = 0.45,
) -> float:
    """从日线价格序列中检测 after_dt 之后发生的所有拆股，返回累积拆股倍数。

    通过检测相邻交易日间价格骤降（< split_threshold 倍）来识别拆股事件：
    例如 AAPL Aug-28 $499 → Aug-31 $129（比值 0.258 < 0.45）→ 识别为 4:1 拆股。
    用于将东方财富不复权价格还原到历史实际市值的正确分母。

    仅用于美股（A 股用 nfq+历史实际股本，不需要价格修正）。
    """
    subset = daily_df[daily_df["dt"] > after_dt].sort_values("dt")
    if subset.empty:
        return 1.0
    prices = subset[close_col].values
    cumulative = 1.0
    for i in range(1, len(prices)):
        p_prev, p_curr = prices[i - 1], prices[i]
        if p_prev > 0 and p_curr > 0:
            ratio = p_curr / p_prev
            if ratio < split_threshold:  # 隔夜暴跌 >55% → 拆股
                implied = 1.0 / ratio
                rounded = round(implied)
                if 2 <= rounded <= 20:  # 合理拆股范围
                    cumulative *= rounded
    return cumulative


def build_oe_yield_history(
    code: str,
    year_data: dict,
    all_annual_cols_sorted: list,
    shares_for_ps: Optional[float],
    rd_cap_ratio: float = 0.0,
    maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO,
    years_back: int = 12,
) -> List[Dict[str, object]]:
    """逐年计算三口径 OE 收益率（OE per share / 年末 MA200）。

    返回列表（时间正序），每项包含：
      year, ma200_price, pess_oe_ps, base_oe_ps, leni_oe_ps,
      pess_yield, base_yield, leni_yield
    收益率单位：%；OE per share 单位：元/股。

    注意：
    - A 股：使用 valuation_shares（巨潮实际期末股本）+ nfq 不复权价格，历史口径一致。
    - 美股：东财 fqt=0 价格含拆股跳变，通过 _detect_cumulative_price_split_factor_after()
      检测年末之后发生的累积拆股倍数，用"历史实际股本 × 历史实际价格"计算历史市值。
      具体：shares_denom = raw_shares / price_split_factor；effective_price = ma200（不变）
      → 等价于 pa/ps = (OE/actual_shares) / actual_price = OE / actual_market_cap。
    - 不应用 OE_HAIRCUT（这里是历史还原，不是估值打折）。
    - MA200 不足 200 个交易日时跳过该年。
    """
    if not all_annual_cols_sorted or shares_for_ps is None or shares_for_ps <= 0:
        return []

    # ── 获取日线数据并计算 MA200 ─────────────────────────────
    try:
        daily = fetch_stock_daily_hist_long(code, years_back=years_back)
    except Exception:
        return []
    if daily is None or daily.empty:
        return []

    close_col = _close_column(daily)
    if close_col is None or "dt" not in daily.columns:
        return []

    daily = daily.sort_values("dt").copy()
    daily["_ma200"] = daily[close_col].rolling(200).mean()

    # 判断是否为美股（东财不复权价格含拆股跳变，需用价格序列检测拆股并修正）
    try:
        from core import data_hk_us as _dhku
        _is_us = (getattr(_dhku, "MARKET", "") == "us")
    except Exception:
        _is_us = False

    results: List[Dict[str, object]] = []
    for col in all_annual_cols_sorted:
        dc = year_data.get(col)
        if dc is None:
            continue

        oe_triple = _owner_earnings_three_caliber(dc, rd_cap_ratio, maint_capex_ratio)
        if oe_triple is None:
            continue
        pess, base, leni = oe_triple  # 单位：亿元（公司级）

        # 年末最后一个交易日的 MA200
        year_int = int(col[:4])
        year_rows = daily[daily["dt"].dt.year == year_int]
        if year_rows.empty:
            continue
        last_row = year_rows.iloc[-1]
        ma200_val = last_row["_ma200"]
        if pd.isna(ma200_val) or ma200_val <= 0:
            continue  # MA200 不足 200 个交易日

        # OE 收益率历史回答的是“当年每股 OE / 当年价格”，应优先使用 as-of 股本口径。
        yr_asof_shares = safe_float(dc.get("asof_shares")) if dc else None
        if yr_asof_shares and yr_asof_shares > 0:
            ps_denom = yr_asof_shares
        else:
            yr_vs = safe_float(dc.get("valuation_shares")) if dc else None
            if yr_vs and yr_vs > 0:
                ps_denom = yr_vs
            else:
                yr_reported = safe_float(dc.get("reported_shares")) if dc else None
                ps_denom = yr_reported if (yr_reported and yr_reported > 0) else shares_for_ps

        if not ps_denom or ps_denom <= 0:
            continue

        pess_ps = pess / ps_denom
        base_ps = base / ps_denom
        leni_ps = leni / ps_denom

        results.append({
            "year": str(year_int),
            "ma200_price": round(float(ma200_val), 2),
            "pess_oe_ps": round(pess_ps, 4),
            "base_oe_ps": round(base_ps, 4),
            "leni_oe_ps": round(leni_ps, 4),
            "pess_yield": round(pess_ps / ma200_val * 100, 2),
            "base_yield": round(base_ps / ma200_val * 100, 2),
            "leni_yield": round(leni_ps / ma200_val * 100, 2),
        })

    return results
