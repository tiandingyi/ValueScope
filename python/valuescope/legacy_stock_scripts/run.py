#!/usr/bin/env python3
"""
统一入口 — 自动判断 A 股 / 港股 / 美股，调用对应数据源生成提价权分析报告。

用法：
  python3 run.py 600519              # A 股贵州茅台
  python3 run.py 000858 --years 8    # A 股五粮液
  python3 run.py 00700.HK            # 港股腾讯
  python3 run.py 3968                # 港股招商银行
  python3 run.py AAPL                # 美股苹果
  python3 run.py COST.US --years 10  # 美股好市多
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _detect_market(raw: str) -> str:
    """根据 ticker 格式判断市场：'a' / 'hk' / 'us'。"""
    s = raw.strip().upper()
    if s.endswith(".HK"):
        return "hk"
    if s.endswith(".US"):
        return "us"
    # 6 位纯数字 → A 股
    if re.fullmatch(r"\d{6}", raw.strip()):
        return "a"
    # 1-5 位纯数字 → 港股
    if raw.strip().isdigit() and 1 <= len(raw.strip()) <= 5:
        return "hk"
    # 纯英文字母 → 美股
    if re.fullmatch(r"[A-Za-z]+", raw.strip()):
        return "us"
    return "us"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 A 股/港股/美股提价权分析 HTML 报告（自动识别市场）"
    )
    parser.add_argument("ticker", nargs="?", help="股票代码：A股如600519；港股如00700.HK/3968；美股如AAPL/COST.US")
    parser.add_argument("--years", "-y", type=int, default=20, help="展示最近多少个财年，默认 20")
    parser.add_argument("--asof-year", type=int, help="按指定年份做时点回放，只使用该年及以前财报")
    parser.add_argument("--asof-price", type=float, help="时点回放时手工指定当时股价")
    parser.add_argument("--outdir", type=Path, default=None, help="HTML 输出目录（港股/美股默认 reports_hk_us_pricing_power）")
    parser.add_argument("--self-check", action="store_true", help="仅执行脚本自检，不生成报告")
    parser.add_argument("--profile", action="store_true", help="输出各阶段耗时")
    parser.add_argument("--no-cache", action="store_true", help="忽略本地缓存，强制从网络重新获取数据")
    parser.add_argument("--backtest", action="store_true", help="多年时点回放回测模式")
    parser.add_argument("--bt-start", type=int, default=None, help="回测起始年份（默认自动推断）")
    parser.add_argument("--bt-end", type=int, default=None, help="回测截止年份（默认自动推断）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── 缓存开关 ──
    if args.no_cache:
        from core import cache as _cache_mod
        _cache_mod.USE_CACHE = False

    raw = args.ticker.strip() if args.ticker else input("请输入股票代码（如 600519 / 00700.HK / AAPL）：").strip()
    market = _detect_market(raw)

    if market == "a":
        # ---------- A 股 ----------
        from valuescope.legacy_stock_scripts.core.orchestrator import self_check, generate_report, LAST_PROFILE

        self_check()
        if args.self_check:
            print("self-check ok")
            return

        code = raw.strip().zfill(6)

        if args.backtest:
            from valuescope.legacy_stock_scripts.core.backtest import run_backtest, print_backtest_table
            bt = run_backtest(code, start_year=args.bt_start, end_year=args.bt_end, years=max(4, args.years))
            print_backtest_table(bt)
            return

        report_path = generate_report(code, max(4, args.years),
                                      asof_year=args.asof_year,
                                      asof_price=args.asof_price)
    else:
        # ---------- 港股 / 美股 ----------
        from valuescope.legacy_stock_scripts.core.data_hk_us import (
            normalize_ticker,
            patch_pricing_power_for_hk_us,
            DEFAULT_OUTPUT_DIR,
        )
        from valuescope.legacy_stock_scripts.core.orchestrator import self_check, generate_report, LAST_PROFILE

        hk_us_market, code = normalize_ticker(raw)
        outdir = args.outdir if args.outdir is not None else DEFAULT_OUTPUT_DIR
        patch_pricing_power_for_hk_us(hk_us_market, outdir)

        self_check()
        if args.self_check:
            print("self-check ok")
            return

        if args.backtest:
            from valuescope.legacy_stock_scripts.core.backtest import run_backtest, print_backtest_table
            bt = run_backtest(code, start_year=args.bt_start, end_year=args.bt_end, years=max(4, args.years))
            print_backtest_table(bt)
            return

        report_path = generate_report(code, max(4, args.years),
                                      asof_year=args.asof_year,
                                      asof_price=args.asof_price)

    print(report_path)

    if args.profile and LAST_PROFILE:
        print("profile:")
        for key in ("company_info", "load_data", "build_rows", "analysis", "render_write", "total"):
            val = LAST_PROFILE.get(key)
            if val is not None:
                print(f"  {key}: {val:.2f}s")


if __name__ == "__main__":
    main()
