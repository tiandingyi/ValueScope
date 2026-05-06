import { test, expect } from "@playwright/test";

test("loads the sample report workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /五粮液 财报分析报告/ })).toBeVisible();
  await expect(page.locator("#market_context").getByText("市场环境：利率与股债性价比")).toBeVisible();
  await expect(page.locator("#pe_percentile").getByText("PE 近十年历史分位")).toBeVisible();
  await expect(page.locator("#eps_percentile").getByText("E（EPS）近十年历史分位")).toBeVisible();
  await expect(page.locator("#cash_flow").getByText("现金流质量")).toBeVisible();
  await expect(page.locator("#shareholder_returns").getByText("股东回报")).toBeVisible();
  await expect(page.locator("#owner_earnings_yield").getByText("所有者收益率历史")).toBeVisible();
});
