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
    expect(screen.getByText("估值锚点")).toBeInTheDocument();
    expect(screen.getByText("市场环境：利率与股债性价比")).toBeInTheDocument();
    expect(screen.getByText("PE 近十年历史分位")).toBeInTheDocument();
    expect(screen.getByText("E（EPS）近十年历史分位")).toBeInTheDocument();
    expect(screen.getByText("现金流质量")).toBeInTheDocument();
    expect(screen.getAllByText("股东回报").length).toBeGreaterThan(0);
    expect(screen.getByText("所有者收益率历史")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});
