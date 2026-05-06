# Sprint 002: Full Report Parity with stock-scripts

Status: Done on 2026-05-06.

Completion evidence:

- Snapshot schema is v0.2 and the committed `000858` sample includes `current_price`, `market_context`, enhanced valuation cards, PE/EPS percentile nodes, valuation history, and OE yield history.
- React renders the report header, sticky report identity bar, market environment section, valuation badges/explanations, PE/EPS line charts, percentile blocks, and scrollable yearly tables.
- Verified with Python tests, Vitest, production build, Playwright E2E, and desktop/mobile screenshots:
  - `test-results/current-valuescope-sprint2-desktop.png`
  - `test-results/current-valuescope-sprint2-mobile.png`

## Sprint Goal

Reproduce the complete visual and informational richness of the stock-scripts pricing-power HTML report inside ValueScope's React UI. After this sprint, a side-by-side comparison of the two reports for the same company should show equivalent section coverage, data density, chart presence, and context explanations.

## Timebox

Two weeks.

## Background

Sprint 001 delivered a working pipeline: Python snapshot generator → JSON → React renderer. However, a visual comparison against the `2025_五粮液_000858_pricing_power.html` reference shows the following gaps:

| Gap | Priority |
|-----|----------|
| 当前股价缺失（元数据和 sticky header 均无） | P0 |
| 估值卡片缺少状态 badge 和"衡量什么/背后含义"解读 | P0 |
| 颜色说明文字无实际颜色渲染 | P1 |
| 缺少市场环境板块（国债、PE、股债溢价 + 走势图） | P1 |
| 元数据布局为竖排，参考为4列水平并排 | P1 |
| 缺少折线图（国债收益率、历史 PE、EPS 历史） | P1 |
| 缺少逐年数据表格（芒格远景假设、PE 历史等） | P2 |
| 缺少 PE / EPS 历史分位分析板块 | P2 |
| Sticky header 无公司标识和实时股价 | P2 |

## Scope

### 快照层（Python）

- 在 snapshot 中新增 `current_price` 字段（来自 tushare 或 AKShare，允许缺失）。
- 新增 `market_context` 节点：
  - 中国 10Y 国债收益率 + 取数日期
  - 历史分位（近10年）
  - 沪深300 PE(TTM) + 盈利率
  - 股债风险溢价（个股及全市场）
  - 国债收益率时间序列（用于图表）
- 在估值卡片节点中新增：
  - `badge`：字符串，如"满足安全边际"、"25x场景显著高于现价"、"负增长，不加分"
  - `badge_color`："green" | "yellow" | "red" | null
  - `what_it_measures`：衡量什么（简短一句）
  - `implication`：背后含义（含敏感性参数说明）
- 在 PE 历史节点中新增逐年数据数组（年份、EPS、PE、收盘价）。
- 在 OE yield 节点中新增逐年三口径收益率数组。
- 新增 `eps_percentile` 节点：当前E、近十年分位、历史区间、相对中位E、EPS时间序列。
- 新增 `pe_percentile` 节点：当前PE、近十年分位、历史区间、相对中位PE、PE时间序列。
- 更新 `docs/report-snapshot-schema.md`（Schema v0.2）。

### UI 层（React）

**US-006: 报告头 — 当前股价与颜色说明**

- 元数据区改为4列水平布局：股票代码 / 覆盖年份 / 样本年数 / 当前股价（缺失时显示"—"）。
- 报告描述中"绿色"/"黄色"/"红色"三个词用对应颜色文字渲染（`text-green-600`、`text-amber-500`、`text-red-500`）。

**US-007: Sticky Header**

- 滚动时顶部固定栏显示：公司简称 + 代码 + 当前股价。
- 不影响现有 Tab 导航布局。

**US-008: 市场环境板块**

- 在报告顶部（估值板块之前）渲染"市场环境：利率与股债性价比"板块。
- 2×2 指标卡：中国10Y国债 / 历史分位 / 沪深300 PE / 股债风险溢价。
- 个股风险溢价提示行（满足/偏薄/偏高三态，对应绿/黄/红）。
- 国债收益率折线图（使用 Recharts 或 Chart.js）：X轴年月，Y轴收益率（%），含均值虚线和当前值标注。
- 国债趋势解读表（持续下行/持续上行的经济含义）。
- 快照中无 `market_context` 时整个板块显示"数据缺失"占位。

**US-009: 估值卡片增强**

- 每张估值卡右上角显示状态 badge（绿/黄/红色标签）。
- 每张卡片展开"衡量什么"和"背后含义"两段解读文字（从 snapshot 读取，非硬编码）。
- OE-DCF 卡显示敏感性参数（终值占比、g±1pp 影响范围、永续增长率±1pp 影响范围）。

**US-010: 折线图（PE 历史 / EPS 历史）**

- "估值"Tab 下新增"历史 PE 走势"图：X轴年份，Y轴PE倍数，含当前PE和中位PE两条虚参考线及标注。
- "估值"Tab 下新增"历史 EPS 趋势"图：X轴年份，Y轴EPS，含当前EPS和中位EPS标注。
- 图表须在移动视口下横向可滚动，不截断。

**US-011: 逐年数据表格**

- "估值"Tab 下复现芒格远景逐年假设表：年份 / 当时价格 / EPS / 折现率 / CAGR（倒序，最新年在前）。
- "估值"Tab 下复现逐年 PE 历史表：年份 / 收盘价 / EPS / PE / 偏离中位。
- "质量"Tab 下复现逐年三口径 OE 收益率表：年份 / 悲观 / 中性 / 宽松口径（含绿/黄/红着色）。
- 表格超出视口高度时可垂直滚动（限高 480px）。

**US-012: PE / EPS 历史分位板块**

- "估值"Tab 下新增"PE 近十年历史分位"板块：当前PE、近十年分位、历史区间、相对中位PE偏差、走势图。
- "估值"Tab 下新增"E（EPS）近十年历史分位"板块：当前E、近十年分位、历史区间、相对中位E偏差、走势图。
- 分位 ≥ 70% 显示黄色警告，≥ 85% 显示红色警告。

## Definition of Done

- Python 快照生成器能为 `000858` 生成包含 `current_price`、`market_context`、增强估值卡片、PE/EPS分位、逐年数组的快照。
- 快照结构通过 schema v0.2 验证。
- React UI 完整渲染上述所有新板块和增强元素。
- 折线图在桌面（1280px）和移动（375px）视口下均正常显示，无截断。
- 逐年数据表超过20行时可滚动，无溢出。
- Sticky header 在滚动100px后出现，显示公司名+代码+股价。
- 与参考HTML报告同公司截图做视觉对比，信息层级和内容覆盖度达到对等。
- 缺失的 `current_price` 或 `market_context` 不导致白屏或报错，显示"—"或"数据缺失"占位。
- 所有现有测试（Python pytest、Vitest、E2E）继续通过。
- `docs/report-snapshot-schema.md` 更新至 v0.2。
- `docs/progress.md`、`docs/agent-handoff.md`、`docs/working-log.md` 在 sprint 结束前更新。
- 不呈现任何买入/卖出建议措辞。

## User Stories 优先顺序

| Story | 标题 | 优先级 | 依赖 |
|-------|------|--------|------|
| US-006 | 报告头增强（股价 + 颜色说明） | P0 | snapshot current_price 字段 |
| US-009 | 估值卡片 badge + 解读 | P0 | snapshot badge/implication 字段 |
| US-007 | Sticky Header | P1 | US-006 |
| US-008 | 市场环境板块 | P1 | snapshot market_context 节点 |
| US-010 | 折线图 | P1 | snapshot 时间序列数组 |
| US-011 | 逐年数据表格 | P2 | snapshot 逐年数组 |
| US-012 | PE/EPS 历史分位板块 | P2 | snapshot percentile 节点 |

## Sprint Review Demo

Demo 脚本：

1. `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10` 生成增强快照。
2. `npm run dev` 启动前端。
3. 加载快照，逐段截图对比参考 HTML 报告：
   - 报告头：股价存在，颜色说明有色。
   - Sticky header：向下滚动后出现。
   - 市场环境板块：指标卡和折线图可见。
   - 估值卡片：badge 和解读文字可见。
   - 折线图：PE 和 EPS 趋势图可见。
   - 逐年表格：可滚动，所有年份显示。
   - 分位板块：分位数值和着色正确。

## Risks

- 实时股价和国债数据依赖外部 API（tushare / AKShare），需做好缺失降级。
- Recharts / Chart.js 打包体积需评估，避免首屏过慢。
- 逐年数组数据量大时（30+ 年），注意 JSON snapshot 和渲染性能。
- 移动端图表横向滚动实现需细化，防止影响页面竖向滚动手势。

## Post-Review Addendum (Coverage Audit)

Date: 2026-05-06

Purpose: tighten Sprint 002 acceptance quality and close parity-scope blind spots found during the user-story audit.

### A. Tightened AC for Existing Stories (US-006 to US-012)

US-006:

- `current_price` missing -> both report cover and sticky bar must show `—`, and the same fallback formatter must be used in both places.
- Color words (`绿色`/`黄色`/`红色`) must be colorized with contrast-safe tokens and have screenshot evidence in desktop + mobile.

US-007:

- Sticky bar must appear only after scrollY >= 100 and be hidden above that threshold.
- Sticky bar must keep tab navigation clickable and must not cover section headings.

US-008:

- `market_context` missing state must include a machine-checkable marker (`details.status = "missing"`) and visible UI placeholder text.
- Bond chart must render both `bond_mean` and `bond_latest` reference lines when values are present.

US-009:

- Valuation cards must render `badge`, `what_it_measures`, and `implication` from snapshot values only; no hard-coded fallback copy.
- OE-DCF sensitivity text must be sourced from snapshot and tested with one explicit assertion.

US-010:

- Insufficient-series rule is standardized: fewer than 3 valid points -> show `数据不足，无法绘图`.
- Mobile 375px screenshot must show horizontal chart scrolling without clipping axis labels.

US-011:

- OE yearly table must apply value-color thresholds on yield columns: >= 8 green, 4-8 yellow, < 4 red.
- Yearly tables must preserve full year coverage order from snapshot (no implicit slicing).

US-012:

- Percentile warning labels must be visible in both card summary and section tone class.
- Missing percentile node must render `分位数据暂缺` (not generic empty table).

### B. Additional User Stories Required for Parity Completeness

US-013: Share-Capital Diagnostics as First-Class Section (P1)

Goal:

- Promote share-basis diagnostics from mixed details into a dedicated section/table for valuation trustworthiness.

Acceptance Criteria:

- Snapshot includes explicit share-capital diagnostics fields (valuation basis, report basis, fallback reason, confidence).
- UI renders a dedicated share-capital diagnostics block with pass/warn/fail tone.
- Existing regression around historical share basis remains green.

US-014: Data-Quality Consistency Contract (P1)

Goal:

- Ensure every newly added section has deterministic missing/warning/not-applicable behavior.

Acceptance Criteria:

- For `current_price`, `market_context`, `pe_percentile`, `eps_percentile`, and valuation enhancements, each field has a documented fallback state in schema doc.
- UI placeholders are section-specific and stable (no generic blank render).
- Add one test fixture with mixed missing/warning states and assert visible labels.

US-015: As-Of Mode Report Surface (P2)

Goal:

- Expose historical point-in-time report generation and rendering to match reference report workflow depth.

Acceptance Criteria:

- Generator supports as-of mode metadata (`source.mode = as_of`, date/year context).
- UI explicitly shows as-of context and prevents accidental confusion with current mode.
- At least one as-of snapshot sample or test fixture is included.

US-016: Bank-Branch Report Path (P2)

Goal:

- Add explicit bank/non-bank branch handling to avoid metric misuse.

Acceptance Criteria:

- Snapshot includes bank-specific section set when `company.is_bank = true`.
- Non-bank-only metrics are hidden or marked not-applicable for bank companies.
- One bank sample snapshot passes schema and renders without broken sections.

US-017: Multi-Market Field Readiness (P2)

Goal:

- Enforce market/currency/accounting clarity beyond CN-A assumptions.

Acceptance Criteria:

- Header and side metadata always display market/currency/accounting unit from snapshot.
- Formatting logic avoids CN-A-only assumptions in labels/units.
- At least one non-CN-A fixture validates no UI breakage.

### C. Revised Completion Gate for Sprint 002

Sprint 002 is considered fully closed only when:

- US-006 to US-012 tightened AC checks all pass.
- US-013 and US-014 are completed.
- US-015 to US-017 are either completed or formally moved to Sprint 003 with explicit rationale and backlog links.
