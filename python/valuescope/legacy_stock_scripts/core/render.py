# core/render.py — auto-extracted
from __future__ import annotations

import html
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from valuescope.legacy_stock_scripts.core.config import (
    REPORTS_DIR, OUTPUT_DIR, DISCOUNT_RATE, TERMINAL_GROWTH, DEFAULT_EXIT_PE,
    PROJECTION_YEARS, MARGIN_OF_SAFETY, LAST_PROFILE,
    MetricAssessment, ValuationAssessment, _dp,
)
from valuescope.legacy_stock_scripts.core.assessment import (
    _rate, _rate_roa, _rate_roe_roic_gap, _rate_icr, _rate_roic,
    _rate_ocf_ratio, _rate_goodwill, _rate_tax, _rate_pledge, _rate_payout,
    _rate_total_yield, _rate_eps_quality, _rate_roe_render, _rate_unlock,
    _rate_valuation_gap, _rate_real_eps,
    assess_gross_margin, assess_gm_delta, assess_purity, assess_dso,
    assess_dpo, assess_ccc, assess_roiic, assess_capex_ratio,
    assess_revenue_growth, assess_opex_trend, assess_asset_turnover,
    assess_roe_ses,
    build_quality_cards, build_quality_module_notes,
    build_quality_year_snapshots, summarize_business_quality,
    _assess_nim, _assess_cost_income, _assess_provision_loan,
    _assess_loan_deposit, _assess_roa,
    _assess_nco_ratio, _assess_ppop_avg_assets, _assess_provision_nco_cover,
    _assess_ppnr_avg_assets, _assess_rotce, _assess_deposit_cost,
    _build_bank_profitability_rows, _build_bank_credit_quality_rows,
    _build_bank_franchise_rows,
    build_bank_stress_test,
    _build_feature_sketch,
    _share_growth_tone,
    analyze_share_basis_coverage,
)
from valuescope.legacy_stock_scripts.core.valuation import (
    roic_percent_from_year_data, interest_coverage_ratio_tag_value,
)
from valuescope.legacy_stock_scripts.core.technicals import (
    _render_wr_section, _render_market_env_section,
)
from valuescope.legacy_stock_scripts.core.utils import (
    get_metric, safe_float, fmt_pct, fmt_num, fmt_yi,
    series_values, trend_text, _trend_arrow,
    tone_class, wrap_value,
    fmt_days, fmt_ratio, fmt_shares, get_real_eps, _equity_denom,
)


def tone_class(tone: str) -> str:
    return {
        "good": "tone-good",
        "warn": "tone-warn",
        "bad": "tone-bad",
        "muted": "tone-muted",
    }.get(tone, "tone-muted")

def wrap_value(text: str, tone: str) -> str:
    return f'<span class="value-chip {tone_class(tone)}">{html.escape(text)}</span>'

def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head_html = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body_html = []
    for row in rows:
        body_html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{''.join(body_html)}</tbody></table>"

def render_key_value_table(caption: str, section_key: str, rows: Sequence[Tuple[str, str]]) -> str:
  head = (
    "<thead><tr>"
    "<th scope='col'>Key</th>"
    "<th scope='col'>Value</th>"
    "</tr></thead>"
  )
  body = "".join(
    "<tr>"
    f"<th scope='row'>{html.escape(str(k))}</th>"
    f"<td>{html.escape(str(v))}</td>"
    "</tr>"
    for k, v in rows
  )
  return (
    f"<table data-ai-section='{html.escape(section_key)}'>"
    f"<caption>{html.escape(caption)}</caption>"
    f"{head}<tbody>{body}</tbody></table>"
  )

def render_assessment_summary_table(caption: str, section_key: str, assessments: Sequence[object]) -> str:
  head = (
    "<thead><tr>"
    "<th scope='col'>Key</th>"
    "<th scope='col'>Label</th>"
    "<th scope='col'>Value</th>"
    "<th scope='col'>Rule</th>"
    "<th scope='col'>Status</th>"
    "<th scope='col'>Tone</th>"
    "<th scope='col'>Meaning</th>"
    "<th scope='col'>Implication</th>"
    "<th scope='col'>Formula</th>"
    "</tr></thead>"
  )
  body_rows: List[str] = []
  for idx, m in enumerate(assessments, start=1):
    label = html.escape(str(getattr(m, "label", "")))
    value_display = html.escape(str(getattr(m, "value_display", "")))
    rule_display = html.escape(str(getattr(m, "rule_display", "")))
    status_text = html.escape(str(getattr(m, "status_text", "")))
    tone = html.escape(str(getattr(m, "tone", "")))
    meaning = html.escape(str(getattr(m, "meaning", "")))
    implication = html.escape(str(getattr(m, "implication", "")))
    formula = html.escape(str(getattr(m, "formula", "")))
    body_rows.append(
      "<tr>"
      f"<th scope='row'>valuation_metric_{idx}</th>"
      f"<td>{label}</td>"
      f"<td>{value_display}</td>"
      f"<td>{rule_display}</td>"
      f"<td>{status_text}</td>"
      f"<td>{tone}</td>"
      f"<td>{meaning}</td>"
      f"<td>{implication}</td>"
      f"<td>{formula}</td>"
      "</tr>"
    )
  return (
    f"<table data-ai-section='{html.escape(section_key)}'>"
    f"<caption>{html.escape(caption)}</caption>"
    f"{head}<tbody>{''.join(body_rows)}</tbody></table>"
  )

def render_valuation_anchor_table(rows: Sequence[Sequence[tuple]]) -> str:
    """非银行年度估值锚点表：双层表头 + 分组 + 背景色。rows: list of list of (html, bg_or_None)。"""
    _grp_th = "padding:8px 10px;border-bottom:2px solid #bbb;text-align:center;font-size:13px;font-weight:700;letter-spacing:0.04em;"
    _sub_th = "padding:8px 8px;border-bottom:1px solid #ddd;text-align:center;font-size:12px;font-weight:600;color:#555;white-space:nowrap;"
    _sep = "border-left:2px solid #d0d0d0;"
    head = (
        f"<tr>"
        f"<th colspan='2' style='{_grp_th}background:#f8f6f0;'>基础</th>"
        f"<th colspan='6' style='{_grp_th}background:#f0f4f8;{_sep}'>估值参数</th>"
        f"<th colspan='4' style='{_grp_th}background:#eef9f1;{_sep}'>OE-DCF 估值区间</th>"
        f"<th colspan='4' style='{_grp_th}background:#f0f0ff;{_sep}'>芒格远景估值区间</th>"
        f"<th style='{_grp_th}background:#f8f6f0;{_sep}'>其他</th>"
        f"</tr>"
        f"<tr>"
        f"<th style='{_sub_th}'>年份</th><th style='{_sub_th}'>当前股价</th>"
        f"<th style='{_sub_th}{_sep}'>OE/股</th><th style='{_sub_th}'>G</th>"
        f"<th style='{_sub_th}'>利润CAGR</th><th style='{_sub_th}'>股息率</th>"
        f"<th style='{_sub_th}'>PEG</th><th style='{_sub_th}'>PEGY</th>"
        f"<th style='{_sub_th}{_sep}'>保守</th><th style='{_sub_th}'>基准</th>"
        f"<th style='{_sub_th}'>宽松</th><th style='{_sub_th}'>现价较基准</th>"
        f"<th style='{_sub_th}{_sep}'>保守</th><th style='{_sub_th}'>基准</th>"
        f"<th style='{_sub_th}'>宽松</th><th style='{_sub_th}'>现价较基准</th>"
        f"<th style='{_sub_th}{_sep}'>派息率</th>"
        f"</tr>"
    )
    _sep_cols = {2, 8, 12, 16}  # columns that start a new group
    body = []
    for ri, row in enumerate(rows):
        stripe = "#fdfcf9" if ri % 2 == 0 else "#ffffff"
        cells = []
        for ci, (content, bg) in enumerate(row):
            sep = _sep if ci in _sep_cols else ""
            bg_color = bg or stripe
            cells.append(f"<td style='padding:8px 8px;{sep}background:{bg_color};'>{content}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table style='width:100%;border-collapse:collapse;font-size:13px;'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def render_pe_percentile_section(pe_history: Optional[Dict[str, object]]) -> str:
    if not pe_history:
        return ""
    points = pe_history.get("points") or []
    current_pe = safe_float(pe_history.get("current_pe"))
    percentile = safe_float(pe_history.get("percentile"))
    hist_median = safe_float(pe_history.get("hist_median"))
    hist_min = safe_float(pe_history.get("hist_min"))
    hist_max = safe_float(pe_history.get("hist_max"))
    sample_count = int(pe_history.get("sample_count") or 0)
    current_vs_median_pct = safe_float(pe_history.get("current_vs_median_pct"))
    note = str(pe_history.get("note") or "")
    if not points or current_pe is None or sample_count < 3:
      reasons = []
      if current_pe is None:
        reasons.append("当前 PE 不可用")
      if not points:
        reasons.append("历史锚点为空")
      if sample_count < 3:
        reasons.append(f"有效样本仅 {sample_count} 个")
      detail = "；".join(reasons) if reasons else "样本不足"
      note_text = note or "历史 PE 样本暂不可用。"
      return f'''
    <section class="section">
      <h2>PE 近十年历史分位</h2>
      <p class="section-intro">这里按“次年 5 月可见口径”回看历史 PE 水位；如果当前 EPS 或历史样本不足，就明确提示原因，不再静默隐藏模块。</p>
      <div class="module-note">暂未展示图表：{html.escape(detail)}。{html.escape(note_text)}</div>
    </section>
  '''

    hist_points = []
    for point in points:
        real_pe = safe_float(point.get("real_pe"))
        if real_pe is None or real_pe <= 0:
            continue
        hist_points.append((str(point.get("fiscal_year") or ""), real_pe))
    if len(hist_points) < 3:
        return ""

    all_vals = [v for _, v in hist_points] + [current_pe]
    y_min = min(all_vals)
    y_max = max(all_vals)
    y_pad = max((y_max - y_min) * 0.12, 1.0)
    chart_min = max(0.0, y_min - y_pad)
    chart_max = y_max + y_pad
    chart_range = chart_max - chart_min if chart_max > chart_min else 1.0

    w, h = 720, 220
    pad_l, pad_r, pad_t, pad_b = 48, 18, 18, 40
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    def sx(i: int, total: int) -> float:
        return pad_l + (i / max(1, total - 1)) * plot_w

    def sy(v: float) -> float:
        return pad_t + (1 - (v - chart_min) / chart_range) * plot_h

    total_pts = len(hist_points)
    poly_points = " ".join(
        f"{sx(i, total_pts):.1f},{sy(v):.1f}"
        for i, (_, v) in enumerate(hist_points)
    )

    x_labels = []
    for i, (year_label, _) in enumerate(hist_points):
        x_labels.append(
            f'<text x="{sx(i, total_pts):.1f}" y="{h - 10}" text-anchor="middle" font-size="10" fill="#7f8c8d">{html.escape(year_label)}</text>'
        )

    y_grid = []
    for idx in range(5):
        v = chart_min + chart_range * idx / 4
        y = sy(v)
        y_grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#edf1f4" stroke-width="1"/>')
        y_grid.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#7f8c8d">{v:.1f}x</text>')

    median_line = ""
    if hist_median is not None:
        median_y = sy(hist_median)
        median_line = (
            f'<line x1="{pad_l}" y1="{median_y:.1f}" x2="{w - pad_r}" y2="{median_y:.1f}" '
            f'stroke="#c67c1a" stroke-width="1.2" stroke-dasharray="5,4"/>'
            f'<text x="{w - pad_r}" y="{median_y - 6:.1f}" text-anchor="end" font-size="10" fill="#c67c1a">中位数 {hist_median:.1f}x</text>'
        )

    current_y = sy(current_pe)
    current_line = (
        f'<line x1="{pad_l}" y1="{current_y:.1f}" x2="{w - pad_r}" y2="{current_y:.1f}" '
        f'stroke="#b42318" stroke-width="1.2" stroke-dasharray="4,3"/>'
        f'<text x="{w - pad_r}" y="{current_y - 6:.1f}" text-anchor="end" font-size="10" fill="#b42318">当前 {current_pe:.1f}x</text>'
    )

    circles = []
    for i, (_, v) in enumerate(hist_points):
        circles.append(f'<circle cx="{sx(i, total_pts):.1f}" cy="{sy(v):.1f}" r="3" fill="#1f6feb" stroke="#fff" stroke-width="1"/>')

    percentile_color = "#1d6b3d" if percentile is not None and percentile <= 30 else "#8a5a00" if percentile is not None and percentile <= 70 else "#a12626"
    percentile_text = f"{percentile:.1f}%" if percentile is not None else "N/A"
    vs_median_text = fmt_pct(current_vs_median_pct) if current_vs_median_pct is not None else "N/A"
    vs_median_color = "#1d6b3d" if current_vs_median_pct is not None and current_vs_median_pct <= -15 else "#8a5a00" if current_vs_median_pct is not None and current_vs_median_pct < 10 else "#a12626"

    cards = [
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">当前PE</div>
      <div style="font-size:24px;font-weight:700;color:var(--ink);">{current_pe:.1f}x</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">最新估值口径</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">近十年分位</div>
      <div style="font-size:24px;font-weight:700;color:{percentile_color};">{percentile_text}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">越低通常越便宜</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">历史区间</div>
      <div style="font-size:24px;font-weight:700;color:var(--ink);">{hist_min:.1f}x ~ {hist_max:.1f}x</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">样本 {sample_count} 年</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">相对中位数</div>
      <div style="font-size:24px;font-weight:700;color:{vs_median_color};">{vs_median_text}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">当前 vs 历史中位PE</div>
    </div>''',
    ]

    return f'''
    <section class="section">
      <h2>PE 近十年历史分位</h2>
      <p class="section-intro">这一段用近十个财年“年报发布后可见”的 PE 锚点来观察估值水位，避免把未来尚未披露的盈利提前带入历史。当前 PE 越靠近历史低分位，统计上通常越便宜；越靠近高分位，说明市场给出的盈利定价越高。</p>
      <div style="display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 16px;">{''.join(cards)}</div>
      <div style="margin:12px 0;overflow-x:auto;">
        <svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;background:var(--bg-secondary);border:1px solid var(--panel-border);border-radius:10px;">
          {''.join(y_grid)}
          {median_line}
          {current_line}
          <polyline points="{poly_points}" fill="none" stroke="#1f6feb" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
          {''.join(circles)}
          {''.join(x_labels)}
        </svg>
      </div>
      <div class="module-note" style="margin-top:10px;font-size:13px;line-height:1.7;">{html.escape(note)}</div>
    </section>'''

def render_eps_percentile_section(eps_history: Optional[Dict[str, object]]) -> str:
    if not eps_history:
        return ""
    points = eps_history.get("points") or []
    current_eps = safe_float(eps_history.get("current_value"))
    percentile = safe_float(eps_history.get("percentile"))
    hist_median = safe_float(eps_history.get("hist_median"))
    hist_min = safe_float(eps_history.get("hist_min"))
    hist_max = safe_float(eps_history.get("hist_max"))
    sample_count = int(eps_history.get("sample_count") or 0)
    current_vs_median_pct = safe_float(eps_history.get("current_vs_median_pct"))
    current_year = str(eps_history.get("current_fiscal_year") or "当前")
    current_src = str(eps_history.get("current_value_src") or "EPS")
    note = str(eps_history.get("note") or "")
    if not points or current_eps is None or sample_count < 3:
      reasons = []
      if current_eps is None:
        reasons.append("当前 E 不可用")
      if not points:
        reasons.append("历史锚点为空")
      if sample_count < 3:
        reasons.append(f"有效样本仅 {sample_count} 个")
      detail = "；".join(reasons) if reasons else "样本不足"
      note_text = note or "历史 E 样本暂不可用。"
      return f'''
    <section class="section">
      <h2>E（EPS）近十年历史分位</h2>
      <p class="section-intro">这一段单独看 PE 里的分母 E。若当前 E 落在历史高分位，低 PE 可能只是利润正处在高景气区间；若当前 E 仍在中低分位，而 PE 又很低，低估的可信度通常更高。</p>
      <div class="module-note">暂未展示图表：{html.escape(detail)}。{html.escape(note_text)}</div>
    </section>
  '''

    hist_points = []
    for point in points:
        eps_value = safe_float(point.get("value"))
        if eps_value is None:
            continue
        hist_points.append((str(point.get("fiscal_year") or ""), eps_value))
    if len(hist_points) < 3:
        return ""

    all_vals = [v for _, v in hist_points] + [current_eps]
    y_min = min(all_vals)
    y_max = max(all_vals)
    y_pad = max((y_max - y_min) * 0.12, 0.2)
    chart_min = y_min - y_pad
    chart_max = y_max + y_pad
    chart_range = chart_max - chart_min if chart_max > chart_min else 1.0

    w, h = 720, 220
    pad_l, pad_r, pad_t, pad_b = 48, 18, 18, 40
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    def sx(i: int, total: int) -> float:
        return pad_l + (i / max(1, total - 1)) * plot_w

    def sy(v: float) -> float:
        return pad_t + (1 - (v - chart_min) / chart_range) * plot_h

    total_pts = len(hist_points)
    poly_points = " ".join(
        f"{sx(i, total_pts):.1f},{sy(v):.1f}"
        for i, (_, v) in enumerate(hist_points)
    )

    x_labels = []
    for i, (year_label, _) in enumerate(hist_points):
        x_labels.append(
            f'<text x="{sx(i, total_pts):.1f}" y="{h - 10}" text-anchor="middle" font-size="10" fill="#7f8c8d">{html.escape(year_label)}</text>'
        )

    y_grid = []
    for idx in range(5):
        v = chart_min + chart_range * idx / 4
        y = sy(v)
        y_grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#edf1f4" stroke-width="1"/>')
        y_grid.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#7f8c8d">{v:.2f}</text>')

    median_line = ""
    if hist_median is not None:
        median_y = sy(hist_median)
        median_line = (
            f'<line x1="{pad_l}" y1="{median_y:.1f}" x2="{w - pad_r}" y2="{median_y:.1f}" '
            f'stroke="#c67c1a" stroke-width="1.2" stroke-dasharray="5,4"/>'
            f'<text x="{w - pad_r}" y="{median_y - 6:.1f}" text-anchor="end" font-size="10" fill="#c67c1a">中位数 {hist_median:.2f}</text>'
        )

    current_y = sy(current_eps)
    current_line = (
        f'<line x1="{pad_l}" y1="{current_y:.1f}" x2="{w - pad_r}" y2="{current_y:.1f}" '
        f'stroke="#b42318" stroke-width="1.2" stroke-dasharray="4,3"/>'
        f'<text x="{w - pad_r}" y="{current_y - 6:.1f}" text-anchor="end" font-size="10" fill="#b42318">当前 {current_year} E {current_eps:.2f}</text>'
    )

    circles = []
    for i, (_, v) in enumerate(hist_points):
        circles.append(f'<circle cx="{sx(i, total_pts):.1f}" cy="{sy(v):.1f}" r="3" fill="#0f766e" stroke="#fff" stroke-width="1"/>')

    percentile_color = "#1d6b3d" if percentile is not None and percentile <= 30 else "#8a5a00" if percentile is not None and percentile <= 70 else "#a12626"
    percentile_text = f"{percentile:.1f}%" if percentile is not None else "N/A"
    vs_median_text = fmt_pct(current_vs_median_pct) if current_vs_median_pct is not None else "N/A"
    vs_median_color = "#1d6b3d" if current_vs_median_pct is not None and current_vs_median_pct <= 0 else "#8a5a00" if current_vs_median_pct is not None and current_vs_median_pct <= 30 else "#a12626"

    cards = [
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">当前E</div>
      <div style="font-size:24px;font-weight:700;color:var(--ink);">{current_eps:.2f}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">{html.escape(current_src)}</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">近十年分位</div>
      <div style="font-size:24px;font-weight:700;color:{percentile_color};">{percentile_text}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">越高越要防利润高点</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">历史区间</div>
      <div style="font-size:24px;font-weight:700;color:var(--ink);">{hist_min:.2f} ~ {hist_max:.2f}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">样本 {sample_count} 年</div>
    </div>''',
        f'''<div style="flex:1;min-width:140px;padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
      <div style="font-size:12px;color:var(--ink-secondary);">相对中位E</div>
      <div style="font-size:24px;font-weight:700;color:{vs_median_color};">{vs_median_text}</div>
      <div style="font-size:11px;color:var(--ink-tertiary);">高于中位数越多越要谨慎</div>
    </div>''',
    ]

    return f'''
    <section class="section">
      <h2>E（EPS）近十年历史分位</h2>
      <p class="section-intro">这里把 PE 的分母单独拆开看。当前 E 如果已经站在历史高分位，低 PE 可能只是因为利润被周期、景气或一次性高点抬得很高；如果当前 E 仍在中低分位，而 PE 已经偏低，低估信号通常更扎实。</p>
      <div style="display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 16px;">{''.join(cards)}</div>
      <div style="margin:12px 0;overflow-x:auto;">
        <svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;background:var(--bg-secondary);border:1px solid var(--panel-border);border-radius:10px;">
          {''.join(y_grid)}
          {median_line}
          {current_line}
          <polyline points="{poly_points}" fill="none" stroke="#0f766e" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
          {''.join(circles)}
          {''.join(x_labels)}
        </svg>
      </div>
      <div class="module-note" style="margin-top:10px;font-size:13px;line-height:1.7;">{html.escape(note)}</div>
    </section>'''

def _render_compact_percentile_block(
    title: str,
    payload: Optional[Dict[str, object]],
    unit: str,
    cheaper_when_higher: bool = False,
) -> str:
    payload = payload or {}
    points = payload.get("points") or []
    current_value = safe_float(payload.get("current_value"))
    percentile = safe_float(payload.get("percentile"))
    hist_min = safe_float(payload.get("hist_min"))
    hist_median = safe_float(payload.get("hist_median"))
    hist_max = safe_float(payload.get("hist_max"))
    current_vs_median_pct = safe_float(payload.get("current_vs_median_pct"))
    sample_count = int(payload.get("sample_count") or 0)
    note = str(payload.get("note") or "")

    if cheaper_when_higher:
        pct_tone = "good" if percentile is not None and percentile >= 70 else "warn" if percentile is not None and percentile >= 40 else "bad"
        rel_tone = "good" if current_vs_median_pct is not None and current_vs_median_pct >= 15 else "warn" if current_vs_median_pct is not None and current_vs_median_pct >= 0 else "bad"
        hint = "分位越高通常越便宜"
    else:
        pct_tone = "good" if percentile is not None and percentile <= 30 else "warn" if percentile is not None and percentile <= 70 else "bad"
        rel_tone = "good" if current_vs_median_pct is not None and current_vs_median_pct <= -15 else "warn" if current_vs_median_pct is not None and current_vs_median_pct < 10 else "bad"
        hint = "分位越低通常越便宜"

    if not points or current_value is None or sample_count < 3:
        return f'''
        <div style="flex:1 1 320px;border:1px solid var(--panel-border);border-radius:12px;padding:14px;background:var(--panel);">
          <h3 style="margin:0 0 8px;">{html.escape(title)}</h3>
          <div class="module-note">暂未形成有效历史分位：{html.escape(note or '样本不足。')}</div>
        </div>
        '''

    rows = []
    valid_points = [p for p in points if safe_float(p.get("value")) is not None]
    for point in valid_points[-5:]:
        value = safe_float(point.get("value"))
        if value is None:
            continue
        rows.append([
            html.escape(str(point.get("fiscal_year") or "")),
            html.escape(str(point.get("anchor_date") or "")),
            wrap_value(f"{value:.2f}{unit}", "good" if cheaper_when_higher else "warn"),
        ])

    return f'''
    <div style="flex:1 1 320px;border:1px solid var(--panel-border);border-radius:12px;padding:14px;background:var(--panel);">
      <h3 style="margin:0 0 8px;">{html.escape(title)}</h3>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:12px;">
        <div style="padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
          <div style="font-size:12px;color:var(--ink-secondary);">当前值</div>
          <div style="font-size:22px;font-weight:700;color:var(--ink);">{current_value:.2f}{html.escape(unit)}</div>
        </div>
        <div style="padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
          <div style="font-size:12px;color:var(--ink-secondary);">历史分位</div>
          <div style="font-size:22px;font-weight:700;">{wrap_value(f'{percentile:.1f}%' if percentile is not None else 'N/A', pct_tone)}</div>
        </div>
        <div style="padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
          <div style="font-size:12px;color:var(--ink-secondary);">历史区间</div>
          <div style="font-size:16px;font-weight:700;color:var(--ink);">{(f'{hist_min:.2f}{unit} ~ {hist_max:.2f}{unit}') if hist_min is not None and hist_max is not None else 'N/A'}</div>
        </div>
        <div style="padding:10px;background:var(--panel-raised);border-radius:8px;text-align:center;">
          <div style="font-size:12px;color:var(--ink-secondary);">相对中位数</div>
          <div style="font-size:22px;font-weight:700;">{wrap_value(fmt_pct(current_vs_median_pct) if current_vs_median_pct is not None else 'N/A', rel_tone)}</div>
        </div>
      </div>
      <div class="module-note" style="margin-bottom:10px;">{html.escape(hint)}；样本 {sample_count} 年。</div>
      <div class="table-wrap">{render_table(['年报锚点', '取价日', title], rows if rows else [['N/A', 'N/A', 'N/A']])}</div>
      <div class="module-note" style="margin-top:10px;">{html.escape(note)}</div>
    </div>
    '''

def render_bank_valuation_context_section(valuation_details: Dict[str, object]) -> str:
    pb_history = valuation_details.get("bank_pb_percentile_history") or {}
    dividend_history = valuation_details.get("bank_dividend_yield_percentile_history") or {}
    quality_filter = valuation_details.get("bank_quality_filter") or {}
    margin = valuation_details.get("bank_margin_of_safety") or {}
    checks = quality_filter.get("checks") or []

    check_cards = []
    for check in checks:
        value = safe_float(check.get("value"))
        label = str(check.get("label") or "")
        tone = str(check.get("tone") or "muted")
        if label in {"拨备覆盖率", "资本充足率", "资本缓冲率", "拨贷比", "ROA"}:
            display = fmt_pct(value) if value is not None else "N/A"
        else:
            display = fmt_num(value) if value is not None else "N/A"
        mode = "（代理）" if check.get("mode") == "proxy" else ""
        check_cards.append(
            f'''<div style="flex:1 1 180px;padding:12px;border:1px solid var(--panel-border);border-radius:10px;background:var(--panel);">
          <div style="font-size:12px;color:var(--ink-secondary);">{html.escape(label + mode)}</div>
          <div style="margin:8px 0 6px;">{wrap_value(display, tone)}</div>
          <div style="font-size:12px;color:var(--ink-secondary);line-height:1.5;">{html.escape(str(check.get('rule') or ''))}</div>
        </div>'''
        )

    reasons_html = "".join(f"<li>{html.escape(str(reason))}</li>" for reason in (margin.get("reasons") or []))
    summary_tone = str(margin.get("tone") or "muted")
    summary_status = str(margin.get("status") or "暂不存在安全边际")
    return f'''
    <section class="section">
      <h2>银行历史分位与安全边际</h2>
      <p class="section-intro">银行不看 PE 历史分位，改看 PB 所处位置、股息率所处位置，以及 ROA / 拨备 / 资本缓冲这三道质量过滤。只有价格便宜和质量过关同时成立，才更接近真正的安全边际。</p>
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch;">
        {_render_compact_percentile_block('PB历史分位', pb_history, 'x', cheaper_when_higher=False)}
        {_render_compact_percentile_block('股息率历史分位', dividend_history, '%', cheaper_when_higher=True)}
      </div>
      <h3 style="margin:18px 0 10px;">质量过滤</h3>
      <div style="display:flex;flex-wrap:wrap;gap:10px;">{''.join(check_cards) if check_cards else '<div class="module-note">暂无可用的银行质量过滤数据。</div>'}</div>
      <div class="module-note" style="margin-top:14px;border-left:4px solid #d0d5dd;">综合判断：{summary_status}</div>
      <ul style="margin-top:10px;">{reasons_html}</ul>
    </section>
    '''


def _render_share_basis_section(diagnostics: Optional[Dict], is_us: bool = False) -> str:
    """Render share basis source & confidence explanation."""
    if not diagnostics:
        return ""

    year_data = diagnostics.get("year_data", {})
    if not year_data:
        return ""

    share_basis = analyze_share_basis_coverage(
        year_data,
        diagnostics.get("annual_cols") or [],
    )
    share_basis_mode = diagnostics.get("share_basis_mode") if isinstance(diagnostics, dict) else None
    is_asof_mode = (share_basis_mode == "asof")
    raw_years = []
    adj_years = []
    for year_key in sorted(year_data.keys()):
        d = year_data[year_key]
        split_fc = safe_float(d.get("split_factor_cumulative", 1.0)) or 1.0
        if split_fc > 1.0:
            raw_years.append((year_key[:4], split_fc))
        elif split_fc == 1.0:
            adj_years.append(year_key[:4])

    market_text = "美股" if is_us else "A股"
    share_basis_conf = share_basis.get("confidence", "中")
    conf_colors = {
        "高": ("var(--good-bg)", "var(--good-fg)"),
        "中": ("var(--warn-bg)", "var(--warn-fg)"),
        "低": ("var(--bad-bg)", "var(--bad-fg)"),
    }
    conf_bg, conf_fg = conf_colors.get(share_basis_conf, ("var(--warn-bg)", "var(--warn-fg)"))
    coverage_text = f"{share_basis.get('valuation_count', 0)}/{share_basis.get('total_years', 0)}"
    fallback_years = share_basis.get("fallback_years") or []
    missing_years = share_basis.get("missing_years") or []
    split_like_jumps = share_basis.get("split_like_jumps") or []
    mixed_basis_jumps = share_basis.get("mixed_basis_jumps") or []
    mixed_semantics = bool(share_basis.get("mixed_semantics"))
    fallback_suffix = f"（{'、'.join(fallback_years)}）" if fallback_years else ""
    missing_suffix = f"（{'、'.join(missing_years)}）" if missing_years else ""
    if share_basis_conf == "高":
        confidence_text = "高。纳入报告的年度都已有 valuation_shares，不需要回退到 legacy shares。"
    elif share_basis_conf == "中":
        confidence_text = "中。大部分年度已使用 valuation_shares，但个别年份仍需回退，历史每股估值应结合 fallback 提示一起看。"
    else:
        confidence_text = "低。历史股本口径仍不完整，部分年份只能回退到 legacy shares 或缺失，历史每股曲线解释要更保守。"

    stats_items = [
        f"<li><strong>valuation_shares 覆盖</strong>：{coverage_text}</li>",
        f"<li><strong>fallback 年份</strong>：{share_basis.get('fallback_count', 0)}{fallback_suffix}</li>",
    ]
    if share_basis.get("missing_count"):
        stats_items.append(f"<li><strong>缺失年份</strong>：{share_basis.get('missing_count', 0)}{missing_suffix}</li>")
    if is_us:
        stats_items.append(f"<li><strong>split-adjusted 年份</strong>：{share_basis.get('split_adjusted_count', 0)}</li>")
    if split_like_jumps:
      stats_items.append(f"<li><strong>自动识别拆股阶跃</strong>：{len(split_like_jumps)} 处（{'、'.join(split_like_jumps)}）</li>")
    if mixed_basis_jumps:
      stats_items.append(f"<li><strong>疑似混口径跳变</strong>：{len(mixed_basis_jumps)} 处（{'、'.join(mixed_basis_jumps)}）</li>")
    if mixed_semantics:
      sems = "、".join(share_basis.get("reported_semantics") or [])
      stats_items.append(f"<li><strong>语义混用</strong>：同一序列出现 period_end 与 derived_from_eps（{sems}）</li>")

    if is_us and raw_years:
        basis_note = f"""
        <div class="explain-card">
          <h3>{market_text}：股本口径与拆股修正</h3>
          <p>{'本报告处于 as-of 回放模式：历史主估值优先采用 <strong>asof_shares</strong>。若 as-of 缺失，才回退到 valuation/reported/legacy shares，并降低置信度。' if is_asof_mode else '本报告默认以 <strong>valuation_shares</strong> 做历史主表重述；<strong>asof_shares</strong> 用于时点回放校验。若 valuation 缺失，才回退到 asof/reported/legacy shares，并降低置信度。'}</p>
          <p><strong>数据来源</strong>：东方财富数据库。东财对 {market_text} 股票的处理分两阶段：</p>
          <ul>
            <li><strong>原始年份</strong>（split_factor_cumulative &gt; 1.0，共 {len(raw_years)} 年）：东财尚未追溯调整EPS → 
              raw_shares × split_factor = 当前拆股口径的统一分母</li>
            <li><strong>已调整年份</strong>（split_factor_cumulative = 1.0，共 {len(adj_years)} 年）：东财已追溯调整EPS → 
              shares 本身已是当前拆股口径</li>
            {''.join(stats_items)}
          </ul>
          <p><span style="background:{conf_bg};color:{conf_fg};padding:3px 10px;border-radius:999px;font-weight:600;">股本置信度：{share_basis_conf}</span></p>
          <p><strong>说明</strong>：{confidence_text}</p>
        </div>"""
    else:
        basis_note = f"""
        <div class="explain-card">
          <h3>{market_text}：股本口径</h3>
          <p>{'本报告处于 as-of 回放模式：历史主估值优先采用 <strong>asof_shares</strong>。若 as-of 缺失，才会回退到 valuation/reported/legacy shares，并同步下调置信度。' if is_asof_mode else '本报告默认以 <strong>valuation_shares</strong> 做历史主表重述；<strong>asof_shares</strong> 用于时点回放校验。若 valuation 缺失，才会回退到 asof/reported/legacy shares，并同步下调置信度。'}</p>
          <p><strong>处理原则</strong>：</p>
          <ul>
            <li>优先使用 <strong>期末股本</strong>（报告期末的实际股份数）</li>
            <li>通过显式 <strong>送转/配股/回购</strong> 调整追踪真实经济稀释</li>
            <li>避免用 profit / eps 倒推股本（因EPS混合了加权平均、追溯调整等多种口径）</li>
            {''.join(stats_items)}
          </ul>
          <p><span style="background:{conf_bg};color:{conf_fg};padding:3px 10px;border-radius:999px;font-weight:600;">股本置信度：{share_basis_conf}</span></p>
          <p><strong>说明</strong>：{confidence_text}</p>
        </div>"""

    return f"""
    <section class="section">
      <h2>股本口径来源与置信度</h2>
      <p class="section-intro">
        本页解释"每股"估值（OE/股、合理股价、OE收益率等）中的 <strong>分母</strong> 来自哪里，以及其可信程度。
        历史每股估值的准确度直接依赖于历史股本序列的可比性。
      </p>
      <div class="explain-grid">
        {basis_note}
        <div class="explain-card">
          <h3>为什么这很重要</h3>
          <p>如果股本口径混乱（比如有年份用加权平均、有的用期末、有的混入了拆股倍数），会导致：</p>
          <ul>
            <li>历史每股价值曲线出现虚假断崖（拆股年份看起来突然"增长" 或 "下跌"）</li>
            <li>OE收益率历史出现 2-4 倍的虚假波动</li>
            <li>历史估值锚点无法相互印证</li>
          </ul>
          <p><strong>本报告的改进</strong>：历史时点估值主表优先采用 as-of 股本口径回答“当年值多少钱”；valuation_shares 只用于当前统一口径的可比展示与覆盖率说明。</p>
        </div>
      </div>
    </section>
    """


def _render_data_quality_section(dq: Optional[Dict]) -> str:
    """Render the data-quality / confidence diagnostic section."""
    if not dq:
        return ""

    confidence = dq.get("confidence", "中")
    conf_score = dq.get("confidence_score", 0)
    conf_colors = {"高": ("var(--good-bg)", "var(--good-fg)"),
                   "中": ("var(--warn-bg)", "var(--warn-fg)"),
                   "低": ("var(--bad-bg)", "var(--bad-fg)")}
    bg, fg = conf_colors.get(confidence, ("var(--warn-bg)", "var(--warn-fg)"))

    # year coverage
    n_years = dq.get("n_years", 0)
    year_range = html.escape(str(dq.get("year_range", "")))

    # field completeness mini-bars
    field_stats = dq.get("field_stats", [])
    field_html_parts = []
    for fs in field_stats:
        pct = fs["pct"]
        f_bg = "var(--good-fg)" if pct >= 80 else ("var(--warn-fg)" if pct >= 50 else "var(--bad-fg)")
        field_html_parts.append(
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
            f'<span style="width:80px;font-size:13px;">{html.escape(fs["field"])}</span>'
            f'<div style="flex:1;height:10px;background:#e9ecef;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{f_bg};border-radius:4px;"></div></div>'
            f'<span style="font-size:12px;color:#666;width:55px;text-align:right;">{fs["present"]}/{fs["total"]}</span></div>'
        )
    field_html = "".join(field_html_parts)

    # industry
    ind_matched = dq.get("industry_matched", False)
    dk = html.escape(str(dq.get("discount_key", "默认")))
    ek = html.escape(str(dq.get("exit_pe_key", "默认")))
    ind_icon = "✅" if ind_matched else "⚠️"
    ind_text = f"{ind_icon} 行业关键词：{dk}（折现率）/ {ek}（退出PE）"

    # model availability
    model_results = dq.get("model_results", [])
    model_parts = []
    for mr in model_results:
        icon = "🟢" if mr["available"] else "⚪"
        label = html.escape(str(mr["label"]))
        status = html.escape(str(mr["status"]))
        model_parts.append(f'<span style="font-size:13px;margin-right:12px;">{icon} {label}<span style="color:#888;font-size:12px;margin-left:3px;">({status})</span></span>')
    model_html = "".join(model_parts)
    n_avail = dq.get("n_models_available", 0)
    n_total = dq.get("n_models_total", 0)

    # price / shares
    price_icon = "✅" if dq.get("has_price") else "❌"
    shares_icon = "✅" if dq.get("has_shares") else "❌"
    share_basis = dq.get("share_basis") or {}
    share_basis_conf = share_basis.get("confidence", "中")
    share_basis_cov = f"{share_basis.get('valuation_count', 0)}/{share_basis.get('total_years', 0)}"
    share_basis_fallback = share_basis.get("fallback_count", 0)
    share_basis_split_like = share_basis.get("split_like_jump_count", 0)
    share_basis_mixed = share_basis.get("mixed_basis_jump_count", 0)
    share_basis_mixed_semantics = 1 if share_basis.get("mixed_semantics") else 0

    # warnings
    warnings = dq.get("warnings", [])
    warn_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
        warn_html = f'<ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--bad-fg);">{items}</ul>'

    dq_kv_table = render_key_value_table(
      "机器可读汇总（数据质量）",
      "data_quality_summary",
      [
        ("confidence_level", confidence),
        ("confidence_score", f"{conf_score}/10"),
        ("years_covered", f"{n_years}"),
        ("year_range", str(dq.get("year_range", ""))),
        ("industry_matched", "true" if ind_matched else "false"),
        ("discount_key", str(dq.get("discount_key", ""))),
        ("exit_pe_key", str(dq.get("exit_pe_key", ""))),
        ("model_availability", f"{n_avail}/{n_total}"),
        ("has_price", "true" if dq.get("has_price") else "false"),
        ("has_shares", "true" if dq.get("has_shares") else "false"),
        ("share_basis_confidence", str(share_basis_conf)),
        ("share_basis_coverage", str(share_basis_cov)),
        ("share_basis_fallback_years", str(share_basis_fallback)),
        ("share_basis_split_like_jumps", str(share_basis_split_like)),
        ("share_basis_mixed_basis_jumps", str(share_basis_mixed)),
        ("share_basis_mixed_semantics", str(share_basis_mixed_semantics)),
      ],
    )

    return f'''
    <!-- BEGIN_SECTION: data_quality -->
    <section class="section">
      <h2>数据质量与置信度</h2>
      <p class="section-intro">这一模块检查报告所依赖的数据完整性，帮你判断上面的结论有多少"地基"。</p>
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px;">
        <div style="background:{bg};color:{fg};padding:6px 16px;border-radius:8px;font-weight:600;font-size:18px;">置信度：{confidence}</div>
        <span style="color:#888;font-size:13px;">综合评分 {conf_score}/10</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div>
          <h3 style="font-size:14px;margin:0 0 6px;">年度覆盖</h3>
          <p style="margin:0;font-size:13px;">{n_years} 年（{year_range}）</p>
        </div>
        <div>
          <h3 style="font-size:14px;margin:0 0 6px;">实时数据</h3>
          <p style="margin:0;font-size:13px;">{price_icon} 股价&emsp;{shares_icon} 总股本</p>
        </div>
      </div>
      <div style="margin-top:12px;">
        <h3 style="font-size:14px;margin:0 0 6px;">历史股本口径</h3>
        <p style="margin:0;font-size:13px;">置信度 {share_basis_conf}；valuation_shares 覆盖 {share_basis_cov}；fallback 年份 {share_basis_fallback}；自动识别拆股阶跃 {share_basis_split_like}；疑似混口径跳变 {share_basis_mixed}；语义混用标记 {share_basis_mixed_semantics}</p>
      </div>
      <div style="margin-top:12px;">
        <h3 style="font-size:14px;margin:0 0 6px;">关键字段完整度</h3>
        {field_html}
      </div>
      <div style="margin-top:12px;">
        <h3 style="font-size:14px;margin:0 0 6px;">行业适配</h3>
        <p style="margin:0;font-size:13px;">{ind_text}</p>
      </div>
      <div style="margin-top:12px;">
        <h3 style="font-size:14px;margin:0 0 6px;">估值模型可用性（{n_avail}/{n_total}）</h3>
        <div style="display:flex;flex-wrap:wrap;gap:4px 0;">{model_html}</div>
      </div>
      <!-- KEY: confidence_level -->
      <!-- KEY: confidence_score -->
      <!-- KEY: model_availability -->
      <div class="table-wrap" style="margin-top:12px;">
        {dq_kv_table}
      </div>
      {warn_html}
    </section>
    <!-- END_SECTION: data_quality -->'''


def render_html(
    code: str,
    company_name: str,
    rows: Sequence[Dict],
    metrics: Sequence[MetricAssessment],
    conclusions: Sequence[str],
    ses_metrics: Sequence[MetricAssessment],
    ses_conclusions: Sequence[str],
    valuation_metrics: Sequence[ValuationAssessment],
    valuation_conclusions: Sequence[str],
    valuation_details: Dict[str, object],
    valuation_history: Sequence[Dict[str, object]],
    diagnostics: Dict[str, object],
    is_bank: bool = False,
    wr_data: Optional[Dict] = None,
    market_env_data: Optional[Dict] = None,
    data_quality: Optional[Dict] = None,
    oe_yield_history: Optional[List[Dict]] = None,
    dollar_retention: Optional[Dict] = None,
) -> str:
    coverage = f"{rows[0]['year']} - {rows[-1]['year']}" if rows else "N/A"
    abs_df = diagnostics.get("abs_df")
    year_data: Dict[str, Dict] = diagnostics.get("year_data", {})
    annual_cols: List[str] = diagnostics.get("annual_cols", [])
    diag_price = safe_float(diagnostics.get("price"))
    diag_mcap = safe_float(diagnostics.get("market_cap"))
    pledge = diagnostics.get("pledge")
    pledge_fetch_status = str(diagnostics.get("pledge_fetch_status") or "")
    quality_cards = build_quality_cards(abs_df, annual_cols, year_data, diagnostics, is_bank=is_bank) if abs_df is not None else {}
    quality_notes = build_quality_module_notes(abs_df, annual_cols, year_data, diagnostics) if abs_df is not None else {}
    decision_summary = summarize_business_quality(metrics, ses_metrics, quality_cards, valuation_metrics, is_bank=is_bank)
    feature_sketch = _build_feature_sketch(decision_summary, rows)

    profitability_rows = []
    for row in rows:
        gm_tone, _ = assess_gross_margin(row.get("gross_margin"))
        purity_base = row.get("purity_with_rnd") if row.get("purity_with_rnd") is not None else row.get("purity")
        purity_tone, _ = assess_purity(purity_base)
        profitability_rows.append(
            [
                html.escape(row["year"]),
                wrap_value(fmt_pct(row.get("gross_margin")), gm_tone),
                html.escape(fmt_pct(row.get("selling_ratio"))),
                html.escape(fmt_pct(row.get("admin_ratio"))),
                html.escape(fmt_pct(row.get("rnd_ratio"))),
                wrap_value(fmt_pct(purity_base), purity_tone),
            ]
        )

    cash_cycle_rows = []
    for row in rows:
        dso_tone, _ = assess_dso(row.get("dso"))
        dpo_tone, _ = assess_dpo(row.get("dpo"))
        ccc_tone, _ = assess_ccc(row.get("ccc"))
        cash_cycle_rows.append(
            [
                html.escape(row["year"]),
                wrap_value(fmt_days(row.get("dso")), dso_tone),
                html.escape(fmt_days(row.get("dio"))),
                wrap_value(fmt_days(row.get("dpo")), dpo_tone),
                wrap_value(fmt_days(row.get("ccc")), ccc_tone),
            ]
        )

    capital_rows = []
    roiic_by_year_3y: Dict[str, Optional[float]] = {}
    roiic_by_year_5y: Dict[str, Optional[float]] = {}
    for idx in range(3, len(rows)):
        latest = rows[idx]
        base = rows[idx - 3]
        capex_vals = [rows[idx - 2].get("capex"), rows[idx - 1].get("capex"), rows[idx].get("capex")]
        capex_sum = sum(capex_vals) if all(v is not None for v in capex_vals) else None
        roiic = None
        if latest.get("operating_profit") is not None and base.get("operating_profit") is not None and capex_sum is not None and capex_sum > 0:
            roiic = (latest["operating_profit"] - base["operating_profit"]) / capex_sum * 100
        roiic_by_year_3y[latest["year"]] = roiic
    for idx in range(5, len(rows)):
        latest = rows[idx]
        base = rows[idx - 5]
        capex_vals = [rows[idx - 4].get("capex"), rows[idx - 3].get("capex"), rows[idx - 2].get("capex"), rows[idx - 1].get("capex"), rows[idx].get("capex")]
        capex_sum = sum(capex_vals) if all(v is not None for v in capex_vals) else None
        roiic = None
        if latest.get("operating_profit") is not None and base.get("operating_profit") is not None and capex_sum is not None and capex_sum > 0:
            roiic = (latest["operating_profit"] - base["operating_profit"]) / capex_sum * 100
        roiic_by_year_5y[latest["year"]] = roiic
    for row in rows:
        capex_tone, _ = assess_capex_ratio(row.get("capex_net_income"))
        _roiic_3y = roiic_by_year_3y.get(row["year"])
        _roiic_5y = roiic_by_year_5y.get(row["year"])
        _roiic_eval = _roiic_5y if _roiic_5y is not None else _roiic_3y
        roiic_tone, _ = assess_roiic(_roiic_eval)
        capital_rows.append(
            [
                html.escape(row["year"]),
                html.escape(fmt_yi(row.get("operating_profit"))),
                html.escape(fmt_yi(row.get("capex"))),
                html.escape(fmt_yi(row.get("net_income"))),
                wrap_value(fmt_ratio(row.get("capex_net_income")), capex_tone),
                wrap_value(fmt_ratio(_roiic_3y), roiic_tone),
                wrap_value(fmt_ratio(_roiic_5y), roiic_tone),
            ]
        )

    ses_rows = []
    for row in rows:
        rev_tone, _ = assess_revenue_growth(safe_float(row.get("revenue_growth")))
        gm_tone, _ = assess_gm_delta(safe_float(row.get("gm_delta")))
        at_tone, _ = assess_asset_turnover(safe_float(row.get("asset_turnover")))
        roe_tone, _ = assess_roe_ses(safe_float(row.get("roe")), safe_float(row.get("asset_turnover")))
        ses_rows.append(
            [
                html.escape(row["year"]),
                wrap_value(fmt_pct(safe_float(row.get("revenue_growth"))), rev_tone),
                wrap_value(fmt_pct(safe_float(row.get("gm_delta"))), gm_tone),
                html.escape(fmt_pct(safe_float(row.get("opex_ratio")))),
                wrap_value(fmt_num(safe_float(row.get("asset_turnover"))), at_tone),
                wrap_value(fmt_pct(safe_float(row.get("roe"))), roe_tone),
            ]
        )

    efficiency_rows = []
    interest_rows = []
    capital_safety_rows = []
    ocf_rows = []
    goodwill_rows = []
    tax_rows = []
    payout_rows = []
    shareholder_rows = []
    eps_rows = []
    efficiency_cards = []
    interest_cards = []
    eps_cards = []
    capital_cards = []
    ocf_cards = []
    goodwill_cards = []
    tax_cards = []
    pledge_cards = []
    payout_cards = []
    shareholder_cards = []

    if annual_cols and abs_df is not None:
        quality_snapshots = build_quality_year_snapshots(abs_df, annual_cols, year_data, diag_mcap)
        for snap in quality_snapshots:
            col = str(snap["col"])
            d = snap["data"]
            roic = safe_float(snap.get("roic"))
            gap = None
            if safe_float(d.get("roe")) is not None and roic is not None:
                gap = safe_float(d.get("roe")) - roic
            efficiency_rows.append([
                html.escape(col[:4]),
                wrap_value(fmt_pct(safe_float(d.get("roa"))), _rate_roa(safe_float(d.get("roa")))),
                wrap_value(fmt_pct(safe_float(d.get("roe"))), _rate_roe_render(safe_float(d.get("roe")))),
                wrap_value(fmt_pct(roic), _rate_roic(roic)),
                wrap_value(fmt_num(gap) if gap is not None else "N/A", _rate_roe_roic_gap(gap)),
            ])

            tag = snap.get("icr_tag")
            icr = safe_float(snap.get("icr"))
            icr_text = "N/A"
            if tag == "surplus":
                icr_text = "∞"
            elif icr is not None:
                icr_text = f"{icr:.2f}x"
            interest_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(safe_float(d.get("op_profit")))),
                html.escape(fmt_yi(safe_float(d.get("fin_cost")))),
                wrap_value(icr_text, _rate_icr(icr, tag)),
            ])

            capital_safety_rows.append([
                html.escape(col[:4]),
                wrap_value(fmt_pct(roic), _rate_roic(roic)),
                html.escape(fmt_yi(safe_float(d.get("net_cash")))),
                html.escape(fmt_yi(safe_float(d.get("int_debt")))),
                html.escape(fmt_yi(safe_float(d.get("due_debt_principal")))),
            ])

            profit = safe_float(snap.get("profit"))
            ocf = safe_float(snap.get("ocf"))
            ocf_ratio = safe_float(snap.get("ocf_ratio"))
            ocf_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(ocf)),
                html.escape(fmt_yi(profit)),
                wrap_value(fmt_pct(ocf_ratio), _rate_ocf_ratio(ocf_ratio)),
            ])

            eq = safe_float(snap.get("eq"))
            gw = safe_float(snap.get("goodwill")) or 0.0
            gw_pct = safe_float(snap.get("gw_pct"))
            goodwill_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(gw)),
                html.escape(fmt_yi(eq)),
                wrap_value(fmt_pct(gw_pct), _rate_goodwill(gw_pct)),
            ])

            pretax = safe_float(snap.get("pretax"))
            tax = safe_float(snap.get("tax"))
            taxes_paid = safe_float(d.get("taxes_paid_cash"))
            book_rate = safe_float(snap.get("book_rate"))
            tax_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(pretax)),
                html.escape(fmt_yi(tax)),
                html.escape(fmt_yi(taxes_paid)),
                wrap_value(fmt_pct(book_rate), _rate_tax(book_rate)),
            ])

            div = safe_float(snap.get("div"))
            payout = safe_float(snap.get("payout"))
            payout_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(div)),
                html.escape(fmt_yi(profit)),
                wrap_value(fmt_pct(payout), _rate_payout(payout)),
            ])

            net_buyback = safe_float(snap.get("net_buyback")) or 0.0
            div_yield = safe_float(snap.get("div_yield"))
            buyback_yield = safe_float(snap.get("buyback_yield"))
            total_yield = safe_float(snap.get("total_yield"))
            shareholder_rows.append([
                html.escape(col[:4]),
                html.escape(fmt_yi(div)),
                html.escape(fmt_yi(net_buyback)),
                html.escape(fmt_pct(div_yield)),
                html.escape(fmt_pct(buyback_yield)),
                wrap_value(fmt_pct(total_yield), _rate_total_yield(total_yield)),
            ])

            real_eps = safe_float(snap.get("real_eps"))
            basic_eps = safe_float(snap.get("basic_eps"))
            diluted_eps = safe_float(snap.get("diluted_eps"))
            ocf_ps = safe_float(snap.get("ocf_ps"))
            quality = safe_float(snap.get("eps_quality"))
            eps_rows.append([
                html.escape(col[:4]),
                wrap_value(fmt_num(real_eps, 3), _rate_real_eps(real_eps)),
                html.escape(fmt_num(basic_eps, 3)),
                html.escape(fmt_num(diluted_eps, 3)),
                html.escape(fmt_num(ocf_ps, 3)),
                wrap_value(fmt_num(quality, 2), _rate_eps_quality(quality)),
            ])

    pledge_rows = []
    if pledge:
        td = pledge.get("trade_date")
        td_text = td.isoformat() if hasattr(td, "isoformat") else str(td)
        calc_pct = safe_float(pledge.get("pledge_ratio_pct"))
        pledge_rows = [[
            html.escape(td_text),
            wrap_value(fmt_pct(calc_pct), _rate_pledge(calc_pct)),
            html.escape(fmt_num(safe_float(pledge.get("pledge_shares_wan")))),
            html.escape(str(pledge.get("pledge_n") or "")),
            html.escape(fmt_num((safe_float(pledge.get("pledge_mv_wan")) or 0.0) / 10000.0)),
        ]]
    elif pledge_fetch_status == "timeout":
        pledge_rows = [["接口超时", "本次未取到", "N/A", "N/A", "N/A"]]
    elif pledge_fetch_status in ("error", "not_found"):
        pledge_rows = [["本次未取到", "接口未返回", "N/A", "N/A", "N/A"]]

    latest_diag = year_data.get(annual_cols[-1], {}) if annual_cols else {}
    latest_roa = safe_float(latest_diag.get("roa"))
    latest_roe = safe_float(latest_diag.get("roe"))
    latest_roic = roic_percent_from_year_data(latest_diag) if latest_diag else None
    roe_roic_gap = (latest_roe - latest_roic) if latest_roe is not None and latest_roic is not None else None
    tag, latest_icr = interest_coverage_ratio_tag_value(latest_diag) if latest_diag else ("na", None)
    latest_real_eps, _ = get_real_eps(abs_df, annual_cols[-1]) if annual_cols and abs_df is not None else (None, "")
    latest_profit = safe_float(latest_diag.get("profit"))
    latest_ocf = safe_float(latest_diag.get("ocf"))
    latest_ocf_ps = (latest_ocf / safe_float(latest_diag.get("shares"))) if latest_ocf is not None and safe_float(latest_diag.get("shares")) not in (None, 0) else None
    latest_eps_quality = (latest_ocf_ps / latest_real_eps) if latest_ocf_ps is not None and latest_real_eps is not None and latest_real_eps > 0 else None
    latest_ocf_ratio = (latest_ocf / latest_profit * 100) if latest_ocf is not None and latest_profit and latest_profit > 0 else None
    latest_eq = _equity_denom(latest_diag)
    latest_gw = safe_float(latest_diag.get("goodwill")) or 0.0
    latest_gw_ratio = (latest_gw / latest_eq * 100) if latest_eq and latest_eq > 0 else None
    latest_pretax = safe_float(latest_diag.get("pretax"))
    latest_tax = safe_float(latest_diag.get("tax"))
    latest_book_rate = (latest_tax / latest_pretax * 100) if latest_pretax and latest_tax is not None and latest_pretax > 0 else None
    latest_div = safe_float(latest_diag.get("dividends_paid"))
    latest_payout = (latest_div / latest_profit * 100) if latest_div is not None and latest_profit and latest_profit > 0 else None
    latest_net_buyback = (safe_float(latest_diag.get("buyback_cash")) or 0.0) - (safe_float(latest_diag.get("equity_inflow_cash")) or 0.0)
    latest_total_yield = ((latest_div or 0.0) + latest_net_buyback) / diag_mcap * 100 if diag_mcap and latest_div is not None else None

    def _render_metric_cards(items: Sequence[MetricAssessment]) -> str:
        out = []
        for m in items:
            formula_html = f'<div class="metric-formula"><strong>公式：</strong>{html.escape(m.formula)}</div>' if m.formula else ""
            trend_html = f' <span title="3年趋势" style="font-size:16px;opacity:0.8;">{html.escape(m.trend)}</span>' if m.trend else ""
            out.append(
                f"""
                <section class="metric-card {tone_class(m.tone)}">
                  <div class="metric-top">
                    <div class="metric-label">{html.escape(m.label)}{trend_html}</div>
                    <div class="metric-status">{html.escape(m.status_text)}</div>
                  </div>
                  <div class="metric-value">{html.escape(m.value_display)}</div>
                  <div class="metric-rule">{html.escape(m.rule_display)}</div>
                  {formula_html}
                  <div class="metric-meaning"><strong>衡量什么：</strong>{html.escape(m.meaning)}</div>
                  <div class="metric-meaning"><strong>背后含义：</strong>{html.escape(m.implication)}</div>
                </section>
                """
            )
        return "".join(out)

    efficiency_cards_html = _render_metric_cards(quality_cards.get("efficiency", []))
    interest_cards_html = _render_metric_cards(quality_cards.get("interest", []))
    eps_cards_html = _render_metric_cards(quality_cards.get("eps", []))
    capital_cards_html = _render_metric_cards(quality_cards.get("capital", []))
    ocf_cards_html = _render_metric_cards(quality_cards.get("ocf", []))
    goodwill_cards_html = _render_metric_cards(quality_cards.get("goodwill", []))
    tax_cards_html = _render_metric_cards(quality_cards.get("tax", []))
    pledge_cards_html = _render_metric_cards(quality_cards.get("pledge", []))
    payout_cards_html = _render_metric_cards(quality_cards.get("payout", []))
    shareholder_cards_html = _render_metric_cards(quality_cards.get("shareholder", []))
    capital_allocation_cards_html = _render_metric_cards(quality_cards.get("capital_allocation", []))
    share_capital = diagnostics.get("share_capital") or {}
    share_capital_cards_html = _render_metric_cards(share_capital.get("cards", []))

    share_capital_rows = []
    for r in share_capital.get("rows", []):
        total_yoy = safe_float(r.get("total_yoy"))
        economic_yoy = safe_float(r.get("economic_total_yoy"))
        float_yoy = safe_float(r.get("float_yoy"))
        total_yoy_tone, _ = _share_growth_tone(total_yoy)
        economic_yoy_tone, _ = _share_growth_tone(economic_yoy)
        float_yoy_tone, _ = _share_growth_tone(float_yoy, is_float=True)
        share_capital_rows.append(
            [
                html.escape(str(r.get("year") or "")),
                html.escape(fmt_shares(safe_float(r.get("total_shares")))),
                html.escape(fmt_shares(safe_float(r.get("float_shares")))),
                html.escape(fmt_pct(safe_float(r.get("float_ratio")))),
                wrap_value(fmt_pct(total_yoy), total_yoy_tone),
                wrap_value(fmt_pct(economic_yoy), economic_yoy_tone),
                html.escape(str(r.get("share_change_label") or "N/A")),
                wrap_value(fmt_pct(float_yoy), float_yoy_tone),
                wrap_value(fmt_num(safe_float(r.get("real_eps")), 3), _rate_real_eps(safe_float(r.get("real_eps")))),
                html.escape(fmt_num(safe_float(r.get("ocf_ps")), 3)),
                html.escape(fmt_num(safe_float(r.get("oe_ps")), 3)),
                html.escape(fmt_num(safe_float(r.get("bvps")), 3)),
                html.escape(fmt_yi(safe_float(r.get("net_buyback")))),
            ]
        )

    unlock_rows = []
    unlock = share_capital.get("unlock") or {}
    for r in unlock.get("rows", []):
        unlock_rows.append(
            [
                html.escape(str(r.get("date") or "")),
                html.escape(fmt_shares(safe_float(r.get("shares")))),
                wrap_value(fmt_pct(safe_float(r.get("ratio_float"))), _rate_unlock(safe_float(r.get("ratio_float")))),
                html.escape(str(r.get("holder_count") or "N/A")),
                html.escape(str(r.get("type") or "N/A")),
            ]
        )
    if not unlock_rows:
        status = str(unlock.get("status") or "")
        if status == "ok_empty_next_12m":
            msg = "未来 12 个月未见可用解禁压力"
        elif status == "not_applicable":
            msg = "不适用当前市场（美股/港股无限售解禁制度）"
        elif status in ("error", "not_found"):
            msg = "接口未取到，本次无法判断"
        else:
            msg = "N/A"
        unlock_rows = [[html.escape(msg), "—", "—", "—", "—"]]

    # --- 历年资本配置画像 ---
    cap_alloc_rows = []
    if is_bank:
        # Bank: 年份, ROA, ROE, NIM(代理), 拨贷比, 成本收入比, 存贷比
        for _ci, _cc in enumerate(annual_cols):
            _cd = year_data.get(_cc, {})
            _b_roa = safe_float(_cd.get("roa"))
            _b_roe = safe_float(_cd.get("roe"))
            _b_nim = safe_float(_cd.get("nim"))
            _b_plr = safe_float(_cd.get("provision_loan_ratio"))
            _b_cir = safe_float(_cd.get("cost_income_ratio"))
            _b_ldr = safe_float(_cd.get("loan_deposit_ratio"))
            _c_year_label = _cc[:4] if len(_cc) >= 4 else _cc
            cap_alloc_rows.append([
                html.escape(_c_year_label),
                wrap_value(fmt_pct(_b_roa), _assess_roa(_b_roa) if _b_roa is not None else "muted"),
                wrap_value(fmt_pct(_b_roe), "good" if _b_roe is not None and _b_roe >= 12 else ("warn" if _b_roe is not None and _b_roe >= 8 else ("bad" if _b_roe is not None else "muted"))),
                wrap_value(fmt_pct(_b_nim), _assess_nim(_b_nim) if _b_nim is not None else "muted"),
                wrap_value(fmt_pct(_b_plr), _assess_provision_loan(_b_plr) if _b_plr is not None else "muted"),
                wrap_value(fmt_pct(_b_cir), _assess_cost_income(_b_cir) if _b_cir is not None else "muted"),
                wrap_value(fmt_pct(_b_ldr), _assess_loan_deposit(_b_ldr) if _b_ldr is not None else "muted"),
            ])
    else:
        for _ci, _cc in enumerate(annual_cols):
            _cd = year_data.get(_cc, {})
            _c_roic = roic_percent_from_year_data(_cd)
            _c_profit = safe_float(_cd.get("profit"))
            _c_div = safe_float(_cd.get("dividends_paid"))
            _c_payout = (_c_div / _c_profit * 100) if _c_div is not None and _c_profit and _c_profit > 0 else None
            # archetype
            _c_rh = _c_roic is not None and _c_roic >= 12
            _c_ph = _c_payout is not None and _c_payout >= 40
            if _c_rh and _c_ph:
                _c_arch, _c_arch_tone = "印钞+分红型", "good"
            elif _c_rh and not _c_ph:
                _c_arch, _c_arch_tone = "高效再投资型", "good"
            elif not _c_rh and _c_ph:
                _c_arch, _c_arch_tone = "低效但愿分红", "warn"
            elif _c_roic is None or _c_payout is None:
                _c_arch, _c_arch_tone = "缺数据", "muted"
            else:
                _c_arch, _c_arch_tone = "低效低分红", "bad"
            # rolling RORE (need 3 prior years of data + current)
            _c_rore = None
            _c_rore_display = "N/A"
            if _ci >= 3 and abs_df is not None:
                _r_first_col = annual_cols[_ci - 3]
                _r_eps_first, _ = get_real_eps(abs_df, _r_first_col)
                _r_eps_last, _ = get_real_eps(abs_df, _cc)
                _r_retained = 0.0
                _r_ok = True
                for _rj in range(_ci - 2, _ci + 1):
                    _rjd = year_data.get(annual_cols[_rj], {})
                    _rjp = safe_float(_rjd.get("profit"))
                    _rjdiv = safe_float(_rjd.get("dividends_paid"))
                    if _rjp is not None:
                        _r_retained += _rjp - (_rjdiv or 0.0)
                    else:
                        _r_ok = False
                if _r_eps_first is not None and _r_eps_last is not None and _r_ok and _r_retained > 0:
                    _r_shares = safe_float(_cd.get("shares"))
                    if _r_shares and _r_shares > 0:
                        _r_rps = _r_retained / _r_shares
                        if _r_rps > 0:
                            _c_rore = (_r_eps_last - _r_eps_first) / _r_rps * 100
                            _c_rore_display = fmt_pct(_c_rore)
                elif _r_eps_first is not None and _r_eps_last is not None and _r_ok and _r_retained <= 0:
                    _c_rore_display = "净返还资本"
            _c_rore_tone = "muted"
            if _c_rore is not None:
                _c_rore_tone = "good" if _c_rore >= 15 else ("warn" if _c_rore >= 8 else "bad")
            elif _c_rore_display == "净返还资本":
                _c_rore_tone = "warn"
            _c_year_label = _cc[:4] if len(_cc) >= 4 else _cc
            cap_alloc_rows.append([
                html.escape(_c_year_label),
                wrap_value(fmt_pct(_c_roic), _rate_roic(_c_roic)),
                wrap_value(fmt_pct(_c_payout), _rate_payout(_c_payout)),
                wrap_value(_c_rore_display, _c_rore_tone),
                wrap_value(html.escape(_c_arch), _c_arch_tone),
            ])

    metric_cards = []
    for m in metrics:
        formula_html = f'<div class="metric-formula"><strong>公式：</strong>{html.escape(m.formula)}</div>' if m.formula else ""
        trend_html = f' <span title="3年趋势" style="font-size:16px;opacity:0.8;">{html.escape(m.trend)}</span>' if m.trend else ""
        metric_cards.append(
            f"""
            <section class="metric-card {tone_class(m.tone)}">
              <div class="metric-top">
                <div class="metric-label">{html.escape(m.label)}{trend_html}</div>
                <div class="metric-status">{html.escape(m.status_text)}</div>
              </div>
              <div class="metric-value">{html.escape(m.value_display)}</div>
              <div class="metric-rule">{html.escape(m.rule_display)}</div>
              {formula_html}
              <div class="metric-meaning"><strong>衡量什么：</strong>{html.escape(m.meaning)}</div>
              <div class="metric-meaning"><strong>背后含义：</strong>{html.escape(m.implication)}</div>
            </section>
            """
        )

    valuation_cards = []
    for m in valuation_metrics:
        formula_html = f'<div class="metric-formula"><strong>公式：</strong>{html.escape(m.formula)}</div>' if m.formula else ""
        valuation_cards.append(
            f"""
            <section class="metric-card {tone_class(m.tone)}">
              <div class="metric-top">
                <div class="metric-label">{html.escape(m.label)}</div>
                <div class="metric-status">{html.escape(m.status_text)}</div>
              </div>
              <div class="metric-value metric-value-small">{html.escape(m.value_display)}</div>
              <div class="metric-rule">{html.escape(m.rule_display)}</div>
              {formula_html}
              <div class="metric-meaning"><strong>衡量什么：</strong>{html.escape(m.meaning)}</div>
              <div class="metric-meaning"><strong>背后含义：</strong>{html.escape(m.implication)}</div>
            </section>
            """
        )
        valuation_summary_table_html = render_assessment_summary_table(
          "机器可读汇总（低估判定）",
          "valuation_overview_summary",
          valuation_metrics,
        )

    ses_cards = []
    for m in ses_metrics:
        formula_html = f'<div class="metric-formula"><strong>公式：</strong>{html.escape(m.formula)}</div>' if m.formula else ""
        trend_html = f' <span title="3年趋势" style="font-size:16px;opacity:0.8;">{html.escape(m.trend)}</span>' if m.trend else ""
        ses_cards.append(
            f"""
            <section class="metric-card {tone_class(m.tone)}">
              <div class="metric-top">
                <div class="metric-label">{html.escape(m.label)}{trend_html}</div>
                <div class="metric-status">{html.escape(m.status_text)}</div>
              </div>
              <div class="metric-value">{html.escape(m.value_display)}</div>
              <div class="metric-rule">{html.escape(m.rule_display)}</div>
              {formula_html}
              <div class="metric-meaning"><strong>衡量什么：</strong>{html.escape(m.meaning)}</div>
              <div class="metric-meaning"><strong>背后含义：</strong>{html.escape(m.implication)}</div>
            </section>
            """
        )

    valuation_history_rows = []
    current_price = safe_float(valuation_details.get("price"))
    valuation_history_fallback_years = []
    for row in valuation_history:
        peg_val = safe_float(row.get("peg"))
        pegy_val = safe_float(row.get("pegy"))
        eps_cagr = safe_float(row.get("eps_cagr"))
        div_yield = safe_float(row.get("div_yield"))
        if eps_cagr is not None and eps_cagr <= 0:
            peg_cell = wrap_value(f"不适用（{row.get('peg_reason') or 'CAGR≤0'}）", "muted")
        else:
            peg_cell = wrap_value(fmt_num(peg_val), "good" if peg_val is not None and peg_val < 1 else ("warn" if peg_val is not None and peg_val <= 2 else "muted"))
        if eps_cagr is not None and div_yield is not None and (eps_cagr + div_yield) <= 0:
            pegy_cell = wrap_value(f"不适用（{row.get('pegy_reason') or 'CAGR+股息率≤0'}）", "muted")
        else:
            pegy_cell = wrap_value(fmt_num(pegy_val), "good" if pegy_val is not None and pegy_val < 1 else ("warn" if pegy_val is not None and pegy_val <= 2 else "muted"))

        if eps_cagr is not None and row.get("eps_cagr_start_year") and row.get("eps_cagr_end_year"):
            eps_cagr_text = f"{fmt_pct(eps_cagr)}（{row.get('eps_cagr_start_year')}→{row.get('eps_cagr_end_year')}）"
        elif row.get("eps_cagr_reason") == "end_profit_non_positive":
            eps_cagr_text = "不适用（利润≤0）"
        elif row.get("eps_cagr_reason") == "no_positive_start":
            eps_cagr_text = "不适用（无正利润起点）"
        else:
            eps_cagr_text = "N/A"

        def _gap_text(v: Optional[float]) -> str:
            if current_price is None or current_price <= 0 or v is None or v <= 0:
                return "N/A"
            gap = (current_price - v) / v * 100
            tone = _rate_valuation_gap(gap)
            return wrap_value(f"{gap:+.1f}%", tone)

        def _pb_water_text(pb_v: Optional[float]) -> str:
            if pb_v is None:
                return "N/A"
            if pb_v < 0.7:
                return wrap_value("深度低估", "good")
            if pb_v < 1.0:
                return wrap_value("破净", "good")
            if pb_v < 1.3:
                return wrap_value("适中", "warn")
            return wrap_value("偏高", "bad")

        if is_bank:
            bps_v = safe_float(row.get("bps"))
            pb_v = safe_float(row.get("pb"))
            gordon_v = safe_float(row.get("gordon_ddm"))
            gordon_mos_v = safe_float(row.get("gordon_mos"))
            valuation_history_rows.append(
                [
                    html.escape(str(row["year"])),
                    html.escape(f"{fmt_num(current_price)} 元" if current_price is not None else "N/A"),
                    html.escape(f"{fmt_num(bps_v)} 元" if bps_v is not None else "N/A"),
                    html.escape(f"{fmt_num(pb_v)}x" if pb_v is not None else "N/A"),
                    wrap_value(f"{fmt_num(gordon_v)} 元", "good" if gordon_v is not None else "muted"),
                    html.escape(eps_cagr_text),
                    html.escape(fmt_pct(safe_float(row.get("div_yield")))),
                    peg_cell,
                    pegy_cell,
                    wrap_value(f"{fmt_num(gordon_mos_v)} 元", "good" if gordon_mos_v is not None else "muted"),
                    _gap_text(gordon_mos_v),
                    _pb_water_text(pb_v),
                    html.escape(fmt_pct(safe_float(row.get("payout")))),
                ]
            )
        else:
              year_label = str(row["year"])
              if not bool(row.get("strict_primary", True)):
                year_label = f"{year_label}*"
                valuation_history_fallback_years.append(str(row["year"]))
              _diag_d = row.get("diag_dcf") or {}
              _diag_m = row.get("diag_munger") or {}
              _dcf_con = safe_float(_diag_d.get("conservative"))
              _dcf_bas = safe_float(_diag_d.get("base"))
              _dcf_len = safe_float(_diag_d.get("lenient"))
              _mun_con = safe_float(_diag_m.get("conservative"))
              _mun_bas = safe_float(_diag_m.get("base"))
              _mun_len = safe_float(_diag_m.get("lenient"))
              _gap_bg_map_h = {"good": "#eef9f1", "warn": "#fff6df", "bad": "#fff0f0"}

              def _val_td(v, color=None):
                """Returns (html, bg_color_or_None)"""
                if v is None:
                  return ("N/A", None)
                txt = html.escape(f"{fmt_num(v)} 元")
                cell_html = f"<strong style='color:{color}'>{txt}</strong>" if color else txt
                bg = None
                if current_price is not None and current_price > 0 and v > 0:
                  gv = (current_price - v) / v * 100
                  bg = _gap_bg_map_h.get(_rate_valuation_gap(gv))
                return (cell_html, bg)

              def _gap_td(v):
                """Returns (html, bg_color_or_None)"""
                if current_price is None or current_price <= 0 or v is None or v <= 0:
                  return ("N/A", None)
                gv = (current_price - v) / v * 100
                tone = _rate_valuation_gap(gv)
                bg = _gap_bg_map_h.get(tone)
                return (wrap_value(f"{gv:+.1f}%", tone), bg)

              valuation_history_rows.append(
                [
                  (html.escape(year_label), None),
                  (html.escape(f"{fmt_num(current_price)} 元" if current_price is not None else "N/A"), None),
                  (html.escape(fmt_num(safe_float(row.get("oe_ps")))), None),
                  (html.escape(fmt_pct(safe_float(row.get("g_bm")))), None),
                  (html.escape(eps_cagr_text), None),
                  (html.escape(fmt_pct(safe_float(row.get("div_yield")))), None),
                  (peg_cell, None),
                  (pegy_cell, None),
                  _val_td(_dcf_con, "#1a7a3a"),
                  _val_td(_dcf_bas, "#1a5fb4"),
                  _val_td(_dcf_len, "#c45500"),
                  _gap_td(_dcf_bas),
                  _val_td(_mun_con, "#1a7a3a"),
                  _val_td(_mun_bas, "#1a5fb4"),
                  _val_td(_mun_len, "#c45500"),
                  _gap_td(_mun_bas),
                  (html.escape(fmt_pct(safe_float(row.get("payout")))), None),
                ]
              )

    fallback_year_hint = ""
    if (not is_bank) and valuation_history_fallback_years:
        years_text = "、".join(sorted(set(valuation_history_fallback_years)))
        fallback_year_hint = f" 标注 * 的年份表示主分母缺失，已回退到替代分母（{years_text}）。"

    _asof_mode = (diagnostics.get("share_basis_mode") == "asof") if isinstance(diagnostics, dict) else False
    if is_bank:
        if _asof_mode:
            valuation_anchor_intro = "这里按年报锚点逐年回看合理估值。当前报告处于 as-of 回放模式，主表按 as-of 历史口径展示。比如现在分析 2025 年，这里也会同时列出基于 2024 年报、2023 年报等锚点算出来的 PB、超额收益模型与相对估值。"
        else:
            valuation_anchor_intro = "这里按年报锚点逐年回看合理估值。主表默认采用 current-basis 重述口径展示历史可比性。比如现在分析 2025 年，这里也会同时列出基于 2024 年报、2023 年报等锚点算出来的 PB、超额收益模型与相对估值。"
    else:
        if _asof_mode:
            valuation_anchor_intro = "这里按年报锚点逐年回看合理估值。当前报告处于 as-of 回放模式，主表按 as-of 历史口径，不把未来拆股或送转事件回写到过去。OE-DCF 使用增长衰减模型（fade DCF）：增长率从估算值逐年衰减至终值，假设竞争优势不会永续。OE 额外打九折作为盈利正常化折扣。" + fallback_year_hint
        else:
            valuation_anchor_intro = "这里按年报锚点逐年回看合理估值。主表默认采用 current-basis（valuation_shares）重述历史可比性；as-of 口径用于时点回放校验。OE-DCF 使用增长衰减模型（fade DCF）：增长率从估算值逐年衰减至终值，假设竞争优势不会永续。OE 额外打九折作为盈利正常化折扣。" + fallback_year_hint

    profitability_note = (
        f"毛利率趋势: {html.escape(trend_text(series_values(rows, 'gross_margin')))}；"
        f"业务纯度趋势: {html.escape(trend_text(series_values(rows, 'purity_with_rnd') or series_values(rows, 'purity')))}。"
    )
    cash_cycle_note = (
        "DSO 是收钱速度，DIO 是存货压多久，DPO 是付钱速度，"
        "CCC 把三者放到同一套资金周转框架里。"
    )
    capital_note = "ROIIC 并行展示 3Y/5Y：3Y更灵敏，5Y更稳健。"
    ses_note = "SES 看的是：规模先扩张，毛利保持克制，费用率下降，最后靠高周转把 ROE 做出来。"

    conclusion_html = "".join(f"<li>{html.escape(line)}</li>" for line in conclusions)
    ses_conclusion_html = "".join(f"<li>{html.escape(line)}</li>" for line in ses_conclusions)
    valuation_conclusion_html = "".join(f"<li>{html.escape(line)}</li>" for line in valuation_conclusions)

    # ── 逐年三口径 OE 收益率 ──────────────────────────────────────────────────
    def _oe_yield_tone(pct: Optional[float]) -> str:
        if pct is None:
            return ""
        if pct >= 8.0:
            return "good"
        if pct >= 4.0:
            return "warn"
        return "bad"

    oe_yield_section_html = ""
    if oe_yield_history:
        header_cells = "".join(
            f"<th>{h}</th>"
            for h in ["年份", "年末MA200(元)", "悲观OE收益率", "基准OE收益率", "宽松OE收益率"]
        )
        trs = []
        for r in oe_yield_history:
            yr = html.escape(str(r.get("year", "")))
            ma200 = r.get("ma200_price")
            py = r.get("pess_yield")
            by = r.get("base_yield")
            ly = r.get("leni_yield")
            ma200_str = f"{ma200:.2f}" if ma200 is not None else "—"
            def _cell(v: Optional[float]) -> str:
                tone = _oe_yield_tone(v)
                cls = f" class=\"tone-{tone}\"" if tone else ""
                text = f"{v:.2f}%" if v is not None else "—"
                return f"<td{cls}>{text}</td>"
            trs.append(
                f"<tr><td>{yr}</td><td>{ma200_str}</td>"
                f"{_cell(py)}{_cell(by)}{_cell(ly)}</tr>"
            )
        tbody = "\n".join(trs)
        oe_yield_section_html = f"""
    <section class="section">
      <h2>逐年三口径 OE 收益率</h2>
      <p class="section-intro">用年末 MA200（200日均线）作为价格分母，逐年计算三口径所有者盈余收益率，呈现不受短期价格波动干扰的历史收益率范围。悲观口径（全部资本支出视为维护性）最保守，宽松口径只扣最低维护性资本支出。收益率 ≥8% 绿色，4–8% 黄色，&lt;4% 红色。</p>
      <div class="table-wrap">
        <table>
          <thead><tr>{header_cells}</tr></thead>
          <tbody>{tbody}</tbody>
        </table>
      </div>
    </section>"""

    # ── 巴菲特「一美元留存检验」section ──────────────────────────
    dollar_retention_section_html = ""
    if dollar_retention and not is_bank:
        dr = dollar_retention
        w_start = html.escape(str(dr.get("window_start", "")))
        w_end = html.escape(str(dr.get("window_end", "")))
        total_ni = dr.get("total_ni") or 0.0
        total_oe = dr.get("total_oe") or 0.0
        total_div = dr.get("total_div") or 0.0
        total_buyback = dr.get("total_buyback") or 0.0
        mcap_start = dr.get("mcap_start") or 0.0
        mcap_end = dr.get("mcap_end") or 0.0
        mva = dr.get("mva") or 0.0
        retained_strict = dr.get("retained_strict") or 0.0
        ratio_strict = dr.get("ratio_strict")
        retained_oe = dr.get("retained_oe") or 0.0
        ratio_oe = dr.get("ratio_oe")
        real_retained = dr.get("real_retained") or 0.0
        real_retained_note = html.escape(str(dr.get("real_retained_note") or ""))
        passed_strict = bool(dr.get("passed_strict"))
        price_start = dr.get("price_start")
        price_end = dr.get("price_end")
        shares_yi = dr.get("shares_yi") or 0.0
        pre_year = dr.get("pre_year_price") or w_start

        def _ratio_tone(r: Optional[float]) -> str:
            if r is None: return "bad"
            if r >= 1.5: return "good"
            if r >= 1.0: return "warn"
            return "bad"

        ratio_strict_str = f"{ratio_strict:.2f}x" if ratio_strict is not None else "N/A"
        ratio_oe_str = f"{ratio_oe:.2f}x" if ratio_oe is not None else "N/A"
        verdict_cls = "good" if passed_strict else "bad"
        verdict_text = "✅ 通过（每留存1元，市场认可了超过1元的价值增长）" if passed_strict else "❌ 未通过（留存资本未带来相应价值增长）"

        # 逐年明细表
        dr_rows_html = ""
        for r in dr.get("rows", []):
            yr = html.escape(str(r.get("year", "")))
            ni_s = fmt_yi(r.get("ni"))
            oe_s = fmt_yi(r.get("oe"))
            div_s = fmt_yi(r.get("div"))
            bb_s = fmt_yi(r.get("buyback"))
            p_s = f"{r['price_ma200']:.2f}" if r.get("price_ma200") is not None else "—"
            dr_rows_html += (
                f"<tr><td>{yr}</td><td class='num'>{oe_s}</td><td class='num'>{ni_s}</td>"
                f"<td class='num'>{div_s}</td><td class='num'>{bb_s}</td><td class='num'>{p_s}</td></tr>"
            )

        dollar_retention_section_html = f"""
    <section class="section">
      <h2>巴菲特「一美元留存检验」</h2>
      <p class="section-intro">
        检验管理层能否将留存的每一元利润转化为至少一元的市值增长（{w_start}–{w_end}，共 {len(dr.get("rows", []))} 个财年）。
        期初市值以 {html.escape(str(pre_year))} 年末 MA200 × 股本估算；期末以 {w_end} 年末 MA200 × 股本估算。
        OE = 所有者盈余（基准口径）。
      </p>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>财年</th><th>OE（亿元）</th><th>净利润（亿元）</th>
            <th>现金股息（亿元）</th><th>回购（亿元）</th><th>年末MA200（元）</th>
          </tr></thead>
          <tbody>{dr_rows_html}</tbody>
          <tfoot>
            <tr class="total-row">
              <td><strong>合计</strong></td>
              <td class="num"><strong>{fmt_yi(total_oe)}</strong></td>
              <td class="num"><strong>{fmt_yi(total_ni)}</strong></td>
              <td class="num"><strong>{fmt_yi(total_div)}</strong></td>
              <td class="num"><strong>{fmt_yi(total_buyback)}</strong></td>
              <td>—</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div class="metrics-grid" style="margin-top:16px">
        <div class="metric-card tone-muted">
          <div class="metric-top"><span class="metric-label">期初市值（{html.escape(str(pre_year))}末）</span></div>
          <div class="metric-value">{fmt_yi(mcap_start)}</div>
          <div class="metric-rule">{f"{price_start:.2f}元/股 × {shares_yi:.2f}亿股" if price_start else ""}</div>
        </div>
        <div class="metric-card tone-muted">
          <div class="metric-top"><span class="metric-label">期末市值（{w_end}末）</span></div>
          <div class="metric-value">{fmt_yi(mcap_end)}</div>
          <div class="metric-rule">{f"{price_end:.2f}元/股 × {shares_yi:.2f}亿股" if price_end else ""}</div>
        </div>
        <div class="metric-card tone-muted">
          <div class="metric-top"><span class="metric-label">市值增值（MVA）</span></div>
          <div class="metric-value">{fmt_yi(mva)}</div>
        </div>
        <div class="metric-card tone-{_ratio_tone(ratio_strict)}">
          <div class="metric-top"><span class="metric-label">比率（MVA / NI留存）</span></div>
          <div class="metric-value">{ratio_strict_str}</div>
          <div class="metric-rule">NI留存 = {fmt_yi(retained_strict)}</div>
        </div>
        <div class="metric-card tone-{_ratio_tone(ratio_oe)}">
          <div class="metric-top"><span class="metric-label">比率（MVA / OE留存）</span></div>
          <div class="metric-value">{ratio_oe_str}</div>
          <div class="metric-rule">OE留存 = {fmt_yi(retained_oe)}</div>
        </div>
        <div class="metric-card tone-muted">
          <div class="metric-top"><span class="metric-label">真实留存（OE − 股息 − 回购）</span></div>
          <div class="metric-value">{fmt_yi(real_retained)}</div>
          <div class="metric-rule">{real_retained_note}</div>
        </div>
      </div>
      <div class="metric-conclusion tone-{verdict_cls}" style="margin-top:12px;">
        {html.escape(verdict_text)}
      </div>
    </section>"""

    resonances = valuation_details.get("resonances") or []
    resonance_summary_table_html = render_key_value_table(
      "机器可读汇总（低估共振）",
      "valuation_resonance_summary",
      [
        ("resonance_count", str(len(resonances))),
        ("conclusion_count", str(len(valuation_conclusions))),
        ("latest_year", str(valuation_details.get("latest_year") or "N/A")),
        ("is_bank", "true" if bool(valuation_details.get("is_bank")) else "false"),
      ],
    )
    rf_dt = valuation_details.get("rf_dt")
    rf_pct = valuation_details.get("rf_pct")
    market_pe = safe_float(valuation_details.get("market_pe"))
    market_pe_label = str(valuation_details.get("market_pe_label") or "")
    cagr_info = valuation_details.get("cagr_info") or {}
    growth_for_peg_pct = safe_float(valuation_details.get("growth_for_peg_pct"))
    pegy = safe_float(valuation_details.get("pegy"))
    pegy_reason = str(valuation_details.get("pegy_reason") or "")
    dividend_yield_pct = safe_float(valuation_details.get("dividend_yield_pct"))
    cagr_pct = safe_float(cagr_info.get("cagr_pct"))
    cagr_window_text = ""
    if cagr_pct is not None and cagr_info.get("start_col") and cagr_info.get("end_col"):
        cagr_window_text = f"，按 {str(cagr_info.get('start_col'))[:4]}→{str(cagr_info.get('end_col'))[:4]} EPS CAGR 计算"
    elif growth_for_peg_pct is not None:
        cagr_window_text = "，EPS CAGR 不适用，改用 SGR/ROE留存增长估算"
    valuation_note = (
        f"当前股价为 {html.escape(fmt_num(current_price) if current_price is not None else 'N/A')} 元；"
        f"最新年报年份为 {html.escape(str(valuation_details.get('latest_year') or 'N/A'))}；"
        f"PEG 使用的增长率为 {html.escape(fmt_pct(growth_for_peg_pct) if growth_for_peg_pct is not None else 'N/A')}"
        f"{html.escape(cagr_window_text)}；"
        f"PEGY 额外加回股息率 {html.escape(fmt_pct(dividend_yield_pct) if dividend_yield_pct is not None else 'N/A')}，当前 PEGY 为 {html.escape(fmt_num(pegy) if pegy is not None else 'N/A')}；"
        f"{html.escape(('PEGY 不适用原因：' + pegy_reason + '；') if pegy is None and pegy_reason else '')}"
        f"全市场锚点为 {html.escape((fmt_num(market_pe) + 'x') if market_pe is not None else 'N/A')}"
        f"{html.escape(('（' + market_pe_label + '）') if market_pe_label else '（腾讯样本和全市场PE兜底均未返回足够有效值）')}；"
        f"十年期国债参考值为 {html.escape(fmt_pct(float(rf_pct)) if rf_pct is not None else 'N/A')}"
        f"{html.escape(f'（{rf_dt}）' if rf_dt else '')}。"
    )

    # Machine-readable summary block for LLM parsing.
    _snap = valuation_details.get("snap") or {}
    _munger_mid = None
    _munger_map = _snap.get("munger") if isinstance(_snap, dict) else None
    _exit_pes = valuation_details.get("exit_pes") or []
    if isinstance(_munger_map, dict) and isinstance(_exit_pes, (list, tuple)) and len(_exit_pes) >= 2:
        _munger_mid = safe_float(_munger_map.get(_exit_pes[1]))

    _resonances = valuation_details.get("resonances") or []
    _confidence = (data_quality or {}).get("confidence") if isinstance(data_quality, dict) else None
    _confidence_score = (data_quality or {}).get("confidence_score") if isinstance(data_quality, dict) else None

    machine_summary_table_html = render_key_value_table(
        "机器可读汇总（全局）",
        "ai_machine_summary",
        [
            ("code", code),
            ("company_name", company_name),
            ("latest_report_year", str(valuation_details.get("latest_year") or "N/A")),
            ("is_bank", "true" if is_bank else "false"),
            ("current_price", fmt_num(current_price) if current_price is not None else "N/A"),
            ("current_pe", fmt_num(safe_float(valuation_details.get("pe_current"))) if safe_float(valuation_details.get("pe_current")) is not None else "N/A"),
            ("current_pb", fmt_num(safe_float(valuation_details.get("pb_current"))) if safe_float(valuation_details.get("pb_current")) is not None else "N/A"),
            ("dcf_intrinsic_value", fmt_num(safe_float(_snap.get("buf_total"))) if isinstance(_snap, dict) and safe_float(_snap.get("buf_total")) is not None else "N/A"),
            ("munger_intrinsic_value_mid", fmt_num(_munger_mid) if _munger_mid is not None else "N/A"),
            ("gordon_intrinsic_value", fmt_num(safe_float(valuation_details.get("gordon_iv"))) if safe_float(valuation_details.get("gordon_iv")) is not None else "N/A"),
            ("mos_ratio", (f"{safe_float(valuation_details.get('mos_ratio')) * 100:.2f}%" if safe_float(valuation_details.get("mos_ratio")) is not None else "N/A")),
            ("discount_rate", (f"{safe_float(valuation_details.get('discount_rate')) * 100:.2f}%" if safe_float(valuation_details.get("discount_rate")) is not None else "N/A")),
            ("resonance_count", str(len(_resonances))),
            ("valuation_action", str(decision_summary.get("action") or "N/A")),
            ("confidence_level", str(_confidence or "N/A")),
            ("confidence_score", f"{_confidence_score}/10" if _confidence_score is not None else "N/A"),
        ],
    )

    # --- 银行条件渲染块 ---
    _ses_info_note = '<div class="module-note" style="border-left:3px solid #3498db;background:#eaf2f8;">\u2139\ufe0f 本公司未触发 SES 模式识别（SES 达标项不足3项），以下 SES 结论仅供对照参考，企业质量评分主要基于提价权维度。</div>'
    ses_section_html = ""
    if not is_bank:
        ses_section_html = f"""
    <section class="section">
      <h2 id="sec-ses">SES 总览</h2>
      <p class="section-intro">这一部分专门看公司是否在运行&ldquo;规模经济分享&rdquo;模式，也就是规模变大后，把一部分效率红利通过价格或毛利克制回馈给用户，再靠高周转把回报做出来。</p>
      <div class="module-note">{html.escape(ses_note)}</div>
      <div class="metrics-grid">
        {''.join(ses_cards)}
      </div>
    </section>

    <section class="section">
      <h2>SES 年度趋势</h2>
      <p class="section-intro">SES 不是单年现象，而是一种连续多年的经营姿态。这里把你指定的五个核心指标按年度展开，专门观察飞轮是否持续成立。</p>
      <div class="table-wrap">
        {render_table(["年份", "营收增速", "毛利率变动", "运营费用率", "总资产周转率", "ROE"], ses_rows)}
      </div>
    </section>

    <section class="section">
      <h2>SES 结论</h2>
      <p class="section-intro">下面的判断只基于你给出的 SES 五项指标，不擅自扩展到其他没点名的经营结论。</p>
      {_ses_info_note if not decision_summary.get('is_ses_archetype') else ''}
      <ul>{ses_conclusion_html}</ul>
    </section>"""

    profitability_section_html = ""
    if is_bank:
        profitability_section_html = f"""
    <section class="section">
      <h2>银行盈利结构</h2>
      <p class="section-intro">银行的盈利来源是息差而非毛利率，这里展示银行的核心盈利驱动指标：净息差代理、成本收入比、拨贷比和存贷比的历年趋势。</p>
      <div class="module-note">银行不适用毛利率/费用率分析，此处替换为银行经营核心指标。</div>
      <div class="table-wrap">
        {render_table(["年份", "ROA", "ROE", "NIM(代理)", "成本收入比", "拨贷比", "存贷比"], _build_bank_profitability_rows(rows))}
      </div>
    </section>

    <section class="section">
      <h2>银行信用质量：PPOP 与 NCO</h2>
      <p class="section-intro">PPOP（拨备前营业利润）衡量银行核心盈利对信用损失的吸收能力；NCO（净核销）反映实际信用损失水平；拨备/NCO 显示银行是在建立还是消耗减值储备。</p>
      <div class="module-note">NCO = 上年贷款减值准备 + 当年信用减值损失 − 当年贷款减值准备。首年因无上年数据显示 N/A。</div>
      <div class="table-wrap">
        {render_table(["年份", "PPOP", "PPOP/平均资产", "NCO", "NCO/平均贷款", "拨备/NCO"], _build_bank_credit_quality_rows(rows))}
      </div>
    </section>

    <section class="section">
      <h2>银行特许经营权：PPNR · ROTCE · 存款成本</h2>
      <p class="section-intro">PPNR（拨备前净收入）衡量银行在极端信贷损失情景下的最大吸收能力——巴菲特1990年分析富国银行的核心指标。ROTCE（有形权益回报率）剔除商誉和无形资产后的真实回报。存款付息率反映低成本存款特许经营权。</p>
      <div class="module-note">PPNR = 税前利润 + 信用减值损失。存款付息率 = 利息支出 / 平均客户存款，为近似值。</div>
      <div class="table-wrap">
        {render_table(["年份", "PPNR", "PPNR/平均资产", "ROTCE", "ROE(对照)", "存款付息率"], _build_bank_franchise_rows(rows))}
      </div>
    </section>"""

        # ── Stress test section ──
        stress = build_bank_stress_test(rows)
        stress_section_html = ""
        if stress:
            _s_rows_html = ""
            for sc in stress["scenarios"]:
                _tone = sc["verdict_tone"]
                _surplus = sc["ppnr_surplus"]
                _surplus_label = f'{_surplus / 1e8:+,.0f} 亿' if _surplus >= 0 else f'<span style="color:var(--bad-fg)">{_surplus / 1e8:+,.0f} 亿</span>'
                _erosion_str = f'{sc["equity_erosion"]:.1f}%' if sc["equity_erosion"] is not None else "N/A"
                _years_str = f'{sc["years_to_cover"]:.1f}' if sc["years_to_cover"] is not None else "N/A"
                _verdict_cls = f'tone-{_tone}'
                _s_rows_html += f"""<tr>
                  <td>{html.escape(sc["name"])}</td>
                  <td>{sc["default_rate"]*100:.0f}%</td>
                  <td>{sc["lgd"]*100:.0f}%</td>
                  <td>{sc["potential_loss"] / 1e8:,.0f} 亿</td>
                  <td>{_surplus_label}</td>
                  <td>{_erosion_str}</td>
                  <td>{_years_str}</td>
                  <td class="{_verdict_cls}">{sc["verdict"]}</td>
                </tr>"""
            stress_section_html = f"""
    <section class="section">
      <h2>极端压力测试：巴菲特银行生存分析</h2>
      <p class="section-intro">沿用巴菲特 1990 年分析富国银行的方法：假设贷款出现极端违约，计算潜在信贷损失，与 PPNR（拨备前净收入）和净资产对比，判断银行能否在不融资的情况下独立扛住危机。</p>
      <div class="module-note">潜在损失 = 总贷款 × 违约率 × 违约损失率(LGD)　|　基准年：{html.escape(str(stress["year"]))}　|　总贷款 {stress["gross_loans"]/1e8:,.0f} 亿　|　PPNR {stress["ppnr"]/1e8:,.0f} 亿　|　净资产 {stress["parent_equity"]/1e8:,.0f} 亿</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>情景</th><th>违约率</th><th>LGD</th><th>潜在损失</th><th>PPNR 盈余/缺口</th><th>净资产侵蚀</th><th>覆盖年数</th><th>判定</th></tr></thead>
          <tbody>{_s_rows_html}</tbody>
        </table>
      </div>
    </section>"""

        profitability_section_html += stress_section_html
    else:
        profitability_section_html = f"""
    <section class="section">
      <h2 id="sec-profitability">盈利能力：产品的溢价护城河</h2>
      <p class="section-intro">如果公司真有提价权，毛利率往往不仅高，而且在多年里比较稳；同时销售费用率和管理费用率不应把这些毛利大幅吃掉。</p>
      <div class="module-note">{html.escape(profitability_note)}</div>
      <div class="table-wrap">
        {render_table(["年份", "毛利率", "销售费用率", "管理费用率", "研发费用率", "业务纯度（优先含研发）"], profitability_rows)}
      </div>
    </section>"""

    cash_cycle_section_html = ""
    if not is_bank:
        cash_cycle_section_html = f"""
    <section class="section" id="sec-cash-cycle">
      <h2>产业链地位：现金效能</h2>
      <p class="section-intro">提价权最终会反映到收款和付款关系上。强势公司通常是收钱快、压货少、付款慢，最终把现金循环周期压得更短。</p>
      <div class="module-note">{html.escape(cash_cycle_note)}</div>
      <div class="table-wrap">
        {render_table(["年份", "DSO", "DIO", "DPO", "CCC"], cash_cycle_rows)}
      </div>
    </section>"""

    roiic_section_html = ""
    if not is_bank:
        roiic_section_html = f"""
    <section class="section">
      <h2>资本配置：扩张扩展性</h2>
      <p class="section-intro">伟大的提价权企业，不只是能赚高利润，还能少花资本就把利润继续做大。这里重点看营业利润扩张是否匹配过去三年的资本投入。</p>
      <div class="module-note">{html.escape(capital_note)}</div>
      <div class="table-wrap">
        {render_table(["年份", "营业利润", "Capex", "归母净利润", "Capex / Net Income", "ROIIC(3Y)", "ROIIC(5Y)"], capital_rows)}
      </div>
    </section>"""

    _wr_raw = _render_wr_section(wr_data)
    wr_section_html = _wr_raw.replace(
        'class="section">\n      <h2>技术指标</h2>',
        'class="section" id="sec-technicals">\n      <h2>技术指标</h2>',
        1
    )

    _vd_mos = valuation_details.get("mos_ratio", MARGIN_OF_SAFETY)
    _vd_mos_keep = f"{(1 - _vd_mos) * 100:.0f}%"
    _vd_mos_pct = f"{_vd_mos * 100:.0f}%"
    _vd_mos_grade = valuation_details.get("mos_grade", "标准")
    _vd_dr = valuation_details.get("discount_rate", DISCOUNT_RATE)
    _vd_dr_key = valuation_details.get("discount_rate_key", "默认")
    _vd_dr_pct = f"{_vd_dr * 100:.0f}%"
    _vd_exit_pes = valuation_details.get("exit_pes", DEFAULT_EXIT_PE)
    _vd_exit_pe_key = valuation_details.get("exit_pe_key", "默认")
    _vd_exit_pe_mid = f"{_vd_exit_pes[1]}x"
    _vd_exit_pe_label = f"{_vd_exit_pes[0]}x/{_vd_exit_pes[1]}x/{_vd_exit_pes[2]}x"

    if is_bank:
        valuation_formula_html = f"""
      <div class="explain-grid">
        <div class="explain-card">
          <h3>PB 估值</h3>
          <p><strong>PB = 股价 / 每股净资产</strong>。银行股的核心资产是贷款组合，账面价值比工业企业更能反映真实价值。</p>
          <p>PB &lt; 0.7 深度低估，0.7~1.0 破净低估，1.0~1.3 合理偏低，&gt; 1.3 估值中性偏高。</p>
        </div>
        <div class="explain-card">
          <h3>超额收益模型 (Residual Income)</h3>
          <p><strong>V = BPS × (ROE - g) / (Ke - g)</strong>，其中 BPS 为每股净资产，ROE 为加权平均净资产收益率，Ke 为折现率，g 为永续增长率（上限 {fmt_pct(TERMINAL_GROWTH * 100)}）。</p>
          <p>当 ROE &gt; Ke 时银行创造超额价值，V &gt; BPS；安全边际价 = <strong>V × {_vd_mos_keep}</strong>（{_vd_mos_grade}，安全边际{_vd_mos_pct}）。</p>
        </div>
        <div class="explain-card">
          <h3>估值参数</h3>
          <p>折现率 Ke = <strong>{_vd_dr_pct}</strong>（{_vd_dr_key}行业），安全边际 = <strong>{_vd_mos_pct}</strong>（{_vd_mos_grade}）。</p>
        </div>"""
    else:
        valuation_formula_html = f"""
      <div class="explain-grid">
        <div class="explain-card">
          <h3>OE-DCF</h3>
          <p><strong>OE = 归母净利润 + 折旧摊销 - 维持性资本开支</strong>，其中维持性资本开支 = <strong>max(min(Capex, D&amp;A), Capex × 70%)</strong>。</p>
          <p><strong>V = Σ[OE_t / (1+r)^t] + TV / (1+r)^n</strong>，安全边际价 = <strong>V × {_vd_mos_keep}</strong>（{_vd_mos_grade}，安全边际{_vd_mos_pct}）。</p>
        </div>
        <div class="explain-card">
          <h3>芒格远景估值</h3>
          <p><strong>V = 持有期分红现值 + 期末股权价值现值 + 净现金</strong>。</p>
          <p>期末股权价值按 <strong>{_vd_exit_pe_label}</strong> 三档退出PE计算（{_vd_exit_pe_key}行业适配），对应保守、基准、乐观三种持有情景。</p>
        </div>
        <div class="explain-card">
          <h3>估值参数</h3>
          <p>折现率 r = <strong>{_vd_dr_pct}</strong>（{_vd_dr_key}行业），永续增长率 g = <strong>3%</strong>，安全边际 = <strong>{_vd_mos_pct}</strong>（{_vd_mos_grade}），退出PE = <strong>{_vd_exit_pe_label}</strong>（{_vd_exit_pe_key}）。</p>
        </div>"""

    # --- 三档情景分析 HTML (1 DCF + 3 芒格矩阵, 对角线高亮) ---
    _sc = valuation_details.get("scenario_analysis")
    if _sc and not is_bank and _sc.get("g_levels"):
        _g_levels = _sc["g_levels"]
        _oe_levels = _sc["oe_levels"]
        _sc_pes  = _sc["exit_pes"]
        _sc_mos  = _sc["mos_ratio"]
        _d_iv  = _sc["dcf_iv"]
        _m_tables = _sc.get("munger_tables", {})
        _diag_colors = {"conservative": "#1a7a3a", "base": "#1a5fb4", "lenient": "#c45500"}
        _diag_keys = ["conservative", "base", "lenient"]
        _sc_price = safe_float(valuation_details.get("price"))
        _gap_bg_map = {"good": "#eef9f1", "warn": "#fff6df", "bad": "#fff0f0"}
        _gap_fg_map = {"good": "#1d6b3d", "warn": "#8a5a00", "bad": "#a12626"}
        def _sc_cell(v, is_diag=False, diag_color=None):
            """返回 (cell_html, gap_bg_color_or_None)"""
            if v is None:
                return ("N/A", None)
            txt = html.escape(f"{fmt_num(v)} 元")
            if is_diag and diag_color:
                val_line = f"<strong style='color:{diag_color}'>{txt}</strong>"
            else:
                val_line = txt
            gap_bg = None
            if _sc_price is not None and _sc_price > 0 and v > 0:
                gap = (_sc_price - v) / v * 100
                gap_tone = _rate_valuation_gap(gap)
                gap_fg = _gap_fg_map.get(gap_tone, "#666")
                gap_bg = _gap_bg_map.get(gap_tone)
                val_line += f"<br><span style='font-size:11px;font-weight:600;color:{gap_fg}'>{gap:+.1f}%</span>"
            return (val_line, gap_bg)
        _sc_tbl_style = "width:100%;border-collapse:collapse;font-size:13px;margin-bottom:10px;"
        _sc_th_style  = "padding:6px 10px;border:1px solid #ddd;background:#f5f5f5;text-align:center;"
        _sc_td_style  = "padding:6px 10px;border:1px solid #eee;text-align:center;"
        def _wrap_sc_table(title, col_heads, body_rows):
            return f"""<h3 style="margin:14px 0 6px;font-size:14px;">{html.escape(title)}</h3>
      <table style="{_sc_tbl_style}"><thead><tr><th style="{_sc_th_style}"></th>{col_heads}</tr></thead>
      <tbody>{body_rows}</tbody></table>""".replace("<th>", f"<th style=\"{_sc_th_style}\">").replace("<td>", f"<td style=\"{_sc_td_style}\">")
        # G 列标头
        _g_heads = "".join(f"<th>{html.escape(gl)}(G={html.escape(fmt_pct(gv*100))})</th>" for gl, gv in _g_levels)
        # ── DCF 3×3 (rows=OE口径, cols=G三档) ──
        _d_iv_rows = ""
        for oi, (oe_label, oe_val) in enumerate(_oe_levels):
            _d_iv_rows += f"<tr><td style='font-weight:600'>{html.escape(oe_label)}({html.escape(fmt_num(oe_val))})</td>"
            for gi, (gl, _) in enumerate(_g_levels):
                _v = _d_iv.get((oe_label, gl))
                _is_diag = (oi == gi)
                _dk = _diag_keys[oi] if _is_diag else None
                _cell_html, _cell_gap_bg = _sc_cell(_v, _is_diag, _diag_colors.get(_dk))
                _bg = _cell_gap_bg or ("#fafaf0" if _is_diag else "")
                _bg_style = f"background:{_bg};" if _bg else ""
                _d_iv_rows += f"<td style='{_bg_style}'>{_cell_html}</td>"
            _d_iv_rows += "</tr>"
        # ── 芒格远景: 每个PE一个3×3 ──
        _munger_sections = ""
        for pi, pe in enumerate(_sc_pes):
            _mt = _m_tables.get(pe, {})
            _m_rows = ""
            for oi, (oe_label, oe_val) in enumerate(_oe_levels):
                _m_rows += f"<tr><td style='font-weight:600'>{html.escape(oe_label)}({html.escape(fmt_num(oe_val))})</td>"
                for gi, (gl, _) in enumerate(_g_levels):
                    _v = _mt.get((oe_label, gl))
                    _is_diag = (oi == gi)
                    _dk = _diag_keys[oi] if _is_diag else None
                    _cell_html, _cell_gap_bg = _sc_cell(_v, _is_diag, _diag_colors.get(_dk))
                    _bg = _cell_gap_bg or ("#fafaf0" if _is_diag else "")
                    _bg_style = f"background:{_bg};" if _bg else ""
                    _m_rows += f"<td style='{_bg_style}'>{_cell_html}</td>"
                _m_rows += "</tr>"
            _munger_sections += _wrap_sc_table(f"芒格远景 — 退出PE {pe}x", _g_heads, _m_rows)
        _diag_legend = f"""<p style="font-size:12px;color:#666;margin:8px 0 2px;">对角线高亮：<span style="color:{_diag_colors['conservative']};font-weight:600">■ 保守</span>（悲观OE × 悲观G）&nbsp;
      <span style="color:{_diag_colors['base']};font-weight:600">■ 基准</span>（基准OE × 基准G）&nbsp;
      <span style="color:{_diag_colors['lenient']};font-weight:600">■ 乐观</span>（宽松OE × 乐观G）</p>"""
        _rd_note = ""
        _rd_snap = valuation_details.get("snap")
        _oe_detail = _rd_snap.get("oe_yearly_detail", []) if _rd_snap else []
        if _rd_snap and _rd_snap.get("rd_cap_ratio", 0) > 0:
            _rd_ratio_pct = _rd_snap["rd_cap_ratio"] * 100
            _rd_adj = _rd_snap.get("rd_cap_adj_total", 0)
            _rd_ind = _rd_snap.get("rd_cap_industry", "")
            if _rd_adj and _rd_adj > 0:
                _rd_adj_yi = fmt_yi(_rd_adj)
                _rd_note = f"""<div style="background:var(--warn-bg);color:var(--warn-fg);border-radius:8px;padding:10px 14px;margin:8px 0 12px;font-size:13px;line-height:1.6;">
        💡 <strong>研发资本化调节已启动</strong>：检测到当前为「{html.escape(_rd_ind)}」高研发行业，已将近5年平均研发费用的 {_rd_ratio_pct:.0f}%（约 {_rd_adj_yi}/年）视为扩张性资本投入并加回所有者盈余（OE），以此还原企业真实造血能力。</div>"""
            else:
                _rd_note = f"""<div style="background:var(--warn-bg);color:var(--warn-fg);border-radius:8px;padding:10px 14px;margin:8px 0 12px;font-size:13px;line-height:1.6;">
        💡 <strong>研发资本化调节</strong>：检测到当前为「{html.escape(_rd_ind)}」高研发行业（资本化比例 {_rd_ratio_pct:.0f}%），但当前数据源未提供研发费用明细，OE 未做调节。如需调节，请参考公司年报中的研发费用数据。</div>"""
        # ── OE 构成透视表 ──
        _oe_detail_html = ""
        if _oe_detail:
            _detail_rows = ""
            for d in _oe_detail:
                _y = d["year"]
                _p = fmt_yi(d["profit"]) if d["profit"] is not None else "N/A"
                _da = fmt_yi(d["da"]) if d["da"] is not None else "N/A"
                _cx = fmt_yi(d["capex"]) if d["capex"] is not None else "N/A"
                _rnd_v = d["rnd_expense"]
                if _rnd_v is not None and _rnd_v > 0:
                    _rnd_s = fmt_yi(_rnd_v)
                    _rnd_style = ""
                elif _rnd_v is not None and _rnd_v == 0:
                    _rnd_s = "0"
                    _rnd_style = ' style="color:var(--bad-fg);font-weight:600"'
                else:
                    _rnd_s = '<span style="color:var(--bad-fg);font-weight:600">缺数据</span>'
                    _rnd_style = ""
                _radj = fmt_yi(d["rnd_adj"]) if d["rnd_adj"] and d["rnd_adj"] > 0 else "—"
                _oe_b = fmt_yi(d["oe_base"]) if d["oe_base"] is not None else "N/A"
                _detail_rows += f"<tr><td>{_y}</td><td>{_p}</td><td>{_da}</td><td>{_cx}</td><td{_rnd_style}>{_rnd_s}</td><td>{_radj}</td><td style='font-weight:600'>{_oe_b}</td></tr>"
            _oe_detail_html = f"""<details style="margin:8px 0 12px;font-size:13px;">
        <summary style="cursor:pointer;font-weight:600;color:#444;">📊 OE 构成透视（点击展开）</summary>
        <table class="data-table" style="margin-top:6px;font-size:12px;">
          <thead><tr><th>年份</th><th>归母净利润</th><th>折旧摊销</th><th>资本开支</th><th>研发费用</th><th>研发加回</th><th>基准OE</th></tr></thead>
          <tbody>{_detail_rows}</tbody>
        </table>
        <p style="font-size:11px;color:#888;margin:4px 0 0;">研发费用显示「缺数据」表示数据源未提供该年研发费用明细；研发加回 = 研发费用 × 资本化比例。</p>
        </details>"""
        scenario_html = f"""
    <section class="section">
      <h2 id="sec-scenario">三档情景分析</h2>
      <p class="section-intro">基于 OE 三口径（悲观/基准/宽松）与 G 三档（双锚法：历史CAGR中位数 vs 质量组），构建敏感性矩阵。安全边际 = {_sc_mos*100:.0f}%。</p>
      {_rd_note}
      {_oe_detail_html}
      {_diag_legend}
      <div class="table-wrap">
        {_wrap_sc_table("OE-DCF — 合理股价（3×3 OE口径 × G三档）", _g_heads, _d_iv_rows)}
        {_munger_sections}
      </div>
    </section>"""
    else:
        scenario_html = ""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(company_name)} 财报分析报告</title>
  <style>
    /* ── Design System v4 — "Notion Light" ── */
    :root {{
      --bg: #ffffff;
      --bg-page: #f7f7f5;
      --panel: #ffffff;
      --panel-raised: #f9f9f7;
      --panel-border: #e9e9e7;

      --ink: #1a1a1a;
      --ink-secondary: #6b6b6b;
      --ink-tertiary: #a3a3a3;

      --good-bg: #edfaef;   --good-fg: #1a7f37;   --good-border: #98e0a0;
      --warn-bg: #fff9e6;   --warn-fg: #9a6700;   --warn-border: #ffc332;
      --bad-bg:  #fff0f0;   --bad-fg:  #cf222e;   --bad-border:  #ffabab;
      --muted-bg: #f7f7f5;  --muted-fg: #6b6b6b;  --muted-border: #e9e9e7;

      --accent: #0969da;
      --accent-light: #ddf4ff;
      --accent-glow: rgba(9,105,218,0.10);

      --line: #e9e9e7;

      --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
      --shadow-md: 0 2px 8px rgba(0,0,0,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--bg-page);
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", -apple-system, system-ui, sans-serif;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      font-size: 14px;
    }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(0,0,0,0.12); border-radius: 3px; }}

    /* ── Top nav bar ── */
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(255,255,255,0.96);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line);
      padding: 0 32px;
      height: 48px;
      display: flex;
      align-items: center;
      gap: 20px;
    }}
    .topbar-brand {{
      font-weight: 700;
      font-size: 14px;
      color: var(--ink);
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .topbar-brand span {{
      color: var(--ink-secondary);
      font-weight: 400;
      font-size: 13px;
      margin-left: 6px;
    }}
    .topbar-price {{
      font-size: 13px;
      color: var(--ink-secondary);
      white-space: nowrap;
      font-weight: 500;
    }}
    .topbar-nav {{
      display: flex;
      gap: 0;
      overflow-x: auto;
      flex: 1;
      scrollbar-width: none;
    }}
    .topbar-nav::-webkit-scrollbar {{ display: none; }}
    .topbar-nav a {{
      flex-shrink: 0;
      font-size: 13px;
      color: var(--ink-secondary);
      text-decoration: none;
      padding: 4px 10px;
      border-radius: 6px;
      transition: color 0.1s, background 0.1s;
      white-space: nowrap;
    }}
    .topbar-nav a:hover {{
      color: var(--ink);
      background: var(--panel-raised);
    }}

    /* ── Layout ── */
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }}

    /* ── Hero — Notion page header style ── */
    .hero {{
      background: var(--bg);
      border-radius: 12px;
      padding: 40px 48px 36px;
      border: 1px solid var(--line);
      margin-bottom: 4px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: 36px;
      font-weight: 800;
      line-height: 1.1;
      letter-spacing: -1px;
      color: var(--ink);
    }}
    .hero h1 em {{
      font-style: normal;
      color: var(--ink-secondary);
      font-weight: 400;
    }}
    .hero p {{
      margin: 12px 0 0;
      max-width: 840px;
      color: var(--ink-secondary);
      font-size: 14px;
      line-height: 1.8;
    }}
    .hero-meta {{
      margin-top: 28px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px 32px;
      padding-top: 20px;
      border-top: 1px solid var(--line);
    }}
    .hero-meta .box {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .hero-meta .k {{
      font-size: 11px;
      color: var(--ink-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 600;
    }}
    .hero-meta .v {{
      font-size: 16px;
      font-weight: 700;
      color: var(--ink);
    }}

    /* ── Decision cards ── */
    .decision-grid {{
      margin-top: 20px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
    }}
    .decision-card {{
      border-radius: 10px;
      padding: 14px 16px;
      border: 1px solid;
    }}
    .decision-card .k {{
      font-size: 11px;
      color: var(--ink-tertiary);
      letter-spacing: 0.05em;
      text-transform: uppercase;
      font-weight: 600;
    }}
    .decision-card .v {{
      margin-top: 8px;
      font-size: 20px;
      font-weight: 800;
      line-height: 1.2;
    }}
    .decision-card .d {{
      margin-top: 6px;
      font-size: 12px;
      line-height: 1.65;
      color: var(--ink-secondary);
    }}
    .decision-band {{
      margin-top: 10px;
      border-radius: 10px;
      padding: 12px 16px;
      border: 1px solid var(--panel-border);
      background: var(--panel-raised);
      font-size: 14px;
      line-height: 1.75;
      font-weight: 500;
      color: var(--ink);
    }}

    /* ── Section ── */
    .section {{
      margin-top: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 24px;
    }}
    .section h2 {{
      margin: 0;
      font-size: 17px;
      font-weight: 700;
      color: var(--ink);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .section h2::before {{
      content: '';
      display: block;
      width: 3px;
      height: 18px;
      border-radius: 999px;
      background: var(--accent);
      flex-shrink: 0;
    }}
    .section-intro {{
      margin: 8px 0 0 11px;
      color: var(--ink-secondary);
      line-height: 1.75;
      font-size: 13px;
    }}

    /* ── Metric cards ── */
    .metrics-grid {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
    }}
    .metric-card {{
      border-radius: 10px;
      padding: 14px 16px;
      border: 1px solid;
      min-height: 190px;
    }}
    .metric-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }}
    .metric-label {{
      font-size: 13px;
      font-weight: 700;
    }}
    .metric-status {{
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 999px;
      white-space: nowrap;
      background: rgba(0,0,0,0.05);
    }}
    .metric-value {{
      margin-top: 14px;
      font-size: 32px;
      font-weight: 900;
      line-height: 1;
      letter-spacing: -1px;
    }}
    .metric-value-small {{
      font-size: 18px;
      line-height: 1.35;
      font-weight: 800;
      word-break: break-word;
      letter-spacing: -0.3px;
    }}
    .metric-rule {{
      margin-top: 6px;
      font-size: 11px;
      opacity: 0.55;
    }}
    .metric-meaning {{
      margin-top: 10px;
      font-size: 12px;
      line-height: 1.65;
      opacity: 0.8;
    }}
    .metric-formula {{
      margin-top: 6px;
      font-size: 11px;
      line-height: 1.6;
      opacity: 0.65;
    }}
    .metric-conclusion {{
      margin-top: 8px;
      font-size: 12px;
      font-weight: 600;
      padding: 7px 10px;
      border-radius: 7px;
      line-height: 1.5;
    }}

    /* ── Tone classes ── */
    .tone-good {{
      background: var(--good-bg);
      color: var(--good-fg);
      border-color: var(--good-border);
    }}
    .tone-warn {{
      background: var(--warn-bg);
      color: var(--warn-fg);
      border-color: var(--warn-border);
    }}
    .tone-bad {{
      background: var(--bad-bg);
      color: var(--bad-fg);
      border-color: var(--bad-border);
    }}
    .tone-muted {{
      background: var(--muted-bg);
      color: var(--muted-fg);
      border-color: var(--muted-border);
    }}

    /* ── Module note ── */
    .module-note {{
      margin-top: 12px;
      padding: 10px 14px;
      border-radius: 8px;
      background: var(--panel-raised);
      color: var(--ink-secondary);
      line-height: 1.75;
      font-size: 12px;
      border: 1px solid var(--line);
    }}

    /* ── Tables ── */
    .table-wrap {{
      overflow-x: auto;
      margin-top: 14px;
      border-radius: 8px;
      border: 1px solid var(--line);
    }}
    .value-chip {{
      display: inline-block;
      padding: 1px 7px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 11px;
      border: 1px solid transparent;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
      font-size: 13px;
    }}
    th, td {{
      padding: 9px 12px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{
      text-align: left;
      position: sticky;
      left: 0;
      background: var(--panel);
      z-index: 1;
    }}
    th {{
      color: var(--ink-tertiary);
      font-weight: 700;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: var(--panel-raised);
      position: sticky;
      top: 0;
    }}
    th:first-child {{
      background: var(--panel-raised);
    }}
    tbody tr:hover td {{
      background: var(--accent-light);
    }}
    tbody tr:hover td:first-child {{
      background: var(--accent-light);
    }}
    tbody tr:nth-child(even) td {{
      background: var(--panel-raised);
    }}
    tbody tr:nth-child(even) td:first-child {{
      background: var(--panel-raised);
    }}
    tbody tr:last-child td {{
      border-bottom: none;
    }}

    /* ── Explain cards ── */
    .explain-grid {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 10px;
    }}
    .explain-card {{
      border-radius: 10px;
      background: var(--panel-raised);
      border: 1px solid var(--line);
      padding: 14px;
    }}
    .explain-card h3 {{
      margin: 0 0 6px;
      font-size: 14px;
      font-weight: 700;
    }}
    .explain-card p {{
      margin: 6px 0 0;
      color: var(--ink-secondary);
      font-size: 12px;
      line-height: 1.75;
    }}
    .explain-card .formula {{
      font-family: 'Menlo', 'Consolas', monospace;
      font-size: 11px;
      color: var(--accent);
      background: var(--accent-light);
      padding: 3px 7px;
      border-radius: 5px;
      display: inline-block;
    }}

    /* ── Misc ── */
    ul {{
      margin: 10px 0 0;
      padding-left: 18px;
      line-height: 1.85;
      color: var(--ink-secondary);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 999px;
      letter-spacing: 0.04em;
    }}
    .section-divider {{
      height: 1px;
      background: var(--line);
      margin: 14px 0;
    }}

    @media (max-width: 720px) {{
      .hero {{ padding: 20px 20px 18px; }}
      .hero h1 {{ font-size: 26px; }}
      .metric-value {{ font-size: 26px; }}
      .section {{ padding: 16px; }}
      .topbar-nav {{ display: none; }}
      .wrap {{ padding: 16px 16px 60px; }}
    }}
  </style>
</head>
<body>
  <nav class="topbar">
    <div class="topbar-brand">{html.escape(company_name)} <span>{html.escape(code)}</span></div>
    <div class="topbar-price">¥{html.escape(str(round(diag_price, 2)) if diag_price else "—")}</div>
    <nav class="topbar-nav">
      <a href="#sec-overview">总览</a>
      <a href="#sec-valuation">估值</a>
      <a href="#sec-scenario">情景矩阵</a>
      <a href="#sec-pricing-power">提价权</a>
      <a href="#sec-ses">SES</a>
      <a href="#sec-quality">财务质量</a>
      <a href="#sec-profitability">盈利能力</a>
      {'<a href="#sec-cash-cycle">现金周期</a>' if not is_bank else ''}
      {'<a href="#sec-technicals">技术面</a>' if wr_data else ''}
    </nav>
  </nav>
  <div class="wrap">
    <section class="hero">
      <h1>{html.escape(company_name)} <em>财报分析报告</em></h1>
      <p>基于财报数据生成的专题分析报告。上方先给出巴菲特和芒格视角下的快速判断，再展开估值、提价权、规模经济分享与财务质量细节。<strong style="color:var(--good-fg);">绿色</strong>代表接近优秀或低估，<strong style="color:var(--warn-fg);">黄色</strong>代表一般或需观察，<strong style="color:var(--bad-fg);">红色</strong>代表明显偏离目标画像。</p>
      <div class="hero-meta">
        <div class="box"><div class="k">股票代码</div><div class="v">{html.escape(code)}</div></div>
        <div class="box"><div class="k">覆盖年份</div><div class="v">{html.escape(coverage)}</div></div>
        <div class="box"><div class="k">样本年数</div><div class="v">{len(rows)} 年</div></div>
        <div class="box"><div class="k">当前股价</div><div class="v">¥{html.escape(str(round(diag_price, 2)) if diag_price else "—")}</div></div>
        <div class="box"><div class="k">生成时间</div><div class="v">{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div></div>
      </div>
    </section>

    {_render_market_env_section(market_env_data)}

    <section class="section" id="sec-overview">
      <h2>巴芒总览</h2>
      <p class="section-intro">这一屏只回答五件事：这是不是好企业、护城河强不强、财务稳不稳、现在贵不贵、值不值得继续深挖。先看结论，再决定要不要往下读细表。</p>
      <div class="decision-grid">
        <section class="decision-card {tone_class(decision_summary['enterprise_tone'])}">
          <div class="k">企业质量 <span style="font-size:11px;opacity:0.7;">（{html.escape(decision_summary.get('enterprise_basis',''))}）</span></div>
          <div class="v">{html.escape(decision_summary['enterprise_label'])}</div>
          <div class="d">{'检测到 SES 特征（≥3项达标），企业质量改用 SES 模式评分：跳过毛利率/标准差/业务纯度，纳入营收增速、毛利克制、费用率、周转率和 ROE。' if decision_summary.get('is_ses_archetype') else '基于提价权模式评分：用毛利率、毛利率稳定性、业务纯度、产业链指标、EPS 质量和税务质量综合判断。'}</div>
        </section>
        <section class="decision-card {tone_class(decision_summary['moat_tone'])}">
          <div class="k">护城河判断 <span style="font-size:11px;opacity:0.7;">（{html.escape(decision_summary.get('moat_basis',''))}）</span></div>
          <div class="v">{html.escape(decision_summary['moat_label'])}</div>
          <div class="d">{'SES 企业的护城河来自规模效率和周转速度，而非高毛利和品牌溢价。这里用 SES 五项指标 + 经营效率 + 产业链地位综合判断。' if decision_summary.get('is_ses_archetype') else '基于提价权模式：关注毛利率水平、毛利率稳定性、业务纯度、回款能力和经营效率，判断护城河来自品牌/渠道/产品力还是周期运气。'}</div>
        </section>
        <section class="decision-card {tone_class(decision_summary['safety_tone'])}">
          <div class="k">财务安全</div>
          <div class="v">{html.escape(decision_summary['safety_label'])}</div>
          <div class="d">{'把拨贷比、存贷比、杠杆倍数和质押放到一起，看这家银行的风险缓冲是否充足。' if is_bank else '把利息压力、净现金、利润含金量、商誉和质押放到一起，看这家公司会不会在外部波动时先伤到资产负债表。'}</div>
        </section>
        <section class="decision-card {tone_class(decision_summary['valuation_tone'])}">
          <div class="k">当前估值</div>
          <div class="v">{html.escape(decision_summary['valuation_label'])}</div>
          <div class="d">{'这里不是只看一个估值模型，而是把 PB、超额收益模型、PEG/PEGY、机会成本和市场锚点交叉核对。' if is_bank else '这里不是只看一个估值模型，而是把 OE-DCF、芒格估值、PEG/PEGY、机会成本和市场锚点交叉核对。'}</div>
        </section>
      </div>
      <div class="decision-band {tone_class(decision_summary['action_tone'])}">
        总结判断：{html.escape(decision_summary['action'])}
      </div>
      <div class="module-note" style="margin-top:12px;font-size:14px;line-height:1.7;border-left:3px solid #7f8c8d;background:var(--panel-raised);">
        <strong>特征速写：</strong>{html.escape(feature_sketch)}
      </div>
    </section>

    <!-- BEGIN_SECTION: valuation_overview -->
    <section class="section">
      <h2 id="sec-valuation">低估判定总览</h2>
      <p class="section-intro">这里把你给出的低估框架并到同一份报告里。判断逻辑不是单点结论，而是让绝对估值、相对估值、资产防御和机会成本互相校验。</p>
      <div class="module-note">{html.escape(valuation_note)}</div>
      <div class="metrics-grid">
        {''.join(valuation_cards)}
      </div>
      <!-- KEY: dcf_intrinsic_value_per_share -->
      <!-- KEY: munger_intrinsic_value_mid -->
      <!-- KEY: valuation_signal -->
      <div class="table-wrap" style="margin-top:12px;">
        {valuation_summary_table_html}
      </div>
    </section>
    <!-- END_SECTION: valuation_overview -->

    <section class="section">
      <h2>年度估值锚点</h2>
      <p class="section-intro">{valuation_anchor_intro}</p>
      <div class="table-wrap">
        {render_table(["年报锚点", "当前股价", "BPS", "PB", "超额收益", "利润CAGR", "股息率", "PEG", "PEGY", "ER安全边际价", "现价较安全边际价", "PB水位", "派息率"], valuation_history_rows) if is_bank else render_valuation_anchor_table(valuation_history_rows)}
      </div>
    </section>

    {oe_yield_section_html}

    {dollar_retention_section_html}

    {render_bank_valuation_context_section(valuation_details) if is_bank else (render_pe_percentile_section(valuation_details.get("pe_percentile_history")) + render_eps_percentile_section(valuation_details.get("eps_percentile_history")))}

    {scenario_html}

    <!-- BEGIN_SECTION: valuation_resonance -->
    <section class="section">
      <h2>低估共振结论</h2>
      <p class="section-intro">真正值得重视的低估，通常不是只有一个模型说便宜，而是多个维度同时给出一致信号。</p>
      <ul>{valuation_conclusion_html}</ul>
      <!-- KEY: resonance_count -->
      <div class="table-wrap" style="margin-top:12px;">
        {resonance_summary_table_html}
      </div>
    </section>
    <!-- END_SECTION: valuation_resonance -->

    <section class="section">
      <h2 id="sec-pricing-power">提价权总览</h2>
      <h2>{"银行经营指标总览" if is_bank else "提价权总览"}</h2>
      <div class="metrics-grid">
        {''.join(metric_cards)}
      </div>
    </section>

    {ses_section_html}

    <section class="section">
      <h2 id="sec-quality">经营效率雷达</h2>
      <p class="section-intro">这一部分对应原始脚本里的 `ROA 去杠杆视角 + ROE vs ROIC 测谎`，核心目的是看高回报究竟来自经营效率，还是更多来自杠杆放大。</p>
      <div class="module-note">{html.escape(quality_notes.get("efficiency", ""))}</div>
      <div class="metrics-grid">{efficiency_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "ROA", "ROE", "ROIC", "ROE-ROIC"], efficiency_rows)}
      </div>
    </section>

    <section class="section">
      <h2>财务呼吸机</h2>
      <p class="section-intro">这一部分沿用原脚本的口径，只看 `EBIT ÷ 财务费用`，不拿 EBITDA 粉饰。它回答的是：公司现在赚到的钱，够不够付利息。</p>
      <div class="module-note">{html.escape(quality_notes.get("interest", ""))}</div>
      <div class="metrics-grid">{interest_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "营业利润", "财务费用", "利息保障倍数"], interest_rows)}
      </div>
    </section>

    <section class="section">
      <h2>EPS 透视</h2>
      <p class="section-intro">这里对应原脚本的 `Real_EPS · 归母基本 · 稀释 · 含金量`。重点不是只看 EPS 大小，而是看每股利润是否真实、是否被稀释、是否有现金支撑。</p>
      <div class="module-note">{html.escape(quality_notes.get("eps", ""))}</div>
      <div class="metrics-grid">{eps_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "Real_EPS", "基本EPS", "稀释EPS", "每股OCF", "含金量"], eps_rows)}
      </div>
    </section>

    <section class="section">
      <h2>资本质量与财务安全</h2>
      <p class="section-intro">这一部分承接原脚本的 `资本质量 & 财务安全（年报）`，重点看 ROIC、净现金、有息负债和短债压力是否处在可接受范围。</p>
      <div class="module-note">{html.escape(quality_notes.get("capital", ""))}</div>
      <div class="metrics-grid">{capital_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "ROIC", "净现金", "有息负债", "到期债务本金"], capital_safety_rows)}
      </div>
    </section>

    <section class="section">
      <h2>净现比雷达</h2>
      <p class="section-intro">这里对应原脚本的 `OCF ÷ 归母净利润（存钱罐真钱 ÷ 账面利润）`。重点看利润有没有转成真钱，而不是只停留在报表上。</p>
      <div class="module-note">{html.escape(quality_notes.get("ocf", ""))}</div>
      <div class="metrics-grid">{ocf_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "经营现金流OCF", "归母净利润", "OCF÷净利润"], ocf_rows)}
      </div>
    </section>

    <section class="section">
      <h2>商誉占比雷达</h2>
      <p class="section-intro">这一部分沿用 `商誉 ÷ 净资产` 的资产质量扫描。商誉太高时，并购溢价和未来减值风险会明显抬升。</p>
      <div class="module-note">{html.escape(quality_notes.get("goodwill", ""))}</div>
      <div class="metrics-grid">{goodwill_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "商誉", "净资产分母", "商誉占净资产"], goodwill_rows)}
      </div>
    </section>

    <section class="section">
      <h2>税务测谎雷达</h2>
      <p class="section-intro">这一部分对应原脚本的 `纸面利润 vs 所得税（法定参照 25% / 高新 15%）`。目的是看利润是否有足够可信度，以及税负是否长期异常偏离。</p>
      <div class="module-note">{html.escape(quality_notes.get("tax", ""))}</div>
      <div class="metrics-grid">{tax_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "EBT", "所得税费用", "支付税费", "纸面有效税率"], tax_rows)}
      </div>
    </section>

    <section class="section">
      <h2>股权质押雷达</h2>
      <p class="section-intro">这里复用了原脚本的东财质押快照。如果质押比例过高，股价波动很容易反过来冲击控制权和流动性。</p>
      <div class="module-note">{html.escape(quality_notes.get("pledge", ""))}</div>
      <div class="metrics-grid">{pledge_cards_html}</div>
      <div class="table-wrap">
        {render_table(["交易日", "质押占总股本", "质押股数(万股)", "质押笔数", "质押市值(亿元)"], pledge_rows if pledge_rows else [["N/A", "N/A", "N/A", "N/A", "N/A"]])}
      </div>
    </section>

    <section class="section">
      <h2>分红健康度</h2>
      <p class="section-intro">这里对应原脚本的 `股利支付率（资本配置试金石）`。核心看的是：公司分红是否稳健，还是在透支利润甚至借钱分红。</p>
      <div class="module-note">{html.escape(quality_notes.get("payout", ""))}</div>
      <div class="metrics-grid">{payout_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "现金分红", "归母净利润", "股利支付率"], payout_rows)}
      </div>
    </section>

    <section class="section">
      <h2>股东回报雷达</h2>
      <p class="section-intro">这里沿用原脚本的 `回购 × 股息 × 总收益率（当前价×总股本口径）`，把股息和净回购放在一张表里看，避免只看表面回购公告。</p>
      <div class="module-note">{html.escape(quality_notes.get("shareholder", ""))}</div>
      <div class="metrics-grid">{shareholder_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "现金分红", "净回购现金", "股息率", "净回购收益率", "总股东收益率"], shareholder_rows)}
      </div>
    </section>

    <section class="section">
      <h2>{"银行经营质量画像" if is_bank else "资本配置画像"}</h2>
      <p class="section-intro">{"银行的核心竞争力在于 ROA × 杠杆 = ROE 的拆解质量、息差稳定性、资产质量（拨备充足度）和成本控制能力。" if is_bank else "巴菲特认为，管理层最重要的工作是资本配置。这里用 RORE（留存收益回报率）和 ROIC × 分红 矩阵来判断公司是否善于把留存利润变成更多盈利。"}</p>
      <div class="module-note">{html.escape(quality_notes.get("capital_allocation", ""))}</div>
      <div class="metrics-grid">{capital_allocation_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "ROA", "ROE", "NIM(代理)", "拨贷比", "成本收入比", "存贷比"] if is_bank else ["年份", "ROIC", "派息率", "RORE(滚动3年)", "配置画像"], cap_alloc_rows if cap_alloc_rows else [["N/A"] * (7 if is_bank else 5)])}
      </div>
    </section>

    <section class="section">
      <h2>股本质量雷达</h2>
      <p class="section-intro">这一部分从巴菲特和芒格的“每股内在价值”视角看股本：公司有没有稀释老股东，回购是否真的减少股本，未来解禁是否带来供给压力，以及每一股背后的利润和现金流有没有变厚。</p>
      <div class="module-note">{html.escape(str(share_capital.get("note") or ""))}</div>
      <div class="metrics-grid">{share_capital_cards_html}</div>
      <div class="table-wrap">
        {render_table(["年份", "总股本", "流通股本", "流通比例", "总股本同比", "真实稀释同比", "变动性质", "流通股本同比", "Real EPS", "每股OCF", "每股OE", "每股净资产", "净回购现金"], share_capital_rows if share_capital_rows else [["N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]])}
      </div>
      <div class="table-wrap">
        {render_table(["未来解禁时间", "解禁股数", "占当前流通股本", "解禁股东数", "限售股类型"], unlock_rows)}
      </div>
    </section>

    {profitability_section_html}

    {cash_cycle_section_html}

    {roiic_section_html}

    {wr_section_html}

    <section class="section">
      <h2>指标说明</h2>
      <p class="section-intro">这一部分是给"第一次看这些指标"的场景准备的，避免只看到字母缩写，不知道它到底在说什么。</p>
      <div class="explain-grid">
        {''.join(f'<div class="explain-card"><h3>{html.escape(m.label)} 是什么</h3><p>{html.escape(m.meaning)}</p><p><em>{html.escape(m.implication)}</em></p>' + (f'<p class="formula">{html.escape(m.formula)}</p>' if m.formula else '') + '</div>' for m in list(metrics) + list(ses_metrics) if m.meaning)}
      </div>
    </section>

    <section class="section">
      <h2>结论</h2>
      <p class="section-intro">{'以下结论基于银行核心经营指标（NIM、成本收入比、拨贷比、存贷比、ROA、ROE），不混入估值口径。' if is_bank else '以下结论只基于你指定的提价权指标，不混入估值口径，也不扩展到其他你没有要求的财务模块。'}</p>
      {'<div class="module-note" style="border-left:3px solid #e67e22;background:#fef9e7;">⚠️ 本公司已被识别为 SES 模式企业（规模经济分享型），毛利率偏低是其商业设计的一部分而非缺陷。以下提价权结论中关于毛利率的评价仅作参考，核心评分已切换至 SES 维度。请重点参阅 SES 结论。</div>' if not is_bank and decision_summary.get('is_ses_archetype') else ''}
      <ul>{conclusion_html}</ul>
    </section>

    <section class="section">
      <h2>估值公式</h2>
      <p class="section-intro">这部分放在最后，方便你在需要追公式时再回看，不打断前面的估值判断阅读。</p>
    {valuation_formula_html}
        <div class="explain-card">
          <h3>CAGR、PEG 与 PEGY</h3>
          <p><strong>CAGR = (Ending / Beginning)^(1/n) - 1</strong>，用于平滑利润或 EPS 的多年增长。</p>
          <p><strong>PEG = PE / CAGR</strong>，<strong>PEGY = PE / (CAGR + Yield)</strong>。对高分红成熟公司，PEGY 往往比 PEG 更贴近真实股东回报。</p>
        </div>
        <div class="explain-card">
          <h3>SGR 交叉校验</h3>
          <p><strong>SGR = ROE × (1 - 派息率)</strong>，它不是这份报告里 PEG 的主增长率口径，但会作为内生增长的交叉校验。</p>
          <p>这样既能避免单年波动，也不会完全忽略企业自身资本回流带来的增长能力。</p>
        </div>
        <div class="explain-card">
          <h3>机会成本</h3>
          <p><strong>盈利率 = 1 / PE = EPS / Price</strong>。</p>
          <p>把股票盈利率与 <strong>10 年期国债收益率 + 3%~5%</strong> 比较，看风险资产是否给出了足够补偿。</p>
        </div>
      </div>
    </section>

    {_render_share_basis_section(diagnostics, is_us=(not str(code).endswith('.HK') and not str(code).isdigit()))}

    <!-- BEGIN_SECTION: ai_machine_summary -->
    <section class="section">
      <h2>机器摘要（AI解析）</h2>
      <p class="section-intro">该模块为模型解析准备，保留稳定键名与结构化表格，便于自动提取关键结论。</p>
      <!-- KEY: dcf_intrinsic_value -->
      <!-- KEY: munger_intrinsic_value_mid -->
      <!-- KEY: gordon_intrinsic_value -->
      <!-- KEY: resonance_count -->
      <!-- KEY: confidence_level -->
      <div class="table-wrap">
        {machine_summary_table_html}
      </div>
    </section>
    <!-- END_SECTION: ai_machine_summary -->

    {_render_data_quality_section(data_quality)}

  </div>
</body>
</html>"""

