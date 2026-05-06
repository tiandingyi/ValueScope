import { z } from "zod";

const statusSchema = z.enum(["ok", "missing", "not_applicable", "warning", "error"]);

export const reportItemSchema = z.object({
  metric: z.string(),
  label: z.string(),
  value: z.unknown().nullable().optional(),
  status: statusSchema,
  tone: z.string().optional(),
  basis: z.string().nullable().optional(),
  meaning: z.string().nullable().optional(),
  implication: z.string().nullable().optional(),
  warning: z.string().nullable().optional(),
});

export const reportSectionSchema = z.object({
  id: z.string(),
  title: z.string(),
  summary: z.string().nullable().optional(),
  items: z.array(reportItemSchema).default([]),
  rows: z.array(z.record(z.string(), z.unknown())).optional(),
  details: z.unknown().optional(),
  data_quality: z.unknown().optional(),
  warnings: z.array(z.unknown()).default([]),
});

export const reportSnapshotSchema = z.object({
  schema_version: z.string().refine((value) => value.split(".")[0] === "0", {
    message: "Unsupported report snapshot major version",
  }),
  generated_at: z.string(),
  source: z.object({
    name: z.string(),
    provider: z.string().optional(),
    mode: z.string().optional(),
    html_debug_path: z.string().optional(),
    notes: z.string().optional(),
  }),
  company: z.object({
    ticker: z.string(),
    name: z.string(),
    market: z.string(),
    currency: z.string().nullable().optional(),
    accounting_unit: z.string().nullable().optional(),
    is_bank: z.boolean().optional(),
  }),
  coverage: z.object({
    period_type: z.string(),
    years: z.array(z.string()),
    requested_years: z.number().optional(),
    asof_year: z.number().nullable().optional(),
    asof_price: z.number().nullable().optional(),
  }),
  metric_definitions: z.record(z.string(), z.unknown()),
  sections: z.array(reportSectionSchema),
  warnings: z.array(z.unknown()).default([]),
  snapshot_path: z.string().optional(),
});

export type ReportSnapshot = z.infer<typeof reportSnapshotSchema>;
export type ReportSection = z.infer<typeof reportSectionSchema>;
export type ReportItem = z.infer<typeof reportItemSchema>;

export function parseReportSnapshot(input: unknown): ReportSnapshot {
  return reportSnapshotSchema.parse(input);
}

export async function loadSampleSnapshot(): Promise<ReportSnapshot> {
  const response = await fetch("/samples/company_report_snapshot.json");
  const json = await response.json();
  return parseReportSnapshot(json);
}

