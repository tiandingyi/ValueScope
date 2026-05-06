import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import sample from "../public/samples/company_report_snapshot.json";

describe("App", () => {
  it("renders the committed sample report", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        json: async () => sample,
      })),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: /五粮液 财报分析报告/ })).toBeInTheDocument();
    expect(screen.getAllByText("估值锚点").length).toBeGreaterThan(0);
    expect(screen.getAllByText("全球十年期收益率曲线").length).toBeGreaterThan(0);
    expect(screen.getAllByText("业务纯度").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PE 近十年历史分位").length).toBeGreaterThan(0);
    expect(screen.getAllByText("E（EPS）近十年历史分位").length).toBeGreaterThan(0);
    expect(screen.getAllByText("现金流质量").length).toBeGreaterThan(0);
    expect(screen.getAllByText("股东回报").length).toBeGreaterThan(0);
    expect(screen.getAllByText("所有者收益率历史").length).toBeGreaterThan(0);

    vi.unstubAllGlobals();
  });
});
