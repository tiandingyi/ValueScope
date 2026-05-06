# Sprint 002: Full Report Parity with stock-scripts

Status: Done on 2026-05-06.

Completion evidence:

- Snapshot schema is v0.3 and the committed `000858` sample includes `current_price`, `market_context`, enhanced valuation cards, PE/EPS percentile nodes, valuation history, OE yield history, data-quality panel, share-basis diagnostics, valuation scenarios/formulas, Williams %R, radar modules, and machine summary.
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
- 更新 `docs/report-snapshot-schema.md`（Schema v0.3）。

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
- 快照结构通过 schema v0.3 验证。
- React UI 完整渲染上述所有新板块和增强元素。
- 折线图在桌面（1280px）和移动（375px）视口下均正常显示，无截断。
- 逐年数据表超过20行时可滚动，无溢出。
- Sticky header 在滚动100px后出现，显示公司名+代码+股价。
- 与参考HTML报告同公司截图做视觉对比，信息层级和内容覆盖度达到对等。
- 缺失的 `current_price` 或 `market_context` 不导致白屏或报错，显示"—"或"数据缺失"占位。
- 所有现有测试（Python pytest、Vitest、E2E）继续通过。
- `docs/report-snapshot-schema.md` 更新至 v0.3。
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

## Goal-Mode User Story Cards

### US-006: 报告头增强（股价 + 颜色说明）

Goal:

- 让用户在第一屏立即确认公司、报告范围、当前股价和颜色语义。

Acceptance Criteria:

- Given 快照包含 `current_price`，when 报告加载，then 报告头显示当前股价。
- Given `current_price` 缺失，when 报告加载，then 报告头和 sticky bar 均显示 `—`。
- Given 报告描述包含绿色/黄色/红色，when 页面渲染，then 三个颜色词使用高对比度语义色。
- Given 桌面和移动视口，when 报告头渲染，then 元数据不重叠、不截断。

### US-007: Sticky Report Identity Bar

Goal:

- 让用户滚动到深处时仍能知道当前报告公司、代码和价格口径。

Acceptance Criteria:

- Given 页面滚动小于 100px，when 用户浏览顶部区域，then sticky report bar 不显示。
- Given 页面滚动大于等于 100px，when 用户继续阅读，then sticky report bar 显示公司简称、代码和当前股价。
- Given sticky report bar 显示，when 用户点击顶部章节导航，then 导航仍可点击且不遮挡章节标题。

### US-008: 市场环境板块

Goal:

- 让估值阅读先有利率、市场 PE 和股债风险溢价背景。

Acceptance Criteria:

- Given 快照包含 `market_context`，when 报告加载，then 页面显示国债、历史分位、沪深300 PE 和股债风险溢价。
- Given 国债收益率序列至少 3 个有效点，when 页面渲染，then 显示折线图和当前/均值参考线。
- Given `market_context.details.status = "missing"`，when 页面渲染，then 显示“数据缺失”占位，不渲染空图表。
- Given 移动视口，when 用户查看图表，then 图表可横向滚动且坐标轴不裁切。

### US-009: 估值卡片增强

Goal:

- 让每个估值结论都披露状态、衡量对象和含义，而不是只给一个数字。

Acceptance Criteria:

- Given 估值 item 包含 `badge` 和 `badge_color`，when 页面渲染，then 卡片显示对应状态标签。
- Given item 包含 `what_it_measures`，when 页面渲染，then 显示“衡量什么”说明。
- Given item 包含 `implication`，when 页面渲染，then 显示“背后含义”说明。
- Given 缺少增强字段，when 页面渲染，then 不用硬编码文案伪造解释。

### US-010: PE / EPS 折线图

Goal:

- 让用户用趋势而不是孤立数字理解历史估值和盈利水位。

Acceptance Criteria:

- Given PE 历史 rows 至少 3 个有效点，when 页面渲染，then 显示历史 PE 走势。
- Given EPS 历史 rows 至少 3 个有效点，when 页面渲染，then 显示历史 EPS 趋势。
- Given 有当前值和历史中位值，when 图表渲染，then 显示对应参考线。
- Given 有效点少于 3 个，when 页面渲染，then 显示“数据不足，无法绘图”。

### US-011: 逐年数据表格

Goal:

- 让用户能审计每年数据，而不是只看摘要结论。

Acceptance Criteria:

- Given 逐年 rows 存在，when 页面渲染，then 表格按快照顺序展示完整覆盖年限。
- Given 表格列多于移动视口宽度，when 页面渲染，then 表格横向滚动且首列保持可见。
- Given OE 收益率列存在，when 数值渲染，then `>= 8` 为绿色、`4-8` 为黄色、`< 4` 为红色。
- Given 表格行数很多，when 用户滚动，then 表头固定且阅读不丢失列语义。

### US-012: PE / EPS 历史分位板块

Goal:

- 让用户快速识别当前 PE 和 EPS 在近十年历史中的位置。

Acceptance Criteria:

- Given `pe_percentile` 存在，when 页面渲染，then 显示当前 PE、分位、历史区间、相对中位偏差和走势图。
- Given `eps_percentile` 存在，when 页面渲染，then 显示当前 EPS、分位、历史区间、相对中位偏差和走势图。
- Given 分位大于等于 70%，when 页面渲染，then 显示黄色警示。
- Given 分位大于等于 85%，when 页面渲染，then 显示红色警示。
- Given 分位节点缺失，when 页面渲染，then 显示“分位数据暂缺”。

### US-013: Share-Capital Diagnostics as First-Class Section

Goal:

- 让股本口径、回退原因和估值可信度成为一等公民。

Acceptance Criteria:

- Given 快照包含股本诊断字段，when 页面渲染，then 显示独立股本诊断区块。
- Given 诊断 confidence 为低或存在 fallback reason，when 页面渲染，then 区块显示 warn/fail 语义状态。
- Given 历史股本口径发生回退，when 生成器运行，then 回退原因被写入快照并由 UI 展示。

### US-014: Data-Quality Consistency Contract

Goal:

- 让所有新增板块都有稳定的缺失、警告和不适用状态。

Acceptance Criteria:

- Given `current_price`、`market_context`、`pe_percentile`、`eps_percentile` 或估值增强字段缺失，when UI 渲染，then 显示对应板块的稳定占位文案。
- Given schema 文档，when 开发者查阅，then 能看到每个新增字段的 fallback 规则。
- Given 混合缺失 fixture，when Vitest 运行，then 可断言关键占位和 warning 文案。

### US-015: As-Of Mode Report Surface

Goal:

- 让历史时点报告和当前报告在 UI 上不会混淆。

Acceptance Criteria:

- Given `source.mode = "as_of"`，when 页面渲染，then 报告头和侧栏显示历史时点上下文。
- Given as-of 快照缺少当前市场模块，when 页面渲染，then 明确标记为历史时点不可用或缺失。
- Given as-of fixture，when 测试运行，then 页面不出现当前报告误导性标签。

### US-016: Bank-Branch Report Path

Goal:

- 让银行公司走银行专用指标，避免工业企业公式误用。

Acceptance Criteria:

- Given `company.is_bank = true`，when 快照生成，then 使用银行专用 section set。
- Given 非银行指标不适用，when 页面渲染，then 隐藏或显示 not-applicable 说明。
- Given 银行样本快照，when UI 加载，then 不出现工业公司公式断裂或空白章节。

### US-017: Multi-Market Field Readiness

Goal:

- 让市场、币种和会计单位在报告里始终显性，避免 A 股假设固化。

Acceptance Criteria:

- Given 快照包含 market/currency/accounting_unit，when 页面渲染，then 报告头或侧栏显示这些字段。
- Given 非 CN-A fixture，when 页面渲染，then 标签、单位和价格格式不发生白屏或明显误导。
- Given 缺少市场专属数据，when 页面渲染，then 显示 missing/not-applicable，而不是套用 A 股结论。

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

### D. HTML Parity Gap Cards Created

Date: 2026-05-06

Source:

- Playwright comparison against `/Users/dingyitian/Desktop/stock-scripts/reports/pricing_power/2025_五 粮 液_000858_pricing_power.html`
- Artifacts:
  - `test-results/html-compare-report.json`
  - `test-results/html-compare-valuescope-desktop.png`
  - `test-results/html-compare-reference-desktop.png`
  - `test-results/html-compare-valuescope-mobile.png`
  - `test-results/html-compare-reference-mobile.png`

Created backlog cards:

| Story | Goal | Priority |
|-------|------|----------|
| US-025 | Render share-basis diagnostics as a first-class report section | P0 |
| US-026 | Render structured data quality and confidence panel | P0 |
| US-027 | Reproduce Williams %R technical indicator module | P2 |
| US-028 | Reproduce valuation scenarios, resonance, and formula appendix | P1 |
| US-029 | Restore detailed operating, safety, and shareholder radar modules | P1 |
| US-030 | Add machine summary for AI parsing | P2 |
| US-031 | Add HTML parity QA gate | P1 |

Goal-mode execution order:

1. US-025 and US-026 first because they close the remaining strict Sprint 002 contract and protect data trust.
2. US-031 next so future parity claims are measured instead of impressionistic.
3. US-028 and US-029 after the QA gate, because they expand information density and table coverage.
4. US-027 and US-030 after core report trust and density are stable.

Do not copy known reference bugs back into ValueScope:

- Reference HTML still contains stale `经营现金流 0/20` and `legacy shares` warnings.
- ValueScope has fixed OCF extraction and distinguishes profit/EPS-derived implied shares from true legacy fallback.

### E. Goal-Mode HTML Parity Cards Implemented

Date: 2026-05-06

Implemented:

| Story | Runtime Outcome | Status |
|-------|-----------------|--------|
| US-025 | `share_basis` snapshot section plus React `股本口径诊断`; EPS-derived implied shares and true legacy fallback are labeled separately. | Done |
| US-026 | `data_quality` section with field coverage bars, model availability chips, warning summary, and share-basis confidence. | Done |
| US-027 | Williams %R technical section with 14/28/60 day values, trend chart, and crossing-event table. | Done |
| US-028 | Valuation scenario matrix, low-valuation resonance details, and valuation formula appendix. | Done |
| US-029 | Focused radar module table for operating, valuation, share-capital, and shareholder-return signals. | Done |
| US-030 | `machine_summary` section for stable downstream parsing; explicitly marked research-only. | Done |
| US-031 | `npm run test:parity` Playwright gate writes screenshots and `test-results/html-compare-report.json`. | Done |

Verification:

- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run test:parity`

Parity result:

- ValueScope mobile overflow: `false`.
- Reference mobile overflow: `true`.
- ValueScope table count after implementation: 16.
- Required parity sections checked by the QA gate: `data_quality`, `machine_summary`, `share_basis`, `technicals`, `valuation_scenarios`, `valuation_formulas`, `radar_modules`, `cash_flow`, `capital_safety`, `shareholder_returns`.

### F. Goal-Mode UX Correction Cards Implemented

Date: 2026-05-06

Source:

- Live critique of `http://127.0.0.1:5173/#overview`.

Created and completed backlog cards:

| Story | Goal | Runtime Outcome | Status |
|-------|------|-----------------|--------|
| US-032 | Move and restyle report controls | Top navbar now keeps only brand; ticker/year/generate controls live in the left rail. | Done |
| US-033 | Move jump directory into left sidebar | Central jump strip removed; left rail contains clickable report directory and E2E verifies `#cash_flow` navigation. | Done |
| US-034 | Reprioritize single-stock sections | Main flow now starts with company/quality/valuation/cash-flow/safety; data quality and machine summary are appendices at the end. | Done |
| US-035 | Add global 10Y yield context | Macro context renamed to a separate global 10Y yield-curve appendix; unavailable countries are labeled as unavailable, not invented. | Done |
| US-036 | Make metric sections colored cards | Major metric sections render boxed red/yellow/green/gray cards with prominent values. | Done |
| US-037 | Make Buffett overview focus on business purity and OE | 巴芒总览 now shows业务纯度 first and discloses the OE/股 basis used in OE收益率 vs 国债. | Done |
| US-038 | Replace ambiguous historical trend block | Unlabeled revenue sparkline replaced by labeled latest-year business signal cards. | Done |
| US-039 | Fix PE/EPS chart readability | Line charts now include axis labels, y-value labels, and unclipped current/median references. | Done |
| US-040 | Color historical tables by trend and quality | EPS/OE/OCF/share and annual quality cells use green/red/yellow trend or threshold coloring. | Done |
| US-041 | Clarify cash-flow meaning and remove source noise | Cash-flow cards explain business meaning; `report_provenance` is removed from the visible cash-flow table; capex intensity is color-coded. | Done |
| US-042 | Improve number units across report | Large money/share numbers are formatted as 亿、万亿、亿股 where appropriate. | Done |
| US-043 | Add capital safety history and missing safety signals | Capital safety now includes historical ROIC, interest coverage, OCF/NI, EPS quality, goodwill, payout, and total-yield rows. | Done |
| US-044 | Expand shareholder returns and Buffett one-dollar test | Shareholder return window now expands to the longest valid confirmed period and includes one-dollar retained-earnings ratio. | Done |
| US-045 | Verify UI corrections with browser QA | Added/updated E2E sidebar navigation assertion and captured `ux-corrections-desktop/mobile.png`; mobile overflow remains false. | Done |

Verification:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 30`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run test:parity`
- Browser screenshots:
  - `test-results/ux-corrections-desktop.png`
  - `test-results/ux-corrections-mobile.png`
