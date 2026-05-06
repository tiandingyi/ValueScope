from __future__ import annotations

import argparse
import json
from pathlib import Path

from valuescope.report_snapshot import generate_report_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a ValueScope company report snapshot.")
    parser.add_argument("ticker", nargs="?", default="000858")
    parser.add_argument("--years", "-y", type=int, default=8)
    parser.add_argument("--outdir", type=Path, default=Path("data/report_snapshots"))
    args = parser.parse_args()

    snapshot = generate_report_snapshot(args.ticker, years=args.years, output_dir=args.outdir)
    print(json.dumps({"snapshot_path": snapshot.get("snapshot_path")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

