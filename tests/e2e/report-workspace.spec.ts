import { test, expect } from "@playwright/test";

test("loads the sample report workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /五粮液 财报分析报告/ })).toBeVisible();
  await expect(page.locator("#market_context").getByText("全球十年期收益率曲线")).toBeVisible();
  await expect(page.locator(".side-rail").getByRole("link", { name: /现金流质量/ })).toBeVisible();
  await page.locator(".side-rail").getByRole("link", { name: /现金流质量/ }).click();
  await expect(page).toHaveURL(/#cash_flow/);
  await expect(page.locator("#pe_percentile").getByText("PE 近十年历史分位")).toBeVisible();
  await expect(page.locator("#eps_percentile").getByText("E（EPS）近十年历史分位")).toBeVisible();
  await expect(page.locator("#cash_flow").getByText("现金流质量")).toBeVisible();
  await expect(page.locator("#shareholder_returns").getByText("股东回报")).toBeVisible();
  await expect(page.locator("#owner_earnings_yield").getByText("所有者收益率历史")).toBeVisible();
});
