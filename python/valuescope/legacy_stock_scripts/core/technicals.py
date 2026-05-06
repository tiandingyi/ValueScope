# core/technicals.py — auto-extracted
from __future__ import annotations

import html
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

import akshare as ak
import pandas as pd
import requests

from valuescope.legacy_stock_scripts.core.cache import disk_cache
from valuescope.legacy_stock_scripts.core.config import (
    DISCOUNT_RATE, TERMINAL_GROWTH, PROJECTION_YEARS,
    _dp, A_MARKET_PE_SAMPLE,
)
from valuescope.legacy_stock_scripts.core.utils import (
    safe_float, fmt_pct, fmt_num, series_values, trend_text,
    _tencent_symbol_prefix,
)
from valuescope.legacy_stock_scripts.core.data_a import (
    get_company_info, get_current_price,
    fetch_stock_daily_hist_long,
    _stock_zh_a_spot_em_cached, fetch_market_pe_anchor,
    _close_column,
)


# ---------------------------------------------------------------------------
# 磁盘缓存：市场环境数据（国债收益率历史 + 沪深300 PE）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
@disk_cache(ttl_days=1)
def _bond_zh_us_rate_hist_cached(start_date: str = "20160101") -> Optional[pd.DataFrame]:
    """获取国债收益率历史（含中国、美国），带磁盘缓存。"""
    try:
        return ak.bond_zh_us_rate(start_date=start_date)
    except Exception:
        return None

@lru_cache(maxsize=1)
@disk_cache(ttl_days=1)
def _stock_index_pe_lg_cached(symbol: str = "沪深300") -> Optional[pd.DataFrame]:
    """获取沪深300 PE 历史，带磁盘缓存。"""
    try:
        return ak.stock_index_pe_lg(symbol=symbol)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Williams %R 技术指标模块
# ---------------------------------------------------------------------------

def build_williams_r(code: str, days: int = 180) -> Optional[Dict]:
    """获取最近交易日数据并计算 14/28/60 日 Williams %R 序列。

    返回 dict: {
      "asof": str,                       # 数据截止日期
      "periods": [14, 28, 60],
      "dates": [str, ...],               # 最后 120 个交易日的日期
      "close": [float, ...],             # 对应收盘价
      "wr": {14: [float|None,...], 28: [...], 60: [...]},
      "latest": {14: float, 28: float, 60: float},
      "crossings": [...],                # 交叉事件列表
    }
    """
    code6 = str(code).zfill(6)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)
    df = pd.DataFrame()

    # --- 通用入口：使用 data_a.fetch_stock_daily_hist_long，
    #     港股/美股时自动 dispatch 到 _dp.fetch_stock_daily_hist_long ---
    try:
        years_back = max(1, days // 365 + 1)
        got = fetch_stock_daily_hist_long(code, years_back=years_back)
        if got is not None and not got.empty:
            if "日期" in got.columns:
                got = got.copy()
                got["日期"] = got["日期"].astype(str).str[:10]
                got = got.sort_values("日期").reset_index(drop=True)
                mask = got["日期"] >= start_ts.strftime("%Y-%m-%d")
                got = got[mask].reset_index(drop=True)
            if not got.empty and all(c in got.columns for c in ("日期", "收盘", "最高", "最低")):
                df = got
    except Exception:
        pass

    # --- A股 fallback：腾讯行情 (OHLC)，仅当非港股/美股模式时使用 ---
    _is_a_share = _dp.fetch_stock_daily_hist_long is None
    if df.empty and _is_a_share:
        try:
            import requests as _req
            sym = f"{_tencent_symbol_prefix(code6)}{code6}"
            url = (
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
                f"param={sym},day,{start_ts.strftime('%Y-%m-%d')},{end_ts.strftime('%Y-%m-%d')},640,nfq"
            )
            r = _req.get(url, timeout=12, headers={"Referer": "https://gu.qq.com"})
            blob = (r.json().get("data") or {}).get(sym) or {}
            rows = blob.get("day") or []
            if rows:
                records = []
                for row in rows:
                    if not row or len(row) < 5:
                        continue
                    try:
                        records.append({
                            "日期": str(row[0]),
                            "收盘": float(row[2]),
                            "最高": float(row[3]),
                            "最低": float(row[4]),
                        })
                    except (TypeError, ValueError):
                        continue
                if records:
                    df = pd.DataFrame(records)
        except Exception:
            pass

    # --- A股 fallback：akshare ---
    if df.empty and _is_a_share:
        for attempt in range(3):
            try:
                got = ak.stock_zh_a_hist(symbol=code6, period="daily",
                                         start_date=start_ts.strftime("%Y%m%d"),
                                         end_date=end_ts.strftime("%Y%m%d"), adjust="")
                if got is not None and not got.empty:
                    df = got
                    break
            except Exception:
                pass
            time.sleep(0.5 + attempt * 0.4)

    if df.empty or len(df) < 60:
        return None

    df = df.sort_values("日期").reset_index(drop=True)
    closes = df["收盘"].astype(float).tolist()
    highs = df["最高"].astype(float).tolist()
    lows = df["最低"].astype(float).tolist()
    dates_all = [str(d)[:10] for d in df["日期"].tolist()]

    periods = [14, 28, 60]
    wr_full: Dict[int, List[Optional[float]]] = {}

    for p in periods:
        series: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < p - 1:
                series.append(None)
                continue
            hh = max(highs[i - p + 1: i + 1])
            ll = min(lows[i - p + 1: i + 1])
            if hh == ll:
                series.append(-50.0)
            else:
                series.append((hh - closes[i]) / (hh - ll) * -100.0)
        wr_full[p] = series

    # 取最后 120 个交易日
    n_display = min(120, len(closes))
    start_idx = len(closes) - n_display
    dates_disp = dates_all[start_idx:]
    close_disp = closes[start_idx:]
    wr_disp: Dict[int, List[Optional[float]]] = {}
    for p in periods:
        wr_disp[p] = wr_full[p][start_idx:]

    latest: Dict[int, Optional[float]] = {}
    for p in periods:
        latest[p] = wr_disp[p][-1] if wr_disp[p] else None

    crossings = _detect_wr_crossings(dates_disp, close_disp, wr_disp, periods)

    asof = dates_disp[-1] if dates_disp else "N/A"
    return {
        "asof": asof,
        "periods": periods,
        "dates": dates_disp,
        "close": close_disp,
        "wr": wr_disp,
        "latest": latest,
        "crossings": crossings,
    }

def _detect_wr_crossings(
    dates: List[str],
    closes: List[float],
    wr: Dict[int, List[Optional[float]]],
    periods: List[int],
) -> List[Dict]:
    """检测 %R 与 -20/-80 的交叉事件。

    返回 [{period, type, date, close, wr_val}, ...]
    type: "超买"（上穿 -20）或 "超卖"（下穿 -80）
    """
    events: List[Dict] = []
    for p in periods:
        series = wr[p]
        for i in range(1, len(series)):
            prev, cur = series[i - 1], series[i]
            if prev is None or cur is None:
                continue
            # 超买：从 <= -20 向上穿越到 > -20
            if prev <= -20 and cur > -20:
                events.append({
                    "period": p,
                    "type": "超买",
                    "date": dates[i],
                    "close": closes[i],
                    "wr_val": cur,
                })
            # 超卖：从 >= -80 向下穿越到 < -80
            if prev >= -80 and cur < -80:
                events.append({
                    "period": p,
                    "type": "超卖",
                    "date": dates[i],
                    "close": closes[i],
                    "wr_val": cur,
                })
    events.sort(key=lambda e: e["date"])
    return events

def _wr_status_label(val: Optional[float]) -> Tuple[str, str]:
    """返回 (状态文本, CSS颜色) 给定 Williams %R 值。"""
    if val is None:
        return "N/A", "#999"
    if val > -20:
        return "超买", "#c0392b"
    if val > -50:
        return "偏强", "#e67e22"
    if val >= -80:
        return "中性", "#2980b9"
    return "超卖", "#27ae60"

def _render_wr_section(wr_data: Optional[Dict]) -> str:
    """渲染完整的 Williams %R HTML 段落（含表格、渐变条、SVG 走势图、交叉事件表）。"""
    if not wr_data:
        return ""

    periods = wr_data["periods"]
    latest = wr_data["latest"]
    dates = wr_data["dates"]
    wr = wr_data["wr"]
    crossings = wr_data["crossings"]
    asof = wr_data["asof"]

    # --- 1) 当前值表格 ---
    table_rows = []
    for p in periods:
        val = latest.get(p)
        label, color = _wr_status_label(val)
        val_str = f"{val:.1f}" if val is not None else "N/A"
        table_rows.append(
            f'<tr><td style="font-weight:600">{p}日</td>'
            f'<td style="font-weight:700;color:{color}">{val_str}</td>'
            f'<td><span style="display:inline-block;padding:2px 10px;border-radius:4px;'
            f'background:{color};color:#fff;font-size:13px">{label}</span></td></tr>'
        )
    summary_table = (
        '<table style="border-collapse:collapse;width:auto;margin:0 auto">'
        '<tr style="border-bottom:2px solid #ddd">'
        '<th style="padding:6px 18px;text-align:left">周期</th>'
        '<th style="padding:6px 18px;text-align:center">%R</th>'
        '<th style="padding:6px 18px;text-align:center">状态</th></tr>'
        + "".join(table_rows)
        + "</table>"
    )

    # --- 2) 渐变条 ---
    mid_val = latest.get(28) or latest.get(14) or -50.0
    bar_pct = (mid_val + 100.0) / 100.0 * 100.0  # -100 -> 0%, 0 -> 100%
    bar_pct = max(0, min(100, bar_pct))
    gradient_bar = f'''
            <div style="margin:16px auto;max-width:500px">
              <div style="position:relative;height:24px;background:linear-gradient(to right,#27ae60 0%,#27ae60 20%,#3498db 20%,#3498db 50%,#e67e22 50%,#e67e22 80%,#c0392b 80%,#c0392b 100%);border-radius:12px;overflow:visible">
                <div style="position:absolute;left:{bar_pct:.1f}%;top:-2px;transform:translateX(-50%);width:4px;height:28px;background:#222;border-radius:2px"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:11px;color:#888;margin-top:2px">
                <span>-100 超卖</span><span>-80</span><span>-50</span><span>-20</span><span>0 超买</span>
              </div>
            </div>'''

    # --- 3) SVG 走势图（只画线，不标注交叉点） ---
    n = len(dates)
    if n < 2:
        svg_chart = ""
    else:
        w, h = 580, 150
        x_step = w / max(n - 1, 1)
        # y 映射：%R 从 0（顶）到 -100（底），留 padding
        pad_top, pad_bot = 14, 16
        chart_h = h - pad_top - pad_bot

        def wr_to_y(val: float) -> float:
            # 0 -> pad_top, -100 -> pad_top + chart_h
            return pad_top + (-val / 100.0) * chart_h

        y_20 = wr_to_y(-20)
        y_80 = wr_to_y(-80)

        colors = {14: "#2980b9", 28: "#e67e22", 60: "#27ae60"}

        lines_svg = []
        # 背景区域
        lines_svg.append(f'<rect x="0" y="{pad_top}" width="{w}" height="{y_20 - pad_top:.1f}" fill="rgba(192,57,43,0.06)"/>')
        lines_svg.append(f'<rect x="0" y="{y_80}" width="{w}" height="{pad_top + chart_h - y_80:.1f}" fill="rgba(39,174,96,0.06)"/>')
        # 阈值线
        lines_svg.append(f'<line x1="0" y1="{y_20:.1f}" x2="{w}" y2="{y_20:.1f}" stroke="#c0392b" stroke-width="0.8" stroke-dasharray="4,3"/>')
        lines_svg.append(f'<line x1="0" y1="{y_80:.1f}" x2="{w}" y2="{y_80:.1f}" stroke="#27ae60" stroke-width="0.8" stroke-dasharray="4,3"/>')
        lines_svg.append(f'<text x="2" y="{y_20 - 3:.1f}" font-size="9" fill="#c0392b">-20 超买</text>')
        lines_svg.append(f'<text x="2" y="{y_80 + 11:.1f}" font-size="9" fill="#27ae60">-80 超卖</text>')

        # 画折线
        for p in periods:
            series = wr[p]
            points = []
            for i in range(n):
                v = series[i]
                if v is not None:
                    x = i * x_step
                    y = wr_to_y(v)
                    points.append(f"{x:.1f},{y:.1f}")
            if points:
                lines_svg.append(
                    f'<polyline points="{" ".join(points)}" fill="none" '
                    f'stroke="{colors[p]}" stroke-width="1.5" stroke-linejoin="round" opacity="0.85"/>'
                )

        # 最新点
        for p in periods:
            v = latest.get(p)
            if v is not None:
                x = (n - 1) * x_step
                y = wr_to_y(v)
                lines_svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{colors[p]}" stroke="#fff" stroke-width="1"/>')

        # 图例
        legend_x = 10
        legend_y = h - 2
        for p in periods:
            lines_svg.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 20}" y2="{legend_y}" stroke="{colors[p]}" stroke-width="2"/>')
            lines_svg.append(f'<text x="{legend_x + 24}" y="{legend_y + 4}" font-size="10" fill="{colors[p]}">{p}日</text>')
            legend_x += 70

        svg_chart = f'''
            <div style="margin:16px auto;max-width:620px;text-align:center">
              <svg viewBox="0 0 {w} {h}" style="width:100%;max-width:600px;height:auto;background:#fafbfc;border-radius:8px;border:1px solid #eee">
                {"".join(lines_svg)}
              </svg>
              <div style="font-size:11px;color:#999;margin-top:4px">Williams %R 三周期走势（最近{n}个交易日）</div>
            </div>'''

    # --- 4) 交叉事件表（放在图下方） ---
    crossing_html = ""
    if crossings:
        c_rows = []
        for c in crossings:
            color = "#c0392b" if c["type"] == "超买" else "#27ae60"
            c_rows.append(
                f'<tr>'
                f'<td style="font-weight:600">{c["period"]}日</td>'
                f'<td><span style="display:inline-block;padding:1px 8px;border-radius:4px;'
                f'background:{color};color:#fff;font-size:12px">{c["type"]}</span></td>'
                f'<td>{c["date"][5:]}</td>'
                f'<td>¥{c["close"]:.2f}</td>'
                f'<td>{c["wr_val"]:.1f}</td>'
                f'</tr>'
            )
        crossing_html = f'''
      <div style="margin-top:12px">
        <h3 style="font-size:14px;margin:8px 0 4px">超买/超卖穿越记录</h3>
        <table style="border-collapse:collapse;width:100%;font-size:13px">
          <thead>
            <tr style="border-bottom:2px solid #ddd;text-align:left">
              <th style="padding:6px 10px">周期</th>
              <th style="padding:6px 10px">类型</th>
              <th style="padding:6px 10px">日期</th>
              <th style="padding:6px 10px">收盘价</th>
              <th style="padding:6px 10px">%R</th>
            </tr>
          </thead>
          <tbody>{"".join(c_rows)}</tbody>
        </table>
      </div>'''

    # --- 5) 公式说明 ---
    formula_html = '''
      <div style="margin-top:12px;padding:10px;background:#f8f9fa;border-radius:6px;font-size:12px;color:#666">
        <strong>公式</strong>：%R = (N日最高价 &minus; 收盘价) / (N日最高价 &minus; N日最低价) &times; (&minus;100)<br>
        <strong>区间</strong>：-100（极度超卖）&rarr; 0（极度超买）<br>
        <strong>提示</strong>：%R 是纯技术指标，不替代基本面估值判断。超卖不等于买入信号，超买不等于卖出信号。应结合本报告的 DCF / 芒格估值综合考量。
      </div>'''

    return f'''
    <section class="section">
      <h2>技术指标</h2>
      <p class="section-intro">Williams %R（威廉指标）衡量当前收盘价在N日最高-最低价区间中的位置。超卖（%R &lt; -80）常出现在价格低点附近，超买（%R &gt; -20）常出现在价格高点附近。此处提供 14日/28日/60日 三个周期，帮助判断短中长期动量。数据截至 {html.escape(asof)}。</p>
      {summary_table}
      {gradient_bar}
      {svg_chart}
      {crossing_html}
      {formula_html}
    </section>'''

# ---------------------------------------------------------------------------
# 市场环境：十年期国债收益率 + 股债性价比
# ---------------------------------------------------------------------------

def build_market_env(pe_current: Optional[float] = None) -> Optional[Dict]:
    """获取十年期国债收益率历史 + 沪深 300 PE，计算股债性价比。

    返回 dict:
      bond_dates, bond_values          - 国债收益率时间序列
      bond_latest, bond_latest_date    - 最新值
      bond_pctile                      - 历史分位
      bond_min, bond_max, bond_mean    - 统计
      bond_label                       - 国债标签（中国/美国）
      csi300_pe, csi300_ey             - 沪深 300 PE/盈利率
      erp                              - 风险溢价 (盈利率 - 国债)
      erp_stock                        - 个股风险溢价 (如 pe_current 有值)
      env_label                        - 市场环境文字概括
    """
    _is_hk_us = _dp.fetch_risk_free_yield is not None

    bond_df = _bond_zh_us_rate_hist_cached("20160101")
    csi_df = _stock_index_pe_lg_cached("沪深300")

    # --- 国债收益率 ---
    col = "美国国债收益率10年" if _is_hk_us else "中国国债收益率10年"
    bond_label = "美国十年期国债收益率" if _is_hk_us else "中国十年期国债收益率"
    if bond_df is None or bond_df.empty or col not in bond_df.columns:
        return None

    bond_df = bond_df.dropna(subset=[col]).copy()
    if len(bond_df) < 30:
        return None

    bond_dates = [str(d)[:10] for d in bond_df["日期"].tolist()]
    bond_values = [float(v) for v in bond_df[col].tolist()]
    bond_latest = bond_values[-1]
    bond_latest_date = bond_dates[-1]
    bond_pctile = sum(1 for v in bond_values if v < bond_latest) / len(bond_values) * 100
    bond_min = min(bond_values)
    bond_max = max(bond_values)
    bond_mean = sum(bond_values) / len(bond_values)

    # --- 沪深 300 PE ---
    csi300_pe = None
    csi300_ey = None
    if csi_df is not None and not csi_df.empty and "滚动市盈率" in csi_df.columns:
        pe_vals = csi_df["滚动市盈率"].dropna()
        if not pe_vals.empty:
            csi300_pe = float(pe_vals.iloc[-1])
            csi300_ey = 1.0 / csi300_pe * 100 if csi300_pe > 0 else None

    # --- 风险溢价 ---
    erp = (csi300_ey - bond_latest) if csi300_ey is not None else None
    erp_stock = None
    if pe_current is not None and pe_current > 0:
        erp_stock = (1.0 / pe_current * 100) - bond_latest

    # --- 环境标签 ---
    if erp is not None:
        if erp >= 5:
            env_label = "股市极度低估，股债性价比极高"
        elif erp >= 3:
            env_label = "股市具备吸引力，风险溢价充足"
        elif erp >= 1:
            env_label = "股市合理偏贵，风险溢价偏薄"
        else:
            env_label = "股市偏贵，债券更具吸引力"
    elif bond_latest < 2.0:
        env_label = "低利率资产荒环境，估值中枢可能抬升"
    elif bond_latest > 3.5:
        env_label = "高利率紧缩环境，估值承压"
    else:
        env_label = "利率中性区间"

    return {
        "bond_dates": bond_dates,
        "bond_values": bond_values,
        "bond_latest": bond_latest,
        "bond_latest_date": bond_latest_date,
        "bond_pctile": bond_pctile,
        "bond_min": bond_min,
        "bond_max": bond_max,
        "bond_mean": bond_mean,
        "bond_label": bond_label,
        "csi300_pe": csi300_pe,
        "csi300_ey": csi300_ey,
        "erp": erp,
        "erp_stock": erp_stock,
        "env_label": env_label,
    }

def _render_market_env_section(env_data: Optional[Dict]) -> str:
    """渲染市场环境段落：国债走势图 + 股债性价比 + 利率分位。"""
    if not env_data:
        return ""

    bond_dates = env_data["bond_dates"]
    bond_values = env_data["bond_values"]
    latest = env_data["bond_latest"]
    latest_date = env_data["bond_latest_date"]
    pctile = env_data["bond_pctile"]
    bond_min = env_data["bond_min"]
    bond_max = env_data["bond_max"]
    bond_mean = env_data["bond_mean"]
    bond_label = env_data.get("bond_label", "十年期国债收益率")
    bond_label_short = bond_label.replace("十年期国债收益率", "10Y国债")
    csi300_pe = env_data["csi300_pe"]
    csi300_ey = env_data["csi300_ey"]
    erp = env_data["erp"]
    erp_stock = env_data["erp_stock"]
    env_label = env_data["env_label"]

    # --- 色彩 ---
    if erp is not None and erp >= 3:
        env_color = "#27ae60"
    elif erp is not None and erp >= 1:
        env_color = "#e67e22"
    elif erp is not None:
        env_color = "#c0392b"
    else:
        env_color = "#2980b9"

    # --- 概要指标卡片 ---
    cards = []
    cards.append(f'''<div style="flex:1;min-width:140px;padding:10px;background:#f9f9f9;border-radius:6px;text-align:center;">
      <div style="font-size:12px;color:#888;">{bond_label_short}</div>
      <div style="font-size:22px;font-weight:700;color:#2c3e50;">{latest:.2f}%</div>
      <div style="font-size:11px;color:#aaa;">{latest_date}</div>
    </div>''')
    cards.append(f'''<div style="flex:1;min-width:140px;padding:10px;background:#f9f9f9;border-radius:6px;text-align:center;">
      <div style="font-size:12px;color:#888;">历史分位</div>
      <div style="font-size:22px;font-weight:700;color:{"#27ae60" if pctile < 30 else "#c0392b" if pctile > 70 else "#e67e22"};">{pctile:.1f}%</div>
      <div style="font-size:11px;color:#aaa;">近10年 ({bond_min:.2f}~{bond_max:.2f}%)</div>
    </div>''')
    if csi300_pe is not None:
        cards.append(f'''<div style="flex:1;min-width:140px;padding:10px;background:#f9f9f9;border-radius:6px;text-align:center;">
      <div style="font-size:12px;color:#888;">沪深300 PE(TTM)</div>
      <div style="font-size:22px;font-weight:700;color:#2c3e50;">{csi300_pe:.1f}x</div>
      <div style="font-size:11px;color:#aaa;">盈利率 {csi300_ey:.2f}%</div>
    </div>''')
    if erp is not None:
        cards.append(f'''<div style="flex:1;min-width:140px;padding:10px;background:#f9f9f9;border-radius:6px;text-align:center;">
      <div style="font-size:12px;color:#888;">股债风险溢价</div>
      <div style="font-size:22px;font-weight:700;color:{env_color};">{erp:.2f}%</div>
      <div style="font-size:11px;color:#aaa;">{env_label}</div>
    </div>''')
    cards_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:12px 0;">' + ''.join(cards) + '</div>'

    # --- 个股风险溢价行 ---
    stock_erp_html = ""
    if erp_stock is not None:
        s_color = "#27ae60" if erp_stock >= 5 else "#e67e22" if erp_stock >= 3 else "#c0392b" if erp_stock >= 0 else "#c0392b"
        s_label = "显著跑赢国债" if erp_stock >= 5 else "达到风险溢价要求" if erp_stock >= 3 else "利差偏薄" if erp_stock >= 0 else "不如国债"
        stock_erp_html = f'''<div style="margin:8px 0;padding:8px 14px;background:#f0f7ff;border-left:4px solid {s_color};border-radius:4px;font-size:13px;">
      <strong>本股风险溢价：</strong>{erp_stock:.2f}%（{s_label}）
    </div>'''

    # --- SVG 走势图 ---
    # 采样到最多 500 点以提高渲染速度
    n = len(bond_dates)
    step = max(1, n // 500)
    d_s = bond_dates[::step]
    v_s = bond_values[::step]
    if bond_dates[-1] != d_s[-1]:
        d_s.append(bond_dates[-1])
        v_s.append(bond_values[-1])

    w, h_svg = 700, 200
    pad_l, pad_r, pad_t, pad_b = 50, 20, 15, 35
    plot_w = w - pad_l - pad_r
    plot_h = h_svg - pad_t - pad_b

    y_min_raw = min(v_s) * 0.95
    y_max_raw = max(v_s) * 1.05
    y_range = y_max_raw - y_min_raw if y_max_raw != y_min_raw else 1

    def sx(i):
        return pad_l + i / max(1, len(v_s) - 1) * plot_w

    def sy(v):
        return pad_t + (1 - (v - y_min_raw) / y_range) * plot_h

    # 走势线
    pts = ' '.join(f'{sx(i):.1f},{sy(v):.1f}' for i, v in enumerate(v_s))

    # Y 轴刻度
    y_ticks_html = ""
    n_yticks = 5
    for j in range(n_yticks + 1):
        yv = y_min_raw + y_range * j / n_yticks
        yp = sy(yv)
        y_ticks_html += f'<text x="{pad_l - 4}" y="{yp + 3}" text-anchor="end" font-size="10" fill="#888">{yv:.1f}%</text>'
        y_ticks_html += f'<line x1="{pad_l}" y1="{yp}" x2="{w - pad_r}" y2="{yp}" stroke="#eee" stroke-width="0.5"/>'

    # X 轴标签（取 5 个时间点）
    x_labels_html = ""
    for j in range(5):
        idx = int(j * (len(d_s) - 1) / 4)
        xp = sx(idx)
        x_labels_html += f'<text x="{xp}" y="{h_svg - 5}" text-anchor="middle" font-size="10" fill="#888">{d_s[idx][:7]}</text>'

    # 最新值标注
    last_x = sx(len(v_s) - 1)
    last_y = sy(v_s[-1])

    # 均值线
    mean_y = sy(bond_mean)
    mean_line = f'<line x1="{pad_l}" y1="{mean_y}" x2="{w - pad_r}" y2="{mean_y}" stroke="#e67e22" stroke-width="1" stroke-dasharray="6,3"/>'
    mean_label = f'<text x="{w - pad_r + 2}" y="{mean_y + 3}" font-size="9" fill="#e67e22">均值 {bond_mean:.2f}%</text>'

    svg_chart = f'''<div style="margin:12px 0;overflow-x:auto;">
      <svg viewBox="0 0 {w} {h_svg}" style="width:100%;max-width:{w}px;font-family:sans-serif;">
        {y_ticks_html}
        {x_labels_html}
        {mean_line}{mean_label}
        <polyline points="{pts}" fill="none" stroke="#3498db" stroke-width="1.5"/>
        <circle cx="{last_x}" cy="{last_y}" r="3.5" fill="#e74c3c"/>
        <text x="{last_x - 5}" y="{last_y - 8}" font-size="10" fill="#e74c3c" text-anchor="end">{v_s[-1]:.2f}%</text>
      </svg>
    </div>'''

    # --- 利率环境解读表 ---
    env_table = '''<div style="margin:10px 0;font-size:12px;">
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:#f5f5f5;">
          <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">国债收益率趋势</th>
          <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">含义</th>
          <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">对股市影响</th>
        </tr></thead>
        <tbody>
          <tr><td style="padding:4px 8px;border:1px solid #eee;">持续下行</td><td style="padding:4px 8px;border:1px solid #eee;">经济预期变差 / 宽松</td><td style="padding:4px 8px;border:1px solid #eee;">利好成长股，利空银行</td></tr>
          <tr><td style="padding:4px 8px;border:1px solid #eee;">持续上行</td><td style="padding:4px 8px;border:1px solid #eee;">经济预期变好 / 收紧</td><td style="padding:4px 8px;border:1px solid #eee;">利好周期价值，利空高估值</td></tr>
          <tr><td style="padding:4px 8px;border:1px solid #eee;">低位横盘 (&lt;2.5%)</td><td style="padding:4px 8px;border:1px solid #eee;">资产荒</td><td style="padding:4px 8px;border:1px solid #eee;">股市估值中枢抬升</td></tr>
        </tbody>
      </table>
    </div>'''

    # --- 风险溢价公式 ---
    formula_html = f'''<div style="margin:8px 0;padding:8px 12px;background:#f9f9f9;border-radius:4px;font-size:12px;color:#666;">
      <strong>股债风险溢价</strong> = 1÷沪深300PE − {bond_label_short}收益率。 &gt;3% 股市有吸引力，&lt;1% 债券更优。
      当前格雷厄姆指标处于历史 <strong>{pctile:.0f}%</strong> 分位({bond_label_short}视角)，利率越低对应估值空间越大。
    </div>'''

    return f'''<section class="section">
      <h2>市场环境：利率与股债性价比</h2>
      {cards_html}
      {stock_erp_html}
      {svg_chart}
      {env_table}
      {formula_html}
    </section>'''

