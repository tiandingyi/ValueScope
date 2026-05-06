# core/assessment.py — auto-extracted
from __future__ import annotations

import html
import math
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import (
    DISCOUNT_RATE, TERMINAL_GROWTH, PROJECTION_YEARS, MARGIN_OF_SAFETY,
    FADE_RATE, OE_HAIRCUT, G_MAX_CAP, LAST_PROFILE,
    _compute_dynamic_mos, _get_industry_discount, _get_industry_exit_pes,
    MAINT_CAPEX_FLOOR_RATIO, MetricAssessment, ValuationAssessment,
    _dp, DataProvider,
)
from valuescope.legacy_stock_scripts.core.utils import (
    get_metric, get_metric_first, get_deduct_parent_net_profit,
    get_real_eps, safe_float, fmt_pct, fmt_days, fmt_ratio, fmt_num,
    fmt_yi, fmt_shares, series_values, trend_text, _trend_arrow,
    pick_first_column, annualize, is_bank, _equity_denom,
    tone_class, wrap_value,
    _parse_cninfo_share_count, _parse_restricted_release_share_count,
)
from valuescope.legacy_stock_scripts.core.data_a import (
    get_company_info, get_current_price, load_data,
    fetch_cashflow_extras, fetch_balance_sheet_extras,
    fetch_income_extras, annual_cols_from_abstract,
    build_year_data_for_valuation, infer_asset_style,
    fetch_share_change_history_safe, fetch_restricted_release_queue_safe,
    current_assets_and_liabilities,
    fetch_listed_pledge_snapshot_safe, fetch_bank_kpi,
)
from valuescope.legacy_stock_scripts.core.valuation import (
    dcf_two_stage, dcf_zero_growth_perpetuity, dcf_fade,
    estimate_growth_rate, compute_cagr, build_eps_cagr_snapshot,
    _owner_earnings_company, _owner_earnings_three_caliber,
    compute_buffett_munger_snapshot, roic_percent_from_year_data,
    interest_coverage_ratio_tag_value,
    build_valuation_assessments, build_valuation_conclusion,
    build_valuation_history,
)


def _rate(
    val: Optional[float],
    *thresholds: Tuple,
    none_tone: str = "muted",
) -> str:
    """通用三色/多级评级工具。

    用法示例:
        _rate(val, ("good", lambda v: v >= 40), ("warn", lambda v: v >= 30))
        # 匹配第一个为 True 的 lambda 返回对应 tone，全不匹配返回 "bad"。
        # val 为 None 时返回 none_tone。

    thresholds: 每个元素为 (tone_str, predicate_fn)，按顺序检查。
    """
    if val is None:
        return none_tone
    for tone, pred in thresholds:
        if pred(val):
            return tone
    return "bad"

# ── 预定义评级规则（供 assess_*, build_quality_cards, render_html 共用） ──

def _rate_roa(v):          return _rate(v, ("good", lambda x: x > 10), ("warn", lambda x: x >= 5))

def _rate_roe_roic_gap(v): return _rate(v, ("good", lambda x: x <= 6), ("warn", lambda x: x <= 10))

def _rate_icr(v, tag=None):
    if tag == "surplus":
        return "good"
    return _rate(v, ("good", lambda x: x >= 5), ("warn", lambda x: x >= 2))

def _rate_roic(v):         return _rate(v, ("good", lambda x: x >= 10), ("warn", lambda x: x >= 6))

def _rate_ocf_ratio(v):    return _rate(v, ("good", lambda x: x >= 100), ("warn", lambda x: x >= 70))

def _rate_goodwill(v):     return _rate(v, ("good", lambda x: x < 10), ("warn", lambda x: x <= 30))

def _rate_tax(v):          return _rate(v, ("good", lambda x: 7 <= x <= 32), ("warn", lambda x: 5 <= x <= 40))

def _rate_pledge(v):       return _rate(v, ("good", lambda x: x < 20), ("warn", lambda x: x < 50))

def _rate_payout(v):       return _rate(v, ("good", lambda x: 30 <= x <= 70), ("warn", lambda x: x <= 100))

def _rate_total_yield(v):  return _rate(v, ("good", lambda x: x >= 4), ("warn", lambda x: x >= 2))

def _rate_total_yield_with_context(v, roic=None, net_buyback=None):
    """Context-aware rating for total shareholder yield considering ROIC."""
    if v is None:
        return "muted", "缺数据"
    # P2: net dilution warning
    dilution_note = ""
    if net_buyback is not None and net_buyback < 0:
        dilution_note = "（存在净增发稀释）"
    # P0: ROIC-linked assessment
    if v >= 4:
        return "good", f"高回馈{dilution_note}" if not dilution_note else f"高回馈{dilution_note}"
    if v >= 2:
        return "warn", f"有回馈{dilution_note}" if not dilution_note else f"有回馈{dilution_note}"
    # low yield — check if justified by high ROIC
    if roic is not None and roic >= 15:
        return "warn", f"低回馈但再投资效率高{dilution_note}"
    if roic is not None and roic < 10:
        return "bad", f"回馈偏弱且再投资效率不高{dilution_note}"
    return "bad", f"回馈偏弱{dilution_note}"

def _rate_eps_quality(v):  return _rate(v, ("good", lambda x: x >= 1), ("warn", lambda x: x >= 0.8))

def _rate_roe_render(v):   return _rate(v, ("good", lambda x: x > 15), ("warn", lambda x: x >= 10))

def _rate_unlock(v):       return _rate(v, ("good", lambda x: x < 5), ("warn", lambda x: x <= 15))

def _rate_valuation_gap(v): return _rate(v, ("good", lambda x: x <= -15), ("warn", lambda x: x < 0))

def _rate_real_eps(v):      return "good" if v is not None and v > 0 else "bad"

def assess_gross_margin(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x >= 40), ("warn", lambda x: x >= 30))
    labels = {"good": "优秀", "warn": "尚可" if latest >= 30 else "一般", "bad": "偏弱"}
    return tone, labels.get(tone, "一般")

def assess_gm_std(std: Optional[float]) -> Tuple[str, str]:
    if std is None:
        return "muted", "缺数据"
    # B级：毛利率稳定性阈值（<5稳，>8波动偏高）来自跨周期经验口径。
    tone = _rate(std, ("good", lambda x: x <= 5), ("warn", lambda x: x <= 8))
    if tone == "good":
        return tone, "顶级稳定" if std < 2 else "优秀稳定"
    return tone, "波动偏大" if tone == "warn" else "明显不稳"

def assess_purity(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x > 20), ("warn", lambda x: x >= 10))
    return tone, {"good": "优秀", "warn": "一般", "bad": "偏弱"}[tone]

def assess_dso(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x < 45), ("warn", lambda x: x <= 60))
    return tone, {"good": "回款强", "warn": "可接受", "bad": "回款偏慢"}[tone]

def assess_dpo(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x > 60), ("warn", lambda x: x >= 45))
    return tone, {"good": "占款能力强", "warn": "一般", "bad": "议价偏弱"}[tone]

def assess_ccc(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x <= 0), ("warn", lambda x: x <= 60))
    if tone == "warn":
        return tone, "尚可" if latest <= 30 else "偏长"
    return tone, "非常优秀" if tone == "good" else "现金占用高"

def assess_roiic(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    # B级：ROIIC 10%/15% 经验阈值，用于再投资效率分层。
    tone = _rate(latest, ("good", lambda x: x >= 15), ("warn", lambda x: x >= 10))
    if tone == "good":
        return tone, "优秀" if latest > 25 else "达标"
    return tone, "偏普通" if tone == "warn" else "扩张效率弱"

def assess_capex_ratio(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    if latest < 0:
        return "bad", "净利为负"
    tone = _rate(latest, ("good", lambda x: x < 25), ("warn", lambda x: x <= 40))
    return tone, {"good": "轻资本", "warn": "中性", "bad": "资本吞噬利润"}[tone]

def build_summary_metrics(rows: Sequence[Dict]) -> Tuple[List[MetricAssessment], Dict[str, Optional[float]]]:
    gm_vals = series_values(rows, "gross_margin")
    purity_with_rnd_vals = series_values(rows, "purity_with_rnd")
    purity_vals = purity_with_rnd_vals if purity_with_rnd_vals else series_values(rows, "purity")
    dso_vals = series_values(rows, "dso")
    dpo_vals = series_values(rows, "dpo")
    ccc_vals = series_values(rows, "ccc")
    capex_ratio_vals = series_values(rows, "capex_net_income")

    gross_margin_latest = gm_vals[-1] if gm_vals else None
    gross_margin_std = statistics.pstdev(gm_vals) if len(gm_vals) >= 2 else None
    purity_latest = purity_vals[-1] if purity_vals else None
    dso_latest = dso_vals[-1] if dso_vals else None
    dpo_latest = dpo_vals[-1] if dpo_vals else None
    ccc_latest = ccc_vals[-1] if ccc_vals else None
    capex_ratio_latest = capex_ratio_vals[-1] if capex_ratio_vals else None

    def _roiic_for_window(window_years: int) -> Optional[float]:
        if len(rows) < window_years + 1:
            return None
        latest = rows[-1]
        base = rows[-(window_years + 1)]
        capex_vals = [r.get("capex") for r in rows[-window_years:]]
        capex_sum = sum(capex_vals) if all(v is not None for v in capex_vals) else None
        if latest.get("operating_profit") is not None and base.get("operating_profit") is not None and capex_sum is not None and capex_sum > 0:
            return (latest["operating_profit"] - base["operating_profit"]) / capex_sum * 100
        return None

    roiic_3y = _roiic_for_window(3)
    roiic_5y = _roiic_for_window(5)
    roiic = roiic_5y if roiic_5y is not None else roiic_3y

    gm_tone, gm_status = assess_gross_margin(gross_margin_latest)
    gm_std_tone, gm_std_status = assess_gm_std(gross_margin_std)
    purity_tone, purity_status = assess_purity(purity_latest)
    dso_tone, dso_status = assess_dso(dso_latest)
    dpo_tone, dpo_status = assess_dpo(dpo_latest)
    ccc_tone, ccc_status = assess_ccc(ccc_latest)
    roiic_tone, roiic_status = assess_roiic(roiic)
    capex_tone, capex_status = assess_capex_ratio(capex_ratio_latest)

    metrics = [
        MetricAssessment(
            label="毛利率",
            value_display=fmt_pct(gross_margin_latest),
            rule_display="优秀: 长期 >= 40%",
            status_text=gm_status,
            tone=gm_tone,
            meaning="衡量产品定价后还能留下多少毛利。",
            implication="毛利率高且能稳住，通常意味着品牌、渠道或产品力足以支撑涨价。",
            trend=_trend_arrow(gm_vals),
        ),
        MetricAssessment(
            label="毛利率标准差",
            value_display=fmt_num(gross_margin_std),
            rule_display="顶级: < 2；优秀: 2~5；危险: > 8",
            status_text=gm_std_status,
            tone=gm_std_tone,
            meaning="衡量过去多年毛利率波动有多大。",
            implication="波动越小，越说明公司不是被动接受价格，而是能主动维持利润结构。",
        ),
        MetricAssessment(
            label="业务纯度",
            value_display=fmt_pct(purity_latest),
            rule_display="优秀: > 20%（优先使用含研发口径）",
            status_text=purity_status,
            tone=purity_tone,
            meaning="毛利率减去销售、管理（优先再减研发）费用率，衡量溢价是否真实留在经营里。",
            implication="如果高毛利必须靠重销售投入维持，那不是真正扎实的提价权。",
            trend=_trend_arrow(purity_vals),
        ),
        MetricAssessment(
            label="DSO",
            value_display=fmt_days(dso_latest),
            rule_display="优秀: < 45 天",
            status_text=dso_status,
            tone=dso_tone,
            meaning="应收账款周转天数，表示卖出后多久能把钱收回来。",
            implication="DSO 越短，说明客户拖款空间越小，公司对下游越强势。",
            trend=_trend_arrow(dso_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="DPO",
            value_display=fmt_days(dpo_latest),
            rule_display="优秀: > 60 天",
            status_text=dpo_status,
            tone=dpo_tone,
            meaning="应付账款周转天数，表示公司平均多久向供应商付款。",
            implication="DPO 越长，说明公司越能占用供应商资金，产业链议价能力越强。",
            trend=_trend_arrow(dpo_vals),
        ),
        MetricAssessment(
            label="CCC",
            value_display=fmt_days(ccc_latest),
            rule_display="优秀: <= 0 天",
            status_text=ccc_status,
            tone=ccc_tone,
            meaning="现金循环周期 = DIO + DSO - DPO，衡量资金从投入到回笼需要多久。",
            implication="CCC 越短越好，若能为负，说明公司在用客户和供应商的钱做生意。",
            trend=_trend_arrow(ccc_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="ROIIC",
            value_display=(f"{fmt_ratio(roiic_3y)} / {fmt_ratio(roiic_5y)}" if roiic_3y is not None and roiic_5y is not None else fmt_ratio(roiic)),
            rule_display="达标: >=10%；优秀: >=15%（并行看3Y/5Y）",
            status_text=roiic_status,
            tone=roiic_tone,
            meaning="增量资本回报率，衡量过去新增投入换回了多少营业利润（3Y灵敏，5Y稳健）。",
            implication="ROIIC 高，说明公司增长不依赖重资产堆砌，提价和模式扩张更有效。",
        ),
        MetricAssessment(
            label="Capex / Net Income",
            value_display=fmt_ratio(capex_ratio_latest),
            rule_display="优秀: < 25%",
            status_text=capex_status,
            tone=capex_tone,
            meaning="资本开支占净利润比重，衡量利润有多少要被再投入吞掉。",
            implication="占比越低，说明企业越靠无形资产赚钱，提价权越不容易被折旧侵蚀。",
            trend=_trend_arrow(capex_ratio_vals, higher_is_better=False),
        ),
    ]

    stats = {
        "gross_margin_std": gross_margin_std,
        "roiic": roiic,
        "roiic_3y": roiic_3y,
        "roiic_5y": roiic_5y,
        "gross_margin_latest": gross_margin_latest,
        "purity_latest": purity_latest,
        "purity_with_rnd_latest": (purity_with_rnd_vals[-1] if purity_with_rnd_vals else None),
        "dso_latest": dso_latest,
        "dpo_latest": dpo_latest,
        "ccc_latest": ccc_latest,
        "capex_ratio_latest": capex_ratio_latest,
    }
    return metrics, stats

def build_conclusion(rows: Sequence[Dict], stats: Dict[str, Optional[float]]) -> List[str]:
    notes: List[str] = []
    gm = stats.get("gross_margin_latest")
    gm_std = stats.get("gross_margin_std")
    purity = stats.get("purity_latest")
    ccc = stats.get("ccc_latest")
    roiic = stats.get("roiic")
    capex_ratio = stats.get("capex_ratio_latest")
    dso = stats.get("dso_latest")
    dpo = stats.get("dpo_latest")

    if gm is not None and gm >= 40 and gm_std is not None and gm_std <= 5:
        notes.append("毛利率水平高且波动可控，产品溢价能力具备较强基础。")
    elif gm is not None and gm < 30:
        notes.append("毛利率不高，单看财务并不能证明公司拥有强提价权。")

    if purity is not None and purity > 20:
        notes.append("业务纯度较高，说明高毛利没有被销售和管理费用大幅吃掉。")
    elif purity is not None and purity < 10:
        notes.append("费用侵蚀较明显，即使有毛利，也未必能沉淀为真正的经营优势。")

    if ccc is not None and ccc <= 0:
        notes.append("现金循环周期为负，具备很强的产业链占款能力。")
    elif ccc is not None and ccc > 60:
        notes.append("现金循环周期较长，资金占用偏重，议价地位需要谨慎看待。")

    if dso is not None and dpo is not None and dpo > dso:
        notes.append("DPO 高于 DSO，说明对供应商的议价能力强于客户对公司的拖款能力。")

    if roiic is not None and roiic >= 15:
        notes.append("增量资本回报率达标，扩张质量较好。")
    elif roiic is not None and roiic < 10:
        notes.append("增量资本回报率偏低，存在为了增长而增长的风险。")

    if capex_ratio is not None and capex_ratio < 25:
        notes.append("资本开支占净利润比重较低，轻资产特征对提价权更友好。")
    elif capex_ratio is not None and capex_ratio > 40:
        notes.append("资本开支吞噬利润较多，提价权可能被重资产维护成本抵消。")

    if not notes:
        notes.append("当前样本没有形成特别鲜明的提价权画像，需要结合行业结构和产品位置继续判断。")
    return notes

# ---- Bank-specific metric assessment helpers ----

def _assess_nim(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val >= 2.0:
        return "good", "优秀"
    if val >= 1.5:
        return "warn", "尚可"
    return "bad", "偏弱"

def _assess_cost_income(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val < 35:
        return "good", "极优"
    if val < 45:
        return "good", "优秀"
    if val < 55:
        return "warn", "一般"
    return "bad", "偏高"

def _assess_provision_loan(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val >= 3.0:
        return "good", "充足"
    if val >= 2.0:
        return "warn", "尚可"
    return "bad", "偏薄"

def _assess_loan_deposit(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val < 75:
        return "good", "保守安全"
    if val < 85:
        return "warn", "适中"
    return "bad", "偏激进"

def _assess_roa(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val >= 1.0:
        return "good", "优秀"
    if val >= 0.7:
        return "warn", "尚可"
    return "bad", "偏弱"

def _assess_leverage(val: Optional[float]) -> Tuple[str, str]:
    if val is None:
        return "muted", "缺数据"
    if val < 12:
        return "good", "相对稳健"
    if val < 16:
        return "warn", "行业正常"
    return "bad", "杠杆偏高"

def _assess_nco_ratio(val: Optional[float]) -> Tuple[str, str]:
    """Assess NCO / Average Loans ratio (%)."""
    if val is None:
        return "muted", "缺数据"
    if val < 0.3:
        return "good", "优秀"
    if val <= 0.6:
        return "warn", "正常"
    return "bad", "偏高"

def _assess_ppop_avg_assets(val: Optional[float]) -> Tuple[str, str]:
    """Assess PPOP / Average Assets ratio (%)."""
    if val is None:
        return "muted", "缺数据"
    if val >= 1.5:
        return "good", "优秀"
    if val >= 1.0:
        return "warn", "尚可"
    return "bad", "偏弱"

def _assess_provision_nco_cover(val: Optional[float]) -> Tuple[str, str]:
    """Assess Provision Expense / NCO cover ratio (x)."""
    if val is None:
        return "muted", "缺数据"
    if val >= 1.2:
        return "good", "增厚储备"
    if val >= 1.0:
        return "warn", "基本覆盖"
    return "bad", "消耗储备"

def _assess_ppnr_avg_assets(val: Optional[float]) -> Tuple[str, str]:
    """Assess PPNR / Average Assets ratio (%)."""
    if val is None:
        return "muted", "缺数据"
    if val >= 2.0:
        return "good", "优秀"
    if val >= 1.5:
        return "warn", "尚可"
    return "bad", "偏弱"

def _assess_rotce(val: Optional[float]) -> Tuple[str, str]:
    """Assess Return on Tangible Common Equity (%)."""
    if val is None:
        return "muted", "缺数据"
    if val >= 15:
        return "good", "优秀"
    if val >= 10:
        return "warn", "尚可"
    return "bad", "偏低"

def _assess_deposit_cost(val: Optional[float]) -> Tuple[str, str]:
    """Assess deposit cost rate (%)."""
    if val is None:
        return "muted", "缺数据"
    if val <= 1.5:
        return "good", "优秀"
    if val <= 2.2:
        return "warn", "一般"
    return "bad", "偏高"

def build_bank_summary_metrics(rows: Sequence[Dict], data: Dict[str, pd.DataFrame]) -> Tuple[List[MetricAssessment], Dict]:
    """Build summary metric cards tailored for banks."""
    nim_vals = series_values(rows, "nim")
    cir_vals = series_values(rows, "cost_income_ratio")
    plr_vals = series_values(rows, "provision_loan_ratio")
    ldr_vals = series_values(rows, "loan_deposit_ratio")
    roe_vals = series_values(rows, "roe")
    roa_vals = series_values(rows, "roa")
    lev_vals = series_values(rows, "leverage_ratio")
    rev_growth_vals = series_values(rows, "revenue_growth")
    nco_ratio_vals = series_values(rows, "nco_avg_loans")
    ppop_ratio_vals = series_values(rows, "ppop_avg_assets")
    pnco_vals = series_values(rows, "provision_nco_cover")
    ppnr_ratio_vals = series_values(rows, "ppnr_avg_assets")
    rotce_vals = series_values(rows, "rotce")
    dep_cost_vals = series_values(rows, "deposit_cost_rate")

    nim_latest = nim_vals[-1] if nim_vals else None
    cir_latest = cir_vals[-1] if cir_vals else None
    plr_latest = plr_vals[-1] if plr_vals else None
    ldr_latest = ldr_vals[-1] if ldr_vals else None
    roe_latest = roe_vals[-1] if roe_vals else None
    roa_latest = roa_vals[-1] if roa_vals else None
    lev_latest = lev_vals[-1] if lev_vals else None
    nim_std = statistics.pstdev(nim_vals) if len(nim_vals) >= 2 else None
    nco_ratio_latest = nco_ratio_vals[-1] if nco_ratio_vals else None
    ppop_ratio_latest = ppop_ratio_vals[-1] if ppop_ratio_vals else None
    pnco_latest = pnco_vals[-1] if pnco_vals else None
    ppnr_ratio_latest = ppnr_ratio_vals[-1] if ppnr_ratio_vals else None
    rotce_latest = rotce_vals[-1] if rotce_vals else None
    dep_cost_latest = dep_cost_vals[-1] if dep_cost_vals else None

    nim_tone, nim_status = _assess_nim(nim_latest)
    cir_tone, cir_status = _assess_cost_income(cir_latest)
    plr_tone, plr_status = _assess_provision_loan(plr_latest)
    ldr_tone, ldr_status = _assess_loan_deposit(ldr_latest)
    roe_tone, roe_status = assess_roe_ses(roe_latest, None)
    roa_tone, roa_status = _assess_roa(roa_latest)
    lev_tone, lev_status = _assess_leverage(lev_latest)
    nco_tone, nco_status = _assess_nco_ratio(nco_ratio_latest)
    ppop_tone, ppop_status = _assess_ppop_avg_assets(ppop_ratio_latest)
    pnco_tone, pnco_status = _assess_provision_nco_cover(pnco_latest)
    ppnr_tone, ppnr_status = _assess_ppnr_avg_assets(ppnr_ratio_latest)
    rotce_tone, rotce_status = _assess_rotce(rotce_latest)
    dep_cost_tone, dep_cost_status = _assess_deposit_cost(dep_cost_latest)

    metrics = [
        MetricAssessment(
            label="NIM(净息差)",
            value_display=fmt_pct(nim_latest),
            rule_display="优秀: >= 2.0%；尚可: >= 1.5%",
            status_text=nim_status,
            tone=nim_tone,
            meaning="衡量银行核心利差赚钱能力。数据来源：东方财富官方披露值。",
            implication="NIM越高说明银行在存贷利差上有更强的定价权，但也需关注风险定价是否合理。",
            formula="净利息收入 / 平均生息资产 × 100%",
            trend=_trend_arrow(nim_vals),
        ),
        MetricAssessment(
            label="NIM标准差",
            value_display=fmt_num(nim_std),
            rule_display="< 0.2 稳定；> 0.3 波动大",
            status_text="稳定" if nim_std is not None and nim_std < 0.2 else ("波动" if nim_std is not None else "缺数据"),
            tone="good" if nim_std is not None and nim_std < 0.2 else ("warn" if nim_std is not None and nim_std < 0.3 else ("bad" if nim_std is not None else "muted")),
            meaning="衡量过去多年净息差波动有多大。",
            implication="波动越小，越说明银行利差定价能力稳定，不容易被利率周期冲击。",
        ),
        MetricAssessment(
            label="成本收入比",
            value_display=fmt_pct(cir_latest),
            rule_display="优秀: < 35%；一般: < 55%",
            status_text=cir_status,
            tone=cir_tone,
            meaning="业务及管理费用 / 营业收入，衡量银行运营效率。",
            implication="成本收入比越低，说明银行每赚一元收入需要花费的运营成本越少，效率越高。",
            formula="业务及管理费用 / 营业收入 × 100%",
            trend=_trend_arrow(cir_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="拨贷比",
            value_display=fmt_pct(plr_latest),
            rule_display="充足: >= 3.0%；一般: >= 2.0%",
            status_text=plr_status,
            tone=plr_tone,
            meaning="贷款损失准备 / 发放贷款总额，衡量银行风险缓冲垫厚度。",
            implication="拨贷比越高，银行吸收潜在坏账的能力越强，但过高也可能是隐藏利润。",
            formula="贷款损失准备 / 发放贷款及垫款 × 100%",
            trend=_trend_arrow(plr_vals),
        ),
        MetricAssessment(
            label="存贷比",
            value_display=fmt_pct(ldr_latest),
            rule_display="保守: < 75%；激进: > 85%",
            status_text=ldr_status,
            tone=ldr_tone,
            meaning="发放贷款 / 客户存款，衡量银行资金运用激进程度。",
            implication="存贷比过高说明银行将更多存款放贷出去，流动性风险加大。",
            formula="发放贷款及垫款 / 客户存款 × 100%",
            trend=_trend_arrow(ldr_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="ROA",
            value_display=fmt_pct(roa_latest),
            rule_display="优秀: >= 1.0%；尚可: >= 0.7%",
            status_text=roa_status,
            tone=roa_tone,
            meaning="资产回报率，衡量银行每一元总资产产生多少利润。",
            implication="ROA是银行经营质量的核心指标，反映了在给定杠杆水平下的真实盈利能力。",
            trend=_trend_arrow(roa_vals),
        ),
        MetricAssessment(
            label="ROE",
            value_display=fmt_pct(roe_latest),
            rule_display="优秀: > 15%；尚可: > 10%",
            status_text=roe_status,
            tone=roe_tone,
            meaning="净资产回报率，衡量股东资本回报。",
            implication="银行ROE = ROA × 杠杆，高ROE需要区分是靠效率还是靠冒险。",
            trend=_trend_arrow(roe_vals),
        ),
        MetricAssessment(
            label="杠杆倍数",
            value_display=fmt_num(lev_latest, digits=1) + "x" if lev_latest is not None else "N/A",
            rule_display="稳健: < 12x；正常: < 16x",
            status_text=lev_status,
            tone=lev_tone,
            meaning="总资产 / 净资产，衡量银行经营的杠杆水平。",
            implication="杠杆越高，ROE中由杠杆贡献的比例越大，潜在风险也越高。",
            formula="总资产 / 归属母公司权益",
            trend=_trend_arrow(lev_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="NCO/平均贷款",
            value_display=fmt_pct(nco_ratio_latest),
            rule_display="优秀: < 0.3%；正常: ≤ 0.6%；偏高: > 0.6%",
            status_text=nco_status,
            tone=nco_tone,
            meaning="净核销额 / 平均贷款余额，衡量银行实际信用损失率。巴菲特核心银行指标。",
            implication="NCO率越低，说明银行贷款质量越好，实际坏账损失越小。趋势比绝对值更重要。",
            formula="NCO / ((期初贷款 + 期末贷款) / 2) × 100%",
            trend=_trend_arrow(nco_ratio_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="拨备/NCO覆盖",
            value_display=fmt_num(pnco_latest, digits=2) + "x" if pnco_latest is not None else "N/A",
            rule_display="增厚储备: ≥ 1.2x；基本覆盖: ≥ 1.0x",
            status_text=pnco_status,
            tone=pnco_tone,
            meaning="信用减值损失 / 净核销额，衡量银行拨备的保守程度。",
            implication="> 1.0 说明银行在持续增厚坏账储备；< 1.0 说明银行在消耗储备，需警惕。",
            formula="信用减值损失 / 净核销额",
            trend=_trend_arrow(pnco_vals),
        ),
        MetricAssessment(
            label="PPOP/平均资产",
            value_display=fmt_pct(ppop_ratio_latest),
            rule_display="优秀: ≥ 1.5%；尚可: ≥ 1.0%",
            status_text=ppop_status,
            tone=ppop_tone,
            meaning="拨备前营业利润 / 平均总资产，衡量银行剔除信用成本后的真实盈利能力。",
            implication="PPOP/资产反映银行的核心赚钱能力，不受拨备政策影响，是评估银行内在价值的关键。",
            formula="(营业收入 − 业务及管理费用) / 平均总资产 × 100%",
            trend=_trend_arrow(ppop_ratio_vals),
        ),
        MetricAssessment(
            label="PPNR/平均资产",
            value_display=fmt_pct(ppnr_ratio_latest),
            rule_display="优秀: ≥ 2.0%；尚可: ≥ 1.5%",
            status_text=ppnr_status,
            tone=ppnr_tone,
            meaning="拨备前净收入 / 平均总资产，衡量银行在极端信贷损失下的最大吸收能力。巴菲特1990年分析富国银行的核心指标。",
            implication="PPNR代表银行一年内可承受的最大信用损失而不侵蚀资本金。PPNR越高，银行在经济衰退中的生存能力越强。",
            formula="(税前利润 + 信用减值损失) / 平均总资产 × 100%",
            trend=_trend_arrow(ppnr_ratio_vals),
        ),
        MetricAssessment(
            label="ROTCE",
            value_display=fmt_pct(rotce_latest),
            rule_display="优秀: ≥ 15%；尚可: ≥ 10%",
            status_text=rotce_status,
            tone=rotce_tone,
            meaning="有形普通股权益回报率，剔除商誉和无形资产后的真实股东回报。巴菲特评估银行特许经营权的核心指标。",
            implication="ROTCE > ROE说明银行有大量商誉/无形资产（可能来自溢价收购）。两者接近说明资产负债表很干净。",
            formula="归母净利润 / (归母净资产 − 商誉 − 无形资产) × 100%",
            trend=_trend_arrow(rotce_vals),
        ),
        MetricAssessment(
            label="存款付息率",
            value_display=fmt_pct(dep_cost_latest),
            rule_display="优秀: ≤ 1.5%；一般: ≤ 2.2%",
            status_text=dep_cost_status,
            tone=dep_cost_tone,
            meaning="利息支出 / 平均客户存款，近似衡量银行的资金成本。",
            implication="存款付息率越低，说明银行低成本存款占比越高（活期/储蓄占比高），拥有更强的存款特许经营权。",
            formula="利息支出 / 平均客户存款 × 100% (近似值)",
            trend=_trend_arrow(dep_cost_vals, higher_is_better=False),
        ),
    ]

    stats = {
        "nim_latest": nim_latest,
        "nim_std": nim_std,
        "cir_latest": cir_latest,
        "plr_latest": plr_latest,
        "ldr_latest": ldr_latest,
        "roe_latest": roe_latest,
        "roa_latest": roa_latest,
        "leverage_latest": lev_latest,
        "nco_ratio_latest": nco_ratio_latest,
        "ppop_ratio_latest": ppop_ratio_latest,
        "provision_nco_latest": pnco_latest,
        "ppnr_ratio_latest": ppnr_ratio_latest,
        "rotce_latest": rotce_latest,
        "deposit_cost_latest": dep_cost_latest,
    }
    return metrics, stats

def build_bank_conclusion(rows: Sequence[Dict], stats: Dict) -> List[str]:
    """Generate conclusion text for bank analysis."""
    notes: List[str] = []
    nim = stats.get("nim_latest")
    nim_std = stats.get("nim_std")
    cir = stats.get("cir_latest")
    plr = stats.get("plr_latest")
    ldr = stats.get("ldr_latest")
    roe = stats.get("roe_latest")
    roa = stats.get("roa_latest")
    lev = stats.get("leverage_latest")

    if nim is not None and nim >= 2.0 and nim_std is not None and nim_std < 0.2:
        notes.append("净息差水平优秀且波动可控，利差定价能力具备较强基础。")
    elif nim is not None and nim < 1.5:
        notes.append("净息差偏低，利差定价空间有限，需关注利率环境变化影响。")

    if cir is not None and cir < 35:
        notes.append("成本收入比极低，运营效率处于行业顶尖水平。")
    elif cir is not None and cir >= 55:
        notes.append("成本收入比偏高，运营效率有较大改善空间。")

    if plr is not None and plr >= 3.0:
        notes.append("拨贷比充足，风险缓冲垫较厚，抗周期能力强。")
    elif plr is not None and plr < 2.0:
        notes.append("拨贷比偏薄，一旦资产质量恶化，利润缓冲不足。")

    if ldr is not None and ldr > 85:
        notes.append("存贷比偏高，资产运用较为激进，流动性风险需关注。")

    if roa is not None and roa >= 1.0:
        notes.append("ROA达到优秀水平，资产回报效率高。")
    elif roa is not None and roa < 0.7:
        notes.append("ROA偏弱，资产回报效率不高。")

    if roe is not None and lev is not None:
        if roe >= 15 and lev < 14:
            notes.append("ROE达标且杠杆适中，盈利质量较好。")
        elif roe >= 15 and lev >= 16:
            notes.append("ROE达标但杠杆偏高，高回报部分由冒险驱动。")

    nco_ratio = stats.get("nco_ratio_latest")
    ppop_ratio = stats.get("ppop_ratio_latest")
    prov_nco = stats.get("provision_nco_latest")

    if nco_ratio is not None:
        if nco_ratio < 0.3:
            notes.append("信用损失率（NCO/平均贷款）极低，资产质量优异。")
        elif nco_ratio > 0.6:
            notes.append("信用损失率（NCO/平均贷款）偏高，需关注信贷资产质量恶化风险。")

    if prov_nco is not None:
        if prov_nco < 1.0:
            notes.append("拨备/NCO低于1倍，银行正在消耗减值储备，若持续将削弱风险缓冲垫。")
        elif prov_nco >= 1.5:
            notes.append("拨备/NCO充裕，银行持续建立减值储备，抗风险能力增强。")

    if ppop_ratio is not None:
        if ppop_ratio >= 2.0:
            notes.append("PPOP/平均资产处于优秀水平，核心盈利能力充足，能有效吸收信用损失。")
        elif ppop_ratio < 1.0:
            notes.append("PPOP/平均资产偏弱，核心盈利对信用损失的吸收能力不足。")

    ppnr_ratio = stats.get("ppnr_ratio_latest")
    rotce = stats.get("rotce_latest")
    dep_cost = stats.get("deposit_cost_latest")

    if ppnr_ratio is not None:
        if ppnr_ratio >= 2.0:
            notes.append("PPNR/平均资产优秀，银行在极端信贷损失场景下仍有充足的盈利缓冲。（巴菲特1990年分析富国银行的核心防线指标）")
        elif ppnr_ratio < 1.5:
            notes.append("PPNR/平均资产偏低，银行在极端经济衰退中的损失吸收能力有限。")

    if rotce is not None:
        if rotce >= 15:
            notes.append("ROTCE优秀，银行拥有真实的高回报特许经营权。")
        elif rotce < 10:
            notes.append("ROTCE偏低，银行有形权益回报不足，特许经营权价值有待提升。")
        if roe is not None and rotce > roe * 1.15:
            notes.append(f"ROTCE({rotce:.1f}%)显著高于ROE({roe:.1f}%)，商誉和无形资产占比较大，需关注收购溢价合理性。")

    if dep_cost is not None:
        if dep_cost <= 1.5:
            notes.append("存款付息率极低，显示银行拥有低成本存款优势（活期/储蓄存款占比可能较高）。")
        elif dep_cost > 2.2:
            notes.append("存款付息率偏高，银行可能过于依赖高成本定期存款或同业负债。")

    # ── Stress test conclusion ──
    stress = build_bank_stress_test(rows)
    if stress:
        severe = stress["scenarios"][1]  # 严重衰退 (Buffett WFC scenario)
        if severe["verdict_tone"] == "good":
            notes.append(f"压力测试：即便在巴菲特级别的严重衰退假设（违约率10%×LGD30%）下，PPNR仍可完全覆盖潜在损失（盈余{severe['ppnr_surplus']/1e8:+,.0f}亿），属于堡垒型银行。")
        elif severe["verdict_tone"] == "warn":
            notes.append(f"压力测试：严重衰退假设下潜在损失超出PPNR（缺口{severe['ppnr_surplus']/1e8:+,.0f}亿），净资产侵蚀{severe['equity_erosion']:.1f}%，判定为「{severe['verdict']}」。")
        else:
            notes.append(f"压力测试：严重衰退假设下净资产侵蚀达{severe['equity_erosion']:.1f}%，判定为「{severe['verdict']}」，银行抗极端风险能力不足。")

    if not notes:
        notes.append("当前样本没有形成特别鲜明的银行经营画像，需结合宏观利率环境和资产质量继续判断。")
    return notes

def assess_revenue_growth(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x > 20), ("warn", lambda x: x >= 10))
    return tone, {"good": "高速扩张", "warn": "有增长", "bad": "扩张偏慢"}[tone]

def assess_gm_delta(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: -1 <= x <= 1), ("warn", lambda x: -3 <= x <= 3))
    return tone, {"good": "稳定分享", "warn": "小幅波动", "bad": "偏离SES画像"}[tone]

def assess_opex_trend(rows: Sequence[Dict]) -> Tuple[str, str, Optional[float]]:
    vals = series_values(rows, "opex_ratio")
    if len(vals) < 3:
        return "muted", "缺数据", None
    slope = vals[-1] - vals[0]
    if slope <= -2:
        return "good", "持续下降", slope
    if slope < 0:
        return "warn", "略有下降", slope
    return "bad", "未见摊薄", slope

def assess_asset_turnover(latest: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    tone = _rate(latest, ("good", lambda x: x > 1.5), ("warn", lambda x: x >= 1.0))
    return tone, {"good": "高周转", "warn": "一般", "bad": "周转偏慢"}[tone]

def assess_roe_ses(latest: Optional[float], asset_turnover: Optional[float]) -> Tuple[str, str]:
    if latest is None:
        return "muted", "缺数据"
    if latest > 15 and asset_turnover is not None and asset_turnover > 1.5:
        return "good", "高回报且由周转支撑"
    if latest >= 12:
        return "warn", "尚可"
    return "bad", "自我造血弱"

def build_ses_metrics(rows: Sequence[Dict]) -> Tuple[List[MetricAssessment], Dict[str, object]]:
    rev_growth_vals = series_values(rows, "revenue_growth")
    gm_delta_vals = series_values(rows, "gm_delta")
    asset_turnover_vals = series_values(rows, "asset_turnover")
    roe_vals = series_values(rows, "roe")
    opex_ratio_vals = series_values(rows, "opex_ratio")

    latest_rev_growth = rev_growth_vals[-1] if rev_growth_vals else None
    latest_gm_delta = gm_delta_vals[-1] if gm_delta_vals else None
    latest_asset_turnover = asset_turnover_vals[-1] if asset_turnover_vals else None
    latest_roe = roe_vals[-1] if roe_vals else None
    latest_opex_ratio = rows[-1].get("opex_ratio") if rows else None

    rev_tone, rev_status = assess_revenue_growth(latest_rev_growth)
    gm_tone, gm_status = assess_gm_delta(latest_gm_delta)
    opex_tone, opex_status, opex_slope = assess_opex_trend(rows)
    at_tone, at_status = assess_asset_turnover(latest_asset_turnover)
    roe_tone, roe_status = assess_roe_ses(latest_roe, latest_asset_turnover)

    metrics = [
        MetricAssessment(
            label="营收增速",
            value_display=fmt_pct(latest_rev_growth),
            rule_display="SES标准: > 20%，且最好持续 3-5 年",
            status_text=rev_status,
            tone=rev_tone,
            meaning="衡量系统吞吐量是否在快速放大。",
            implication="没有外部扩张，就没有规模红利，也谈不上把规模红利分享给客户。",
            formula="(本期营收 - 上期营收) / 上期营收 × 100%",
            trend=_trend_arrow(rev_growth_vals),
        ),
        MetricAssessment(
            label="毛利率变动",
            value_display=fmt_pct(latest_gm_delta),
            rule_display="SES标准: 长期落在 [-1%, +1%]",
            status_text=gm_status,
            tone=gm_tone,
            meaning="衡量公司在规模扩大后是否把成本优势回馈给用户。",
            implication="毛利率稳定甚至微降，说明公司没有把规模红利全拿去抬利润，而是在主动分享。",
            formula="本期毛利率 - 上期毛利率",
            trend=_trend_arrow(gm_delta_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="运营费用率",
            value_display=fmt_pct(safe_float(latest_opex_ratio)),
            rule_display="SES标准: 随营收增长持续下降",
            status_text=opex_status,
            tone=opex_tone,
            meaning="衡量销售和管理开销是否被规模有效摊薄。",
            implication="只有运营杠杆释放出来，企业才能在降价的同时不把利润打穿。",
            formula="(销售费用 + 管理费用) / 营业收入 × 100%",
            trend=_trend_arrow(opex_ratio_vals, higher_is_better=False),
        ),
        MetricAssessment(
            label="总资产周转率",
            value_display=fmt_num(latest_asset_turnover),
            rule_display="SES标准: > 1.5，越高越好",
            status_text=at_status,
            tone=at_tone,
            meaning="衡量每一块钱资产一年能跑出多少收入。",
            implication="SES 企业往往靠速度和复用率而不是厚利润生存，高周转是模式成立的硬条件。",
            formula="营业收入 / 平均总资产",
            trend=_trend_arrow(asset_turnover_vals),
        ),
        MetricAssessment(
            label="ROE",
            value_display=fmt_pct(latest_roe),
            rule_display="SES标准: > 15%，且主要由周转驱动",
            status_text=roe_status,
            tone=roe_tone,
            meaning="衡量这种低毛利高周转模式最终能不能形成足够资本回报。",
            implication="如果 ROE 不够高，说明系统虽然忙，但没有把忙碌转化成优秀回报。",
            formula="归母净利润 / 平均净资产 × 100%",
            trend=_trend_arrow(roe_vals),
        ),
    ]

    details = {
        "latest_rev_growth": latest_rev_growth,
        "latest_gm_delta": latest_gm_delta,
        "latest_opex_ratio": latest_opex_ratio,
        "opex_slope": opex_slope,
        "latest_asset_turnover": latest_asset_turnover,
        "latest_roe": latest_roe,
    }
    return metrics, details

def build_ses_conclusion(rows: Sequence[Dict], details: Dict[str, object]) -> List[str]:
    notes: List[str] = []
    rev = safe_float(details.get("latest_rev_growth"))
    gm_delta = safe_float(details.get("latest_gm_delta"))
    opex_slope = safe_float(details.get("opex_slope"))
    at = safe_float(details.get("latest_asset_turnover"))
    roe = safe_float(details.get("latest_roe"))

    if rev is not None and rev > 20:
        notes.append("外部扩张速度达标，系统吞吐量正在快速放大。")
    elif rev is not None:
        notes.append("外部扩张不够快，SES 飞轮的第一推动力还不够强。")

    if gm_delta is not None and -1 <= gm_delta <= 1:
        notes.append("毛利率变动很克制，符合把规模红利分享给客户的 SES 特征。")
    elif gm_delta is not None:
        notes.append("毛利率变动偏大，说明规模红利未必在稳定回馈给用户。")

    if opex_slope is not None and opex_slope < 0:
        notes.append("运营费用率在下降，运营杠杆正在释放。")
    elif opex_slope is not None:
        notes.append("运营费用率没有下降，规模扩张对费用摊薄还不明显。")

    if at is not None and at > 1.5:
        notes.append("总资产周转率较高，说明系统靠速度和复用率在运转。")
    elif at is not None:
        notes.append("资产周转率一般，SES 模式的“快”还不够突出。")

    if roe is not None and roe > 15 and at is not None and at > 1.5:
        notes.append("ROE 达标且有高周转支撑，SES 模式具备较好的可持续性。")
    elif roe is not None:
        notes.append("ROE 没有明显达到 SES 理想标准，模式最终回报还需要继续验证。")

    return notes

def build_quality_cards(
    abs_df: pd.DataFrame,
    annual_cols: Sequence[str],
    year_data: Dict[str, Dict],
    diagnostics: Dict[str, object],
    is_bank: bool = False,
) -> Dict[str, List[MetricAssessment]]:
    latest_col = annual_cols[-1] if annual_cols else None
    latest = year_data.get(latest_col, {}) if latest_col else {}
    price = safe_float(diagnostics.get("price"))
    mcap = safe_float(diagnostics.get("market_cap"))
    pledge = diagnostics.get("pledge")

    latest_roa = safe_float(latest.get("roa"))
    latest_roe = safe_float(latest.get("roe"))
    latest_roic = roic_percent_from_year_data(latest) if latest else None
    roe_roic_gap = (latest_roe - latest_roic) if latest_roe is not None and latest_roic is not None else None
    icr_tag, latest_icr = interest_coverage_ratio_tag_value(latest) if latest else ("na", None)
    latest_real_eps, _ = get_real_eps(abs_df, latest_col) if latest_col and abs_df is not None else (None, "")
    latest_basic_eps = safe_float(get_metric(abs_df, "基本每股收益", latest_col)) if latest_col else None
    latest_diluted_eps = safe_float(get_metric(abs_df, "稀释每股收益", latest_col)) if latest_col else None
    latest_profit = safe_float(latest.get("profit"))
    latest_ocf = safe_float(latest.get("ocf"))
    latest_shares = safe_float(latest.get("shares"))
    latest_ocf_ps = (latest_ocf / latest_shares) if latest_ocf is not None and latest_shares not in (None, 0) else None
    latest_eps_quality = (latest_ocf_ps / latest_real_eps) if latest_ocf_ps is not None and latest_real_eps not in (None, 0) else None
    latest_net_cash = safe_float(latest.get("net_cash"))
    latest_int_debt = safe_float(latest.get("int_debt"))
    latest_due_debt = safe_float(latest.get("due_debt_principal"))
    latest_ocf_ratio = (latest_ocf / latest_profit * 100) if latest_ocf is not None and latest_profit and latest_profit > 0 else None
    latest_eq = _equity_denom(latest)
    latest_goodwill = safe_float(latest.get("goodwill")) or 0.0
    latest_gw_ratio = (latest_goodwill / latest_eq * 100) if latest_eq and latest_eq > 0 else None
    latest_pretax = safe_float(latest.get("pretax"))
    latest_tax = safe_float(latest.get("tax"))
    latest_taxes_paid = safe_float(latest.get("taxes_paid_cash"))
    latest_book_rate = (latest_tax / latest_pretax * 100) if latest_pretax and latest_tax is not None and latest_pretax > 0 else None
    latest_div = safe_float(latest.get("dividends_paid"))
    latest_payout = (latest_div / latest_profit * 100) if latest_div is not None and latest_profit and latest_profit > 0 else None
    latest_net_buyback = (safe_float(latest.get("buyback_cash")) or 0.0) - (safe_float(latest.get("equity_inflow_cash")) or 0.0)
    latest_div_yield = (latest_div / mcap * 100) if mcap and latest_div is not None else None
    latest_buyback_yield = (latest_net_buyback / mcap * 100) if mcap else None
    latest_total_yield = ((latest_div or 0.0) + latest_net_buyback) / mcap * 100 if mcap and latest_div is not None else None

    # P1: 3-year average total shareholder yield for more stable assessment
    _ty_vals = []
    for _c in annual_cols[-3:]:
        _d = year_data.get(_c, {})
        _div = safe_float(_d.get("dividends_paid"))
        _nb = (safe_float(_d.get("buyback_cash")) or 0.0) - (safe_float(_d.get("equity_inflow_cash")) or 0.0)
        _ty = ((_div or 0.0) + _nb) / mcap * 100 if mcap and _div is not None else None
        if _ty is not None:
            _ty_vals.append(_ty)
    avg_total_yield_3y = sum(_ty_vals) / len(_ty_vals) if _ty_vals else None
    # Use 3-year avg for tone/status, but show latest in value_display
    yield_for_rating = avg_total_yield_3y if avg_total_yield_3y is not None else latest_total_yield
    sh_tone, sh_status = _rate_total_yield_with_context(yield_for_rating, roic=latest_roic, net_buyback=latest_net_buyback)
    pledge_ratio = safe_float(pledge.get("pledge_ratio_pct")) if pledge else None

    # ---- 银行专用质量卡片 ----
    if is_bank:
        b_nim = safe_float(latest.get("nim"))
        b_cir = safe_float(latest.get("cost_income_ratio"))
        b_plr = safe_float(latest.get("provision_loan_ratio"))
        b_ldr = safe_float(latest.get("loan_deposit_ratio"))
        b_lev = safe_float(latest.get("leverage_ratio"))
        b_total_assets = safe_float(latest.get("total_assets"))
        b_parent_equity = safe_float(latest.get("parent_equity"))
        b_roa_val = safe_float(latest.get("roa"))
        b_roe_val = safe_float(latest.get("roe"))
        b_car = None  # 资本充足率暂无来源

        # -- ROA with bank thresholds --
        def _bk_roa_tone(v):
            if v is None: return "muted"
            if v >= 1.0: return "good"
            if v >= 0.7: return "warn"
            return "bad"

        # -- leverage for bank --
        def _bk_lev_tone(v):
            if v is None: return "muted"
            if v <= 12: return "good"
            if v <= 16: return "warn"
            return "bad"

        bank_cards: Dict[str, List[MetricAssessment]] = {
            "efficiency": [
                MetricAssessment(
                    label="ROA（银行）",
                    value_display=fmt_pct(b_roa_val),
                    rule_display="优: >=1.0%；稳健: 0.7%~1.0%；偏弱: <0.7%",
                    status_text={"good": "资产盈利优秀", "warn": "资产盈利稳健", "bad": "资产盈利偏弱", "muted": "缺数据"}[_bk_roa_tone(b_roa_val)],
                    tone=_bk_roa_tone(b_roa_val),
                    meaning="银行总资产一年能产出多少利润，是衡量银行经营效率的核心指标。",
                    implication="ROA 高说明银行在资产端的定价和风控能力强，反之则可能依赖杠杆堆ROE。",
                    formula="净利润 / 平均总资产 × 100%",
                ),
                MetricAssessment(
                    label="杠杆倍数",
                    value_display=f"{b_lev:.1f}x" if b_lev is not None else "N/A",
                    rule_display="稳健: <12x；关注: 12x~16x；激进: >16x",
                    status_text={"good": "杠杆稳健", "warn": "杠杆偏高", "bad": "杠杆激进", "muted": "缺数据"}[_bk_lev_tone(b_lev)],
                    tone=_bk_lev_tone(b_lev),
                    meaning="总资产与归母权益之比，反映银行的杠杆水平。",
                    implication="银行天然高杠杆经营，但杠杆过高则抗风险缓冲更薄，需结合ROA和拨备判断安全性。",
                    formula="总资产 / 归母权益",
                ),
            ],
            "eps": [
                MetricAssessment(
                    label="Real_EPS",
                    value_display=fmt_num(latest_real_eps, 3),
                    rule_display="越高越好；重点看是否长期为正",
                    status_text="主业盈利为正" if latest_real_eps is not None and latest_real_eps > 0 else "主业盈利偏弱",
                    tone=_rate_real_eps(latest_real_eps),
                    meaning="扣非归母净利润折算到每股后的收益，更接近主业真实赚钱能力。",
                    implication="银行的非经常性损益较少，Real_EPS 与 Basic EPS 通常接近。",
                    formula="扣非归母净利润 / 加权平均股本",
                ),
            ],
            "risk": [
                MetricAssessment(
                    label="拨贷比",
                    value_display=fmt_pct(b_plr),
                    rule_display="充足: >=3.0%；达标: 2.0%~3.0%；不足: <2.0%",
                    status_text={"good": "拨备充足", "warn": "拨备达标", "bad": "拨备不足", "muted": "缺数据"}[_assess_provision_loan(b_plr)[0]],
                    tone=_assess_provision_loan(b_plr)[0],
                    meaning="贷款损失准备相对贷款总额的覆盖程度，是银行风险缓冲的核心指标。",
                    implication="拨贷比越高，对坏账的吸收能力越强；不足时一旦不良暴露，利润会被大幅吞噬。",
                    formula="贷款损失准备 / 发放贷款及垫款 × 100%",
                ),
                MetricAssessment(
                    label="存贷比",
                    value_display=fmt_pct(b_ldr),
                    rule_display="稳健: <75%；关注: 75%~85%；激进: >85%",
                    status_text={"good": "存贷稳健", "warn": "存贷偏紧", "bad": "存贷激进", "muted": "缺数据"}[_assess_loan_deposit(b_ldr)[0]],
                    tone=_assess_loan_deposit(b_ldr)[0],
                    meaning="贷款占存款的比例，反映银行资金运用的激进程度。",
                    implication="存贷比过高意味着存款转化为贷款的比例过大，流动性缓冲不足。",
                    formula="发放贷款及垫款 / 客户存款 × 100%",
                ),
            ],
            "tax": [
                MetricAssessment(
                    label="纸面有效税率",
                    value_display=fmt_pct(latest_book_rate),
                    rule_display="大体匹配 25% 档更安心",
                    status_text={"good": "税率匹配", "warn": "偏离关注", "bad": "税危", "muted": "缺数据"}[_rate_tax(latest_book_rate)],
                    tone=_rate_tax(latest_book_rate),
                    meaning="看报表上的所得税费用与利润总额是否大致匹配。",
                    implication="银行一般按25%缴税，极低税率需关注递延税或拨备调节。",
                    formula="所得税费用 / 利润总额 × 100%",
                ),
            ],
            "pledge": [
                MetricAssessment(
                    label="质押占总股本",
                    value_display=fmt_pct(pledge_ratio),
                    rule_display="安全: <20%；关注: 20%~50%；紧绷: 50%~80%；危卵: >80%",
                    status_text={"good": "安全区", "warn": "温和关注", "bad": "高杠杆风险", "muted": "缺数据"}[_rate_pledge(pledge_ratio)],
                    tone=_rate_pledge(pledge_ratio),
                    meaning="看大股东质押对总股本的占用程度。",
                    implication="银行股质押比例一般较低，若偏高需关注控股股东隐患。",
                    formula="质押股数 / 总股本 × 100%",
                ),
            ],
            "payout": [
                MetricAssessment(
                    label="股利支付率",
                    value_display=fmt_pct(latest_payout),
                    rule_display="稳健: 30%~50%；监管底线: 30%",
                    status_text={"good": "稳健分红", "warn": "高派息/低派息", "bad": "异常分红", "muted": "缺数据"}[_rate_payout(latest_payout)],
                    tone=_rate_payout(latest_payout),
                    meaning="银行分红受监管约束，需平衡股东回馈和资本充足率补充。",
                    implication="银行派息率通常30%左右，过高可能削弱核心资本，过低说明需要内生补充资本。",
                    formula="现金分红 / 归母净利润 × 100%",
                ),
            ],
            "shareholder": [
                MetricAssessment(
                    label="总股东收益率",
                    value_display=(
                        f"{fmt_pct(latest_total_yield)}（3年均值 {fmt_pct(avg_total_yield_3y)}）"
                        if avg_total_yield_3y is not None and latest_total_yield is not None
                        else fmt_pct(latest_total_yield)
                    ),
                    rule_display="银行股主要靠股息回馈；4%~6% 为佳",
                    status_text=sh_status,
                    tone=sh_tone,
                    meaning="把现金分红和净回购合在一起，看股东实际拿到多少回馈。",
                    implication="银行股回购较少，股东回馈主要靠分红。稳定的高股息率是银行股的核心吸引力之一。",
                    formula="(现金分红 + 净回购) / 当前市值 × 100%（评判基于近3年均值）",
                ),
            ],
            "capital_allocation": [
                MetricAssessment(
                    label="ROE 拆解（银行）",
                    value_display=f"ROA {fmt_pct(b_roa_val)} × 杠杆 {b_lev:.1f}x = ROE {fmt_pct(b_roe_val)}" if b_roa_val is not None and b_lev is not None else "N/A",
                    rule_display="ROA >= 1% 且杠杆 <= 13x 为优，高杠杆堆 ROE 需警惕",
                    status_text=(
                        "高质量ROE" if b_roa_val is not None and b_roa_val >= 1.0 and b_lev is not None and b_lev <= 13
                        else "杠杆驱动ROE" if b_roa_val is not None and b_roa_val < 0.7
                        else "ROE质量尚可"
                    ),
                    tone=(
                        "good" if b_roa_val is not None and b_roa_val >= 1.0 and b_lev is not None and b_lev <= 13
                        else "bad" if b_roa_val is not None and b_roa_val < 0.7
                        else "warn"
                    ) if b_roa_val is not None else "muted",
                    meaning="把 ROE 拆成 ROA × 杠杆倍数，判断银行的 ROE 来源是经营能力还是杠杆放大。",
                    implication="巴菲特看银行先看 ROA：ROA 高说明资产本身赚钱，杠杆只是合理利用；ROA 低但 ROE 高，说明全靠借钱堆业绩。",
                ),
                MetricAssessment(
                    label="资本配置画像（银行）",
                    value_display=(
                        "高效稳健型" if b_roa_val is not None and b_roa_val >= 1.0 and latest_payout is not None and latest_payout >= 30
                        else "高效低分红型" if b_roa_val is not None and b_roa_val >= 1.0
                        else "低效但愿分红" if latest_payout is not None and latest_payout >= 30
                        else "低效低分红"
                    ),
                    rule_display=f"ROA {fmt_pct(b_roa_val)}（门槛1%） | 派息率 {fmt_pct(latest_payout)}（门槛30%）",
                    status_text=(
                        f"ROA {'高' if b_roa_val is not None and b_roa_val >= 1.0 else '低'} × 分红 {'高' if latest_payout is not None and latest_payout >= 30 else '低'}"
                    ),
                    tone=(
                        "good" if b_roa_val is not None and b_roa_val >= 1.0 and latest_payout is not None and latest_payout >= 30
                        else "good" if b_roa_val is not None and b_roa_val >= 1.0
                        else "warn" if latest_payout is not None and latest_payout >= 30
                        else "bad"
                    ),
                    meaning="用 ROA 和分红率两个维度，判断银行属于哪种资本配置风格。",
                    implication="ROA高且分红稳健是巴菲特最认可的银行（如富国银行早期）；ROA低靠杠杆堆ROE的银行风险大。",
                ),
            ],
        }
        return bank_cards

    cards: Dict[str, List[MetricAssessment]] = {
        "efficiency": [
            MetricAssessment(
                label="ROA",
                value_display=fmt_pct(latest_roa),
                rule_display="优: >10%；稳健: 5%~10%；偏弱: <5%",
                status_text={"good": "高效经营", "warn": "稳健经营", "bad": "低效/重资产", "muted": "缺数据"}[_rate_roa(latest_roa)],
                tone=_rate_roa(latest_roa),
                meaning="在不看杠杆的前提下，资产本身一年能赚回多少利润。",
                implication="ROA 高，才更像真正的经营护城河；ROA 低而 ROE 高时，要警惕高杠杆放大。",
                formula="净利润 / 平均总资产 × 100%",
            ),
            MetricAssessment(
                label="ROE vs ROIC",
                value_display=fmt_num(roe_roic_gap),
                rule_display="差距越小越好；>8pp 需警惕杠杆堆 ROE",
                status_text={"good": "反杠杆协调", "warn": "反杠杆关注", "bad": "纸老虎风险", "muted": "缺数据"}[_rate_roe_roic_gap(roe_roic_gap)],
                tone=_rate_roe_roic_gap(roe_roic_gap),
                meaning="比较股东回报率和投入资本回报率，拆出杠杆对 ROE 的放大作用。",
                implication="如果 ROE 远高于 ROIC，企业看起来很赚钱，但收益可能更多来自负债，而不是经营质量。",
                formula="ROE - ROIC",
            ),
        ],
        "interest": [
            MetricAssessment(
                label="利息保障倍数",
                value_display="∞" if icr_tag == "surplus" else (f"{latest_icr:.2f}x" if latest_icr is not None else "N/A"),
                rule_display="优: >5x；警戒: <2x；拒绝: <1.5x",
                status_text={"good": "极度安全", "warn": "走钢丝", "bad": "财务高压", "muted": "缺数据"}[_rate_icr(latest_icr, icr_tag)],
                tone=_rate_icr(latest_icr, icr_tag),
                meaning="看 EBIT 够不够覆盖财务费用，判断企业是否需要‘呼吸机’续命。",
                implication="保障倍数过低时，利润只要稍有波动，就会先冲击偿债安全而不是估值弹性。",
                formula="EBIT / 财务费用",
            )
        ],
        "eps": [
            MetricAssessment(
                label="Real_EPS",
                value_display=fmt_num(latest_real_eps, 3),
                rule_display="越高越好；重点看是否长期为正",
                status_text="主业盈利为正" if latest_real_eps is not None and latest_real_eps > 0 else "主业盈利偏弱",
                tone=_rate_real_eps(latest_real_eps),
                meaning="扣非归母净利润折算到每股后的收益，更接近主业真实赚钱能力。",
                implication="它能避开一次性收益把 EPS ‘抬得很好看’的问题。",
                formula="扣非归母净利润 / 加权平均股本",
            ),
            MetricAssessment(
                label="含金量",
                value_display=fmt_num(latest_eps_quality, 2),
                rule_display="优: >=1；正常: 0.8~1；危险: <0.8",
                status_text={"good": "真钱支撑", "warn": "基本匹配", "bad": "纸面偏虚", "muted": "缺数据"}[_rate_eps_quality(latest_eps_quality)],
                tone=_rate_eps_quality(latest_eps_quality),
                meaning="每股经营现金流相对 Real_EPS 的覆盖程度。",
                implication="含金量低时，账面 EPS 不一定能顺利转化成真实现金回笼。",
                formula="每股 OCF / Real_EPS",
            ),
        ],
        "capital": [
            MetricAssessment(
                label="ROIC",
                value_display=fmt_pct(latest_roic),
                rule_display="优: >=10%；可接受: 6%~10%",
                status_text={"good": "资本优良", "warn": "一般", "bad": "资本效率弱", "muted": "缺数据"}[_rate_roic(latest_roic)],
                tone=_rate_roic(latest_roic),
                meaning="看企业投入进去的权益和有息负债，最终能不能赚回像样的回报。",
                implication="ROIC 低，说明钱是投进去了，但资本回报没有跟上。",
                formula="NOPAT / (股东权益 + 有息负债) × 100%",
            ),
            MetricAssessment(
                label="净现金",
                value_display=fmt_yi(latest_net_cash),
                rule_display="正值通常更安全",
                status_text="净现金" if latest_net_cash is not None and latest_net_cash >= 0 else "净负债",
                tone="good" if latest_net_cash is not None and latest_net_cash >= 0 else "warn",
                meaning="看企业手里自由现金与有息负债抵消后的净头寸。",
                implication="净现金越厚，财务腾挪空间越大；净负债越重，对利率和再融资越敏感。",
                formula="货币资金 + 交易性金融资产 - 有息负债",
            ),
        ],
        "ocf": [
            MetricAssessment(
                label="OCF ÷ 净利润",
                value_display=fmt_pct(latest_ocf_ratio),
                rule_display="优: >=100%；正常: 80%~100%；偏弱: 70%~80%；危险: <70%",
                status_text={"good": "印钞机", "warn": ("正常运转" if latest_ocf_ratio is not None and latest_ocf_ratio >= 80 else "跑步机"), "bad": "危险红线", "muted": "缺数据"}[_rate_ocf_ratio(latest_ocf_ratio)],
                tone=_rate_ocf_ratio(latest_ocf_ratio),
                meaning="看经营现金流相对账面净利润的覆盖程度。",
                implication="它直接回答‘利润是纸上的，还是袋里的’。",
                formula="OCF / 归母净利润 × 100%",
            )
        ],
        "goodwill": [
            MetricAssessment(
                label="商誉 ÷ 净资产",
                value_display=fmt_pct(latest_gw_ratio),
                rule_display="干净: <10%；关注: 10%~30%；高危: >30%",
                status_text={"good": "商誉干净", "warn": "并购症", "bad": "商誉高危", "muted": "缺数据"}[_rate_goodwill(latest_gw_ratio)],
                tone=_rate_goodwill(latest_gw_ratio),
                meaning="看企业账面净资产里，有多少是并购溢价形成的‘空气’。",
                implication="商誉占比过高时，未来一旦减值，会直接吞利润、打击估值和信心。",
                formula="商誉 / 净资产 × 100%",
            )
        ],
        "tax": [
            MetricAssessment(
                label="纸面有效税率",
                value_display=fmt_pct(latest_book_rate),
                rule_display="大体匹配 15%/25% 档更安心",
                status_text={"good": "税率匹配", "warn": "偏离关注", "bad": "税危", "muted": "缺数据"}[_rate_tax(latest_book_rate)],
                tone=_rate_tax(latest_book_rate),
                meaning="看报表上的所得税费用与利润总额是否大致匹配。",
                implication="长期极低税率若又没有充分解释，往往意味着利润质量或税务口径需要深挖。",
                formula="所得税费用 / 利润总额 × 100%",
            )
        ],
        "pledge": [
            MetricAssessment(
                label="质押占总股本",
                value_display=fmt_pct(pledge_ratio),
                rule_display="安全: <20%；关注: 20%~50%；紧绷: 50%~80%；危卵: >80%",
                status_text={"good": "安全区", "warn": "温和关注", "bad": "高杠杆风险", "muted": "缺数据"}[_rate_pledge(pledge_ratio)],
                tone=_rate_pledge(pledge_ratio),
                meaning="看大股东质押对总股本的占用程度。",
                implication="质押比例高时，股价波动可能反过来触发补仓、平仓和控制权风险。",
                formula="质押股数 / 总股本 × 100%",
            )
        ],
        "payout": [
            MetricAssessment(
                label="股利支付率",
                value_display=fmt_pct(latest_payout),
                rule_display="稳健: 30%~70%；偏低/偏高: 0%~30% 或 70%~100%；危险: >100%",
                status_text={"good": "稳健分红", "warn": "高派息/低派息", "bad": "高息陷阱", "muted": "缺数据"}[_rate_payout(latest_payout)],
                tone=_rate_payout(latest_payout),
                meaning="看公司分红是稳健回馈股东，还是在透支利润。",
                implication="支付率太低说明老板未必愿意分钱，太高则可能牺牲再投资能力甚至借钱分红。",
                formula="现金分红 / 归母净利润 × 100%",
            )
        ],
        "shareholder": [
            MetricAssessment(
                label="总股东收益率",
                value_display=(
                    f"{fmt_pct(latest_total_yield)}（3年均值 {fmt_pct(avg_total_yield_3y)}）"
                    if avg_total_yield_3y is not None and latest_total_yield is not None
                    else fmt_pct(latest_total_yield)
                ),
                rule_display="强回馈常见于 4%~8%；结合ROIC看回馈是否合理",
                status_text=sh_status,
                tone=sh_tone,
                meaning="把现金分红和净回购合在一起，看股东实际拿到多少回馈。",
                implication="有些公司看起来分红一般，但净回购很强；也有些公司一边回购一边增发，老股东实际并没占便宜。高ROIC公司低回馈可能是合理的再投资选择。",
                formula="(现金分红 + 净回购) / 当前市值 × 100%（评判基于近3年均值）",
            )
        ],
    }

    # --- P1: RORE & 资本配置画像 ---
    rore = None
    rore_tone = "muted"
    rore_status = "缺数据"
    rore_value_display = "N/A"
    rore_formula_detail = "(最新 Real_EPS - 3年前 Real_EPS) / (近3年累计留存收益/股) × 100%"
    cap_archetype = "待判断"
    cap_archetype_tone = "muted"
    if len(annual_cols) >= 4:
        _first_col = annual_cols[-4]
        _last_col = annual_cols[-1]
        _first_d = year_data.get(_first_col, {})
        _last_d = year_data.get(_last_col, {})
        _eps_first, _ = get_real_eps(abs_df, _first_col) if abs_df is not None else (None, "")
        _eps_last, _ = get_real_eps(abs_df, _last_col) if abs_df is not None else (None, "")
        # cumulative retained earnings over middle 3 years (not including first year's)
        _retained_sum = 0.0
        _retained_ok = True
        for _rc in annual_cols[-3:]:
            _rd = year_data.get(_rc, {})
            _rp = safe_float(_rd.get("profit"))
            _rdiv = safe_float(_rd.get("dividends_paid"))
            if _rp is not None:
                _retained_sum += _rp - (_rdiv or 0.0)
            else:
                _retained_ok = False
        if _eps_first is not None and _eps_last is not None and _retained_ok and _retained_sum > 0:
            _shares_last = safe_float(_last_d.get("shares"))
            if _shares_last and _shares_last > 0:
                _retained_per_share = _retained_sum / _shares_last
                rore = (_eps_last - _eps_first) / _retained_per_share * 100 if _retained_per_share > 0 else None
                if rore is not None:
                    rore_value_display = fmt_pct(rore)
                    rore_formula_detail = (
                        f"({fmt_num(_eps_last)} - {fmt_num(_eps_first)}) / {fmt_num(_retained_per_share)} × 100%"
                        f" = {fmt_pct(rore)}"
                    )
        elif _eps_first is not None and _eps_last is not None and _retained_ok and _retained_sum <= 0:
            rore_status = "近3年净返还资本"
            rore_value_display = "净返还资本"
            rore_formula_detail = (
                f"近3年累计留存收益 = {fmt_yi(_retained_sum)}（股息高于净利润），"
                "分母 <= 0，当前口径下 RORE 不适用。"
            )
        if rore is not None:
            if rore >= 15:
                rore_tone, rore_status = "good", "留存增值高效"
            elif rore >= 8:
                rore_tone, rore_status = "warn", "留存增值一般"
            else:
                rore_tone, rore_status = "bad", "留存增值偏弱"

    # Capital allocation archetype: ROIC × payout 2×2 matrix
    _roic_high = latest_roic is not None and latest_roic >= 12
    _payout_high = latest_payout is not None and latest_payout >= 40
    if _roic_high and _payout_high:
        cap_archetype = "印钞+分红型"
        cap_archetype_tone = "good"
    elif _roic_high and not _payout_high:
        cap_archetype = "高效再投资型"
        cap_archetype_tone = "good"
    elif not _roic_high and _payout_high:
        cap_archetype = "低效但愿分红"
        cap_archetype_tone = "warn"
    else:
        cap_archetype = "低效低分红"
        cap_archetype_tone = "bad"

    cards["capital_allocation"] = [
        MetricAssessment(
            label="RORE（留存收益回报率）",
            value_display=rore_value_display,
            rule_display="优: >=15%；达标: 8%~15%；偏弱: <8%",
            status_text=rore_status,
            tone=rore_tone,
            meaning="公司把没分掉的利润留存下来后，每一块钱留存能多创造多少每股收益。",
            implication="RORE 高说明公司留存利润真正在增值，而不是沉没在低效资产里。巴菲特认为这是检验管理层资本配置能力的核心指标。",
            formula=rore_formula_detail,
        ),
        MetricAssessment(
            label="资本配置画像",
            value_display=cap_archetype,
            rule_display=f"ROIC {fmt_pct(latest_roic)}（门槛12%） | 派息率 {fmt_pct(latest_payout)}（门槛40%）",
            status_text=f"ROIC {'高' if _roic_high else '低'} × 分红 {'高' if _payout_high else '低'}",
            tone=cap_archetype_tone,
            meaning="用 ROIC 和分红率两个维度，判断公司属于哪种资本配置风格。",
            implication="印钞+分红型是巴芒最爱（如可口可乐）；高效再投资型是伯克希尔模式（如早年Amazon）；低效但愿分红至少还给股东，但长期成长性存疑。",
        ),
    ]

    return cards

def _build_shareholder_note(
    total_yield, latest_roic, div, ocf, net_buyback, payout,
    annual_cols, year_data, mcap,
) -> str:
    parts = []
    # Base assessment
    if total_yield is not None and total_yield >= 2:
        parts.append("对股东有实质回馈，不只是口头上说重视股东。")
    elif total_yield is not None and latest_roic is not None and latest_roic >= 15:
        parts.append("综合回馈偏低，但ROIC较高，可能是在把钱用于高效再投资（类似伯克希尔模式）。")
    else:
        parts.append("对股东的综合回馈偏弱，要看公司究竟把钱花到哪里去了。")
    # P2: Net dilution warning
    if net_buyback is not None and net_buyback < 0:
        parts.append("注意：增发金额超过回购金额，存在净增发稀释，老股东每股权益被摊薄。")
    # P3: Dividend sustainability check
    if div is not None and ocf is not None and div > 0 and ocf > 0 and div > ocf:
        parts.append("⚠ 现金分红超过经营现金流，可能在借钱分红，分红可持续性存疑。")
    # P3: Payout rising but profit not growing (check last 3 years)
    if len(annual_cols) >= 3:
        recent = annual_cols[-3:]
        payouts = []
        profits = []
        for c in recent:
            _d = year_data.get(c, {})
            _div = safe_float(_d.get("dividends_paid"))
            _profit = safe_float(_d.get("profit"))
            if _div is not None and _profit is not None and _profit > 0:
                payouts.append(_div / _profit * 100)
                profits.append(_profit)
        if len(payouts) >= 3:
            payout_rising = payouts[-1] > payouts[0] + 5
            profit_flat_or_down = profits[-1] <= profits[0] * 1.05
            if payout_rising and profit_flat_or_down:
                parts.append("近3年分红率上升但利润未增长，分红可持续性需要关注。")
    return " ".join(parts)

def build_quality_module_notes(
    abs_df: pd.DataFrame,
    annual_cols: Sequence[str],
    year_data: Dict[str, Dict],
    diagnostics: Dict[str, object],
) -> Dict[str, str]:
    latest_col = annual_cols[-1] if annual_cols else None
    latest = year_data.get(latest_col, {}) if latest_col else {}
    latest_roa = safe_float(latest.get("roa"))
    latest_roe = safe_float(latest.get("roe"))
    latest_roic = roic_percent_from_year_data(latest) if latest else None
    gap = (latest_roe - latest_roic) if latest_roe is not None and latest_roic is not None else None
    tag, icr = interest_coverage_ratio_tag_value(latest) if latest else ("na", None)
    real_eps, _ = get_real_eps(abs_df, latest_col) if latest_col and abs_df is not None else (None, "")
    ocf = safe_float(latest.get("ocf"))
    profit = safe_float(latest.get("profit"))
    shares = safe_float(latest.get("shares"))
    ocf_ps = (ocf / shares) if ocf is not None and shares not in (None, 0) else None
    eps_quality = (ocf_ps / real_eps) if ocf_ps is not None and real_eps not in (None, 0) else None
    ocf_ratio = (ocf / profit * 100) if ocf is not None and profit and profit > 0 else None
    eq = _equity_denom(latest)
    gw = safe_float(latest.get("goodwill")) or 0.0
    gw_ratio = (gw / eq * 100) if eq and eq > 0 else None
    pretax = safe_float(latest.get("pretax"))
    tax = safe_float(latest.get("tax"))
    book_rate = (tax / pretax * 100) if pretax and tax is not None and pretax > 0 else None
    pledge = diagnostics.get("pledge")
    pledge_fetch_status = str(diagnostics.get("pledge_fetch_status") or "")
    pledge_ratio = safe_float(pledge.get("pledge_ratio_pct")) if pledge else None
    div = safe_float(latest.get("dividends_paid"))
    payout = (div / profit * 100) if div is not None and profit and profit > 0 else None
    mcap = safe_float(diagnostics.get("market_cap"))
    net_buyback = (safe_float(latest.get("buyback_cash")) or 0.0) - (safe_float(latest.get("equity_inflow_cash")) or 0.0)
    total_yield = ((div or 0.0) + net_buyback) / mcap * 100 if mcap and div is not None else None

    return {
        "efficiency": (
            "经营效率偏强，回报更多来自经营本身。"
            if latest_roa is not None and latest_roa >= 5 and gap is not None and gap <= 6
            else "经营效率与杠杆贡献需要一起看，ROE 不能单独相信。"
        ),
        "interest": (
            "利息覆盖较从容，财务压力暂不突出。"
            if tag == "surplus" or (icr is not None and icr >= 5)
            else "利息覆盖偏弱，利润波动会先冲击偿债安全。"
        ),
        "eps": (
            "每股收益的现金支撑较好，主业 EPS 质量更可信。"
            if eps_quality is not None and eps_quality >= 0.8
            else "EPS 的现金含量偏弱，读数时要防止只看到账面利润。"
        ),
        "capital": (
            "资本质量尚可，投入资本能赚回像样回报。"
            if latest_roic is not None and latest_roic >= 10
            else "资本回报一般，财务安全更依赖后续经营改善。"
        ),
        "ocf": (
            "利润转现金的能力较好，账面利润兑现度不错。"
            if ocf_ratio is not None and ocf_ratio >= 70
            else "利润兑现成现金的过程偏吃力，需继续盯应收和库存。"
        ),
        "goodwill": (
            "商誉包袱不重，资产质量相对干净。"
            if gw_ratio is not None and gw_ratio < 10
            else "商誉占比需要关注，并购溢价和减值风险不能忽视。"
        ),
        "tax": (
            "纸面税率大体可解释，利润可信度更高一些。"
            if book_rate is not None and 7 <= book_rate <= 32
            else "税率长期偏离常识区间时，要回到附注核实利润质量。"
        ),
        "pledge": (
            "股权质押压力不大，控制权和补仓风险相对温和。"
            if pledge_ratio is not None and pledge_ratio < 20
            else (
                "股权质押需要关注，股价波动可能放大流动性和控制权风险。"
                if pledge_ratio is not None
                else (
                    "股权质押接口本次超时，页面未取到快照，不代表公司一定没有质押。"
                    if pledge_fetch_status == "timeout"
                    else (
                        "股权质押接口本次未取到数据，可能是接口波动，也可能是当期没有可用快照。"
                        if pledge_fetch_status in ("error", "not_found")
                        else "本次未提供股权质押快照。"
                    )
                )
            )
        ),
        "payout": (
            "分红节奏相对稳健，资本配置偏成熟。"
            if payout is not None and 30 <= payout <= 70
            else "分红策略要继续观察，可能偏保守，也可能偏激进。"
        ),
        "shareholder": _build_shareholder_note(
            total_yield, latest_roic, div, ocf, net_buyback, payout,
            annual_cols, year_data, mcap,
        ),
        "capital_allocation": (
            f"ROIC {fmt_pct(latest_roic)} 且派息率 {fmt_pct(payout)}，资本配置偏巴菲特理想型。"
            if latest_roic is not None and latest_roic >= 12 and payout is not None and payout >= 40
            else (
                f"ROIC {fmt_pct(latest_roic)} 但派息率仅 {fmt_pct(payout)}，可能走伯克希尔式全额留存再投资路线，需关注留存收益回报率（RORE）是否真正创造超额价值。"
                if latest_roic is not None and latest_roic >= 12
                else (
                    f"ROIC {fmt_pct(latest_roic)} 偏低但派息率 {fmt_pct(payout)}，至少钱回到了股东手里，但长期靠低效资产扩张不可持续。"
                    if payout is not None and payout >= 40
                    else f"ROIC {fmt_pct(latest_roic)} 偏低且派息率 {fmt_pct(payout)} 也不高，钱留在公司手里也没有高效增值，最不理想的资本配置。"
                )
            )
        ),
    }

def _latest_share_change_before(df: pd.DataFrame, as_of: pd.Timestamp) -> Optional[pd.Series]:
    if df is None or df.empty or "变动日期" not in df.columns:
        return None
    tmp = df.copy()
    tmp["_dt"] = pd.to_datetime(tmp["变动日期"], errors="coerce")
    tmp = tmp[tmp["_dt"].notna() & (tmp["_dt"] <= as_of)].sort_values("_dt")
    if tmp.empty:
        return None
    return tmp.iloc[-1]

def _share_change_rows_between(
    df: pd.DataFrame,
    start_exclusive: Optional[pd.Timestamp],
    end_inclusive: pd.Timestamp,
) -> pd.DataFrame:
    if df is None or df.empty or "变动日期" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["_dt"] = pd.to_datetime(tmp["变动日期"], errors="coerce")
    tmp = tmp[tmp["_dt"].notna() & (tmp["_dt"] <= end_inclusive)]
    if start_exclusive is not None:
        tmp = tmp[tmp["_dt"] > start_exclusive]
    return tmp.sort_values("_dt")

def _normalize_share_change_reason(val: object) -> str:
    if val is None or pd.isna(val):
        return ""
    return str(val).replace(" ", "").strip()

def _classify_share_change_reasons(reasons: Sequence[str]) -> Tuple[str, str]:
    meaningful = [
        r for r in reasons
        if r and not any(token in r for token in ("定期报告", "季度报告", "中期报告", "年度报告"))
    ]
    if not meaningful:
        return "none", "定期报告"

    bonus_hit = any(any(token in r for token in ("转增", "送股", "送转", "拆股", "拆细", "资本公积", "公积金转增")) for r in meaningful)
    financing_hit = any(any(token in r for token in ("增发", "配股", "转股", "可转债", "股权激励", "期权", "限制性股票", "员工持股", "配售股份上市", "发行", "IPO", "上市")) for r in meaningful)
    reduction_hit = any(any(token in r for token in ("回购注销", "注销", "减资")) for r in meaningful)

    if bonus_hit and not financing_hit and not reduction_hit:
        return "bonus", "送转/拆股"
    if reduction_hit and not financing_hit and not bonus_hit:
        return "reduction", "回购注销/减资"
    if financing_hit and not bonus_hit:
        return "financing", "融资/转股/激励"
    if financing_hit and bonus_hit:
        return "mixed", "融资+送转混合"
    return "unknown", "原因待辨识"

def _annotate_share_change_effective_shares(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "变动日期" not in df.columns:
        return df
    tmp = df.copy()
    tmp["_dt"] = pd.to_datetime(tmp["变动日期"], errors="coerce")
    tmp = tmp[tmp["_dt"].notna()].sort_values("_dt").copy()
    if tmp.empty:
        return tmp

    raw_totals = [_parse_cninfo_share_count(val) for val in tmp["总股本"].tolist()] if "总股本" in tmp.columns else [None] * len(tmp)
    kinds: List[str] = []
    labels: List[str] = []
    effective_totals: List[Optional[float]] = []
    prev_total: Optional[float] = None
    prev_effective: Optional[float] = None

    for idx, (_, row) in enumerate(tmp.iterrows()):
        total = raw_totals[idx] if idx < len(raw_totals) else None
        kind, label = _classify_share_change_reasons([_normalize_share_change_reason(row.get("变动原因"))])
        if total is None:
            effective = prev_effective
        elif prev_total is None or prev_effective is None:
            effective = total
        elif kind == "bonus":
            effective = prev_effective
        else:
            ratio = (total / prev_total) if prev_total and prev_total > 0 else None
            effective = (prev_effective * ratio) if ratio is not None else total
        kinds.append(kind)
        labels.append(label)
        effective_totals.append(effective)
        if total is not None:
            prev_total = total
        if effective is not None:
            prev_effective = effective

    tmp["_change_kind"] = kinds
    tmp["_change_label"] = labels
    tmp["_effective_total_shares"] = effective_totals
    return tmp

def _classify_share_change_interval(
    df: pd.DataFrame,
    start_exclusive: Optional[pd.Timestamp],
    end_inclusive: pd.Timestamp,
) -> Tuple[str, str, List[str]]:
    tmp = _share_change_rows_between(df, start_exclusive, end_inclusive)
    if tmp.empty or "变动原因" not in tmp.columns:
        return "unknown", "数据不足", []

    reasons = []
    for raw in tmp["变动原因"].tolist():
        reason = _normalize_share_change_reason(raw)
        if reason and reason not in reasons:
            reasons.append(reason)
    if not reasons:
        return "unknown", "原因缺失", []
    kind, label = _classify_share_change_reasons(reasons)
    return kind, label, reasons

def _value_cagr_from_rows(rows: Sequence[Dict[str, object]], key: str) -> Optional[float]:
    pairs = [(int(r["year"]), safe_float(r.get(key))) for r in rows if safe_float(r.get(key)) is not None]
    pairs = [(y, v) for y, v in pairs if v is not None and v > 0]
    if len(pairs) < 2:
        return None
    start_y, start_v = pairs[0]
    end_y, end_v = pairs[-1]
    return compute_cagr(start_v, end_v, end_y - start_y)

def _share_growth_tone(v: Optional[float], is_float: bool = False) -> Tuple[str, str]:
    if v is None:
        return "muted", "数据不足"
    if v <= 1:
        return "good", "基本未稀释"
    if v <= 3:
        return "warn", "温和增加"
    return "bad", "稀释压力" if not is_float else "流通扩张快"

def _future_unlock_pressure(code: str, current_float_shares: Optional[float]) -> Dict[str, object]:
    df, status = fetch_restricted_release_queue_safe(code)
    today = pd.Timestamp.now().normalize()
    horizon = today + pd.Timedelta(days=365)
    out = {
        "status": status,
        "unlock_shares": None,
        "unlock_ratio_float": None,
        "rows": [],
    }
    if status != "ok" or df.empty or "解禁时间" not in df.columns:
        return out
    tmp = df.copy()
    tmp["_dt"] = pd.to_datetime(tmp["解禁时间"], errors="coerce")
    tmp = tmp[tmp["_dt"].notna() & (tmp["_dt"] >= today) & (tmp["_dt"] <= horizon)].copy()
    if tmp.empty:
        out["status"] = "ok_empty_next_12m"
        return out

    total_unlock = 0.0
    rows = []
    for _, r in tmp.sort_values("_dt").iterrows():
        shares = _parse_restricted_release_share_count(r.get("实际解禁数量"))
        if shares is None:
            shares = _parse_restricted_release_share_count(r.get("解禁数量"))
        if shares is not None:
            total_unlock += shares
        ratio = (shares / current_float_shares * 100) if shares is not None and current_float_shares and current_float_shares > 0 else None
        rows.append(
            {
                "date": r.get("解禁时间"),
                "shares": shares,
                "ratio_float": ratio,
                "holder_count": r.get("解禁股东数"),
                "type": r.get("限售股类型"),
            }
        )
    out["unlock_shares"] = total_unlock
    out["unlock_ratio_float"] = (total_unlock / current_float_shares * 100) if current_float_shares and current_float_shares > 0 else None
    out["rows"] = rows[:8]
    return out

def build_share_capital_analysis(
    code: str,
    abs_df: pd.DataFrame,
    annual_cols: Sequence[str],
    year_data: Dict[str, Dict],
    current_total_shares: Optional[float],
    share_basis_mode: Optional[str] = None,
    maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO,
) -> Dict[str, object]:
    share_df, share_status = fetch_share_change_history_safe(code)
    if share_status == "ok":
        share_df = _annotate_share_change_effective_shares(share_df)
    rows: List[Dict[str, object]] = []
    prev_as_of: Optional[pd.Timestamp] = None
    primary_basis = "asof" if share_basis_mode == "asof" else "current"
    for col in annual_cols:
        as_of = pd.Timestamp(f"{col[:4]}-12-31")
        share_row = _latest_share_change_before(share_df, as_of) if share_status == "ok" else None
        change_kind, change_label, change_reasons = (
            _classify_share_change_interval(share_df, prev_as_of, as_of)
            if share_status == "ok"
            else (
                "unknown",
                "未接入美股公司行为数据源" if not str(code).strip().isdigit() else "接口缺失",
                [],
            )
        )
        d = year_data.get(col, {})
        asof_total_shares = _parse_cninfo_share_count(share_row.get("总股本")) if share_row is not None else None
        float_shares = _parse_cninfo_share_count(share_row.get("已流通股份")) if share_row is not None else None
        economic_total_shares = safe_float(share_row.get("_effective_total_shares")) if share_row is not None else None
        if primary_basis == "asof":
            total_shares = (
                asof_total_shares
                or safe_float(d.get("asof_shares"))
                or safe_float(d.get("valuation_shares"))
                or safe_float(d.get("reported_shares"))
                or safe_float(d.get("shares"))
            )
        else:
            total_shares = (
                safe_float(d.get("valuation_shares"))
                or asof_total_shares
                or safe_float(d.get("asof_shares"))
                or safe_float(d.get("reported_shares"))
                or safe_float(d.get("shares"))
            )
        if economic_total_shares is None:
            economic_total_shares = total_shares
        if primary_basis == "current" and not str(code).strip().isdigit() and total_shares is not None:
            # 港美股在 current-basis 下，优先保证可交易股本口径与主分母一致。
            float_shares = total_shares
        if float_shares is None and total_shares is not None and not str(code).strip().isdigit():
            # 美股通常没有 A 股“限售股/流通 A 股”同款口径；缺少逐年 public float 时，
            # 用普通股 outstanding 作为股本质量模块的可交易股本近似。
            float_shares = total_shares
        profit = safe_float(d.get("profit"))
        ocf = safe_float(d.get("ocf"))
        shares_for_ps = total_shares
        if shares_for_ps is None:
            if primary_basis == "asof":
                shares_for_ps = safe_float(d.get("asof_shares")) or safe_float(d.get("valuation_shares"))
            else:
                shares_for_ps = safe_float(d.get("valuation_shares")) or safe_float(d.get("asof_shares"))
        shares_for_ps = shares_for_ps or safe_float(d.get("reported_shares")) or safe_float(d.get("shares"))
        real_eps, _ = get_real_eps(abs_df, col)
        oe = _owner_earnings_company(d, maint_capex_ratio=maint_capex_ratio) if d and safe_float(d.get("profit")) is not None else None
        net_buyback = (safe_float(d.get("buyback_cash")) or 0.0) - (safe_float(d.get("equity_inflow_cash")) or 0.0)
        rows.append(
            {
                "col": col,
                "year": col[:4],
                "total_shares": total_shares,
                "economic_total_shares": economic_total_shares,
                "float_shares": float_shares,
                "float_ratio": (float_shares / total_shares * 100) if float_shares and total_shares and total_shares > 0 else None,
                "real_eps": real_eps,
                "ocf_ps": (ocf / shares_for_ps) if ocf is not None and shares_for_ps and shares_for_ps > 0 else None,
                "oe_ps": (oe / shares_for_ps) if oe is not None and shares_for_ps and shares_for_ps > 0 else None,
                "bvps": safe_float(get_metric(abs_df, "每股净资产", col)),
                "net_buyback": net_buyback,
                "profit": profit,
                "share_change_kind": change_kind,
                "share_change_label": change_label,
                "share_change_reasons": change_reasons,
            }
        )
        prev_as_of = as_of

    prev: Optional[Dict[str, object]] = None
    for row in rows:
        total = safe_float(row.get("total_shares"))
        economic_total = safe_float(row.get("economic_total_shares"))
        float_s = safe_float(row.get("float_shares"))
        prev_total = safe_float(prev.get("total_shares")) if prev else None
        prev_economic = safe_float(prev.get("economic_total_shares")) if prev else None
        prev_float = safe_float(prev.get("float_shares")) if prev else None
        row["total_yoy"] = (total / prev_total - 1) * 100 if total and prev_total and prev_total > 0 else None
        row["economic_total_yoy"] = (
            (economic_total / prev_economic - 1) * 100
            if economic_total is not None and prev_economic and prev_economic > 0
            else None
        )
        row["float_yoy"] = (float_s / prev_float - 1) * 100 if float_s and prev_float and prev_float > 0 else None
        prev = row

    total_cagr = _value_cagr_from_rows(rows, "total_shares")
    economic_total_cagr = _value_cagr_from_rows(rows, "economic_total_shares")
    float_cagr = _value_cagr_from_rows(rows, "float_shares")
    real_eps_cagr = _value_cagr_from_rows(rows, "real_eps")
    ocf_ps_cagr = _value_cagr_from_rows(rows, "ocf_ps")
    oe_ps_cagr = _value_cagr_from_rows(rows, "oe_ps")
    latest = rows[-1] if rows else {}
    latest_total = safe_float(latest.get("total_shares")) or current_total_shares
    latest_float = safe_float(latest.get("float_shares"))
    unlock = _future_unlock_pressure(code, latest_float)
    unlock_ratio = safe_float(unlock.get("unlock_ratio_float"))

    total_tone, total_status = _share_growth_tone(total_cagr)
    economic_tone, economic_status = _share_growth_tone(economic_total_cagr)
    float_tone, float_status = _share_growth_tone(float_cagr, is_float=True)
    latest_float_ratio = safe_float(latest.get("float_ratio"))
    bonus_years = [str(r.get("year")) for r in rows if r.get("share_change_kind") == "bonus" and safe_float(r.get("total_yoy")) not in (None, 0)]
    financing_years = [str(r.get("year")) for r in rows if r.get("share_change_kind") in ("financing", "mixed") and safe_float(r.get("total_yoy")) not in (None, 0)]
    unknown_years = [str(r.get("year")) for r in rows if r.get("share_change_kind") == "unknown" and safe_float(r.get("total_yoy")) not in (None, 0)]
    if bonus_years and (economic_total_cagr is None or economic_total_cagr <= 1):
        dilution_tone, dilution_status = "good", "送转为主，非融资稀释"
    elif unknown_years and total_tone in ("warn", "bad") and (economic_total_cagr is None or economic_total_cagr <= 3):
        dilution_tone, dilution_status = "warn", "股本扩张，原因待辨识"
    elif economic_tone == "bad":
        dilution_tone, dilution_status = "bad", "真实稀释压力"
    elif economic_tone == "warn":
        dilution_tone, dilution_status = "warn", "真实股本温和增加"
    elif float_cagr is not None and float_cagr > 10 and (latest_float_ratio is None or latest_float_ratio < 95):
        dilution_tone, dilution_status = "warn", "流通扩张中"
    elif economic_tone == "good":
        dilution_tone, dilution_status = "good", "股本稳定"
    else:
        dilution_tone, dilution_status = "muted", "数据不足"

    buybacks = [safe_float(r.get("net_buyback")) or 0.0 for r in rows]
    total_net_buyback = sum(buybacks)
    latest_economic_yoy = safe_float(latest.get("economic_total_yoy"))
    positive_buyback_years = sum(1 for v in buybacks if v > 0)
    pseudo_buyback = (
        total_net_buyback > 0
        and economic_total_cagr is not None
        and economic_total_cagr > 0
        and positive_buyback_years >= 2
    )
    if pseudo_buyback:
        buyback_tone, buyback_status = "bad", "伪回购/被稀释抵消"
    elif total_net_buyback > 0 and latest_economic_yoy is not None and latest_economic_yoy <= 0 and (economic_total_cagr is None or economic_total_cagr <= 0):
        buyback_tone, buyback_status = "good", "真实增厚"
    elif total_net_buyback > 0 and bonus_years and (economic_total_cagr is None or economic_total_cagr <= 0):
        buyback_tone, buyback_status = "warn", "回购有效但伴随送转"
    elif total_net_buyback > 0:
        buyback_tone, buyback_status = "warn", "名义回购"
    elif total_net_buyback < 0:
        buyback_tone, buyback_status = "bad", "反向稀释"
    else:
        buyback_tone, buyback_status = "muted", "回购不明显"

    if unlock_ratio is None:
        unlock_tone = "muted"
        unlock_status = "无可用压力"
    elif unlock_ratio < 5:
        unlock_tone, unlock_status = "good", "压力低"
    elif unlock_ratio <= 15:
        unlock_tone, unlock_status = "warn", "需观察"
    else:
        unlock_tone, unlock_status = "bad", "压力高"

    value_cagrs = [v for v in (real_eps_cagr, ocf_ps_cagr, oe_ps_cagr) if v is not None]
    avg_value_cagr = sum(value_cagrs) / len(value_cagrs) if value_cagrs else None
    if avg_value_cagr is None:
        value_tone, value_status = "muted", "数据不足"
    elif avg_value_cagr >= 8:
        value_tone, value_status = "good", "每股变厚"
    elif avg_value_cagr >= 0:
        value_tone, value_status = "warn", "温和增厚"
    else:
        value_tone, value_status = "bad", "每股变薄"

    cards = [
        MetricAssessment(
            label="股本稀释",
            value_display=f"原始 {fmt_pct(total_cagr)} / 真实 {fmt_pct(economic_total_cagr)}",
            rule_display="优: 真实股本 CAGR <=1%；关注: 1%~3%；危险: >3%",
            status_text=dilution_status,
            tone=dilution_tone,
            meaning="把原始总股本变化和真实融资稀释拆开看，尽量剔除送转/拆股这类不改变经济权益的名义扩张。",
            implication="巴芒视角下，真正该警惕的是融资、转股和激励带来的经济性稀释，而不是高送转造成的会计口径放大。",
            formula="真实股本 CAGR = 剔除送转/拆股后的有效股本序列 CAGR",
        ),
        MetricAssessment(
            label="回购真实性",
            value_display=f"净回购 {fmt_yi(total_net_buyback)}",
            rule_display="真实增厚: 净回购为正且真实股本不增；伪回购: 花钱回购但真实股本仍扩张",
            status_text=buyback_status,
            tone=buyback_tone,
            meaning="看回购现金是否真正减少了经济性股本，而不是被增发、可转债、激励或单纯送转干扰。",
            implication="真正的回购是在低估时替老股东买回未来现金流；如果花了钱但真实股本还扩张，回购更像是在替稀释买单。",
            formula="净回购现金 = 回购支付现金 - 吸收投资收到现金；再交叉检查真实股本 CAGR",
        ),
        MetricAssessment(
            label="未来解禁压力",
            value_display=fmt_pct(unlock_ratio),
            rule_display="优: <5%；观察: 5%~15%；压力高: >15%",
            status_text=unlock_status,
            tone=unlock_tone,
            meaning="看未来 12 个月可能进入流通的限售股，相对当前流通股本有多大。",
            implication="解禁不是一定要卖，但它会改变供给结构；压力过大时，价格安全边际要更厚。",
            formula="未来12个月解禁股数 / 当前流通股本 × 100%",
        ),
        MetricAssessment(
            label="每股价值增厚",
            value_display=f"Real EPS {fmt_pct(real_eps_cagr)} / OE {fmt_pct(oe_ps_cagr)}",
            rule_display="优: 平均 CAGR >=8%；持平: 0%~8%；变薄: <0%",
            status_text=value_status,
            tone=value_tone,
            meaning="把利润、现金流和所有者盈余都折到每一股上，观察老股东手里的单股价值有没有变厚。",
            implication="总利润增长但每股不增长，说明扩张收益被股本稀释吃掉了。",
            formula="每股指标 CAGR = (期末每股值 / 期初每股值)^(1/n) - 1",
        ),
    ]

    good = sum(1 for c in cards if c.tone == "good")
    bad = sum(1 for c in cards if c.tone == "bad")
    if bad:
        note = "股本质量结论：存在明显稀释或解禁压力，老股东每股权益需要重点复核。"
    elif good >= 2 and value_tone in ("good", "warn"):
        note = "股本质量结论：股本结构相对克制，老股东每股价值没有被明显摊薄。"
    else:
        note = "股本质量结论：目前没有形成强烈好坏判断，重点看后续股本变化和每股价值趋势。"

    if pseudo_buyback:
        note += " 公司存在伪回购风险：历史累计净回购为正，但总股本仍在扩张，说明回购可能主要被股权激励、增发或转股稀释抵消。"
    if bonus_years:
        note += f" 检测到送转/拆股年份：{'、'.join(bonus_years)}，这些年份的股本扩大已尽量从真实稀释口径中剔除。"
    if financing_years:
        note += f" 检测到融资/转股/激励扩股年份：{'、'.join(financing_years)}。"
    if unknown_years:
        note += f" 部分股本变化原因无法可靠识别（{'、'.join(unknown_years)}），这些年份仍按保守口径处理。"
    if not str(code).strip().isdigit():
        note += " 美股流通股本按普通股 outstanding 近似，SEC public float 多以市值披露，不能直接当股数使用。"
    if share_status != "ok":
        note += f" 股本变动接口本次状态为 {share_status}，年度表已尽量用财报隐含股本兜底。"
    if unlock.get("status") in ("error", "not_found"):
        note += " 解禁接口本次未取到，不等同于未来没有解禁。"
    elif unlock.get("status") == "not_applicable":
        note += " 解禁压力口径不适用于当前市场，表格中的 N/A 不代表缺财报数据。"
    elif unlock.get("status") == "ok_empty_next_12m":
        note += " 解禁接口未显示未来 12 个月有可用解禁压力。"

    return {
        "cards": cards,
        "rows": rows,
        "unlock": unlock,
        "note": note,
        "share_status": share_status,
        "latest_total_shares": latest_total,
        "economic_total_cagr": economic_total_cagr,
    }

def build_extended_diagnostics(code: str, data: Dict[str, pd.DataFrame], total_shares: Optional[float], years: int, maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO) -> Dict[str, object]:
    abs_df = data["abstract"]
    year_data = build_year_data_for_valuation(data)
    annual_cols = [c for c in annual_cols_from_abstract(abs_df) if c in year_data][-years:]
    price_tuple = data.get("current_price_tuple") or get_current_price(code)
    price = safe_float(price_tuple[0])
    sh_mcap = total_shares
    share_basis_mode = data.get("_share_basis_mode")
    if sh_mcap is None and annual_cols:
        latest_row = year_data.get(annual_cols[-1]) or {}
        preferred_key = "asof_shares" if share_basis_mode == "asof" else "valuation_shares"
        sh_mcap = safe_float(latest_row.get(preferred_key))
        if sh_mcap is None or sh_mcap <= 0:
            sh_mcap = safe_float(latest_row.get("reported_shares"))
        if sh_mcap is None or sh_mcap <= 0:
            sh_mcap = safe_float(latest_row.get("shares"))
    market_cap = (price * sh_mcap) if price and sh_mcap and sh_mcap > 0 else None
    pledge, pledge_fetch_status = fetch_listed_pledge_snapshot_safe(code)
    share_capital = build_share_capital_analysis(
        code,
        abs_df,
        annual_cols,
        year_data,
        sh_mcap,
        share_basis_mode=share_basis_mode,
        maint_capex_ratio=maint_capex_ratio,
    )
    return {
        "abs_df": abs_df,
        "year_data": year_data,
        "annual_cols": annual_cols,
        "price": price,
        "shares": sh_mcap,
        "share_basis_mode": share_basis_mode,
        "market_cap": market_cap,
        "pledge": pledge,
        "pledge_fetch_status": pledge_fetch_status,
        "share_capital": share_capital,
    }


def analyze_share_basis_coverage(
    year_data: Dict[str, Dict],
    annual_cols: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    cols = [c for c in (annual_cols or sorted(year_data.keys())) if c in year_data]
    valuation_years: List[str] = []
    fallback_years: List[str] = []
    reported_fallback_years: List[str] = []
    eps_derived_years: List[str] = []
    legacy_fallback_years: List[str] = []
    missing_years: List[str] = []
    split_adjusted_years: List[str] = []
    split_like_jumps: List[str] = []
    mixed_basis_jumps: List[str] = []
    semantics_seen: set = set()

    prev_col = None
    prev_asof = None
    prev_val = None

    for col in cols:
        row = year_data.get(col) or {}
        valuation_shares = safe_float(row.get("valuation_shares"))
        reported_shares = safe_float(row.get("reported_shares"))
        legacy_shares = safe_float(row.get("shares"))
        year_label = str(col)[:4]
        reported_source = str(row.get("reported_shares_source") or "").strip()
        if valuation_shares is not None and valuation_shares > 0:
            valuation_years.append(year_label)
        elif reported_shares is not None and reported_shares > 0:
            fallback_years.append(year_label)
            reported_fallback_years.append(year_label)
            if reported_source == "profit_over_eps_derived":
                eps_derived_years.append(year_label)
        elif legacy_shares is not None and legacy_shares > 0:
            fallback_years.append(year_label)
            legacy_fallback_years.append(year_label)
        else:
            missing_years.append(year_label)

        split_factor = safe_float(row.get("split_factor_cumulative")) or 1.0
        if split_factor > 1.0:
            split_adjusted_years.append(year_label)

        sem = str(row.get("reported_shares_semantics") or "").strip()
        if sem:
            semantics_seen.add(sem)

        asof_shares = safe_float(row.get("asof_shares"))
        if prev_col and prev_asof and prev_asof > 0 and asof_shares and asof_shares > 0:
            ratio = asof_shares / prev_asof
            if ratio >= 2.0 or ratio <= 0.5:
                explained_by_split = False
                valuation_shares = safe_float(row.get("valuation_shares"))
                if prev_val and prev_val > 0 and valuation_shares and valuation_shares > 0:
                    vr = valuation_shares / prev_val
                    if 0.7 <= vr <= 1.4:
                        explained_by_split = True
                span = f"{str(prev_col)[:4]}→{year_label}"
                if explained_by_split:
                    split_like_jumps.append(span)
                else:
                    mixed_basis_jumps.append(span)

        prev_col = col
        prev_asof = asof_shares
        prev_val = safe_float(row.get("valuation_shares"))

    total_years = len(cols)
    unresolved = len(fallback_years) + len(missing_years)
    coverage_ratio = (len(valuation_years) / total_years) if total_years else 0.0
    if total_years and unresolved == 0:
        confidence = "高"
    elif total_years and unresolved <= max(1, total_years // 3):
        confidence = "中"
    else:
        confidence = "低"

    mixed_semantics = ("period_end" in semantics_seen and "derived_from_eps" in semantics_seen)
    if mixed_basis_jumps or mixed_semantics:
        # 语义混用或无法解释的跳变出现时，下调一档置信度。
        if confidence == "高":
            confidence = "中"
        elif confidence == "中":
            confidence = "低"

    return {
        "total_years": total_years,
        "valuation_years": valuation_years,
        "valuation_count": len(valuation_years),
        "coverage_ratio": coverage_ratio,
        "fallback_years": fallback_years,
        "fallback_count": len(fallback_years),
        "reported_fallback_years": reported_fallback_years,
        "reported_fallback_count": len(reported_fallback_years),
        "eps_derived_years": eps_derived_years,
        "eps_derived_count": len(eps_derived_years),
        "legacy_fallback_years": legacy_fallback_years,
        "legacy_fallback_count": len(legacy_fallback_years),
        "missing_years": missing_years,
        "missing_count": len(missing_years),
        "split_adjusted_years": split_adjusted_years,
        "split_adjusted_count": len(split_adjusted_years),
        "split_like_jumps": split_like_jumps,
        "split_like_jump_count": len(split_like_jumps),
        "mixed_basis_jumps": mixed_basis_jumps,
        "mixed_basis_jump_count": len(mixed_basis_jumps),
        "reported_semantics": sorted(semantics_seen),
        "mixed_semantics": mixed_semantics,
        "confidence": confidence,
    }

def build_quality_year_snapshots(
    abs_df: pd.DataFrame,
    annual_cols: Sequence[str],
    year_data: Dict[str, Dict],
    diag_mcap: Optional[float],
) -> List[Dict[str, object]]:
    snapshots: List[Dict[str, object]] = []
    if abs_df is None or abs_df.empty:
        return snapshots
    for col in annual_cols:
        d = year_data.get(col, {})
        profit = safe_float(d.get("profit"))
        ocf = safe_float(d.get("ocf"))
        shares = safe_float(d.get("shares"))
        roic = roic_percent_from_year_data(d) if d else None
        real_eps, _ = get_real_eps(abs_df, col)
        basic_eps = safe_float(get_metric(abs_df, "基本每股收益", col))
        diluted_eps = safe_float(get_metric(abs_df, "稀释每股收益", col))
        ocf_ps = (ocf / shares) if ocf is not None and shares not in (None, 0) else None
        eps_quality = (ocf_ps / real_eps) if ocf_ps is not None and real_eps is not None and real_eps > 0 else None
        ocf_ratio = (ocf / profit * 100) if ocf is not None and profit is not None and profit > 0 else None
        eq = _equity_denom(d)
        goodwill = safe_float(d.get("goodwill")) or 0.0
        gw_pct = (goodwill / eq * 100) if eq and eq > 0 else None
        pretax = safe_float(d.get("pretax"))
        tax = safe_float(d.get("tax"))
        book_rate = (tax / pretax * 100) if pretax is not None and tax is not None and pretax > 0 else None
        div = safe_float(d.get("dividends_paid"))
        payout = (div / profit * 100) if div is not None and profit is not None and profit > 0 else None
        net_buyback = (safe_float(d.get("buyback_cash")) or 0.0) - (safe_float(d.get("equity_inflow_cash")) or 0.0)
        div_yield = (div / diag_mcap * 100) if diag_mcap and div is not None else None
        buyback_yield = (net_buyback / diag_mcap * 100) if diag_mcap else None
        total_yield = ((div or 0.0) + net_buyback) / diag_mcap * 100 if diag_mcap and div is not None else None
        tag, icr = interest_coverage_ratio_tag_value(d)
        snapshots.append(
            {
                "col": col,
                "year": col[:4],
                "data": d,
                "roic": roic,
                "real_eps": real_eps,
                "basic_eps": basic_eps,
                "diluted_eps": diluted_eps,
                "ocf_ps": ocf_ps,
                "eps_quality": eps_quality,
                "ocf_ratio": ocf_ratio,
                "eq": eq,
                "goodwill": goodwill,
                "gw_pct": gw_pct,
                "pretax": pretax,
                "tax": tax,
                "book_rate": book_rate,
                "div": div,
                "payout": payout,
                "net_buyback": net_buyback,
                "div_yield": div_yield,
                "buyback_yield": buyback_yield,
                "total_yield": total_yield,
                "icr_tag": tag,
                "icr": icr,
                "profit": profit,
                "ocf": ocf,
            }
        )
    return snapshots

def summarize_business_quality(
    metrics: Sequence[MetricAssessment],
    ses_metrics: Sequence[MetricAssessment],
    quality_cards: Dict[str, List[MetricAssessment]],
    valuation_metrics: Sequence[ValuationAssessment],
    is_bank: bool = False,
) -> Dict[str, str]:
    def tone_score(t: str) -> int:
        return {"good": 2, "warn": 1, "muted": 1, "bad": 0}.get(t, 1)

    def find_by_label(items: Sequence[object], label: str):
        return next((x for x in items if getattr(x, "label", "") == label), None)

    def _weight_for_label(label: str, bank_mode: bool) -> float:
        # C级：工程化权重，反映“资本回报优先”而非等权平均。
        if bank_mode:
            if "NIM" in label or "成本收入" in label:
                return 2.0
            if "拨贷" in label or "杠杆" in label or "存贷" in label:
                return 2.2
            if "ROE" in label or "分红" in label or "股东" in label:
                return 1.5
            return 1.0
        if "ROIC" in label or "ROIIC" in label or "RORE" in label:
            return 2.5
        if "毛利率" in label or "业务纯度" in label or "CCC" in label:
            return 1.8
        if "含金量" in label or "净现金" in label or "利息" in label or "商誉" in label:
            return 1.6
        if "派息" in label or "股东" in label or "质押" in label or "稀释" in label:
            return 1.3
        return 1.0

    # --- P0: detect SES archetype ---
    ses_good = sum(1 for x in ses_metrics if getattr(x, "tone", "muted") == "good")
    ses_total = len(ses_metrics) if ses_metrics else 0
    is_ses_archetype = ses_good >= 3 and ses_total >= 4

    if is_bank:
        # 银行: 用银行经营指标评分，跳过 SES 和提价权
        # 注意：bank_metrics 已包含 ROA/ROE/杠杆倍数，不再追加 efficiency 卡片
        # 否则 ROA 和杠杆倍数 会被重复计入同一桶（杠杆 2.2× 权重被翻倍放大）
        is_ses_archetype = False
        pricing_items = list(metrics)
        quality_items = (
            list(metrics)
            + list(quality_cards.get("eps", []))
            + list(quality_cards.get("tax", []))
        )
        safety_items = (
            list(quality_cards.get("risk", []))
            + list(quality_cards.get("pledge", []))
        )
        enterprise_basis = "银行经营指标评分"
        moat_basis = "银行经营指标评分"
    elif is_ses_archetype:
        # SES 模式：efficiency 仅进 pricing_items（与 normal 模式一致）
        pricing_items = list(metrics[3:]) + list(quality_cards.get("efficiency", [])) + list(ses_metrics)
        quality_items = (
            list(metrics[3:])
            + list(ses_metrics)
            + list(quality_cards.get("eps", []))
            + list(quality_cards.get("tax", []))
        )
        enterprise_basis = "SES模式评分"
        moat_basis = "SES模式评分"
        safety_items = (
            list(quality_cards.get("interest", []))
            + list(quality_cards.get("capital", []))
            + list(quality_cards.get("ocf", []))
            + list(quality_cards.get("goodwill", []))
            + list(quality_cards.get("pledge", []))
        )
    else:
        pricing_items = list(metrics[:4]) + list(quality_cards.get("efficiency", []))
        quality_items = list(metrics) + list(quality_cards.get("eps", [])) + list(quality_cards.get("tax", []))
        enterprise_basis = "提价权模式评分"
        moat_basis = "提价权模式评分"
        safety_items = (
            list(quality_cards.get("interest", []))
            + list(quality_cards.get("capital", []))
            + list(quality_cards.get("ocf", []))
            + list(quality_cards.get("goodwill", []))
            + list(quality_cards.get("pledge", []))
        )

    def bucket(items: Sequence[object], bank_mode: bool) -> Tuple[int, int, int, float]:
        goods = sum(1 for x in items if getattr(x, "tone", "muted") == "good")
        warns = sum(1 for x in items if getattr(x, "tone", "muted") == "warn")
        bads = sum(1 for x in items if getattr(x, "tone", "muted") == "bad")
        if not items:
            return goods, warns, bads, 1.0
        weights = [_weight_for_label(getattr(x, "label", ""), bank_mode) for x in items]
        weighted_sum = sum(tone_score(getattr(x, "tone", "muted")) * w for x, w in zip(items, weights))
        weight_total = sum(weights) if weights else 1.0
        avg = weighted_sum / weight_total
        return goods, warns, bads, avg

    q_good, _q_warn, q_bad, q_avg = bucket(quality_items, is_bank)
    p_good, _p_warn, p_bad, p_avg = bucket(pricing_items, is_bank)
    s_good, _s_warn, s_bad, s_avg = bucket(safety_items, is_bank)
    v_good = sum(1 for x in valuation_metrics if getattr(x, "tone", "muted") == "good")
    v_warn = sum(1 for x in valuation_metrics if getattr(x, "tone", "muted") == "warn")
    v_bad = sum(1 for x in valuation_metrics if getattr(x, "tone", "muted") == "bad")
    capex_metric = find_by_label(metrics, "Capex / Net Income")
    capex_veto = capex_metric is not None and getattr(capex_metric, "tone", "muted") == "bad"
    earnings_yield_metric = find_by_label(valuation_metrics, "盈利率 vs 国债")
    earnings_yield_veto = earnings_yield_metric is not None and getattr(earnings_yield_metric, "tone", "muted") == "bad"

    if q_avg >= 1.55 and q_bad <= 2 and q_good >= 7:
        enterprise_label, enterprise_tone = "优秀企业", "good"
    elif q_avg >= 1.25 and q_bad <= 4:
        enterprise_label, enterprise_tone = "良好企业", "good"
    elif q_avg >= 0.95:
        enterprise_label, enterprise_tone = "一般企业", "warn"
    else:
        enterprise_label, enterprise_tone = "回避型", "bad"

    if capex_veto and enterprise_label == "优秀企业":
        enterprise_label, enterprise_tone = "良好企业", "good"

    if p_avg >= 1.55 and p_bad == 0:
        moat_label, moat_tone = "护城河强", "good"
    elif p_avg >= 1.1:
        moat_label, moat_tone = "护城河中等", "warn"
    else:
        moat_label, moat_tone = "护城河偏弱", "bad"

    if s_avg >= 1.5 and s_bad <= 1:
        safety_label, safety_tone = "财务很稳", "good"
    elif s_avg >= 1.0 and s_bad <= 2:
        safety_label, safety_tone = "财务可控", "warn"
    else:
        safety_label, safety_tone = "财务承压", "bad"

    if v_good >= 3 and v_bad <= 1:
        valuation_label, valuation_tone = "估值偏低", "good"
    elif v_good >= 1 or v_warn >= 3:
        valuation_label, valuation_tone = "估值中性", "warn"
    else:
        valuation_label, valuation_tone = "估值偏贵", "bad"

    if earnings_yield_veto:
        valuation_label, valuation_tone = "机会成本不合格", "bad"

    if earnings_yield_veto:
        action = "盈利率没有跑赢十年期国债，按机会成本看不值得买入。"
        action_tone = "bad"
    elif capex_veto and enterprise_tone == "good":
        action = "企业经营质量不错，但资本开支吞噬利润，暂时达不到伟大公司的门槛。"
        action_tone = "warn"
    elif enterprise_label == "优秀企业" and safety_tone == "good" and valuation_tone == "good":
        action = "优秀企业，且价格进入可重点研究区。"
        action_tone = "good"
    elif enterprise_label == "良好企业" and safety_tone == "good" and valuation_tone == "good":
        action = "良好企业，且价格已经具备继续深挖的吸引力。"
        action_tone = "good"
    elif enterprise_tone == "good" and valuation_tone != "good":
        action = f"{enterprise_label}，但安全边际还不算厚，适合持续跟踪。"
        action_tone = "warn"
    elif enterprise_tone != "good" and valuation_tone == "good":
        action = "价格看起来不贵，但企业质量还没达到巴芒偏好的确定性。"
        action_tone = "warn"
    else:
        action = "暂时更像观察标的，还不够像能放心重仓的巴芒型公司。"
        action_tone = "bad"

    return {
        "enterprise_label": enterprise_label,
        "enterprise_tone": enterprise_tone,
        "enterprise_basis": enterprise_basis,
        "moat_label": moat_label,
        "moat_tone": moat_tone,
        "moat_basis": moat_basis,
        "safety_label": safety_label,
        "safety_tone": safety_tone,
        "valuation_label": valuation_label,
        "valuation_tone": valuation_tone,
        "action": action,
        "action_tone": action_tone,
        "is_ses_archetype": is_ses_archetype,
    }

def _build_bank_profitability_rows(rows: Sequence[Dict]) -> List[List[str]]:
    """Build bank profitability table rows for HTML."""
    result = []
    for row in rows:
        b_roa = safe_float(row.get("roa"))
        b_roe = safe_float(row.get("roe"))
        b_nim = safe_float(row.get("nim"))
        b_cir = safe_float(row.get("cost_income_ratio"))
        b_plr = safe_float(row.get("provision_loan_ratio"))
        b_ldr = safe_float(row.get("loan_deposit_ratio"))
        result.append([
            html.escape(row["year"]),
            wrap_value(fmt_pct(b_roa), _assess_roa(b_roa) if b_roa is not None else "muted"),
            wrap_value(fmt_pct(b_roe), "good" if b_roe is not None and b_roe >= 12 else ("warn" if b_roe is not None and b_roe >= 8 else ("bad" if b_roe is not None else "muted"))),
            wrap_value(fmt_pct(b_nim), _assess_nim(b_nim) if b_nim is not None else "muted"),
            wrap_value(fmt_pct(b_cir), _assess_cost_income(b_cir) if b_cir is not None else "muted"),
            wrap_value(fmt_pct(b_plr), _assess_provision_loan(b_plr) if b_plr is not None else "muted"),
            wrap_value(fmt_pct(b_ldr), _assess_loan_deposit(b_ldr) if b_ldr is not None else "muted"),
        ])
    return result


def _build_bank_credit_quality_rows(rows: Sequence[Dict]) -> List[List[str]]:
    """Build bank credit quality table rows (PPOP, NCO, Prov/NCO) for HTML."""
    result = []
    for row in rows:
        ppop = row.get("ppop")
        ppop_aa = safe_float(row.get("ppop_avg_assets"))
        nco = row.get("nco")
        nco_al = safe_float(row.get("nco_avg_loans"))
        prov_nco = safe_float(row.get("provision_nco_cover"))
        result.append([
            html.escape(row["year"]),
            fmt_yi(ppop) if ppop is not None else "N/A",
            wrap_value(fmt_pct(ppop_aa), _assess_ppop_avg_assets(ppop_aa) if ppop_aa is not None else "muted"),
            fmt_yi(nco) if nco is not None else "N/A",
            wrap_value(fmt_pct(nco_al), _assess_nco_ratio(nco_al) if nco_al is not None else "muted"),
            wrap_value(f"{prov_nco:.2f}x" if prov_nco is not None else "N/A", _assess_provision_nco_cover(prov_nco) if prov_nco is not None else "muted"),
        ])
    return result

def _build_bank_franchise_rows(rows: Sequence[Dict]) -> List[List[str]]:
    """Build bank franchise quality table rows (PPNR, ROTCE, deposit cost) for HTML."""
    result = []
    for row in rows:
        ppnr = row.get("ppnr")
        ppnr_aa = safe_float(row.get("ppnr_avg_assets"))
        rotce = safe_float(row.get("rotce"))
        dep_cost = safe_float(row.get("deposit_cost_rate"))
        roe = safe_float(row.get("roe"))
        result.append([
            html.escape(row["year"]),
            fmt_yi(ppnr) if ppnr is not None else "N/A",
            wrap_value(fmt_pct(ppnr_aa), _assess_ppnr_avg_assets(ppnr_aa) if ppnr_aa is not None else "muted"),
            wrap_value(fmt_pct(rotce), _assess_rotce(rotce) if rotce is not None else "muted"),
            wrap_value(fmt_pct(roe), ("good" if roe is not None and roe >= 15 else ("warn" if roe is not None and roe >= 10 else "bad")) if roe is not None else "muted"),
            wrap_value(fmt_pct(dep_cost), _assess_deposit_cost(dep_cost) if dep_cost is not None else "muted"),
        ])
    return result

def build_bank_stress_test(rows: Sequence[Dict]) -> Optional[Dict]:
    """
    Run Buffett-style bank stress test (1990 WFC method).
    Returns dict with 3 stress scenarios, or None if data insufficient.
    """
    if not rows:
        return None
    latest = rows[-1]
    gross_loans = safe_float(latest.get("gross_loans"))
    ppnr = safe_float(latest.get("ppnr"))
    parent_equity = safe_float(latest.get("parent_equity"))
    if gross_loans is None or ppnr is None or parent_equity is None:
        return None
    if gross_loans <= 0 or parent_equity <= 0:
        return None

    scenarios = [
        {"name": "温和衰退", "default_rate": 0.05, "lgd": 0.20, "desc": "正常经济放缓"},
        {"name": "严重衰退", "default_rate": 0.10, "lgd": 0.30, "desc": "巴菲特1990年WFC假设"},
        {"name": "极端危机", "default_rate": 0.15, "lgd": 0.40, "desc": "系统性金融危机"},
    ]

    results = []
    for s in scenarios:
        potential_loss = gross_loans * s["default_rate"] * s["lgd"]
        ppnr_surplus = ppnr - potential_loss
        equity_erosion = max(0, potential_loss - ppnr) / parent_equity * 100 if parent_equity > 0 else None
        years_to_cover = potential_loss / ppnr if ppnr > 0 else None

        if ppnr_surplus >= 0:
            verdict = "堡垒型"
            verdict_tone = "good"
        elif equity_erosion is not None and equity_erosion < 5:
            verdict = "可扛"
            verdict_tone = "warn"
        elif equity_erosion is not None and equity_erosion < 15:
            verdict = "承压"
            verdict_tone = "warn"
        else:
            verdict = "脆弱"
            verdict_tone = "bad"

        results.append({
            "name": s["name"],
            "desc": s["desc"],
            "default_rate": s["default_rate"],
            "lgd": s["lgd"],
            "potential_loss": potential_loss,
            "ppnr_surplus": ppnr_surplus,
            "equity_erosion": equity_erosion,
            "years_to_cover": years_to_cover,
            "verdict": verdict,
            "verdict_tone": verdict_tone,
        })

    return {
        "year": latest.get("year", ""),
        "gross_loans": gross_loans,
        "ppnr": ppnr,
        "parent_equity": parent_equity,
        "scenarios": results,
    }

def _build_feature_sketch(decision_summary: Dict[str, object], rows: Sequence[Dict]) -> str:
    """Auto-generate a 2-3 sentence company archetype description."""
    parts: List[str] = []
    is_ses = decision_summary.get("is_ses_archetype", False)
    ent = decision_summary.get("enterprise_label", "")
    moat = decision_summary.get("moat_label", "")

    gm = rows[-1].get("gross_margin") if rows else None
    if is_ses:
        parts.append(f"该企业呈现 SES（规模经济分享）模式特征，企业质量评定为「{ent}」，护城河评定为「{moat}」。")
    else:
        if gm is not None and gm >= 40:
            parts.append(f"该企业具备高毛利特征（{gm:.1f}%），企业质量评定为「{ent}」，护城河评定为「{moat}」。")
        elif gm is not None and gm >= 25:
            parts.append(f"该企业毛利率中等（{gm:.1f}%），企业质量评定为「{ent}」，护城河评定为「{moat}」。")
        else:
            gm_text = f"（{gm:.1f}%）" if gm is not None else ""
            parts.append(f"该企业毛利率偏低{gm_text}，企业质量评定为「{ent}」，护城河评定为「{moat}」。")

    safety = decision_summary.get("safety_label", "")
    valuation = decision_summary.get("valuation_label", "")
    parts.append(f"财务安全评定为「{safety}」，估值评定为「{valuation}」。")

    action = decision_summary.get("action", "")
    if action:
        parts.append(action)

    return "".join(parts)


# ── 数据质量 / 置信度诊断 ──────────────────────────────────

def build_data_quality_report(
    rows: Sequence[Dict],
    valuation_metrics: Sequence,
    valuation_details: Dict[str, object],
    diagnostics: Dict[str, object],
    industry_text: str,
    is_bank: bool = False,
) -> Dict[str, object]:
    """Produce a data-quality / confidence diagnostic dict.

    Dimensions checked:
    1. Year coverage
    2. Key field completeness across year rows
    3. Industry adaptation (specific match vs default fallback)
    4. Valuation model availability
    5. Price / shares availability
    6. Aggregate confidence level
    """

    warnings: list = []

    # ── 1. Year coverage ──
    n_years = len(rows)
    year_range = f"{rows[0]['year']}–{rows[-1]['year']}" if rows else "无数据"
    if n_years == 0:
        warnings.append("年度数据为空，所有指标均无法计算。")
    elif n_years < 3:
        warnings.append(f"仅有 {n_years} 年数据，趋势评估置信度偏低。")
    elif n_years < 5:
        warnings.append(f"仅有 {n_years} 年数据（建议 ≥5 年）。")

    # ── 2. Key field completeness ──
    if is_bank:
        key_fields = [
            ("net_income", "净利润"),
            ("revenue", "营业收入"),
        ]
    else:
        key_fields = [
            ("revenue", "营业收入"),
            ("net_income", "净利润"),
            ("gross_margin", "毛利率"),
            ("ocf", "经营现金流"),
            ("capex", "资本支出"),
        ]

    field_stats: list = []
    for field_key, field_label in key_fields:
        present = sum(1 for r in rows if r.get(field_key) is not None)
        pct = (present / n_years * 100) if n_years else 0.0
        field_stats.append({
            "field": field_label,
            "present": present,
            "total": n_years,
            "pct": pct,
        })
        if n_years and pct < 60:
            warnings.append(f"「{field_label}」仅有 {present}/{n_years} 年有值（{pct:.0f}%），可能影响评估准确性。")

    # ── 3. Industry adaptation ──
    discount_key = valuation_details.get("discount_rate_key", "")
    exit_pe_key = valuation_details.get("exit_pe_key", "")
    industry_matched = bool(discount_key) and discount_key != "默认"
    if not industry_matched:
        warnings.append("行业未精确匹配，折现率与退出PE使用默认值（可能高估或低估内在价值）。")

    # ── 4. Valuation model availability ──
    model_results: list = []
    for vm in (valuation_metrics or []):
        label = getattr(vm, "label", str(vm))
        tone = getattr(vm, "tone", "")
        status = getattr(vm, "status_text", "")
        available = tone not in ("muted",)
        model_results.append({
            "label": label,
            "available": available,
            "status": status,
        })
    n_models = len(model_results)
    n_available = sum(1 for m in model_results if m["available"])
    if n_models and n_available == 0:
        warnings.append("所有估值模型均不可用，估值结论缺乏定量支撑。")
    elif n_models and n_available <= 2:
        warnings.append(f"仅 {n_available}/{n_models} 个估值模型可用，共振判断可能不充分。")

    # ── 5. Price / shares availability ──
    price = safe_float(diagnostics.get("price"))
    shares = safe_float(diagnostics.get("shares"))
    share_basis = analyze_share_basis_coverage(
        diagnostics.get("year_data") or {},
        diagnostics.get("annual_cols") or [],
    )
    if price is None:
        warnings.append("当前股价缺失，每股估值与盈利率无法计算。")
    if shares is None:
        warnings.append("总股本缺失，每股指标无法计算。")
    if share_basis.get("legacy_fallback_count"):
        fallback_years = "、".join(share_basis.get("legacy_fallback_years") or [])
        warnings.append(f"历史股本仍有 {share_basis['legacy_fallback_count']} 年回退到 legacy shares：{fallback_years}。")
    if share_basis.get("eps_derived_count"):
        eps_years = "、".join(share_basis.get("eps_derived_years") or [])
        warnings.append(f"历史股本有 {share_basis['eps_derived_count']} 年使用归母净利润/EPS推导的隐含股本：{eps_years}。")
    reported_other_count = int(share_basis.get("reported_fallback_count") or 0) - int(share_basis.get("eps_derived_count") or 0)
    if reported_other_count > 0:
        reported_years = [
            year
            for year in (share_basis.get("reported_fallback_years") or [])
            if year not in set(share_basis.get("eps_derived_years") or [])
        ]
        warnings.append(f"历史股本有 {reported_other_count} 年使用 reported_shares 回退：{'、'.join(reported_years)}。")
    if share_basis.get("missing_count"):
        missing_years = "、".join(share_basis.get("missing_years") or [])
        warnings.append(f"历史股本仍有 {share_basis['missing_count']} 年缺少 valuation_shares 与 legacy shares：{missing_years}。")
    if share_basis.get("split_like_jump_count"):
        spans = "、".join(share_basis.get("split_like_jumps") or [])
        warnings.append(f"检测到 {share_basis['split_like_jump_count']} 处拆股驱动的 as-of 每股阶跃：{spans}。")
    if share_basis.get("mixed_basis_jump_count"):
        spans = "、".join(share_basis.get("mixed_basis_jumps") or [])
        warnings.append(f"检测到 {share_basis['mixed_basis_jump_count']} 处疑似混口径股本跳变：{spans}。")

    # ── 6. Aggregate confidence ──
    score = 0
    # year coverage: 0-3
    if n_years >= 5:
        score += 3
    elif n_years >= 3:
        score += 2
    elif n_years >= 1:
        score += 1
    # field completeness: 0-3
    avg_pct = (sum(f["pct"] for f in field_stats) / len(field_stats)) if field_stats else 0
    if avg_pct >= 90:
        score += 3
    elif avg_pct >= 70:
        score += 2
    elif avg_pct >= 40:
        score += 1
    # industry: 0-1
    if industry_matched:
        score += 1
    # models: 0-2
    if n_available >= 4:
        score += 2
    elif n_available >= 2:
        score += 1
    # price + shares: 0-1
    if price is not None and shares is not None:
        score += 1
    # total max = 10
    if score >= 8:
        confidence = "高"
    elif score >= 5:
        confidence = "中"
    else:
        confidence = "低"

    return {
        "n_years": n_years,
        "year_range": year_range,
        "field_stats": field_stats,
        "industry_matched": industry_matched,
        "discount_key": discount_key or "默认",
        "exit_pe_key": exit_pe_key or "默认",
        "model_results": model_results,
        "n_models_available": n_available,
        "n_models_total": n_models,
        "has_price": price is not None,
        "has_shares": shares is not None,
        "share_basis": share_basis,
        "confidence": confidence,
        "confidence_score": score,
        "warnings": warnings,
    }


def build_dollar_retention_test(
    year_data: dict,
    all_annual_cols_sorted: list,
    valuation_shares: Optional[float],
    oe_yield_history: List[Dict],
    rd_cap_ratio: float = 0.0,
    maint_capex_ratio: float = MAINT_CAPEX_FLOOR_RATIO,
    window_years: int = 10,
) -> Optional[Dict]:
    """巴菲特「一美元留存检验」。

    在最近 window_years 个完整财年内，计算：
      - 每年 OE（三口径基准）、净利润、现金股息、回购
      - 期初 / 期末市值（使用 oe_yield_history 中年末 MA200 价格 × 统一股本）
      - 比率 = 市值增值 / (净利润合计 - 股息合计)  ≥1 则通过

    返回 dict，键：
      window_start, window_end,
      rows (List[dict]): 逐年明细
      total_ni, total_oe, total_div, total_buyback,
      mcap_start, mcap_end, mva,
      retained_strict, ratio_strict,
      retained_oe, ratio_oe,
      real_retained,
      passed_strict (bool)
    若数据不足则返回 None。
    """
    if not year_data or not all_annual_cols_sorted or not valuation_shares or valuation_shares <= 0:
        return None

    # ── 选取最近 window_years 个财年 ──────────────────────────
    cols_all = sorted(all_annual_cols_sorted)
    cols_window = cols_all[-(window_years):]
    if len(cols_window) < 3:
        return None

    # 用 oe_yield_history 建立 year→MA200 映射（用于市值估算）
    price_map: Dict[str, float] = {
        str(r["year"]): float(r["ma200_price"])
        for r in (oe_yield_history or [])
        if r.get("ma200_price") and r.get("year")
    }

    rows_out: List[Dict] = []
    for col in cols_window:
        dc = year_data.get(col)
        if dc is None:
            continue
        year_str = str(col)[:4]

        ni = safe_float(dc.get("profit"))           # 单位：亿元
        da_v = safe_float(dc.get("da"))             # 亿元
        capex_v = safe_float(dc.get("capex"))       # 亿元
        div_v = safe_float(dc.get("dividends_paid"))  # 亿元，公司级
        buyback_v = safe_float(dc.get("buyback_cash"))  # 亿元

        if ni is None:
            continue

        # OE 基准口径
        oe_triple = _owner_earnings_three_caliber(dc, rd_cap_ratio, maint_capex_ratio)
        oe_base = oe_triple[1] if oe_triple is not None else ni  # fallback to NI

        rows_out.append({
            "year": year_str,
            "ni": ni,
            "oe": oe_base,
            "div": div_v or 0.0,
            "buyback": buyback_v or 0.0,
            "price_ma200": price_map.get(year_str),
        })

    if len(rows_out) < 3:
        return None

    # ── 期初 / 期末市值（年末 MA200 × 统一股本） ──────────────
    # 期初 = 第一个财年年末的 MA200（期"前一年"更好，但用第一年近似）
    start_year = rows_out[0]["year"]
    end_year = rows_out[-1]["year"]

    # 尝试使用 window 起点前一年的 MA200 作为期初价格
    idx_first_col = cols_all.index(cols_window[0]) if cols_window[0] in cols_all else -1
    pre_col = cols_all[idx_first_col - 1] if idx_first_col > 0 else None
    pre_year = str(pre_col)[:4] if pre_col else None
    price_start = price_map.get(pre_year or "") or price_map.get(start_year)
    price_end = price_map.get(end_year)

    if price_start is None or price_end is None:
        return None

    shares_yi = valuation_shares  # 单位：亿股
    mcap_start = price_start * shares_yi     # 亿元
    mcap_end = price_end * shares_yi         # 亿元
    mva = mcap_end - mcap_start

    total_ni = sum(r["ni"] for r in rows_out)
    total_oe = sum(r["oe"] for r in rows_out)
    total_div = sum(r["div"] for r in rows_out)
    total_buyback = sum(r["buyback"] for r in rows_out)

    retained_strict = total_ni - total_div
    retained_oe = total_oe - total_div
    real_retained = total_oe - total_div - total_buyback

    ratio_strict = mva / retained_strict if retained_strict > 0 else None
    ratio_oe = mva / retained_oe if retained_oe > 0 else None
    passed_strict = ratio_strict is not None and ratio_strict >= 1.0

    # 真实留存为负时加注释
    real_retained_note = ""
    if real_retained < 0:
        real_retained_note = "（向股东返还资本超过所产生的OE，部分靠举债支撑）"

    return {
        "window_start": start_year,
        "window_end": end_year,
        "pre_year_price": pre_year,
        "rows": rows_out,
        "total_ni": total_ni,
        "total_oe": total_oe,
        "total_div": total_div,
        "total_buyback": total_buyback,
        "mcap_start": mcap_start,
        "mcap_end": mcap_end,
        "mva": mva,
        "retained_strict": retained_strict,
        "ratio_strict": ratio_strict,
        "retained_oe": retained_oe,
        "ratio_oe": ratio_oe,
        "real_retained": real_retained,
        "real_retained_note": real_retained_note,
        "passed_strict": passed_strict,
        "shares_yi": shares_yi,
        "price_start": price_start,
        "price_end": price_end,
    }
