import { useEffect, useMemo, useState } from "react";
import {
  loadSampleSnapshot,
  parseReportSnapshot,
  type ReportItem,
  type ReportSnapshot,
  type ReportSection,
} from "./reportSnapshot";

type LoadState =
  | { kind: "empty" }
  | { kind: "loading"; message: string }
  | { kind: "ready"; snapshot: ReportSnapshot }
  | { kind: "error"; message: string };

type GenerateResponse =
  | { ok: true; snapshot: unknown; snapshot_path?: string }
  | { ok: false; error: { code: string; message: string } };

type TableColumn = {
  key: string;
  label: string;
  kind?: "money" | "percent" | "days" | "multiple" | "number" | "text";
};

const SECTION_COPY: Record<string, { title: string; eyebrow: string; summary?: string }> = {
  overview: {
    title: "投资画像总览",
    eyebrow: "核心结论",
    summary: "先读经营质量结论，再看估值锚点和年度数据。以下内容是研究辅助，不构成买卖建议。",
  },
  market_context: {
    title: "全球十年期收益率曲线",
    eyebrow: "宏观利率附录",
    summary: "可验证的十年期国债收益率作为机会成本背景单独展示，不放进单股财报主结论。",
  },
  data_quality: {
    title: "数据质量与置信度",
    eyebrow: "可验证性",
    summary: "把字段覆盖、估值模型可用性、股本口径和排除年度拆开看，任何缺失都不按 0 处理。",
  },
  machine_summary: {
    title: "机器可读摘要",
    eyebrow: "解析接口",
    summary: "面向后续自动解析的事实摘要，只保留数据状态和研究辅助边界。",
  },
  quality: {
    title: "经营质量",
    eyebrow: "盈利能力",
    summary: "观察毛利率、费用吞噬、现金循环和增量资本回报，判断利润质量是否扎实。",
  },
  pricing_power: {
    title: "提价权与运营效率",
    eyebrow: "商业质量",
    summary: "把收入增长、毛利率变化、费用率、资产周转和 ROE 放在一起看，避免只看单一指标。",
  },
  radar_modules: {
    title: "经营与资本雷达模块",
    eyebrow: "拆分扫描",
    summary: "把经营质量、提价权、估值、股本质量和股东回报拆成可扫描模块。",
  },
  valuation: {
    title: "估值锚点",
    eyebrow: "价格与安全边际",
    summary: "多个估值模型交叉验证，任何单一模型都不能作为最终买卖依据。",
  },
  cash_flow: {
    title: "现金流质量",
    eyebrow: "年报现金流",
    summary: "只展示已纳入年度历史的年报行；经营现金流缺失时明确标记，不补 0。",
  },
  capital_safety: {
    title: "资本安全",
    eyebrow: "股本与稀释",
    summary: "检查股本口径、真实稀释、回购有效性和市值基础，用来解释估值风险。",
  },
  share_basis: {
    title: "股本口径诊断",
    eyebrow: "估值分母",
    summary: "单独披露财报股本、EPS 推导隐含股本和 legacy 回退，避免把不同股本来源混为一谈。",
  },
  shareholder_returns: {
    title: "股东回报",
    eyebrow: "分红与留存",
    summary: "分红、回购和留存收益只按已确认年报窗口重算，避免混入未确认年度。",
  },
  annual_rows: {
    title: "年度财务质量",
    eyebrow: "历史数据",
    summary: "年度行保留缺失值，不把缺失数据当作 0。",
  },
  valuation_history: {
    title: "芒格远景逐年假设",
    eyebrow: "逐年估值",
    summary: "逐年查看所有者收益、成长率、分红率和估值模型输出。",
  },
  valuation_scenarios: {
    title: "估值情景与低估共振",
    eyebrow: "场景复核",
    summary: "三档所有者收益、增长率和退出市盈率组合，用来复核估值结构和模型共振。",
  },
  valuation_formulas: {
    title: "估值公式附录",
    eyebrow: "模型口径",
    summary: "把每个估值模型的公式、方向和限制条件独立展示，便于复核。",
  },
  technicals: {
    title: "Williams %R 技术面",
    eyebrow: "价格位置",
    summary: "技术指标只作为价格位置辅助，不构成交易建议。",
  },
  pe_percentile: {
    title: "PE 近十年历史分位",
    eyebrow: "历史估值水位",
    summary: "用次年5月后的收盘价和年度 EPS 还原历史 PE，观察当前估值水位。",
  },
  eps_percentile: {
    title: "E（EPS）近十年历史分位",
    eyebrow: "盈利历史水位",
    summary: "用年度 EPS 样本比较当前盈利在历史中的位置。",
  },
  diagnostics: {
    title: "诊断信息",
    eyebrow: "数据口径",
    summary: "价格、市值、股本和质押等口径用于解释估值基础。",
  },
  owner_earnings_yield: {
    title: "所有者收益率历史",
    eyebrow: "现金回报",
    summary: "保守、基准、宽松三种口径用于观察现金收益率区间。",
  },
  dollar_retention: {
    title: "留存收益检验",
    eyebrow: "股东价值",
    summary: "对照留存利润、分红、回购和市值变化，检查留存收益是否创造价值。",
  },
  metric_explanations: {
    title: "指标说明",
    eyebrow: "公式与含义",
    summary: "每个指标都应披露公式、方向、阈值或解释依据。",
  },
};

const STATUS_LABELS: Record<string, string> = {
  ok: "正常",
  warning: "需关注",
  missing: "缺失",
  not_applicable: "不适用",
  error: "错误",
};

const MODE_LABELS: Record<string, string> = {
  current: "当前报告",
  as_of: "历史时点",
  sample: "样本报告",
};

const SOURCE_LABELS: Record<string, string> = {
  legacy_stock_scripts: "本地生成",
  sample: "内置样本",
};

const TABLE_COLUMNS: Record<string, TableColumn[]> = {
  annual_rows: [
    { key: "year", label: "年份", kind: "text" },
    { key: "revenue", label: "营业收入", kind: "money" },
    { key: "gross_margin", label: "毛利率", kind: "percent" },
    { key: "purity_with_rnd", label: "业务纯度", kind: "percent" },
    { key: "dso", label: "DSO", kind: "days" },
    { key: "dpo", label: "DPO", kind: "days" },
    { key: "ccc", label: "CCC", kind: "days" },
    { key: "capex_net_income", label: "资本开支/净利", kind: "percent" },
    { key: "revenue_growth", label: "收入增速", kind: "percent" },
    { key: "roe", label: "ROE", kind: "percent" },
  ],
  cash_flow: [
    { key: "year", label: "年份", kind: "text" },
    { key: "ocf", label: "经营现金流", kind: "money" },
    { key: "net_income", label: "净利润", kind: "money" },
    { key: "capex", label: "资本开支", kind: "money" },
    { key: "capex_net_income", label: "资本开支/净利", kind: "percent" },
  ],
  valuation_history: [
    { key: "year", label: "年份", kind: "text" },
    { key: "munger_mid", label: "芒格25x", kind: "number" },
    { key: "oe_dcf", label: "OE-DCF", kind: "number" },
    { key: "eps_cagr", label: "EPS复合增速", kind: "percent" },
    { key: "exit_pes", label: "退出PE", kind: "text" },
    { key: "div_yield", label: "股息率", kind: "percent" },
    { key: "peg", label: "PEG", kind: "multiple" },
    { key: "pegy", label: "PEGY", kind: "multiple" },
    { key: "share_basis_used", label: "股本口径", kind: "text" },
  ],
  pe_percentile: [
    { key: "year", label: "年份", kind: "text" },
    { key: "anchor_date", label: "锚点日期", kind: "text" },
    { key: "price", label: "当时价格", kind: "number" },
    { key: "eps", label: "EPS", kind: "number" },
    { key: "pe", label: "PE", kind: "multiple" },
  ],
  eps_percentile: [
    { key: "year", label: "年份", kind: "text" },
    { key: "eps", label: "EPS", kind: "number" },
    { key: "real_eps", label: "真实EPS", kind: "number" },
    { key: "basic_eps", label: "基本EPS", kind: "number" },
    { key: "basis", label: "口径", kind: "text" },
  ],
  owner_earnings_yield: [
    { key: "year", label: "年份", kind: "text" },
    { key: "ma200_price", label: "200日均价", kind: "number" },
    { key: "pess_oe_ps", label: "保守所有者收益/股", kind: "number" },
    { key: "base_oe_ps", label: "基准所有者收益/股", kind: "number" },
    { key: "leni_oe_ps", label: "宽松所有者收益/股", kind: "number" },
    { key: "pess_yield", label: "保守收益率", kind: "percent" },
    { key: "base_yield", label: "基准收益率", kind: "percent" },
    { key: "leni_yield", label: "宽松收益率", kind: "percent" },
  ],
  shareholder_returns: [
    { key: "year", label: "年份", kind: "text" },
    { key: "ni", label: "净利润", kind: "money" },
    { key: "oe", label: "所有者收益", kind: "money" },
    { key: "div", label: "分红", kind: "money" },
    { key: "buyback", label: "回购", kind: "money" },
    { key: "retained_oe", label: "留存OE", kind: "money" },
    { key: "one_dollar_return", label: "一美元检验", kind: "multiple" },
    { key: "price_ma200", label: "200日均价", kind: "number" },
  ],
  radar_modules: [
    { key: "module", label: "模块", kind: "text" },
    { key: "signal", label: "信号", kind: "text" },
    { key: "value", label: "当前值", kind: "text" },
    { key: "status", label: "状态", kind: "text" },
    { key: "basis", label: "口径", kind: "text" },
    { key: "source", label: "来源", kind: "text" },
    { key: "warning", label: "提醒", kind: "text" },
  ],
  data_quality: [
    { key: "field", label: "字段", kind: "text" },
    { key: "present", label: "有值年数", kind: "number" },
    { key: "total", label: "总年数", kind: "number" },
    { key: "pct", label: "覆盖率", kind: "percent" },
  ],
  share_basis: [
    { key: "year", label: "年份", kind: "text" },
    { key: "total_shares", label: "总股本", kind: "number" },
    { key: "economic_total_shares", label: "经济股本", kind: "number" },
    { key: "float_shares", label: "流通股本", kind: "number" },
    { key: "total_yoy", label: "总股本同比", kind: "percent" },
    { key: "economic_total_yoy", label: "经济股本同比", kind: "percent" },
    { key: "real_eps", label: "真实EPS", kind: "number" },
    { key: "ocf_ps", label: "OCF/股", kind: "number" },
    { key: "oe_ps", label: "OE/股", kind: "number" },
    { key: "share_change_label", label: "变动解释", kind: "text" },
  ],
  technicals: [
    { key: "date", label: "日期", kind: "text" },
    { key: "wr_14", label: "14日%R", kind: "number" },
    { key: "wr_28", label: "28日%R", kind: "number" },
    { key: "wr_60", label: "60日%R", kind: "number" },
  ],
  technical_crossings: [
    { key: "date", label: "日期", kind: "text" },
    { key: "period", label: "周期", kind: "number" },
    { key: "type", label: "事件", kind: "text" },
    { key: "close", label: "收盘价", kind: "number" },
    { key: "wr_val", label: "%R", kind: "number" },
  ],
  valuation_formulas: [
    { key: "model", label: "模型", kind: "text" },
    { key: "value", label: "当前值", kind: "text" },
    { key: "formula", label: "公式/规则", kind: "text" },
    { key: "direction", label: "方向", kind: "text" },
    { key: "meaning", label: "衡量什么", kind: "text" },
    { key: "caveat", label: "限制条件", kind: "text" },
    { key: "status", label: "状态", kind: "text" },
  ],
  valuation_scenarios: [
    { key: "owner_earnings_case", label: "OE情景", kind: "text" },
    { key: "owner_earnings_ps", label: "OE/股", kind: "number" },
    { key: "growth_case", label: "增长情景", kind: "text" },
    { key: "growth", label: "增长率", kind: "percent" },
    { key: "dcf_iv", label: "DCF内在价值", kind: "number" },
    { key: "munger_20x", label: "芒格20x", kind: "number" },
    { key: "munger_25x", label: "芒格25x", kind: "number" },
    { key: "munger_30x", label: "芒格30x", kind: "number" },
  ],
  machine_summary: [
    { key: "key", label: "Key", kind: "text" },
    { key: "value", label: "Value", kind: "text" },
    { key: "basis", label: "Basis", kind: "text" },
  ],
  capital_safety: [
    { key: "year", label: "年份", kind: "text" },
    { key: "roic", label: "ROIC", kind: "percent" },
    { key: "interest_coverage", label: "利息保障倍数", kind: "multiple" },
    { key: "interest_tag", label: "利息状态", kind: "text" },
    { key: "ocf_ratio", label: "OCF/净利", kind: "percent" },
    { key: "eps_quality", label: "EPS含金量", kind: "multiple" },
    { key: "goodwill_ratio", label: "商誉/权益", kind: "percent" },
    { key: "payout", label: "派息率", kind: "percent" },
    { key: "total_yield", label: "综合回报率", kind: "percent" },
  ],
};

const DETAIL_LABELS: Record<string, string> = {
  price: "当前价格",
  market_cap: "总市值",
  shares: "估值股本",
  share_capital: "股本诊断",
  pledge: "质押信息",
  pledge_fetch_status: "质押数据状态",
  window_start: "起始年份",
  window_end: "结束年份",
  pre_year_price: "期初价格",
  total_ni: "累计净利润",
  total_oe: "累计所有者收益",
  total_div: "累计分红",
  total_buyback: "累计回购",
  mcap_start: "期初市值",
  mcap_end: "期末市值",
  mva: "市值增加",
  ratio_strict: "严格留存回报",
  ratio_oe: "OE留存回报",
  retained_strict: "严格口径留存",
  retained_oe: "所有者收益口径留存",
  real_retained: "真实留存收益",
  real_retained_note: "留存说明",
  passed_strict: "严格口径通过",
  shares_yi: "股本（亿股）",
  price_start: "期初价格",
  confidence: "置信度",
  confidence_score: "置信分",
  year_range: "年份范围",
  industry_matched: "行业匹配",
  discount_key: "折现参数",
  exit_pe_key: "退出市盈率参数",
  coverage_ratio: "股本覆盖率",
  valuation_count: "估值股本年数",
  eps_derived_years: "EPS推导年份",
  legacy_fallback_years: "Legacy回退年份",
  reported_semantics: "财报股本语义",
  source_policy: "股本来源规则",
  asof: "截至日期",
  periods: "周期",
  latest: "最新值",
  warning_count: "警告数量",
  research_only: "研究辅助",
  advice_policy: "建议边界",
};

export function App() {
  const [ticker, setTicker] = useState("000858");
  const [years, setYears] = useState(8);
  const [state, setState] = useState<LoadState>({ kind: "empty" });

  useEffect(() => {
    void loadSampleSnapshot()
      .then((snapshot) => setState({ kind: "ready", snapshot }))
      .catch(() => setState({ kind: "empty" }));
  }, []);

  async function generateReport() {
    setState({ kind: "loading", message: "正在生成本地报告快照..." });
    try {
      const response = await fetch("/api/generate-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, years }),
      });
      const payload = (await response.json()) as GenerateResponse;
      if (!payload.ok) {
        setState({ kind: "error", message: payload.error.message });
        return;
      }
      const snapshot = parseReportSnapshot(payload.snapshot);
      setState({ kind: "ready", snapshot });
    } catch (error) {
      const message = error instanceof Error ? error.message : "报告生成失败。";
      setState({ kind: "error", message });
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-brand">
          <strong>ValueScope</strong>
          <span>本地价值研究工作台</span>
        </div>
      </header>

      <div className="wrap">
        {state.kind === "empty" && <EmptyState />}
        {state.kind === "loading" && <StatusPanel title="生成中" message={state.message} />}
        {state.kind === "error" && <StatusPanel title="生成失败" message={state.message} tone="error" />}
        {state.kind === "ready" && (
          <ReportView
            snapshot={state.snapshot}
            ticker={ticker}
            years={years}
            isGenerating={false}
            onTickerChange={setTicker}
            onYearsChange={setYears}
            onGenerate={() => void generateReport()}
          />
        )}
      </div>
    </>
  );
}

function EmptyState() {
  return (
    <section className="empty-state">
      <h2>尚未加载报告快照</h2>
      <p>可以生成本地报告，也可以继续查看内置样本。</p>
    </section>
  );
}

function StatusPanel({ title, message, tone }: { title: string; message: string; tone?: "error" }) {
  return (
    <section className={tone === "error" ? "status-panel error" : "status-panel"}>
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}

function ReportView({
  snapshot,
  ticker,
  years,
  isGenerating,
  onTickerChange,
  onYearsChange,
  onGenerate,
}: {
  snapshot: ReportSnapshot;
  ticker: string;
  years: number;
  isGenerating: boolean;
  onTickerChange: (value: string) => void;
  onYearsChange: (value: number) => void;
  onGenerate: () => void;
}) {
  const [showSticky, setShowSticky] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowSticky(window.scrollY >= 100);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const sections = useMemo(
    () => orderSections(snapshot.sections.filter((section) => section.items.length > 0 || section.rows?.length || section.details)),
    [snapshot],
  );
  const keyItems = useMemo(() => buildKeyItems(sections), [sections]);
  const annualRows = sections.find((section) => section.id === "annual_rows")?.rows ?? [];
  const valuationRows = sections.find((section) => section.id === "valuation_history")?.rows ?? [];
  const peRows = sections.find((section) => section.id === "pe_percentile")?.rows ?? [];
  const epsRows = sections.find((section) => section.id === "eps_percentile")?.rows ?? [];
  const companyName = normalizeCompanyName(snapshot.company.name);
  const reportNavItems = buildReportNavItems(sections, valuationRows, peRows, epsRows);

  return (
    <>
      <div className={`report-sticky${showSticky ? " visible" : ""}`} aria-label="当前报告">
        <strong>{companyName}</strong>
        <span>{snapshot.company.ticker}</span>
        <span>{formatPrice(snapshot.current_price)}</span>
      </div>
      <section className="hero report-cover" id="overview">
        <div className="report-cover-main">
          <p className="eyebrow">{formatMarket(snapshot.company.market)} · {formatMode(snapshot.source.mode)}</p>
          <h1 aria-label={`${companyName} 财报分析报告`}>{companyName}<span>财报分析报告</span></h1>
          <p className="report-intro">基于本地数据快照渲染。<span className="text-green">绿色</span>代表接近优秀或低估，<span className="text-amber">黄色</span>代表需要观察，<span className="text-red">红色</span>代表明显偏离目标画像；缺失值保持“缺失”，不会被当作 0。</p>
        </div>
        <div className="hero-meta">
          <div className="box">
            <div className="k">股票代码</div>
            <div className="v">{snapshot.company.ticker}</div>
          </div>
          <div className="box">
            <div className="k">覆盖年份</div>
            <div className="v">{snapshot.coverage.years.at(0) ?? "N/A"} - {snapshot.coverage.years.at(-1) ?? "N/A"}</div>
          </div>
          <div className="box">
            <div className="k">样本年数</div>
            <div className="v">{snapshot.coverage.years.length} 年</div>
          </div>
          <div className="box">
            <div className="k">当前股价</div>
            <div className="v">{formatPrice(snapshot.current_price)}</div>
          </div>
          <div className="box">
            <div className="k">币种 / 单位</div>
            <div className="v">{snapshot.company.currency ?? "未知"} · {snapshot.company.accounting_unit ?? "未知"}</div>
          </div>
          <div className="box">
            <div className="k">生成时间</div>
            <div className="v">{formatDate(snapshot.generated_at)}</div>
          </div>
        </div>
      </section>

      <div className="report-layout">
        <aside className="side-rail" aria-label="快照信息">
          <ReportControls
            ticker={ticker}
            years={years}
            isGenerating={isGenerating}
            onTickerChange={onTickerChange}
            onYearsChange={onYearsChange}
            onGenerate={onGenerate}
          />
          <ReportNav items={reportNavItems} />
          <div className="rail-heading">
            <span>快照上下文</span>
            <strong>{formatMode(snapshot.source.mode)}</strong>
          </div>
          <div>
            <span>快照版本</span>
            <strong>{snapshot.schema_version}</strong>
          </div>
          <div>
            <span>数据来源</span>
            <strong>{formatSource(snapshot.source.provider ?? snapshot.source.name)}</strong>
          </div>
          <div>
            <span>币种</span>
            <strong>{snapshot.company.currency ?? "未知"}</strong>
          </div>
          <div>
            <span>会计单位</span>
            <strong>{snapshot.company.accounting_unit ?? "未知"}</strong>
          </div>
          <div>
            <span>覆盖期</span>
            <strong>{snapshot.coverage.years.at(0) ?? "N/A"} - {snapshot.coverage.years.at(-1) ?? "N/A"}</strong>
          </div>
        </aside>
        <section className="section-stack">
          <BuffettMungerOverview sections={sections} snapshot={snapshot} />

          {keyItems.length > 0 && (
            <section className="kpi-strip" aria-label="关键指标">
              {keyItems.map((item) => (
                <MetricTile key={`${item.metric}-${item.label}`} item={item} />
              ))}
            </section>
          )}

          {snapshot.warnings.length > 0 && (
            <section className="warning-band">
              <h2>数据质量提示</h2>
              <ul>
                {snapshot.warnings.map((warning, index) => (
                  <li key={index}>{formatWarning(warning)}</li>
                ))}
              </ul>
            </section>
          )}

          {annualRows.length > 1 && <BusinessHistorySnapshot rows={annualRows} />}
          {(valuationRows.length > 1 || peRows.length > 1 || epsRows.length > 1) && (
            <section className="chart-section" id="valuation_charts">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">估值走势</p>
                  <h2>PE、EPS 与估值锚点趋势</h2>
                </div>
                <span>移动端可横向滚动</span>
              </div>
              <div className="mini-chart-grid">
                <LineChart title="历史 PE 走势" rows={peRows} xKey="year" yKey="pe" unit="x" referenceKeys={["hist_median", "current"]} details={sections.find((section) => section.id === "pe_percentile")?.details} />
                <LineChart title="历史 EPS 趋势" rows={epsRows} xKey="year" yKey="eps" referenceKeys={["hist_median", "current"]} details={sections.find((section) => section.id === "eps_percentile")?.details} />
              </div>
            </section>
          )}

          {sections.filter((section) => section.id !== "overview").map((section) => (
            <ReportSectionCard key={section.id} section={section} snapshot={snapshot} />
          ))}
        </section>
      </div>
    </>
  );
}

function ReportNav({ items }: { items: Array<{ id: string; label: string; meta: string }> }) {
  if (items.length === 0) return null;
  return (
    <nav className="report-index" aria-label="报告阅读目录">
      {items.map((item) => (
        <a href={`#${item.id}`} key={item.id}>
          <strong>{item.label}</strong>
          <span>{item.meta}</span>
        </a>
      ))}
    </nav>
  );
}

function ReportControls({
  ticker,
  years,
  isGenerating,
  onTickerChange,
  onYearsChange,
  onGenerate,
}: {
  ticker: string;
  years: number;
  isGenerating: boolean;
  onTickerChange: (value: string) => void;
  onYearsChange: (value: number) => void;
  onGenerate: () => void;
}) {
  return (
    <form
      className="rail-controls"
      onSubmit={(event) => {
        event.preventDefault();
        onGenerate();
      }}
    >
      <div className="rail-heading">
        <span>生成报告</span>
        <strong>本地快照</strong>
      </div>
      <label aria-label="股票代码">
        <span>股票代码</span>
        <input value={ticker} onChange={(event) => onTickerChange(event.target.value)} />
      </label>
      <label aria-label="年数">
        <span>历史年数</span>
        <input type="number" min={4} max={80} value={years} onChange={(event) => onYearsChange(Number(event.target.value))} />
      </label>
      <button type="submit" disabled={isGenerating}>{isGenerating ? "生成中" : "生成报告"}</button>
    </form>
  );
}

function MetricTile({ item }: { item: ReportItem }) {
  return (
    <article className={`kpi-tile ${item.status}`}>
      <span>{formatMetricLabel(item.label)}</span>
      <strong>{formatMetricValue(item.value, item.status)}</strong>
      <small>{formatDisplayText(item.warning ?? item.basis ?? item.meaning ?? "报告指标")}</small>
    </article>
  );
}

function MetricCardGrid({ items, sectionId, currentPrice }: { items: ReportItem[]; sectionId: string; currentPrice?: unknown }) {
  return (
    <div className={sectionId === "metric_explanations" ? "metric-card-grid explanation-list" : "metric-card-grid"}>
      {items.map((item) => (
        <article className={`metric-card-v2 ${metricToneClass(item)}`} key={`${item.metric}-${item.label}`}>
          <div className="metric-card-head">
            <strong>{formatMetricLabel(item.label)}</strong>
            <span>{STATUS_LABELS[item.status] ?? item.status}</span>
          </div>
          <div className="metric-card-value">{formatMetricValue(item.value, item.status)}</div>
          {item.badge && <div className="metric-card-badge">{formatDisplayText(item.badge)}</div>}
          <p>{formatDisplayText(item.basis ?? item.meaning ?? "未提供口径说明")}</p>
          {sectionId === "valuation" && item.label === "OE收益率 vs 国债" && (
            <p className="metric-card-extra">{ownerEarningsBasisText(item.value, currentPrice)}</p>
          )}
          {sectionId === "valuation" && item.what_it_measures && <p><b>衡量：</b>{formatDisplayText(item.what_it_measures)}</p>}
          {sectionId === "valuation" && item.implication && <p><b>含义：</b>{formatDisplayText(item.implication)}</p>}
        </article>
      ))}
    </div>
  );
}

function metricToneClass(item: ReportItem): string {
  if (item.status === "ok") return "ok";
  if (item.status === "warning") return "warning";
  if (item.status === "error") return "error";
  return "missing";
}

function ownerEarningsBasisText(value: unknown, currentPrice: unknown): string {
  const text = String(value ?? "");
  const match = text.match(/OE Yield\s*([0-9.]+)%/i);
  if (!match) return "OE口径来自所有者收益/股 ÷ 当前股价；具体历史口径见“所有者收益率历史”。";
  const yieldPct = Number(match[1]);
  const price = numberValue(currentPrice);
  if (!Number.isFinite(yieldPct) || price === null) return `本项使用 OE收益率 ${yieldPct.toFixed(1)}%，OE口径来自所有者收益/股 ÷ 当前股价。`;
  const oePs = (price * yieldPct) / 100;
  return `本项使用的 OE 约 ${oePs.toFixed(2)} 元/股（由 ${yieldPct.toFixed(1)}% × 当前股价反推），用于和十年期国债做机会成本比较。`;
}

function BusinessHistorySnapshot({ rows }: { rows: Array<Record<string, unknown>> }) {
  const latest = rows.at(-1) ?? {};
  const previous = rows.at(-2) ?? {};
  return (
    <section className="chart-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">历史速览</p>
          <h2>关键经营指标最新年度变化</h2>
        </div>
        <span>{rows.length} 年历史</span>
      </div>
      <div className="history-snapshot-grid">
        <TrendInfoCard label="业务纯度" value={latest.purity_with_rnd} previous={previous.purity_with_rnd} kind="percent" />
        <TrendInfoCard label="收入增速" value={latest.revenue_growth} previous={previous.revenue_growth} kind="percent" />
        <TrendInfoCard label="资本开支/净利" value={latest.capex_net_income} previous={previous.capex_net_income} kind="percent" inverse />
        <TrendInfoCard label="ROE" value={latest.roe} previous={previous.roe} kind="percent" />
      </div>
    </section>
  );
}

function TrendInfoCard({
  label,
  value,
  previous,
  kind,
  inverse = false,
}: {
  label: string;
  value: unknown;
  previous: unknown;
  kind: TableColumn["kind"];
  inverse?: boolean;
}) {
  const current = numberValue(value);
  const prev = numberValue(previous);
  const delta = current !== null && prev !== null ? current - prev : null;
  const status = delta === null ? "missing" : (inverse ? delta <= 0 : delta >= 0) ? "ok" : "warning";
  return (
    <article className={`signal-card ${status}`}>
      <span>{label}</span>
      <strong>{formatCell(value, { key: label, label, kind })}</strong>
      <small>{delta === null ? "同比缺失" : `同比 ${delta >= 0 ? "+" : ""}${formatCell(delta, { key: label, label, kind })}`}</small>
    </article>
  );
}

function ReportSectionCard({ section, snapshot }: { section: ReportSection; snapshot: ReportSnapshot }) {
  const visibleRows = section.rows ?? [];
  const copy = sectionCopy(section);
  const columns = tableColumnsFor(section.id, visibleRows);
  const summaryMeta = sectionSummaryMeta(section);
  if (section.id === "market_context") {
    return <MarketContextCard section={section} copy={copy} />;
  }
  if (section.id === "pe_percentile" || section.id === "eps_percentile") {
    return <PercentileCard section={section} copy={copy} columns={columns} />;
  }
  if (section.id === "data_quality") {
    return <DataQualityCard section={section} copy={copy} columns={columns} />;
  }
  if (section.id === "share_basis") {
    return <ShareBasisCard section={section} copy={copy} columns={columns} />;
  }
  if (section.id === "technicals") {
    return <TechnicalsCard section={section} copy={copy} columns={columns} />;
  }
  return (
    <article className={`section section-${section.id}`} id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{summaryMeta}</span>
      </div>
      {(copy.summary || section.summary) && <p className="section-summary">{copy.summary ?? section.summary}</p>}
      {section.id === "overview" && section.items.length > 0 && (
        <ol className="conclusion-list">
          {section.items.map((item) => (
            <li key={`${item.metric}-${item.value}`}>
              <span>{formatMetricValue(item.value, item.status)}</span>
            </li>
          ))}
        </ol>
      )}
      {section.id !== "overview" && section.items.length > 0 && (
        <MetricCardGrid items={section.items.slice(0, section.id === "metric_explanations" ? 14 : 12)} sectionId={section.id} currentPrice={snapshot.current_price} />
      )}
      {section.details !== undefined && <DetailsGrid details={section.details} />}
      {section.id === "valuation" && <ValuationOverviewSummary section={section} snapshot={snapshot} />}
      {section.id === "valuation" && section.items.length > 0 && <ValuationAuditTable items={section.items} />}
      {visibleRows.length > 0 && <DataTable rows={visibleRows} columns={columns} sectionId={section.id} />}
    </article>
  );
}

function MarketContextCard({ section, copy }: { section: ReportSection; copy: { title: string; eyebrow: string; summary?: string } }) {
  const details = asRecord(section.details);
  const rows = Array.isArray(section.rows) ? section.rows : [];
  return (
    <article className="section market-section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{sectionSummaryMeta(section)}</span>
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      {details.status === "missing" ? (
        <div className="missing-block">数据缺失</div>
      ) : (
        <>
          <div className="country-yield-strip">
            <span className="active">中国 10Y</span>
            <span className="muted">美国 10Y 暂无本地源</span>
            <span className="muted">日本 10Y 暂无本地源</span>
            <span className="muted">德国 10Y 暂无本地源</span>
          </div>
          <div className="market-card-grid">
            <InfoCard label="中国10Y国债" value={formatPercent(details.bond_latest)} note={String(details.bond_latest_date ?? "")} />
            <InfoCard label="历史分位" value={formatPercent(details.bond_percentile)} note={formatRange(details.bond_min, details.bond_max, "%")} />
            <InfoCard label="十年区间低点" value={formatPercent(details.bond_min)} note="曲线底部参考" />
            <InfoCard label="十年区间高点" value={formatPercent(details.bond_max)} note="曲线顶部参考" />
          </div>
          <LineChart title="中国十年期国债收益率曲线" rows={rows} xKey="date" yKey="yield_pct" unit="%" details={details} referenceKeys={["bond_mean", "bond_latest"]} />
          <div className="trend-meaning-table">
            <div><strong>持续下行</strong><span>通常意味着无风险收益率下降，权益估值空间可能抬升，但也可能反映增长预期走弱。</span></div>
            <div><strong>持续上行</strong><span>通常意味着资金机会成本提高，估值承压，需要更厚的风险溢价。</span></div>
            <div><strong>低位横盘 (&lt;2.5%)</strong><span>通常意味着资产荒环境，股市估值中枢可能抬升，但需关注盈利质量是否同步改善。</span></div>
          </div>
        </>
      )}
    </article>
  );
}

function PercentileCard({
  section,
  copy,
  columns,
}: {
  section: ReportSection;
  copy: { title: string; eyebrow: string; summary?: string };
  columns: TableColumn[];
}) {
  const rows = section.rows ?? [];
  const details = asRecord(section.details);
  const percentile = numberValue(details.percentile);
  return (
    <article className={`section percentile-section ${percentileTone(percentile)}`} id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{percentile === null ? "分位数据暂缺" : formatPercent(percentile)}</span>
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      <div className="market-card-grid">
        <InfoCard label="当前值" value={formatCell(details.current, { key: "current", label: "当前值", kind: section.id === "pe_percentile" ? "multiple" : "number" })} note={`样本 ${details.sample_count ?? "—"} 年`} />
        <InfoCard label="近十年分位" value={formatPercent(percentile)} note={percentileWarning(percentile)} />
        <InfoCard label="历史区间" value={formatRange(details.hist_min, details.hist_max)} note={`中位数 ${formatMaybeNumber(details.hist_median)}`} />
        <InfoCard label="相对中位数" value={formatPercent(details.current_vs_median_pct)} note={String(details.method ?? "")} />
      </div>
      <LineChart title={section.id === "pe_percentile" ? "PE 分位走势图" : "EPS 分位走势图"} rows={rows} xKey="year" yKey={section.id === "pe_percentile" ? "pe" : "eps"} details={details} referenceKeys={["hist_median", "current"]} unit={section.id === "pe_percentile" ? "x" : ""} />
      {rows.length > 0 && <DataTable rows={rows} columns={columns} sectionId={section.id} />}
    </article>
  );
}

function DataQualityCard({
  section,
  copy,
  columns,
}: {
  section: ReportSection;
  copy: { title: string; eyebrow: string; summary?: string };
  columns: TableColumn[];
}) {
  const details = asRecord(section.details);
  const rows = section.rows ?? [];
  const modelResults = Array.isArray(details.model_results) ? details.model_results.map(asRecord) : [];
  const shareBasis = asRecord(details.share_basis);
  return (
    <article className="section quality-panel-section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{String(details.confidence ?? "置信度缺失")}</span>
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      <div className="quality-dashboard">
        <InfoCard label="整体置信度" value={String(details.confidence ?? "—")} note={`评分 ${details.confidence_score ?? "—"}`} />
        <InfoCard label="年份范围" value={String(details.year_range ?? "—")} note="进入报告快照的原始覆盖窗口" />
        <InfoCard label="估值模型" value={`${modelResults.filter((item) => item.available === true).length}/${modelResults.length || "—"}`} note="可计算 / 总模型" />
        <InfoCard label="股本口径" value={String(shareBasis.confidence ?? "—")} note={`覆盖率 ${formatPercent(percentFromRatio(shareBasis.coverage_ratio))}`} />
      </div>
      {rows.length > 0 && (
        <div className="coverage-bars">
          {rows.map((row) => (
            <div key={String(row.field)}>
              <span>{formatDisplayText(String(row.field ?? ""))}</span>
              <div><i style={{ width: `${Math.max(0, Math.min(100, numberValue(row.pct) ?? 0))}%` }} /></div>
              <strong>{formatPercent(row.pct)}</strong>
            </div>
          ))}
        </div>
      )}
      {modelResults.length > 0 && (
        <div className="model-chip-list">
          {modelResults.map((model) => (
            <span className={model.available ? "available" : "missing"} key={String(model.label)}>
              {formatDisplayText(String(model.label ?? "模型"))} · {formatDisplayText(String(model.status ?? ""))}
            </span>
          ))}
        </div>
      )}
      {rows.length > 0 && <DataTable rows={rows} columns={columns} sectionId={section.id} />}
    </article>
  );
}

function ShareBasisCard({
  section,
  copy,
  columns,
}: {
  section: ReportSection;
  copy: { title: string; eyebrow: string; summary?: string };
  columns: TableColumn[];
}) {
  const details = asRecord(section.details);
  const rows = section.rows ?? [];
  return (
    <article className="section share-basis-section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{String(details.confidence ?? "口径待核查")}</span>
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      <div className="market-card-grid">
        <InfoCard label="估值股本" value={formatCell(details.shares, { key: "shares", label: "估值股本", kind: "number" })} note="用于市值和每股估值分母" />
        <InfoCard label="股本覆盖率" value={formatPercent(percentFromRatio(details.coverage_ratio))} note={`${details.valuation_count ?? "—"} 个估值年份`} />
        <InfoCard label="EPS推导年份" value={`${arrayLength(details.eps_derived_years)} 年`} note={shortList(details.eps_derived_years)} />
        <InfoCard label="Legacy回退" value={`${arrayLength(details.legacy_fallback_years)} 年`} note={shortList(details.legacy_fallback_years) || "未触发"} />
      </div>
      {section.items.length > 0 && (
        <div className="metric-list">
          {section.items.map((item) => (
            <div className={`metric-row ${item.status}`} key={`${item.metric}-${item.label}`}>
              <div>
                <div className="metric-title-line">
                  <strong>{formatMetricLabel(item.label)}</strong>
                  {item.badge && <span className={`metric-badge ${badgeToneClass(item.badge_color)}`}>{formatDisplayText(item.badge)}</span>}
                </div>
                <p>{formatDisplayText(item.basis ?? item.meaning ?? "")}</p>
              </div>
              <span>{formatMetricValue(item.value, item.status)}</span>
            </div>
          ))}
        </div>
      )}
      <DetailsGrid details={{ source_policy: details.source_policy, reported_semantics: details.reported_semantics }} />
      {rows.length > 0 && <DataTable rows={rows} columns={columns} sectionId={section.id} />}
    </article>
  );
}

function TechnicalsCard({
  section,
  copy,
  columns,
}: {
  section: ReportSection;
  copy: { title: string; eyebrow: string; summary?: string };
  columns: TableColumn[];
}) {
  const rows = section.rows ?? [];
  const details = asRecord(section.details);
  const crossings = Array.isArray(details.crossings) ? details.crossings.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row)) : [];
  return (
    <article className="section technicals-section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        <span>{String(details.asof ?? "截至日缺失")}</span>
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      {section.items.length > 0 && (
        <div className="market-card-grid">
          {section.items.map((item) => (
            <InfoCard key={item.metric} label={formatMetricLabel(item.label)} value={formatMetricValue(item.value, item.status)} note={item.basis ?? ""} />
          ))}
        </div>
      )}
      <div className="wr-threshold">
        <span>超卖 -100 至 -80</span>
        <span>中性 -80 至 -20</span>
        <span>超买 -20 至 0</span>
      </div>
      <LineChart title="Williams %R 28日走势" rows={rows} xKey="date" yKey="wr_28" details={{ oversold: -80, overbought: -20 }} referenceKeys={["oversold", "overbought"]} />
      {crossings.length > 0 && (
        <>
          <h3 className="subtable-title">交叉事件</h3>
          <DataTable rows={crossings.slice(-24)} columns={TABLE_COLUMNS.technical_crossings} sectionId="technical_crossings" />
        </>
      )}
      {rows.length > 0 && <DataTable rows={rows.slice(-40)} columns={columns} sectionId={section.id} />}
    </article>
  );
}

function InfoCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="info-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

function DataTable({
  rows,
  columns,
  sectionId,
}: {
  rows: Array<Record<string, unknown>>;
  columns: TableColumn[];
  sectionId: string;
}) {
  return (
    <div className="table-wrap data-table-shell">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column.key} className={cellToneClass(sectionId, column, row[column.key], row, rows[rowIndex - 1])}>{formatCell(row[column.key], column)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SECTION_DISPLAY_ORDER = [
  "overview",
  "quality",
  "pricing_power",
  "radar_modules",
  "valuation",
  "valuation_scenarios",
  "pe_percentile",
  "eps_percentile",
  "cash_flow",
  "capital_safety",
  "share_basis",
  "shareholder_returns",
  "annual_rows",
  "valuation_history",
  "owner_earnings_yield",
  "technicals",
  "market_context",
  "valuation_formulas",
  "diagnostics",
  "dollar_retention",
  "metric_explanations",
  "data_quality",
  "machine_summary",
];

function orderSections(sections: ReportSection[]): ReportSection[] {
  const order = new Map(SECTION_DISPLAY_ORDER.map((id, index) => [id, index]));
  return [...sections].sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999));
}

function buildReportNavItems(
  sections: ReportSection[],
  valuationRows: Array<Record<string, unknown>>,
  peRows: Array<Record<string, unknown>>,
  epsRows: Array<Record<string, unknown>>,
): Array<{ id: string; label: string; meta: string }> {
  const base = [
    { id: "buffett_overview", label: "巴芒总览", meta: "四维判断" },
    ...(valuationRows.length > 1 || peRows.length > 1 || epsRows.length > 1
      ? [{ id: "valuation_charts", label: "估值走势", meta: "PE / EPS" }]
      : []),
  ];
  const sectionItems = sections
    .filter((section) => ["valuation", "valuation_scenarios", "quality", "pricing_power", "radar_modules", "cash_flow", "capital_safety", "share_basis", "shareholder_returns", "annual_rows", "owner_earnings_yield", "technicals", "market_context", "data_quality", "machine_summary"].includes(section.id))
    .map((section) => {
      const copy = sectionCopy(section);
      return { id: section.id, label: copy.title, meta: sectionSummaryMeta(section) };
    });
  return [...base, ...sectionItems];
}

function sectionSummaryMeta(section: ReportSection): string {
  const warningCount = section.warnings.length;
  const missingCount = section.items.filter((item) => ["missing", "not_applicable", "error"].includes(item.status)).length;
  const rowCount = section.rows?.length ?? 0;
  if (warningCount > 0) return `${warningCount} 个提醒`;
  if (missingCount > 0) return `${missingCount} 个缺失`;
  if (rowCount > 0) return `${rowCount} 行`;
  return "已加载";
}

function LineChart({
  title,
  rows,
  xKey,
  yKey,
  unit,
  details,
  referenceKeys = [],
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  unit?: string;
  details?: unknown;
  referenceKeys?: string[];
}) {
  const points = rows
    .map((row) => ({ x: String(row[xKey] ?? ""), y: numberValue(row[yKey]) }))
    .filter((point): point is { x: string; y: number } => point.x !== "" && point.y !== null);
  if (points.length < 3) {
    return (
      <div className="line-chart-card">
        <h3>{title}</h3>
        <div className="missing-block">数据不足，无法绘图</div>
      </div>
    );
  }
  const detailMap = asRecord(details);
  const references = referenceKeys
    .map((key) => ({ key, value: numberValue(detailMap[key]) }))
    .filter((ref): ref is { key: string; value: number } => ref.value !== null);
  const values = [...points.map((point) => point.y), ...references.map((ref) => ref.value)];
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const padding = rawMax === rawMin ? Math.max(Math.abs(rawMax) * 0.1, 1) : (rawMax - rawMin) * 0.12;
  const min = rawMin - padding;
  const max = rawMax + padding;
  const span = max === min ? 1 : max - min;
  const width = Math.max(640, points.length * 56);
  const height = 260;
  const padLeft = 56;
  const padRight = 78;
  const padTop = 28;
  const padBottom = 48;
  const sx = (index: number) => padLeft + (index / (points.length - 1)) * (width - padLeft - padRight);
  const sy = (value: number) => height - padBottom - ((value - min) / span) * (height - padTop - padBottom);
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${sx(index).toFixed(1)} ${sy(point.y).toFixed(1)}`).join(" ");
  return (
    <div className="line-chart-card">
      <h3>{title}</h3>
      <div className="line-chart-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} className="axis" />
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} className="axis" />
          <text x={padLeft} y={height - 14} className="chart-label">横轴：{xAxisLabel(xKey)}</text>
          <text x={14} y={padTop + 6} className="chart-label" transform={`rotate(-90 14 ${padTop + 6})`}>纵轴：{yAxisLabel(yKey, unit)}</text>
          <text x={padLeft - 8} y={sy(rawMax) + 4} textAnchor="end" className="chart-label">{formatChartNumber(rawMax, unit)}</text>
          <text x={padLeft - 8} y={sy(rawMin) + 4} textAnchor="end" className="chart-label">{formatChartNumber(rawMin, unit)}</text>
          {references.map((ref) => {
            const y = sy(ref.value);
            return (
              <g key={ref.key}>
                <line x1={padLeft} y1={y} x2={width - padRight} y2={y} className="reference-line" />
                <text x={width - padRight - 4} y={Math.max(padTop + 10, Math.min(height - padBottom - 8, y - 5))} textAnchor="end" className="chart-label">{referenceLabel(ref.key)} {formatChartNumber(ref.value, unit)}</text>
              </g>
            );
          })}
          <path d={path} className="trend-line" />
          {points.map((point, index) => (
            <g key={`${point.x}-${index}`}>
              <circle cx={sx(index)} cy={sy(point.y)} r="3.2" className="trend-dot" />
              {index % Math.ceil(points.length / 8) === 0 || index === points.length - 1 ? (
                <text x={sx(index)} y={height - 28} textAnchor="middle" className="chart-label">{point.x.slice(0, 7)}</text>
              ) : null}
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  return {};
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatPrice(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "—" : `${number.toFixed(2)} 元`;
}

function formatPercent(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "—" : `${number.toFixed(2)}%`;
}

function formatMultiple(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "—" : `${number.toFixed(2)}x`;
}

function formatMaybeNumber(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "—" : number.toFixed(2);
}

function formatRange(low: unknown, high: unknown, suffix = ""): string {
  const lowNumber = numberValue(low);
  const highNumber = numberValue(high);
  if (lowNumber === null || highNumber === null) return "—";
  return `${lowNumber.toFixed(2)}${suffix} - ${highNumber.toFixed(2)}${suffix}`;
}

function formatChartNumber(value: number, unit?: string): string {
  return `${value.toFixed(2)}${unit ?? ""}`;
}

function referenceLabel(key: string): string {
  const labels: Record<string, string> = {
    hist_median: "中位",
    current: "当前",
    bond_mean: "均值",
    bond_latest: "当前",
    oversold: "超卖",
    overbought: "超买",
  };
  return labels[key] ?? key;
}

function xAxisLabel(key: string): string {
  if (key === "year") return "年份";
  if (key === "date") return "日期";
  return key;
}

function yAxisLabel(key: string, unit?: string): string {
  const labels: Record<string, string> = {
    pe: "PE",
    eps: "EPS",
    yield_pct: "收益率",
    wr_28: "Williams %R",
  };
  return `${labels[key] ?? key}${unit ? ` (${unit})` : ""}`;
}

function erpStatusText(status: string): string {
  if (status === "sufficient") return "风险补偿充足";
  if (status === "thin") return "利差偏薄，需要继续观察";
  if (status === "negative") return "盈利率低于国债收益率";
  return "缺少个股 PE 或国债数据";
}

function percentileTone(value: number | null): string {
  if (value === null) return "missing";
  if (value >= 85) return "hot";
  if (value >= 70) return "warm";
  return "normal";
}

function percentileWarning(value: number | null): string {
  if (value === null) return "分位数据缺失";
  if (value >= 85) return "高于 85%，红色警示";
  if (value >= 70) return "高于 70%，黄色警示";
  return "未触发高分位警示";
}

function badgeToneClass(color: ReportItem["badge_color"]): "good" | "warn" | "bad" | "muted" {
  if (color === "green") return "good";
  if (color === "yellow") return "warn";
  if (color === "red") return "bad";
  return "muted";
}

function formatMetricValue(value: unknown, status: string): string {
  if (value === null || value === undefined) return STATUS_LABELS[status] ?? "缺失";
  return translateDisplayText(String(value));
}

function isLongMetricValue(value: unknown): boolean {
  return typeof value === "string" && value.length > 24;
}

function formatCell(value: unknown, column?: TableColumn): string {
  if (value === null || value === undefined) return "缺失";
  if (Array.isArray(value)) return value.join("/");
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "缺失";
    if (/(shares|股本|股数)/i.test(column?.key ?? column?.label ?? "")) return `${(value / 100000000).toFixed(2)} 亿股`;
    if (column?.kind === "money" || (!column?.kind && Math.abs(value) >= 100000000)) {
      if (Math.abs(value) >= 1000000000000) return `${(value / 1000000000000).toFixed(2)} 万亿`;
      return `${(value / 100000000).toFixed(2)} 亿`;
    }
    if (column?.kind === "percent") return `${value.toFixed(1)}%`;
    if (column?.kind === "days") return `${value.toFixed(1)} 天`;
    if (column?.kind === "multiple") return `${value.toFixed(2)}x`;
    return Math.abs(value) >= 100 ? value.toFixed(2) : value.toFixed(4).replace(/\.?0+$/, "");
  }
  return translateDisplayText(String(value));
}

function percentFromRatio(value: unknown): number | null {
  const number = numberValue(value);
  if (number === null) return null;
  return Math.abs(number) <= 1 ? number * 100 : number;
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function shortList(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return "";
  const first = value.slice(0, 4).map(String).join("、");
  return value.length > 4 ? `${first} 等` : first;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatWarning(warning: unknown): string {
  if (typeof warning === "object" && warning !== null && "message" in warning) {
    return formatDisplayText(String((warning as { message: unknown }).message));
  }
  return formatDisplayText(String(warning));
}

function buildKeyItems(sections: ReportSection[]): ReportItem[] {
  const byId = (id: string) => sections.find((section) => section.id === id)?.items ?? [];
  const picks = [
    ...byId("quality").filter((item) => ["业务纯度", "ROIIC"].includes(item.label)),
    ...byId("valuation").filter((item) => ["OE-DCF", "芒格远景估值", "OE收益率 vs 国债"].includes(item.label)),
    ...byId("pricing_power").filter((item) => ["营收增速", "ROE"].includes(item.label)),
  ];
  return picks.slice(0, 4);
}

function sectionCopy(section: ReportSection) {
  return SECTION_COPY[section.id] ?? {
    title: section.title,
    eyebrow: section.id.replaceAll("_", " "),
    summary: section.summary ?? undefined,
  };
}

function BuffettMungerOverview({ sections, snapshot }: { sections: ReportSection[]; snapshot: ReportSnapshot }) {
  const qualityItems = sections.find((section) => section.id === "quality")?.items ?? [];
  const valuationItems = sections.find((section) => section.id === "valuation")?.items ?? [];
  const purity = qualityItems.find((item) => item.label === "业务纯度");
  const oeYield = valuationItems.find((item) => item.label === "OE收益率 vs 国债");
  const quality = sectionSignal(qualityItems);
  const moat = sectionSignal(sections.find((section) => section.id === "pricing_power")?.items ?? []);
  const safety = sectionSignal(sections.find((section) => section.id === "capital_safety")?.items ?? []);
  const valuation = sectionSignal(valuationItems);

  return (
    <section className="buffett-overview" id="buffett_overview">
      <h2>巴芒总览</h2>
      <p>这一屏先回答五件事：企业质量、护城河、财务安全、当前估值和是否值得继续深挖。</p>
      <div className="buffett-grid">
        <SummaryCard title="业务纯度" value={formatMetricValue(purity?.value, purity?.status ?? "missing")} note={purity?.basis ?? "扣除销售、管理、研发后的业务含金量"} tone={toneFromStatus(purity?.status)} />
        <SummaryCard title="护城河判断" value={moat.label} note="基于提价权与运营效率指标" tone={moat.tone} />
        <SummaryCard title="财务安全" value={safety.label} note="结合负债、净现金和资本结构信号" tone={safety.tone} />
        <SummaryCard title="当前估值" value={valuation.label} note="多个估值锚点交叉核对" tone={valuation.tone} />
        <SummaryCard title="OE vs 国债" value={formatMetricValue(oeYield?.value, oeYield?.status ?? "missing")} note={ownerEarningsBasisText(oeYield?.value, snapshot.current_price)} tone={toneFromStatus(oeYield?.status)} />
      </div>
      <div className="summary-conclusion">总结判断：{overallConclusion([quality.tone, moat.tone, safety.tone, valuation.tone])}</div>
      <div className="summary-traits">
        <strong>特征速写：</strong>
        {snapshot.company.name}目前在经营质量、护城河、财务安全和估值四个维度中的综合表现为“{overallLabel([quality.tone, moat.tone, safety.tone, valuation.tone])}”。
      </div>
    </section>
  );
}

function SummaryCard({ title, value, note, tone }: { title: string; value: string; note: string; tone: "good" | "warn" | "bad" }) {
  return (
    <article className={`decision-card tone-${tone}`}>
      <div className="k">{title}</div>
      <div className="v">{value}</div>
      <div className="d">{note}</div>
    </article>
  );
}

function toneFromStatus(status?: string): "good" | "warn" | "bad" {
  if (status === "ok") return "good";
  if (status === "missing" || status === "not_applicable") return "warn";
  return "bad";
}

function sectionSignal(items: ReportItem[]): { tone: "good" | "warn" | "bad"; label: string } {
  const badCount = items.filter((item) => ["warning", "error"].includes(item.status)).length;
  const total = Math.max(items.length, 1);
  const ratio = badCount / total;
  if (ratio >= 0.5) return { tone: "bad", label: "需谨慎" };
  if (ratio >= 0.25) return { tone: "warn", label: "中性偏谨慎" };
  return { tone: "good", label: "相对稳健" };
}

function overallConclusion(tones: Array<"good" | "warn" | "bad">): string {
  if (tones.includes("bad")) return "暂时更像观察标的，还需要更多安全边际。";
  if (tones.includes("warn")) return "基本面具备跟踪价值，但仍需继续验证关键风险项。";
  return "整体质量较稳，具备继续深入研究的基础。";
}

function overallLabel(tones: Array<"good" | "warn" | "bad">): string {
  if (tones.includes("bad")) return "观察型";
  if (tones.includes("warn")) return "平衡型";
  return "稳健型";
}

function ValuationOverviewSummary({ section, snapshot }: { section: ReportSection; snapshot: ReportSnapshot }) {
  const marketContext = asRecord(snapshot.market_context);
  const marketDate = String(marketContext.bond_latest_date ?? "未知");
  const marketPe = formatMaybeNumber(marketContext.csi300_pe_ttm);
  const currentYear = snapshot.coverage.years.at(-1) ?? "未知";
  const currentPrice = formatPrice(snapshot.current_price);
  const pegItem = section.items.find((item) => item.label.includes("PEG"));
  const pegyItem = section.items.find((item) => item.label.includes("PEGY"));

  return (
    <div className="valuation-brief">
      当前股价为 {currentPrice}；最新年报年份为 {currentYear}；
      PEG 口径为 {formatDisplayText(pegItem?.value ? String(pegItem.value) : "未提供")}；
      PEGY 口径为 {formatDisplayText(pegyItem?.value ? String(pegyItem.value) : "未提供")}；
      全市场锚点约 {marketPe}x；十年期国债参考日期为 {marketDate}。
    </div>
  );
}

function ValuationAuditTable({ items }: { items: ReportItem[] }) {
  return (
    <div className="table-wrap machine-table">
      <table>
        <caption>机器可读汇总（低估判定）</caption>
        <thead>
          <tr>
            <th>Key</th>
            <th>Label</th>
            <th>Value</th>
            <th>Rule</th>
            <th>Status</th>
            <th>Tone</th>
            <th>Meaning</th>
            <th>Implication</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={`${item.metric}-${index}`}>
              <td>{`valuation_metric_${index + 1}`}</td>
              <td>{formatMetricLabel(item.label)}</td>
              <td>{formatMetricValue(item.value, item.status)}</td>
              <td>{formatDisplayText(item.basis ?? "-")}</td>
              <td>{STATUS_LABELS[item.status] ?? item.status}</td>
              <td>{formatDisplayText(item.tone ?? "-")}</td>
              <td>{formatDisplayText(item.what_it_measures ?? item.meaning ?? "-")}</td>
              <td>{formatDisplayText(item.implication ?? "-")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function cellToneClass(sectionId: string, column: TableColumn, value: unknown, row?: Record<string, unknown>, previousRow?: Record<string, unknown>): string {
  if (sectionId === "owner_earnings_yield" && ["pess_yield", "base_yield", "leni_yield"].includes(column.key)) {
    const n = numberValue(value);
    if (n === null) return "";
    if (n >= 8) return "yield-good";
    if (n >= 4) return "yield-warn";
    return "yield-bad";
  }
  const n = numberValue(value);
  if (n === null) return "";
  if (["share_basis", "owner_earnings_yield", "annual_rows", "eps_percentile"].includes(sectionId)) {
    const trendKeys = ["real_eps", "basic_eps", "eps", "ocf_ps", "oe_ps", "base_oe_ps", "pess_oe_ps", "leni_oe_ps", "purity_with_rnd", "roe", "revenue_growth"];
    if (trendKeys.includes(column.key)) {
      const previous = previousRow ? numberValue(previousRow[column.key]) : null;
      if (previous !== null) return n >= previous ? "trend-up" : "trend-down";
    }
  }
  if (column.key === "capex_net_income") {
    if (n <= 25) return "yield-good";
    if (n <= 60) return "yield-warn";
    return "yield-bad";
  }
  if (sectionId === "capital_safety") {
    if (column.key === "roic") return n >= 10 ? "yield-good" : n >= 6 ? "yield-warn" : "yield-bad";
    if (column.key === "interest_coverage") return n >= 5 ? "yield-good" : n >= 2 ? "yield-warn" : "yield-bad";
    if (column.key === "ocf_ratio") return n >= 80 ? "yield-good" : n >= 50 ? "yield-warn" : "yield-bad";
  }
  if (sectionId === "shareholder_returns" && column.key === "one_dollar_return") {
    return n >= 1 ? "yield-good" : "yield-bad";
  }
  return "";
}

function tableColumnsFor(sectionId: string, rows: Array<Record<string, unknown>>): TableColumn[] {
  const preferred = TABLE_COLUMNS[sectionId];
  if (preferred) return preferred.filter((column) => rows.some((row) => column.key in row));
  const keys = rows[0] ? Object.keys(rows[0]).slice(0, 8) : [];
  return keys.map((key) => ({ key, label: DETAIL_LABELS[key] ?? key, kind: inferColumnKind(key) }));
}

function inferColumnKind(key: string): TableColumn["kind"] {
  if (/(peg|pegy)/i.test(key)) return "multiple";
  if (/(margin|ratio|yield|growth|roe|roic|cagr|purity|payout)/i.test(key)) return "percent";
  if (/(revenue|cost|income|capex|cash|mcap|market_cap|div|buyback|oe|price|value)/i.test(key)) return "money";
  if (/(dso|dpo|dio|ccc|days)/i.test(key)) return "days";
  return "number";
}

function DetailsGrid({ details }: { details: unknown }) {
  const entries = detailEntries(details);
  if (entries.length === 0) return null;
  return (
    <dl className="details-grid">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{DETAIL_LABELS[key] ?? key}</dt>
          <dd>{formatDetailValue(key, value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function detailEntries(details: unknown): Array<[string, unknown]> {
  if (details === null || typeof details !== "object" || Array.isArray(details)) return [];
  return Object.entries(details as Record<string, unknown>)
    .filter(([, value]) => value !== null && value !== undefined && value !== "" && typeof value !== "object")
    .slice(0, 12);
}

function formatDetailValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return formatCell(value, { key, label: key, kind: inferColumnKind(key) });
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return translateDisplayText(String(value));
}

function formatMetricLabel(label: string): string {
  const labels: Record<string, string> = {
    Conclusion: "结论",
    PE: "市盈率",
    "OE-DCF": "所有者收益DCF",
    "PEG × CAGR": "PEG 与增长率",
    PEGY: "PEGY 含股息",
    "OE收益率 vs 国债": "所有者收益率 vs 国债",
    "Net-Net": "净流动资产估值",
    "Owner Earnings Yield": "所有者收益率",
    "Missing Values": "缺失值规则",
    "Capex / Net Income": "资本开支/净利润",
    "Quality": "经营质量",
    "Pricing Power": "提价权",
    "Valuation": "估值",
  };
  return labels[label] ?? label;
}

function formatDisplayText(value: string): string {
  return translateDisplayText(value);
}

function translateDisplayText(value: string): string {
  return value
    .replaceAll("OE-DCF", "所有者收益DCF")
    .replaceAll("OE Yield", "所有者收益率")
    .replaceAll("Owner Earnings", "所有者收益")
    .replaceAll("EPS CAGR", "EPS复合增速")
    .replaceAll("退出PE", "退出市盈率")
    .replaceAll("个股PE", "个股市盈率")
    .replaceAll("市场锚", "市场估值锚")
    .replaceAll("全市场中位 PE", "全市场中位市盈率")
    .replaceAll("PE /", "市盈率 /")
    .replaceAll("PE <", "市盈率 <")
    .replaceAll("PE = ", "市盈率 = ")
    .replaceAll("Dividend Yield", "股息率")
    .replaceAll("asof_shares", "截至日股本")
    .replaceAll("reported_shares", "财报股本")
    .replaceAll("current_shares", "当前股本")
    .replaceAll("ok", "正常")
    .replaceAll("true", "是")
    .replaceAll("false", "否");
}

function formatMarket(market: string): string {
  if (market === "CN-A") return "A 股";
  if (market === "HK") return "港股";
  if (market === "US") return "美股";
  return market;
}

function formatMode(mode?: string): string {
  return MODE_LABELS[mode ?? "current"] ?? "当前报告";
}

function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

function normalizeCompanyName(name: string): string {
  return /[\u4e00-\u9fff]/.test(name) ? name.replace(/\s+/g, "") : name;
}
