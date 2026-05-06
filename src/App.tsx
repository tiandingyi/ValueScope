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
    title: "市场环境：利率与股债性价比",
    eyebrow: "宏观估值锚",
    summary: "用十年期国债、沪深300估值和风险溢价解释当前估值环境；缺失时不推断。",
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
    { key: "report_provenance", label: "年报来源", kind: "text" },
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
    { key: "price_ma200", label: "200日均价", kind: "number" },
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
        <nav className="topbar-nav" aria-label="报告章节">
          <a href="#overview">总览</a>
          <a href="#valuation">估值</a>
          <a href="#quality">质量</a>
          <a href="#cash_flow">现金流</a>
          <a href="#shareholder_returns">股东回报</a>
        </nav>
        <form
          className="generate-form"
          onSubmit={(event) => {
            event.preventDefault();
            void generateReport();
          }}
        >
          <label aria-label="股票代码">
            <span>股票代码</span>
            <input value={ticker} onChange={(event) => setTicker(event.target.value)} />
          </label>
          <label aria-label="年数">
            <span>年数</span>
            <input
              type="number"
              min={4}
              max={20}
              value={years}
              onChange={(event) => setYears(Number(event.target.value))}
            />
          </label>
          <button type="submit" disabled={state.kind === "loading"}>
            生成报告
          </button>
        </form>
      </header>

      <div className="wrap">
        {state.kind === "empty" && <EmptyState />}
        {state.kind === "loading" && <StatusPanel title="生成中" message={state.message} />}
        {state.kind === "error" && <StatusPanel title="生成失败" message={state.message} tone="error" />}
        {state.kind === "ready" && <ReportView snapshot={state.snapshot} />}
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

function ReportView({ snapshot }: { snapshot: ReportSnapshot }) {
  const [showSticky, setShowSticky] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowSticky(window.scrollY >= 100);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const sections = useMemo(
    () => snapshot.sections.filter((section) => section.items.length > 0 || section.rows?.length || section.details),
    [snapshot],
  );
  const keyItems = useMemo(() => buildKeyItems(sections), [sections]);
  const annualRows = sections.find((section) => section.id === "annual_rows")?.rows ?? [];
  const valuationRows = sections.find((section) => section.id === "valuation_history")?.rows ?? [];
  const peRows = sections.find((section) => section.id === "pe_percentile")?.rows ?? [];
  const epsRows = sections.find((section) => section.id === "eps_percentile")?.rows ?? [];
  const companyName = normalizeCompanyName(snapshot.company.name);

  return (
    <>
      <div className={`report-sticky${showSticky ? " visible" : ""}`} aria-label="当前报告">
        <strong>{companyName}</strong>
        <span>{snapshot.company.ticker}</span>
        <span>{formatPrice(snapshot.current_price)}</span>
      </div>
      <section className="hero" id="overview">
        <div>
          <p className="eyebrow">{formatMarket(snapshot.company.market)} · {formatMode(snapshot.source.mode)}</p>
          <h1>{companyName} 财报分析报告</h1>
          <p className="report-intro">
            基于本地数据快照渲染。<span className="text-green">绿色</span>代表接近优秀或低估，<span className="text-amber">黄色</span>代表需要观察，<span className="text-red">红色</span>代表明显偏离目标画像；缺失值保持“缺失”，不会被当作 0。
          </p>
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
            <div className="k">生成时间</div>
            <div className="v">{formatDate(snapshot.generated_at)}</div>
          </div>
        </div>
      </section>

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

      {annualRows.length > 1 && <TrendSection rows={annualRows} />}
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

      <div className="report-layout">
        <aside className="side-rail" aria-label="快照信息">
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
        </aside>
        <section className="section-stack">
          {sections.map((section) => (
            <ReportSectionCard key={section.id} section={section} snapshot={snapshot} />
          ))}
        </section>
      </div>
    </>
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

function TrendSection({ rows }: { rows: Array<Record<string, unknown>> }) {
  const values = rows
    .map((row) => (typeof row.revenue === "number" ? row.revenue : null))
    .filter((value): value is number => value !== null);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const points = values
    .map((value, index) => {
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 100;
      const y = max === min ? 50 : 90 - ((value - min) / (max - min)) * 70;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <section className="chart-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">历史趋势</p>
          <h2>收入趋势与报告阅读顺序</h2>
        </div>
        <span>本地快照</span>
      </div>
      <div className="chart-grid">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="收入趋势">
          <polyline points={points} fill="none" stroke="#2f80ed" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
          <line x1="0" y1="90" x2="100" y2="90" stroke="#d9ded5" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="reading-order">
          <strong>先看结论，再看估值，最后追溯财务质量。</strong>
          <p>报告页应该像研究工作台，不像数据结构预览。关键指标、风险提示和年度表必须在第一屏之后立刻出现。</p>
        </div>
      </div>
    </section>
  );
}

function ReportSectionCard({ section, snapshot }: { section: ReportSection; snapshot: ReportSnapshot }) {
  const visibleRows = section.rows ?? [];
  const copy = sectionCopy(section);
  const columns = tableColumnsFor(section.id, visibleRows);
  if (section.id === "market_context") {
    return <MarketContextCard section={section} copy={copy} />;
  }
  if (section.id === "pe_percentile" || section.id === "eps_percentile") {
    return <PercentileCard section={section} copy={copy} columns={columns} />;
  }
  return (
    <article className="section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        {section.warnings.length > 0 && <span>{section.warnings.length} 个提醒</span>}
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
        <div className={section.id === "metric_explanations" ? "metric-list explanation-list" : "metric-list"}>
          {section.items.slice(0, 10).map((item) => (
            <div className={`metric-row ${item.status}${isLongMetricValue(item.value) ? " long-value" : ""}`} key={`${item.metric}-${item.label}`}>
              <div>
                <div className="metric-title-line">
                  <strong>{formatMetricLabel(item.label)}</strong>
                  {item.badge && <span className={`metric-badge ${item.badge_color ?? "muted"}`}>{formatDisplayText(item.badge)}</span>}
                </div>
                <p>{formatDisplayText(item.basis ?? item.meaning ?? "未提供口径说明")}</p>
                {section.id === "valuation" && (
                  <div className="metric-explain">
                    {item.what_it_measures && <p><b>衡量什么：</b>{formatDisplayText(item.what_it_measures)}</p>}
                    {item.implication && <p><b>背后含义：</b>{formatDisplayText(item.implication)}</p>}
                  </div>
                )}
              </div>
              <span>{formatMetricValue(item.value, item.status)}</span>
            </div>
          ))}
        </div>
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
  const status = String(details.stock_erp_status ?? "missing");
  return (
    <article className="section market-section" id={section.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
        </div>
        {section.warnings.length > 0 && <span>数据缺失</span>}
      </div>
      <p className="section-summary">{copy.summary ?? section.summary}</p>
      {details.status === "missing" ? (
        <div className="missing-block">数据缺失</div>
      ) : (
        <>
          <div className="market-card-grid">
            <InfoCard label="中国10Y国债" value={formatPercent(details.bond_latest)} note={String(details.bond_latest_date ?? "")} />
            <InfoCard label="历史分位" value={formatPercent(details.bond_percentile)} note={formatRange(details.bond_min, details.bond_max, "%")} />
            <InfoCard label="沪深300 PE" value={formatMultiple(details.csi300_pe_ttm)} note={`盈利率 ${formatPercent(details.csi300_earnings_yield)}`} />
            <InfoCard label="股债风险溢价" value={formatPercent(details.market_equity_risk_premium)} note={String(details.summary ?? "")} />
          </div>
          <div className={`erp-callout ${status}`}>
            <strong>个股风险溢价：{formatPercent(details.stock_equity_risk_premium)}</strong>
            <span>{erpStatusText(status)}</span>
          </div>
          <LineChart title="国债收益率走势" rows={rows} xKey="date" yKey="yield_pct" unit="%" details={details} referenceKeys={["bond_mean", "bond_latest"]} />
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
        <span>{formatPercent(percentile)}</span>
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
    <div className="table-wrap">
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
                <td key={column.key} className={cellToneClass(sectionId, column, row[column.key])}>{formatCell(row[column.key], column)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max === min ? 1 : max - min;
  const width = Math.max(520, points.length * 54);
  const height = 220;
  const pad = 34;
  const sx = (index: number) => pad + (index / (points.length - 1)) * (width - pad * 2);
  const sy = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2);
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${sx(index).toFixed(1)} ${sy(point.y).toFixed(1)}`).join(" ");
  return (
    <div className="line-chart-card">
      <h3>{title}</h3>
      <div className="line-chart-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} className="axis" />
          <line x1={pad} y1={pad} x2={pad} y2={height - pad} className="axis" />
          {references.map((ref) => {
            const y = sy(ref.value);
            return (
              <g key={ref.key}>
                <line x1={pad} y1={y} x2={width - pad} y2={y} className="reference-line" />
                <text x={width - pad + 4} y={y + 4} className="chart-label">{referenceLabel(ref.key)} {formatChartNumber(ref.value, unit)}</text>
              </g>
            );
          })}
          <path d={path} className="trend-line" />
          {points.map((point, index) => (
            <g key={`${point.x}-${index}`}>
              <circle cx={sx(index)} cy={sy(point.y)} r="3.2" className="trend-dot" />
              {index % Math.ceil(points.length / 8) === 0 || index === points.length - 1 ? (
                <text x={sx(index)} y={height - 10} textAnchor="middle" className="chart-label">{point.x.slice(0, 7)}</text>
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
  };
  return labels[key] ?? key;
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
    if (column?.kind === "money" || (!column?.kind && Math.abs(value) >= 100000000)) return `${(value / 100000000).toFixed(2)} 亿`;
    if (column?.kind === "percent") return `${value.toFixed(1)}%`;
    if (column?.kind === "days") return `${value.toFixed(1)} 天`;
    if (column?.kind === "multiple") return value.toFixed(2);
    return Math.abs(value) >= 100 ? value.toFixed(2) : value.toFixed(4).replace(/\.?0+$/, "");
  }
  return translateDisplayText(String(value));
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
    ...byId("valuation").filter((item) => ["OE-DCF", "芒格远景估值", "OE收益率 vs 国债"].includes(item.label)),
    ...byId("quality").filter((item) => ["毛利率", "业务纯度", "ROIIC"].includes(item.label)),
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
  const quality = sectionSignal(sections.find((section) => section.id === "quality")?.items ?? []);
  const moat = sectionSignal(sections.find((section) => section.id === "pricing_power")?.items ?? []);
  const safety = sectionSignal(sections.find((section) => section.id === "capital_safety")?.items ?? []);
  const valuation = sectionSignal(sections.find((section) => section.id === "valuation")?.items ?? []);

  return (
    <section className="buffett-overview" id="buffett_overview">
      <h2>巴芒总览</h2>
      <p>这一屏先回答五件事：企业质量、护城河、财务安全、当前估值和是否值得继续深挖。</p>
      <div className="buffett-grid">
        <SummaryCard title="企业质量" value={quality.label} note="基于经营质量指标综合判断" tone={quality.tone} />
        <SummaryCard title="护城河判断" value={moat.label} note="基于提价权与运营效率指标" tone={moat.tone} />
        <SummaryCard title="财务安全" value={safety.label} note="结合负债、净现金和资本结构信号" tone={safety.tone} />
        <SummaryCard title="当前估值" value={valuation.label} note="多个估值锚点交叉核对" tone={valuation.tone} />
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

function cellToneClass(sectionId: string, column: TableColumn, value: unknown): string {
  if (sectionId !== "owner_earnings_yield") return "";
  if (!["pess_yield", "base_yield", "leni_yield"].includes(column.key)) return "";
  const n = numberValue(value);
  if (n === null) return "";
  if (n >= 8) return "yield-good";
  if (n >= 4) return "yield-warn";
  return "yield-bad";
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
