# core/orchestrator.py — auto-extracted
from __future__ import annotations

import inspect
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import (
    REPORTS_DIR, OUTPUT_DIR, DISCOUNT_RATE, TERMINAL_GROWTH,
    PROJECTION_YEARS, MARGIN_OF_SAFETY, FADE_RATE, OE_HAIRCUT,
    G_MAX_CAP, LAST_PROFILE,
    _compute_dynamic_mos, _get_industry_discount, _get_industry_exit_pes,
    MAINT_CAPEX_FLOOR_RATIO, MetricAssessment, ValuationAssessment,
    DataProvider, _dp, _get_maint_capex_floor_ratio, _get_rd_capitalization_ratio,
)
from valuescope.legacy_stock_scripts.core.utils import (
    get_metric, get_metric_first, get_deduct_parent_net_profit,
    get_real_eps, safe_float, fmt_pct, fmt_num, fmt_yi,
    series_values, trend_text, is_bank, _trend_arrow, pick_first_column,
)
from valuescope.legacy_stock_scripts.core.data_a import (
    get_company_info, get_current_price, load_data,
    fetch_cashflow_extras, fetch_balance_sheet_extras,
    fetch_income_extras, annual_cols_from_abstract,
    build_year_data_for_valuation,
    fetch_listed_pledge_snapshot_safe, fetch_bank_kpi,
    fetch_eastmoney_bank_data,
    build_pb_history_post_may, build_dual_pe_history_post_may,
    infer_asset_style, fetch_market_pe_anchor,
    current_assets_and_liabilities,
    fetch_share_change_history_safe, fetch_restricted_release_queue_safe,
    _filter_data_as_of_year, get_historical_price_as_of,
)
from valuescope.legacy_stock_scripts.core.valuation import (
    estimate_growth_rate, compute_cagr, build_eps_cagr_snapshot,
    compute_buffett_munger_snapshot, roic_percent_from_year_data,
    interest_coverage_ratio_tag_value,
    build_valuation_assessments, build_valuation_conclusion,
    build_valuation_history, build_oe_yield_history,
)
from valuescope.legacy_stock_scripts.core.assessment import (
    build_summary_metrics, build_conclusion,
    build_bank_summary_metrics, build_bank_conclusion,
    assess_revenue_growth, assess_gm_delta, assess_opex_trend,
    assess_asset_turnover, assess_roe_ses,
    build_ses_metrics, build_ses_conclusion,
    build_quality_cards, build_quality_module_notes,
    build_share_capital_analysis, build_extended_diagnostics,
    build_quality_year_snapshots, summarize_business_quality,
    _build_feature_sketch,
    build_data_quality_report,
    build_dollar_retention_test,
)
from valuescope.legacy_stock_scripts.core.render import render_html
from valuescope.legacy_stock_scripts.core.technicals import (
    build_williams_r, build_market_env,
    _render_wr_section, _render_market_env_section,
)


def self_check() -> None:
    expected = [
        ("render_html", ["code", "company_name", "rows", "metrics", "conclusions", "ses_metrics", "ses_conclusions", "valuation_metrics", "valuation_conclusions", "valuation_details", "valuation_history", "diagnostics", "is_bank", "wr_data", "market_env_data", "data_quality", "oe_yield_history", "dollar_retention"]),
        ("generate_report", ["code", "years", "asof_year", "asof_price"]),
        ("build_extended_diagnostics", ["code", "data", "total_shares", "years", "maint_capex_ratio"]),
    ]
    failures = []
    scope = globals()
    for fn_name, params in expected:
        fn = scope.get(fn_name)
        if fn is None:
            failures.append(f"缺少函数: {fn_name}")
            continue
        sig = inspect.signature(fn)
        actual = list(sig.parameters.keys())
        if actual != params:
            failures.append(f"{fn_name} 参数不匹配: 期望 {params}，实际 {actual}")
    if failures:
        raise RuntimeError("脚本自检失败:\n" + "\n".join(failures))

def build_year_rows(data: Dict[str, pd.DataFrame], years: int) -> List[Dict]:
    abs_df = data["abstract"]
    income_df = data["income"]
    balance_df = data["balance"]
    cf_extras = data["cashflow_extras"]
    bank_flag = bool(data.get("is_bank"))

    annual_cols = annual_cols_from_abstract(abs_df)
    if not annual_cols:
        return []

    # Compute bank KPIs upfront if applicable
    bank_kpi_map: Dict[str, Dict] = {}
    em_bank_map: Dict[str, Dict] = {}
    if bank_flag:
        # Reuse pre-computed map if generate_report() already fetched it
        bank_kpi_map = data.get("_bank_kpi_map") or fetch_bank_kpi(data, annual_cols)
        em_bank_map = data.get("_em_bank") or {}

    revenue_col = pick_first_column(income_df, ("营业总收入", "营业收入"))
    cost_col = pick_first_column(income_df, ("营业成本", "营业总成本"))
    selling_col = pick_first_column(income_df, ("销售费用", "营业费用", "销售及分销费用"))
    admin_col = pick_first_column(income_df, ("管理费用",))
    rnd_col = pick_first_column(income_df, ("研发费用", "研发支出"))
    op_profit_col = pick_first_column(income_df, ("营业利润",))

    inventory_col = pick_first_column(balance_df, ("存货",))
    ar_col = pick_first_column(balance_df, ("应收账款", "应收票据及应收账款"))
    ap_col = pick_first_column(balance_df, ("应付账款", "应付票据及应付账款"))

    cf_map: Dict[str, pd.Series] = {}
    if cf_extras is not None and not cf_extras.empty:
        cf_extras = cf_extras.copy()
        cf_extras["报告日"] = cf_extras["报告日"].astype(str)
        cf_map = {
            str(row["报告日"]): row
            for _, row in cf_extras.iterrows()
        }

    income_map = {}
    if not income_df.empty:
        income_map = {str(row["报告日"]): row for _, row in income_df.iterrows()}

    balance_map = {}
    if not balance_df.empty:
        balance_map = {str(row["报告日"]): row for _, row in balance_df.iterrows()}

    ordered = annual_cols[-years:]

    # Filter out years with severely incomplete data (no net income from any
    # source).  Without net income, almost no useful ratio can be computed and
    # the year row would be full of N/A values.
    def _has_net_income(col: str) -> bool:
        if safe_float(get_metric(abs_df, "归母净利润", col)) is not None:
            return True
        ri = income_map.get(col)
        if ri is not None:
            for _c in ("归属于母公司所有者的净利润", "净利润"):
                if _c in ri.index and safe_float(ri[_c]) is not None:
                    return True
        return False

    ordered = [c for c in ordered if _has_net_income(c)]

    rows: List[Dict] = []
    prev_inventory = None
    prev_ar = None
    prev_ap = None
    prev_revenue = None
    prev_gross_margin = None
    for col in ordered:
        row_income = income_map.get(col)
        row_balance = balance_map.get(col)
        row_cf = cf_map.get(col)

        gross_margin = safe_float(get_metric(abs_df, "毛利率", col))
        net_income = safe_float(get_metric(abs_df, "归母净利润", col))

        revenue = safe_float(row_income[revenue_col]) if row_income is not None and revenue_col else None
        operating_cost = safe_float(row_income[cost_col]) if row_income is not None and cost_col else None

        # Sanity check: recompute gross margin from income data if abstract value
        # is clearly corrupted (e.g. -412% due to mismatched revenue/cost)
        if revenue and revenue > 0 and operating_cost is not None:
            computed_gm = (revenue - operating_cost) / revenue * 100
            if gross_margin is not None and abs(gross_margin - computed_gm) > 50:
                gross_margin = computed_gm
            elif gross_margin is None:
                gross_margin = computed_gm
        if gross_margin is not None and (gross_margin < -100 or gross_margin > 100):
            gross_margin = None
        selling_expense = safe_float(row_income[selling_col]) if row_income is not None and selling_col else None
        admin_expense = safe_float(row_income[admin_col]) if row_income is not None and admin_col else None
        rnd_expense = safe_float(row_income[rnd_col]) if row_income is not None and rnd_col else None
        operating_profit = safe_float(row_income[op_profit_col]) if row_income is not None and op_profit_col else None

        inventory_end = safe_float(row_balance[inventory_col]) if row_balance is not None and inventory_col else None
        ar_end = safe_float(row_balance[ar_col]) if row_balance is not None and ar_col else None
        ap_end = safe_float(row_balance[ap_col]) if row_balance is not None and ap_col else None

        if operating_cost is None and revenue is not None and gross_margin is not None:
            operating_cost = revenue * max(0.0, 1.0 - gross_margin / 100.0)
        if inventory_col is None:
            inventory_end = 0.0
        if ar_col is None:
            ar_end = 0.0

        capex = safe_float(row_cf["capex"]) if row_cf is not None and "capex" in row_cf else None
        ocf = safe_float(row_cf["ocf"]) if row_cf is not None and "ocf" in row_cf else None

        selling_ratio = None
        admin_ratio = None
        rnd_ratio = None
        purity = None
        purity_with_rnd = None
        if revenue and revenue > 0:
            if selling_expense is not None:
                selling_ratio = selling_expense / revenue * 100
            if admin_expense is not None:
                admin_ratio = admin_expense / revenue * 100
            if rnd_expense is not None:
                rnd_ratio = rnd_expense / revenue * 100
            if gross_margin is not None and selling_ratio is not None and admin_ratio is not None:
                purity = gross_margin - selling_ratio - admin_ratio
                purity_with_rnd = purity - rnd_ratio if rnd_ratio is not None else None

        dio = None
        if operating_cost and operating_cost > 0 and inventory_end is not None:
            inventory_avg = (prev_inventory + inventory_end) / 2 if prev_inventory is not None else inventory_end
            dio = inventory_avg / operating_cost * 365

        dso = None
        if revenue and revenue > 0 and ar_end is not None:
            ar_avg = (prev_ar + ar_end) / 2 if prev_ar is not None else ar_end
            dso = ar_avg / revenue * 365

        dpo = None
        if operating_cost and operating_cost > 0 and ap_end is not None:
            ap_avg = (prev_ap + ap_end) / 2 if prev_ap is not None else ap_end
            dpo = ap_avg / operating_cost * 365

        ccc = None
        if dio is not None and dso is not None and dpo is not None:
            ccc = dio + dso - dpo

        capex_net_income = None
        if capex is not None and net_income and abs(net_income) > 1e-9:
            capex_net_income = capex / net_income * 100

        revenue_growth = None
        if revenue is not None and prev_revenue is not None and abs(prev_revenue) > 1e-9:
            revenue_growth = (revenue - prev_revenue) / prev_revenue * 100

        gm_delta = None
        if gross_margin is not None and prev_gross_margin is not None:
            gm_delta = gross_margin - prev_gross_margin

        opex_ratio = None
        if revenue and revenue > 0:
            sr = selling_ratio or 0.0
            ar = admin_ratio or 0.0
            opex_ratio = sr + ar

        asset_turnover = safe_float(get_metric(abs_df, "总资产周转率", col))
        roe = safe_float(get_metric_first(abs_df, col, "净资产收益率(ROE)", "净资产收益率_平均"))

        rows.append(
            {
                "year": col[:4],
                "date_key": col,
                "gross_margin": gross_margin,
                "revenue": revenue,
                "operating_cost": operating_cost,
                "selling_ratio": selling_ratio,
                "admin_ratio": admin_ratio,
                "rnd_ratio": rnd_ratio,
                "purity": purity,
                "purity_with_rnd": purity_with_rnd,
                "inventory_end": inventory_end,
                "ar_end": ar_end,
                "ap_end": ap_end,
                "dio": dio,
                "dso": dso,
                "dpo": dpo,
                "ccc": ccc,
                "operating_profit": operating_profit,
                "capex": capex,
                "ocf": ocf,
                "net_income": net_income,
                "capex_net_income": capex_net_income,
                "revenue_growth": revenue_growth,
                "gm_delta": gm_delta,
                "opex_ratio": opex_ratio,
                "asset_turnover": asset_turnover,
                "roe": roe,
            }
        )

        # Inject bank-specific KPIs into row
        if bank_flag and col in bank_kpi_map:
            bk = bank_kpi_map[col]
            rows[-1].update({
                "nim": bk.get("nim"),
                "cost_income_ratio": bk.get("cost_income_ratio"),
                "provision_loan_ratio": bk.get("provision_loan_ratio"),
                "loan_deposit_ratio": bk.get("loan_deposit_ratio"),
                "leverage_ratio": bk.get("leverage_ratio"),
                "total_assets": bk.get("total_assets"),
                "parent_equity": bk.get("parent_equity"),
                "gross_loans": bk.get("gross_loans"),
                "deposits": bk.get("deposits"),
                "net_interest_income": bk.get("net_interest_income"),
                "credit_impairment": bk.get("credit_impairment"),
                "biz_admin_expense": bk.get("biz_admin_expense"),
                "loan_provisions": bk.get("loan_provisions"),
                "pretax_profit": bk.get("pretax_profit"),
                "net_profit_parent": bk.get("net_profit_parent"),
                "goodwill": bk.get("goodwill"),
                "intangible_assets": bk.get("intangible_assets"),
                "interest_expense": bk.get("interest_expense"),
            })
            # For banks, derive ROA from abstract
            roa = safe_float(get_metric_first(abs_df, col, "总资产收益率(ROA)", "总资产报酬率(ROA)", "总资产报酬率", "总资产净利率_平均"))
            if roa is None and net_income is not None and bk.get("total_assets") and bk["total_assets"] > 0:
                roa = net_income / bk["total_assets"] * 100
            rows[-1]["roa"] = roa
            # Override with official EastMoney regulatory data
            if col in em_bank_map:
                for _ek, _ev in em_bank_map[col].items():
                    if _ev is not None:
                        rows[-1][_ek] = _ev

        if inventory_end is not None:
            prev_inventory = inventory_end
        if ar_end is not None:
            prev_ar = ar_end
        if ap_end is not None:
            prev_ap = ap_end
        if revenue is not None:
            prev_revenue = revenue
        if gross_margin is not None:
            prev_gross_margin = gross_margin

    # ---- Bank post-processing: NCO + PPOP ----
    if bank_flag and len(rows) > 0:
        for i, r in enumerate(rows):
            # PPOP = revenue - biz_admin_expense
            _rev = r.get("revenue")
            _bae = r.get("biz_admin_expense")
            if _rev is not None and _bae is not None:
                r["ppop"] = _rev - _bae
            else:
                r["ppop"] = None

            # PPOP / Avg Assets
            _ta_cur = r.get("total_assets")
            if i > 0:
                _ta_prev = rows[i - 1].get("total_assets")
            else:
                _ta_prev = None
            if r.get("ppop") is not None and _ta_cur and _ta_cur > 0:
                avg_ta = ((_ta_prev + _ta_cur) / 2) if _ta_prev else _ta_cur
                r["ppop_avg_assets"] = r["ppop"] / avg_ta * 100
            else:
                r["ppop_avg_assets"] = None

            # NCO = prior_allowance + credit_impairment - current_allowance
            _lla_cur = r.get("loan_loss_allowance")
            _ci = r.get("credit_impairment")
            if _lla_cur is None and r.get("loan_provisions"):
                _lla_cur = r["loan_provisions"]  # fallback to Sina
            if i > 0:
                _lla_prev = rows[i - 1].get("loan_loss_allowance")
                if _lla_prev is None:
                    _lla_prev = rows[i - 1].get("loan_provisions")
            else:
                _lla_prev = None
            if _lla_prev is not None and _ci is not None and _lla_cur is not None:
                nco = _lla_prev + _ci - _lla_cur
                r["nco"] = nco

                # NCO / Avg Loans
                _gl_cur = r.get("total_loans") or r.get("gross_loans")
                _gl_prev = rows[i - 1].get("total_loans") or rows[i - 1].get("gross_loans") if i > 0 else None
                if _gl_cur and _gl_cur > 0:
                    avg_gl = ((_gl_prev + _gl_cur) / 2) if _gl_prev else _gl_cur
                    r["nco_avg_loans"] = nco / avg_gl * 100
                else:
                    r["nco_avg_loans"] = None

                # Provision / NCO cover
                if nco > 0:
                    r["provision_nco_cover"] = _ci / nco
                else:
                    r["provision_nco_cover"] = None
            else:
                r["nco"] = None
                r["nco_avg_loans"] = None
                r["provision_nco_cover"] = None

            # PPNR = pretax_profit + credit_impairment (add back provision charge)
            _pretax = r.get("pretax_profit")
            if _pretax is not None and _ci is not None:
                r["ppnr"] = _pretax + abs(_ci)
            else:
                r["ppnr"] = None

            # PPNR / Avg Assets
            if r.get("ppnr") is not None and _ta_cur and _ta_cur > 0:
                avg_ta_ppnr = ((_ta_prev + _ta_cur) / 2) if _ta_prev else _ta_cur
                r["ppnr_avg_assets"] = r["ppnr"] / avg_ta_ppnr * 100
            else:
                r["ppnr_avg_assets"] = None

            # ROTCE = net_profit_parent / (parent_equity - goodwill - intangible_assets) × 100%
            _npp = r.get("net_profit_parent")
            _eq = r.get("parent_equity")
            _gw = r.get("goodwill") or 0
            _ia = r.get("intangible_assets") or 0
            if _npp is not None and _eq is not None:
                tce = _eq - _gw - _ia
                if tce > 0:
                    r["rotce"] = _npp / tce * 100
                else:
                    r["rotce"] = None
            else:
                r["rotce"] = None

            # Deposit cost rate (proxy) = 利息支出 / 平均存款 × 100%
            _ie = r.get("interest_expense")
            _dep_cur = r.get("deposits")
            _dep_prev = rows[i - 1].get("deposits") if i > 0 else None
            if _ie is not None and _dep_cur and _dep_cur > 0:
                avg_dep = ((_dep_prev + _dep_cur) / 2) if _dep_prev else _dep_cur
                r["deposit_cost_rate"] = _ie / avg_dep * 100
            else:
                r["deposit_cost_rate"] = None

    return rows

def generate_report(code: str, years: int, asof_year: Optional[int] = None, asof_price: Optional[float] = None) -> Path:
    t0 = time.perf_counter()
    name, total_shares, industry_text = get_company_info(code)
    t_company = time.perf_counter()
    data = load_data(code)
    if asof_year is not None:
        data = _filter_data_as_of_year(data, asof_year)
        asof_date = pd.Timestamp(f"{int(asof_year):04d}-12-31")
        if asof_price is not None and asof_price > 0:
            data["current_price_tuple"] = (float(asof_price), "手工指定(as-of)", str(asof_date.date()))
        else:
            data["current_price_tuple"] = get_historical_price_as_of(code, asof_date)
        total_shares = None
    bank_flag = is_bank(industry_text, name)
    data["is_bank"] = bank_flag
    # is_bank was not set during load_data(), so year_data lacks bank KPIs.
    # Re-inject them now that we know it's a bank.
    if bank_flag:
        yd = data.get("year_data")
        if isinstance(yd, dict) and yd:
            bank_kpi_map = fetch_bank_kpi(data, list(yd.keys()))
            data["_bank_kpi_map"] = bank_kpi_map
            for _col, _bk in bank_kpi_map.items():
                if _col in yd:
                    yd[_col].update({
                        "nim": _bk.get("nim"),
                        "cost_income_ratio": _bk.get("cost_income_ratio"),
                        "provision_loan_ratio": _bk.get("provision_loan_ratio"),
                        "provision_coverage_ratio": _bk.get("provision_coverage_ratio"),
                        "loan_deposit_ratio": _bk.get("loan_deposit_ratio"),
                        "leverage_ratio": _bk.get("leverage_ratio"),
                        "capital_adequacy_ratio": _bk.get("capital_adequacy_ratio"),
                        "capital_buffer_ratio": _bk.get("capital_buffer_ratio"),
                        "total_assets": _bk.get("total_assets"),
                        "parent_equity": _bk.get("parent_equity"),
                    })
            # Override with official regulatory data from EastMoney
            em_bank = fetch_eastmoney_bank_data(code)
            for _col, _em in em_bank.items():
                if _col in yd:
                    for _k, _v in _em.items():
                        if _v is not None:
                            yd[_col][_k] = _v
            # Store for build_year_rows to pick up
            data["_em_bank"] = em_bank
    t_data = time.perf_counter()
    rows = build_year_rows(data, years)
    if not rows:
        raise RuntimeError("未找到可用年报数据")
    latest_year = rows[-1]["year"]
    t_rows = time.perf_counter()

    # 先构建股本诊断，提取“经济股本”作为估值每股口径，避免送转/拆股造成名义稀释噪音。
    maint_capex_ratio, maint_capex_key = _get_maint_capex_floor_ratio(industry_text, name)
    rd_cap_ratio, _ = _get_rd_capitalization_ratio(industry_text, name)
    diagnostics = build_extended_diagnostics(code, data, total_shares, max(4, years), maint_capex_ratio=maint_capex_ratio)
    # 估值分母必须用实际总股本，不可用 economic_total_shares（仅剔除送转/拆股后的虚拟
    # 股本，用于股本质量模块展示融资稀释）。否则送转后分母缩水，每股OE严重虚高。
    valuation_shares = total_shares
    diag_year_data = diagnostics.get("year_data") or {}
    diag_annual_cols = diagnostics.get("annual_cols") or []
    preferred_share_key = "asof_shares" if data.get("_share_basis_mode") == "asof" else "valuation_shares"
    if valuation_shares is None and diag_annual_cols:
        latest_diag = diag_year_data.get(diag_annual_cols[-1]) or {}
        valuation_shares = safe_float(latest_diag.get(preferred_share_key))
        if valuation_shares is None:
            valuation_shares = safe_float(latest_diag.get("reported_shares"))
    # API 偶发返回 None 时，从股本诊断的实际总股本回补
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
        conclusions = build_bank_conclusion(rows, stats)
        ses_metrics, ses_details = [], {}
        ses_conclusions = []
    else:
        metrics, stats = build_summary_metrics(rows)
        conclusions = build_conclusion(rows, stats)
        ses_metrics, ses_details = build_ses_metrics(rows)
        ses_conclusions = build_ses_conclusion(rows, ses_details)
    dynamic_mos, mos_grade = _compute_dynamic_mos(metrics)
    ind_discount, ind_discount_key = _get_industry_discount(industry_text, name)
    ind_exit_pes, ind_exit_pe_key = _get_industry_exit_pes(industry_text)
    valuation_metrics, valuation_details = build_valuation_assessments(code, name, industry_text, valuation_shares, data, mos=dynamic_mos, discount_rate=ind_discount, exit_pes=ind_exit_pes)
    valuation_details["mos_ratio"] = dynamic_mos
    valuation_details["mos_grade"] = mos_grade
    valuation_details["discount_rate"] = ind_discount
    valuation_details["discount_rate_key"] = ind_discount_key
    valuation_details["exit_pes"] = ind_exit_pes
    valuation_details["exit_pe_key"] = ind_exit_pe_key
    valuation_details["shares_for_valuation"] = valuation_shares
    valuation_conclusions = build_valuation_conclusion(valuation_details)
    valuation_history = build_valuation_history(data, valuation_shares, is_bank=bank_flag, mos=dynamic_mos, discount_rate=ind_discount, exit_pes=ind_exit_pes, industry_text=industry_text, company_name=name, history_years=years)
    oe_yield_history = build_oe_yield_history(
        code,
        diagnostics.get("year_data") or {},
        diagnostics.get("annual_cols") or [],
        valuation_shares,
        rd_cap_ratio=rd_cap_ratio,
        maint_capex_ratio=maint_capex_ratio,
        years_back=max(years, 12),
    )
    wr_data = None if asof_year is not None else build_williams_r(code)
    pe_for_env = safe_float(valuation_details.get("pe_current"))
    market_env_data = None if asof_year is not None else build_market_env(pe_current=pe_for_env)
    data_quality = build_data_quality_report(rows, valuation_metrics, valuation_details, diagnostics, industry_text, is_bank=bank_flag)
    dollar_retention = build_dollar_retention_test(
        diagnostics.get("year_data") or {},
        diagnostics.get("annual_cols") or [],
        valuation_shares,
        oe_yield_history,
        rd_cap_ratio=rd_cap_ratio,
        maint_capex_ratio=maint_capex_ratio,
    )
    t_analysis = time.perf_counter()

    out_dir = _dp.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{latest_year}_{name}_{code}_pricing_power.html"
    html_doc = render_html(
        code,
        name,
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
        is_bank=bank_flag,
        wr_data=wr_data,
        market_env_data=market_env_data,
        data_quality=data_quality,
        oe_yield_history=oe_yield_history,
        dollar_retention=dollar_retention,
    )
    out_path.write_text(html_doc, encoding="utf-8")
    t_write = time.perf_counter()
    LAST_PROFILE.clear()
    LAST_PROFILE.update({
        "company_info": t_company - t0,
        "load_data": t_data - t_company,
        "build_rows": t_rows - t_data,
        "analysis": t_analysis - t_rows,
        "render_write": t_write - t_analysis,
        "total": t_write - t0,
    })
    return out_path
