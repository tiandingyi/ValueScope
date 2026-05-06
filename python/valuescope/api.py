from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from valuescope.report_snapshot import ReportSnapshotError, generate_report_snapshot

app = FastAPI(title="ValueScope Local API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateReportRequest(BaseModel):
    ticker: str = Field(default="000858", min_length=1, max_length=16)
    years: int = Field(default=8, ge=4, le=20)
    asof_year: Optional[int] = Field(default=None, ge=1990, le=2100)
    asof_price: Optional[float] = Field(default=None, gt=0)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate-report")
def generate_report(request: GenerateReportRequest) -> dict[str, object]:
    try:
        snapshot = generate_report_snapshot(
            request.ticker,
            years=request.years,
            asof_year=request.asof_year,
            asof_price=request.asof_price,
            output_dir=Path("data/report_snapshots"),
        )
    except ReportSnapshotError as exc:
        return {
            "ok": False,
            "error": {
                "code": "report_generation_failed",
                "message": str(exc),
            },
        }
    return {
        "ok": True,
        "snapshot": snapshot,
        "snapshot_path": snapshot.get("snapshot_path"),
    }

