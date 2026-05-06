import { describe, expect, it } from "vitest";
import { parseReportSnapshot } from "./reportSnapshot";
import sample from "../public/samples/company_report_snapshot.json";

describe("report snapshot schema", () => {
  it("accepts the committed sample snapshot", () => {
    const parsed = parseReportSnapshot(sample);
    expect(parsed.company.ticker).toBe("000858");
    expect(parsed.sections.map((section) => section.id)).toEqual(
      expect.arrayContaining(["market_context", "valuation", "pe_percentile", "eps_percentile", "cash_flow", "capital_safety", "shareholder_returns"]),
    );
    expect(parsed.schema_version).toBe("0.2.0");
    expect(parsed.current_price).toEqual(expect.any(Number));
    expect(parsed.market_context).toBeTruthy();
    expect(parsed.pe_percentile).toBeTruthy();
    expect(parsed.eps_percentile).toBeTruthy();
  });

  it("uses confirmed annual history and excludes unverified latest rows", () => {
    const parsed = parseReportSnapshot(sample);
    const annualRows = parsed.sections.find((section) => section.id === "annual_rows")?.rows ?? [];
    const shareholderRows = parsed.sections.find((section) => section.id === "shareholder_returns")?.rows ?? [];
    expect(parsed.coverage.years.at(-1)).toBe("2024");
    expect(annualRows.every((row) => row.report_type === "annual")).toBe(true);
    expect(annualRows.some((row) => row.year === "2025")).toBe(false);
    expect(shareholderRows.some((row) => row.year === "2025")).toBe(false);
    expect(parsed.warnings.some((warning) => JSON.stringify(warning).includes("2025"))).toBe(true);
  });

  it("rejects unsupported major versions", () => {
    expect(() =>
      parseReportSnapshot({
        ...sample,
        schema_version: "1.0.0",
      }),
    ).toThrow(/Unsupported report snapshot major version/);
  });

  it("preserves unavailable values with explicit status", () => {
    const parsed = parseReportSnapshot(sample);
    const valuation = parsed.sections.find((section) => section.id === "valuation");
    const notApplicable = valuation?.items.find((item) => item.status === "not_applicable");
    expect(notApplicable?.value).toMatch(/不适用/);
    expect(notApplicable?.basis ?? notApplicable?.meaning).toBeTruthy();
    expect(valuation?.items.some((item) => item.badge || item.what_it_measures || item.implication)).toBe(true);
  });
});
