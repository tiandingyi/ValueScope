"""
持久化数据缓存 — 将 load_data() 返回的财报数据 dict 序列化为 JSON 存储，
后续运行同一公司时优先从缓存加载，跳过耗时的 API 调用。

缓存位置：data/raw/<code>.json
函数级缓存：data/raw/fn_cache/<func>_<args>.json
失效策略：缓存文件超过 CACHE_MAX_AGE_DAYS 天自动失效；
         或通过 --no-cache 强制刷新。
当前股价（current_price_tuple）不缓存，每次实时获取。
"""
from __future__ import annotations

import functools
import json
import re
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

CACHE_DIR = Path("data/raw")
CACHE_MAX_AGE_DAYS = 90

# 缓存版本：修改数据结构/序列化格式时递增，旧缓存自动失效
CACHE_VERSION = "2"

# 全局开关，由 run.py 根据 --no-cache 设置
USE_CACHE = True


def _df_to_json(df: pd.DataFrame) -> dict:
    """DataFrame → 可 JSON 序列化的 dict（split 格式保留列名和索引）。"""
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return {"_empty": True}
    result = json.loads(df.to_json(orient="split", date_format="iso", default_handler=str))
    # 保存列 dtype，用于反序列化时恢复（避免 "000858" → 858 等问题）
    result["_dtypes"] = {str(c): str(df[c].dtype) for c in df.columns}
    return result


def _json_to_df(obj: dict) -> pd.DataFrame:
    """从 split 格式 dict 还原 DataFrame。"""
    if obj is None or obj.get("_empty"):
        return pd.DataFrame()
    dtypes = obj.get("_dtypes")
    if dtypes:
        # 手动构建 DataFrame 以避免 pd.read_json 的类型推断
        # （如 "000858" → 858）
        columns = obj.get("columns", [])
        data = obj.get("data", [])
        index = obj.get("index")
        df = pd.DataFrame(data, columns=columns, index=index)
        for col, dt in dtypes.items():
            if col in df.columns:
                try:
                    if dt == "object":
                        pass  # 已经是原始值，保持不变
                    elif "datetime" in dt:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    elif "int" in dt:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    elif "float" in dt:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                except Exception:
                    pass
        return df
    # 兜底：旧缓存无 _dtypes 字段
    return pd.read_json(StringIO(json.dumps(obj)), orient="split")


def _serialize_value(val: Any) -> Any:
    """递归序列化 data dict 中的值。"""
    if isinstance(val, pd.DataFrame):
        return {"_type": "dataframe", "_data": _df_to_json(val)}
    if isinstance(val, dict):
        return {"_type": "dict", "_data": {k: _serialize_value(v) for k, v in val.items()}}
    if isinstance(val, (list, tuple)):
        tag = "tuple" if isinstance(val, tuple) else "list"
        return {"_type": tag, "_data": [_serialize_value(v) for v in val]}
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val) if not np.isnan(val) else None
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    return val


def _deserialize_value(obj: Any) -> Any:
    """递归反序列化。"""
    if isinstance(obj, dict):
        t = obj.get("_type")
        if t == "dataframe":
            return _json_to_df(obj["_data"])
        if t == "dict":
            return {k: _deserialize_value(v) for k, v in obj["_data"].items()}
        if t == "tuple":
            return tuple(_deserialize_value(v) for v in obj["_data"])
        if t == "list":
            return [_deserialize_value(v) for v in obj["_data"]]
        # 普通 dict（无 _type 标记）
        return {k: _deserialize_value(v) for k, v in obj.items()}
    return obj


def _cache_path(code: str, market: str = "") -> Path:
    prefix = f"{market}_" if market else ""
    return CACHE_DIR / f"{prefix}{code}.json"


def save_cache(code: str, data: Dict[str, Any], *, market: str = "") -> None:
    """将 load_data() 返回的 data dict 写入缓存文件。
    排除 current_price_tuple（每次实时获取）。"""
    to_save = {}
    for k, v in data.items():
        if k == "current_price_tuple":
            continue
        to_save[k] = _serialize_value(v)
    to_save["_meta"] = {
        "code": code,
        "cached_at": datetime.now().isoformat(),
        "timestamp": time.time(),
        "version": CACHE_VERSION,
        "market": market,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(code, market)
    path.write_text(json.dumps(to_save, ensure_ascii=False, indent=1), encoding="utf-8")


def _balance_df_is_sane(df: pd.DataFrame) -> bool:
    """检查 balance_df 是否是真正的资产负债表（而非被碰撞污染的现金流量表）。"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return True  # 空表视为可接受，不触发失效
    _BALANCE_MARKERS = {"货币资金", "流动资产", "资产总计", "应付账款",
                        "存货", "应收账款", "应付票据及应付账款"}
    return bool(set(df.columns) & _BALANCE_MARKERS)


def _cashflow_extras_is_sane(ce: pd.DataFrame, balance_raw: pd.DataFrame) -> bool:
    """检查 cashflow_extras.da 是否意外等于 balance_raw 中的累计折旧（污染标志）。

    当 fn_cache key 碰撞时，cashflow_raw = balance_raw，fetch_cashflow_extras
    的 DA fallback 会将 balance_raw['累计折旧']（累计值，非年度流量）误用为 DA。
    只要前5个年度中有 ≥2 对非空值 (da, 累计折旧) 完全吻合，即判定为污染。
    """
    if ce is None or not isinstance(ce, pd.DataFrame) or ce.empty:
        return True
    if balance_raw is None or not isinstance(balance_raw, pd.DataFrame):
        return True
    if "累计折旧" not in balance_raw.columns or "da" not in ce.columns:
        return True
    try:
        annual = balance_raw[balance_raw["报告日"].astype(str).str.endswith("1231")]
        leiji = pd.to_numeric(annual["累计折旧"], errors="coerce").values
        da = ce["da"].values
        n = min(len(leiji), len(da), 5)
        if n == 0:
            return True
        # 检查前5对中，非空的 累计折旧 与 da 是否吻合
        matched = sum(
            1 for a, b in zip(leiji[:n], da[:n])
            if pd.notna(a) and pd.notna(b) and abs(float(a) - float(b)) < 1.0
        )
        return matched < 2  # ≥2 对完全吻合 → 判定为污染 → 返回 False (not sane)
    except Exception:
        return True


def load_cache(code: str, *, market: str = "") -> Optional[Dict[str, Any]]:
    """从缓存文件加载 data dict。
    返回 None 如果缓存不存在、已过期、版本不匹配或全局开关关闭。"""
    if not USE_CACHE:
        return None
    # Try new market-prefixed path first, then fall back to legacy path
    path = _cache_path(code, market)
    _using_legacy = False
    if not path.exists() and market:
        path = _cache_path(code)  # legacy fallback
        _using_legacy = True
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    meta = raw.get("_meta", {})
    # 版本校验：旧版缓存（无 version 字段）视为过期
    if meta.get("version") != CACHE_VERSION:
        return None
    # 市场校验：传入 market 时，必须与缓存一致
    # For legacy fallback: reject if cache has a DIFFERENT market, or has NO market at all
    # (a cache without market field could be from any market — too risky to accept cross-market)
    if market:
        cached_market = meta.get("market", "")
        if cached_market != market:
            return None
    ts = meta.get("timestamp", 0)
    age_days = (time.time() - ts) / 86400
    if age_days > CACHE_MAX_AGE_DAYS:
        return None
    result = {}
    for k, v in raw.items():
        if k == "_meta":
            continue
        result[k] = _deserialize_value(v)
    # 防御：校验 balance_df 不是被 fn_cache key 碰撞污染的现金流量表数据
    if not _balance_df_is_sane(result.get("balance")):
        print(f"  ⚠️  缓存 balance_df 疑似被污染（不含资产负债表特征列），强制刷新")
        path.unlink(missing_ok=True)
        return None
    # 防御：校验 cashflow_extras.da 不是 balance_raw 中的累计折旧（fn_cache 碰撞导致 cashflow_raw=balance_raw）
    if not _cashflow_extras_is_sane(result.get("cashflow_extras"), result.get("balance_raw")):
        print(f"  ⚠️  缓存 cashflow_extras.da 疑似为累计折旧（fn_cache 碰撞），强制刷新")
        path.unlink(missing_ok=True)
        return None
    return result


def cache_age_info(code: str, market: str = "") -> Tuple[bool, str]:
    """返回缓存是否存在及简短描述，用于终端提示。"""
    path = _cache_path(code, market)
    if not path.exists() and market:
        path = _cache_path(code)  # legacy fallback
    if not path.exists():
        return False, "无缓存"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        meta = raw.get("_meta", {})
        cached_at = meta.get("cached_at", "?")
        ts = meta.get("timestamp", 0)
        age_days = (time.time() - ts) / 86400
        ver = meta.get("version", "?")
        if ver != CACHE_VERSION:
            return False, f"缓存版本不匹配（v{ver}→v{CACHE_VERSION}，需刷新）"
        if age_days > CACHE_MAX_AGE_DAYS:
            return False, f"缓存已过期（{cached_at}，{age_days:.0f}天前）"
        mkt = meta.get("market", "")
        tag = f"v{ver}" + (f"/{mkt}" if mkt else "")
        return True, f"使用缓存（{cached_at}，{age_days:.0f}天前，{tag}）"
    except Exception:
        return False, "缓存读取失败"


# ---------------------------------------------------------------------------
# 函数级磁盘缓存装饰器
# ---------------------------------------------------------------------------
_FN_CACHE_DIR = CACHE_DIR / "fn_cache"

def _fn_cache_dir() -> Path:
    """返回带版本号的函数级缓存目录，版本变更时自动隔离旧缓存。"""
    return _FN_CACHE_DIR / f"v{CACHE_VERSION}"

def _sanitize_key(s: str) -> str:
    """将字符串转为稳定、唯一的文件名安全字符串。

    对于含非 ASCII 字符（如中文）的参数，追加 6 位 MD5 短 hash，
    避免"资产负债表"与"现金流量表"等等长字符串映射到相同下划线序列。
    """
    import hashlib
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(s))
    if sanitized != str(s):
        h = hashlib.md5(s.encode("utf-8")).hexdigest()[:6]
        return f"{sanitized}_{h}"
    return sanitized


def disk_cache(ttl_days: float = 1.0):
    """函数级磁盘缓存装饰器。

    用法（可叠加在 @lru_cache 下方）::

        @lru_cache(maxsize=32)
        @disk_cache(ttl_days=1)
        def my_slow_api(code: str) -> pd.DataFrame: ...

    - 结果通过 _serialize_value/_deserialize_value 序列化，支持
      DataFrame / dict / tuple / list / scalar。
    - 遵守全局 USE_CACHE 开关和 --no-cache。
    - 缓存文件: data/raw/fn_cache/<func_name>_<arg1>_<arg2>.json
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not USE_CACHE:
                return fn(*args, **kwargs)
            # 构建缓存 key
            key_parts = [fn.__name__]
            key_parts.extend(_sanitize_key(str(a)) for a in args)
            key_parts.extend(f"{_sanitize_key(k)}_{_sanitize_key(v)}"
                             for k, v in sorted(kwargs.items()))
            fname = "_".join(key_parts) + ".json"
            cache_dir = _fn_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / fname
            # 尝试从磁盘读取
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    ts = raw.get("_ts", 0)
                    if (time.time() - ts) / 86400 <= ttl_days:
                        return _deserialize_value(raw["_data"])
                except (json.JSONDecodeError, KeyError, OSError):
                    pass
            # 缓存未命中，调用原函数
            result = fn(*args, **kwargs)
            # 写入磁盘
            try:
                payload = {
                    "_ts": time.time(),
                    "_fn": fn.__name__,
                    "_data": _serialize_value(result),
                }
                path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass  # 写缓存失败不影响正常返回
            return result
        return wrapper
    return decorator
