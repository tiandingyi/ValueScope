# core/config.py — auto-extracted
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


REPORTS_DIR = "reports"

OUTPUT_DIR = Path(REPORTS_DIR) / "pricing_power"

DISCOUNT_RATE = 0.10

TERMINAL_GROWTH = 0.03

PROJECTION_YEARS = 10

MARGIN_OF_SAFETY = 0.30  # 默认值，实际按企业质量动态调整

FADE_RATE = 0.80          # B级：竞争优势衰减率，假设护城河逐年削弱 20%

OE_HAIRCUT = 0.90         # B级：盈利正常化折扣，假设当前盈利高于长期可持续水平

G_MAX_CAP = 0.15          # B级：长期增速上限，不假设任何公司持续增长超 15%

LAST_PROFILE: Dict[str, float] = {}

# Evidence levels used by INDICATOR_GUIDE:
# A = model/theory-derived
# B = long-run empirical convention
# C = engineering guardrail


def _compute_dynamic_mos(metrics: Sequence) -> Tuple[float, str]:
    """根据经营指标 tone 计算动态安全边际。

    Returns (mos_ratio, grade_label).
    """
    if not metrics:
        return MARGIN_OF_SAFETY, "标准"
    _ts = {"good": 2, "warn": 1, "muted": 1, "bad": 0}
    total = sum(_ts.get(getattr(m, "tone", "muted"), 1) for m in metrics)
    avg = total / len(metrics)
    # C级：工程化分层映射，把确定性评分转成安全边际区间。
    if avg >= 1.55:
        return 0.20, "高确定性"
    if avg >= 1.25:
        return 0.30, "标准"
    if avg >= 0.95:
        return 0.40, "中等不确定性"
    return 0.50, "高不确定性"

# 行业差异化折现率: 现金流确定性越高 → 折现率越低
INDUSTRY_DISCOUNT_MAP: Dict[str, float] = {
    "白酒": 0.08,
    "调味品": 0.08,
    "饮料": 0.09,
    "食品": 0.09,
    "医药": 0.09,
    "消费": 0.09,
    "银行": 0.10,
    "保险": 0.10,
    "证券": 0.11,
    "房地产": 0.12,
    "建筑": 0.12,
    "有色": 0.12,
    "钢铁": 0.12,
    "化工": 0.11,
    "汽车": 0.11,
    "电子": 0.11,
    "半导体": 0.12,
    "计算机": 0.11,
    "传媒": 0.11,
    "通信": 0.10,
    "互联网": 0.11,
    "零售": 0.10,
    "电力": 0.09,
    "公用事业": 0.09,
}

def _get_industry_discount(industry_text: str, company_name: str = "") -> Tuple[float, str]:
    """根据行业关键词匹配折现率。返回 (rate, matched_key|'默认')."""
    if not industry_text:
        return DISCOUNT_RATE, "默认"
    for key, rate in INDUSTRY_DISCOUNT_MAP.items():
        if key in industry_text:
            return rate, key
    return DISCOUNT_RATE, "默认"

# 行业差异化芒格退出PE: (低档, 基准, 高档)
INDUSTRY_EXIT_PE: Dict[str, Tuple[int, int, int]] = {
    "银行": (6, 8, 10),
    "保险": (8, 10, 13),
    "白酒": (20, 25, 30),
    "调味品": (20, 25, 30),
    "饮料": (18, 22, 27),
    "食品": (15, 20, 25),
    "医药": (18, 22, 28),
    "消费": (15, 20, 25),
    "电力": (10, 14, 18),
    "公用事业": (10, 14, 18),
    "证券": (10, 15, 20),
    "房地产": (6, 10, 14),
    "建筑": (8, 12, 16),
    "有色": (8, 12, 18),
    "钢铁": (6, 10, 14),
    "化工": (10, 15, 20),
    "汽车": (10, 15, 20),
    "电子": (15, 20, 25),
    "半导体": (15, 20, 28),
    "计算机": (15, 20, 28),
    "传媒": (12, 18, 25),
    "通信": (12, 16, 20),
    "互联网": (15, 20, 28),
    "零售": (12, 16, 20),
}

DEFAULT_EXIT_PE: Tuple[int, int, int] = (15, 20, 25)

def _get_industry_exit_pes(industry_text: str) -> Tuple[Tuple[int, int, int], str]:
    """根据行业关键词匹配芒格退出PE。返回 ((low, mid, high), matched_key|'默认')."""
    if not industry_text:
        return DEFAULT_EXIT_PE, "默认"
    for key, pes in INDUSTRY_EXIT_PE.items():
        if key in industry_text:
            return pes, key
    return DEFAULT_EXIT_PE, "默认"

# ── 研发资本化调节 ─────────────────────────────────────
# 高研发行业：部分研发支出实质为扩张性资本投入，可加回OE以还原真实造血能力。
# 比例含义：当期研发费用中"扩张性"占比，加回到调节后净利润。
# 匹配顺序：精确关键词在前，通用关键词在后。
RD_CAP_INDUSTRY_MAP: Dict[str, float] = {
    "创新药": 0.50,
    "生物制品": 0.45,
    "生物": 0.45,
    "软件": 0.40,
    "医药": 0.35,
    "制药": 0.35,
    "计算机": 0.35,
    "互联网": 0.35,
    "医疗器械": 0.30,
    "医疗设备": 0.30,
    "半导体": 0.25,
    "芯片": 0.25,
    "集成电路": 0.25,
    "新能源汽车": 0.25,
    "智能驾驶": 0.25,
    "汽车零部件": 0.20,
    "汽车": 0.20,
    "游戏": 0.25,
    "航空航天": 0.20,
    "国防军工": 0.20,
    "电子": 0.20,
    "通信": 0.20,
    "光伏": 0.20,
    "新能源": 0.20,
}

# 港美股公司名称→行业兜底映射（当 industry_text 为空或无法匹配时使用 company_name）
RD_CAP_NAME_OVERRIDES: Dict[str, Tuple[float, str]] = {
    "腾讯": (0.35, "互联网"),
    "阿里巴巴": (0.35, "互联网"),
    "百度": (0.35, "互联网"),
    "京东": (0.35, "互联网"),
    "美团": (0.35, "互联网"),
    "拼多多": (0.35, "互联网"),
    "网易": (0.35, "互联网"),
    "字节": (0.35, "互联网"),
    "苹果": (0.20, "电子"),
    "Apple": (0.20, "电子"),
    "Microsoft": (0.40, "软件"),
    "微软": (0.40, "软件"),
    "Google": (0.35, "互联网"),
    "Alphabet": (0.35, "互联网"),
    "Meta": (0.35, "互联网"),
    "Amazon": (0.35, "互联网"),
    "亚马逊": (0.35, "互联网"),
    "NVIDIA": (0.25, "芯片"),
    "英伟达": (0.25, "芯片"),
    "台积电": (0.25, "半导体"),
    "TSMC": (0.25, "半导体"),
    "中芯国际": (0.25, "半导体"),
    "恒瑞": (0.35, "制药"),
    "迈瑞": (0.35, "医药"),
    "药明": (0.45, "生物"),
    "Snowflake": (0.40, "软件"),
    "Salesforce": (0.40, "软件"),
    "Adobe": (0.40, "软件"),
    "Oracle": (0.40, "软件"),
    "Intel": (0.25, "半导体"),
    "AMD": (0.25, "半导体"),
    "Qualcomm": (0.25, "芯片"),
    "Broadcom": (0.25, "芯片"),
    "Tesla": (0.25, "新能源汽车"),
    "特斯拉": (0.25, "新能源汽车"),
    "比亚迪": (0.25, "新能源汽车"),
    "理想": (0.25, "新能源汽车"),
    "蔚来": (0.25, "新能源汽车"),
    "小鹏": (0.25, "新能源汽车"),
    "宁德时代": (0.20, "新能源"),
    "隆基": (0.20, "光伏"),
    "大疆": (0.25, "智能驾驶"),
    "华为": (0.35, "通信"),
    "中兴": (0.20, "通信"),
    "科大讯飞": (0.35, "计算机"),
    "海康威视": (0.20, "电子"),
    "韦尔股份": (0.25, "芯片"),
    "Moderna": (0.50, "创新药"),
    "Pfizer": (0.35, "制药"),
    "Johnson": (0.30, "医疗器械"),
    "Medtronic": (0.30, "医疗器械"),
    "Intuitive": (0.30, "医疗器械"),
}
RD_CAP_DEFAULT: float = 0.0  # 未匹配行业不调节


def _get_rd_capitalization_ratio(industry_text: str, company_name: str = "") -> Tuple[float, str]:
    """根据行业关键词匹配研发资本化调节比例。返回 (ratio, matched_key|'默认').
    优先匹配 industry_text，其次匹配 company_name（含名称兜底映射）。"""
    # 1. 行业关键词匹配
    if industry_text:
        for key, ratio in RD_CAP_INDUSTRY_MAP.items():
            if key in industry_text:
                return ratio, key
    # 2. 公司名称行业关键词匹配
    if company_name:
        for key, ratio in RD_CAP_INDUSTRY_MAP.items():
            if key in company_name:
                return ratio, key
        # 3. 名称兜底映射
        for name_key, (ratio, label) in RD_CAP_NAME_OVERRIDES.items():
            if name_key in company_name:
                return ratio, label
    return RD_CAP_DEFAULT, "默认"


PLEDGE_PROFILE_TIMEOUT_SEC = 4

PLEDGE_RATIO_TIMEOUT_SEC = 6

PLEDGE_MAX_DATES = 5

PLEDGE_TOTAL_TIMEOUT_SEC = 30

BOND_ZH_US_RATE_TIMEOUT_SEC = 20

A_MARKET_PE_SAMPLE = (
    "sh600519",
    "sz000858",
    "sz300750",
    "sh601318",
    "sh600036",
    "sh601899",
    "sz000333",
    "sh601166",
    "sh600900",
    "sz002594",
    "sh601088",
    "sh600030",
    "sh600276",
    "sh600887",
    "sz000651",
    "sh600309",
    "sh600050",
    "sh601668",
    "sh601888",
    "sh600023",
)

MARKET_PE_ANCHOR_CACHE = Path(REPORTS_DIR) / "pricing_power" / ".a_market_pe_anchor_cache.json"

class TimeoutAbort(Exception):
    pass

# ---------------------------------------------------------------------------
# DataProvider — 把所有被 HK/US 模块替换的「数据获取接口」集中到一个对象
# 内部函数通过 _dp.<method>() 调用；HK/US 只需替换 _dp 的字段。
# ---------------------------------------------------------------------------
@dataclass
class DataProvider:
    """可替换的数据获取接口集合；默认实现指向 A 股函数。"""
    load_data: object = None                     # (code) -> Dict
    get_company_info: object = None              # (code) -> (name, shares, industry)
    get_current_price: object = None             # (code) -> (price, source, time)
    get_historical_price_as_of: object = None    # (code, asof_date) -> (price, source, time) | None
    fetch_stock_daily_hist_long: object = None   # (code, years_back) -> DataFrame
    fetch_market_pe_anchor: object = None        # () -> (pe, label)
    fetch_risk_free_yield: object = None         # () -> (pct, date_str)
    fetch_pledge_snapshot: object = None         # (code) -> (dict|None, status)
    fetch_share_change_history: object = None    # (code) -> (DataFrame, status)
    fetch_restricted_release_queue: object = None  # (code) -> (DataFrame, status)
    annual_cols_from_abstract: object = None      # (abs_df) -> List[str]
    output_dir: Path = Path(REPORTS_DIR) / "pricing_power"

_dp = DataProvider()

_DEDUCT_PARENT_NET_PROFIT_NAMES = (
    "归属于上市公司股东的扣除非经常性损益的净利润",
    "归属于上市公司股东的扣除非经常性损益后的净利润",
    "归母扣非净利润",
    "扣非净利润",
)

_REAL_EPS_ROW_NAMES = (
    "归属于上市公司股东的扣除非经常性损益的每股收益",
    "扣除非经常性损益后的基本每股收益",
    "扣除非经常性损益后基本每股收益",
    "每股收益(扣除非经常性损益)",
    "扣非每股收益",
)

MAINT_CAPEX_FLOOR_RATIO = 0.70

# ── 行业维护性 Capex 比例 ───────────────────────────────
# 重资产扩张型行业的 capex 中，增长性占比远高于维护性。
# 默认 70% 对成熟制造业合理，但对零售扩张、科技基建等偏高。
# 此映射覆盖 MAINT_CAPEX_FLOOR_RATIO，让 OE 更准确地反映真实造血能力。
MAINT_CAPEX_INDUSTRY_MAP: Dict[str, float] = {
    # 零售/消费：新开门店 = 增长投资，维护性占比低
    "零售": 0.40,
    "超市": 0.35,
    "百货": 0.40,
    "商贸": 0.40,
    "餐饮": 0.45,
    "连锁": 0.40,
    # 科技基建：数据中心/云 capex 多为扩容
    "云计算": 0.40,
    "数据中心": 0.40,
    # 物流/仓储
    "物流": 0.45,
    "快递": 0.45,
    # 轻资产行业：capex 本身就小，比例影响有限
    "软件": 0.50,
    "互联网": 0.45,
    "游戏": 0.45,
    # 传统重资产：维护性 capex 占大头
    "电力": 0.75,
    "公用事业": 0.75,
    "钢铁": 0.75,
    "石油": 0.70,
    "矿业": 0.70,
    "有色": 0.70,
}

# 港美股公司名称→维护性Capex比例兜底映射
MAINT_CAPEX_NAME_OVERRIDES: Dict[str, Tuple[float, str]] = {
    "Costco": (0.35, "零售"),
    "开市客": (0.35, "零售"),
    "Walmart": (0.40, "零售"),
    "沃尔玛": (0.40, "零售"),
    "Target": (0.40, "零售"),
    "Home Depot": (0.40, "零售"),
    "Lowe": (0.40, "零售"),
    "Kroger": (0.40, "零售"),
    "克罗格": (0.40, "零售"),
    "Amazon": (0.40, "零售"),
    "亚马逊": (0.40, "零售"),
    "Starbucks": (0.40, "餐饮"),
    "星巴克": (0.40, "餐饮"),
    "McDonald": (0.45, "餐饮"),
    "麦当劳": (0.45, "餐饮"),
    "永辉": (0.40, "超市"),
    "物美": (0.40, "超市"),
    "高鑫": (0.40, "超市"),
    "名创优品": (0.40, "零售"),
}


def _get_maint_capex_floor_ratio(industry_text: str, company_name: str = "") -> Tuple[float, str]:
    """根据行业关键词匹配维护性Capex下限比例。返回 (ratio, matched_key|'默认')."""
    if industry_text:
        for key, ratio in MAINT_CAPEX_INDUSTRY_MAP.items():
            if key in industry_text:
                return ratio, key
    if company_name:
        for key, ratio in MAINT_CAPEX_INDUSTRY_MAP.items():
            if key in company_name:
                return ratio, key
        for name_key, (ratio, label) in MAINT_CAPEX_NAME_OVERRIDES.items():
            if name_key in company_name:
                return ratio, label
    return MAINT_CAPEX_FLOOR_RATIO, "默认"

@dataclass
class MetricAssessment:
    label: str
    value_display: str
    rule_display: str
    status_text: str
    tone: str
    meaning: str
    implication: str
    formula: str = ""
    trend: str = ""

@dataclass
class ValuationAssessment:
    label: str
    value_display: str
    rule_display: str
    status_text: str
    tone: str
    meaning: str
    implication: str
    formula: str = ""


# ── 港美股行业覆盖注册表 ─────────────────────────────────
# 港美股通常无法从数据源获取可匹配的中文行业关键词，导致
# _get_industry_discount / _get_industry_exit_pes 全部回退到默认值。
# 本注册表通过「代码→中文行业关键词」映射，让已有行业差异化逻辑对港美股同样生效。
#
# 匹配优先级：代码精确匹配 > 公司名称子串匹配（复用已有 INDUSTRY_* 映射表关键词）。
# 新增公司只需在此处加一行，无需修改函数逻辑。

HK_US_INDUSTRY_CODE_MAP: Dict[str, str] = {
    # ── 银行 ──
    "BAC": "银行", "JPM": "银行", "WFC": "银行", "C": "银行",
    "GS": "银行", "MS": "银行", "USB": "银行", "PNC": "银行",
    "03988": "银行", "01398": "银行", "03968": "银行", "00939": "银行",
    # ── 保险 ──
    "BRK-B": "保险", "AIG": "保险",
    "02318": "保险", "02628": "保险",
    # ── 零售 ──
    "COST": "零售", "WMT": "零售", "KR": "零售", "TGT": "零售",
    "HD": "零售", "LOW": "零售",
    # ── 电子 ──
    "AAPL": "电子",
    "01810": "电子",   # 小米
    "00992": "电子",   # 联想
    # ── 半导体 ──
    "TSM": "半导体", "INTC": "半导体", "AMD": "半导体",
    "NVDA": "半导体", "QCOM": "半导体", "AVGO": "半导体",
    "00981": "半导体", # 中芯国际
    # ── 互联网 ──
    "GOOGL": "互联网", "GOOG": "互联网", "META": "互联网",
    "AMZN": "互联网", "NTES": "互联网",
    "00700": "互联网", "09988": "互联网", "09618": "互联网",
    "09888": "互联网", "01024": "互联网", "03690": "互联网",
    "09626": "互联网", "09999": "互联网",
    # ── 计算机/软件 ──
    "MSFT": "计算机", "SNOW": "计算机", "CRM": "计算机",
    "ADBE": "计算机", "ORCL": "计算机",
    # ── 医药 ──
    "BIIB": "医药", "PFE": "医药", "JNJ": "医药",
    "LLY": "医药", "ABBV": "医药", "MRK": "医药",
    "MRNA": "医药", "GILD": "医药", "DVA": "医药",
    # ── 化工/石油 ──
    "OXY": "化工", "XOM": "化工", "CVX": "化工",
    # ── 汽车 ──
    "TSLA": "汽车",
    "01211": "汽车",   # 比亚迪
    # ── 有色/矿业 ──
    "01208": "有色",   # 五矿资源
    "02099": "有色",   # 中国黄金国际
    # ── 通信 ──
    "00941": "通信",   # 中国移动
    "00728": "通信",   # 中国电信
}

# 公司名称子串→行业关键词（当代码未命中时的兜底）
HK_US_INDUSTRY_NAME_MAP: Dict[str, str] = {
    "银行": "银行", "Bank": "银行",
    "保险": "保险", "Insurance": "保险",
    "石油": "化工", "Petroleum": "化工", "Oil & Gas": "化工",
    "黄金": "有色", "Gold": "有色", "Mining": "有色", "矿业": "有色",
    "半导体": "半导体", "Semiconductor": "半导体",
    "制药": "医药", "Pharma": "医药", "Biotech": "医药",
    "零售": "零售", "Retail": "零售",
    "互联网": "互联网", "Internet": "互联网",
    "软件": "计算机", "Software": "计算机",
    "汽车": "汽车", "Auto": "汽车",
    "电力": "电力", "Power": "电力", "Utility": "公用事业",
}


def resolve_hk_us_industry(code: str, company_name: str = "") -> str:
    """从注册表查找港美股行业关键词。

    优先代码精确匹配，其次公司名称子串匹配。返回中文行业关键词或空字符串。
    """
    ind = HK_US_INDUSTRY_CODE_MAP.get(code, "")
    if ind:
        return ind
    if company_name:
        for key, val in HK_US_INDUSTRY_NAME_MAP.items():
            if key in company_name:
                return val
    return ""

