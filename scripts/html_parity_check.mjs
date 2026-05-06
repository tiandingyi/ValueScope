import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const valuescopeUrl = process.env.VALUESCOPE_URL ?? "http://127.0.0.1:5173/#overview";
const referenceUrl =
  process.env.REFERENCE_HTML_URL ??
  "file:///Users/dingyitian/Desktop/stock-scripts/reports/pricing_power/2025_%E4%BA%94%20%E7%B2%AE%20%E6%B6%B2_000858_pricing_power.html";
const outDir = path.resolve("test-results");

const requiredValueScopeSections = [
  "data_quality",
  "machine_summary",
  "share_basis",
  "technicals",
  "valuation_scenarios",
  "valuation_formulas",
  "radar_modules",
  "cash_flow",
  "capital_safety",
  "shareholder_returns",
];

async function inspectPage(page, url, name) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 45_000 });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: path.join(outDir, `html-compare-${name}-desktop.png`), fullPage: true });
  const desktop = await page.evaluate(() => ({
    h2: Array.from(document.querySelectorAll("h2")).map((node) => node.textContent?.trim() ?? ""),
    tables: document.querySelectorAll("table").length,
    svgs: document.querySelectorAll("svg").length,
    sections: document.querySelectorAll("section, article.section").length,
    bodyScrollWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
    textLength: document.body.innerText.length,
  }));
  await page.setViewportSize({ width: 390, height: 900 });
  await page.screenshot({ path: path.join(outDir, `html-compare-${name}-mobile.png`), fullPage: true });
  const mobile = await page.evaluate(() => ({
    bodyScrollWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
    overflowingElements: Array.from(document.querySelectorAll("body *"))
      .filter((node) => node.scrollWidth > window.innerWidth + 1)
      .slice(0, 10)
      .map((node) => ({
        tag: node.tagName.toLowerCase(),
        id: node.id || null,
        className: typeof node.className === "string" ? node.className : "",
        scrollWidth: node.scrollWidth,
      })),
  }));
  return { url, desktop, mobile };
}

await fs.mkdir(outDir, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const valuescope = await inspectPage(page, valuescopeUrl, "valuescope");
  const reference = await inspectPage(page, referenceUrl, "reference");
  await page.goto(valuescopeUrl, { waitUntil: "networkidle", timeout: 45_000 });
  const sectionPresence = {};
  for (const id of requiredValueScopeSections) {
    sectionPresence[id] = await page.locator(`#${id}`).count();
  }
  const report = {
    generated_at: new Date().toISOString(),
    valuescope,
    reference,
    required_sections: requiredValueScopeSections.map((id) => ({
      id,
      present: Number(sectionPresence[id] ?? 0) > 0,
    })),
    checks: {
      valuescope_mobile_overflow: valuescope.mobile.bodyScrollWidth > valuescope.mobile.viewportWidth,
      reference_mobile_overflow: reference.mobile.bodyScrollWidth > reference.mobile.viewportWidth,
      valuescope_table_count: valuescope.desktop.tables,
      reference_table_count: reference.desktop.tables,
    },
  };
  await fs.writeFile(path.join(outDir, "html-compare-report.json"), JSON.stringify(report, null, 2));

  const missing = report.required_sections.filter((section) => !section.present).map((section) => section.id);
  if (missing.length > 0) {
    throw new Error(`Missing required ValueScope sections: ${missing.join(", ")}`);
  }
  if (report.checks.valuescope_mobile_overflow) {
    throw new Error(`ValueScope mobile overflow: ${valuescope.mobile.bodyScrollWidth}px > ${valuescope.mobile.viewportWidth}px`);
  }
  console.log(JSON.stringify(report.checks, null, 2));
} finally {
  await browser.close();
}
