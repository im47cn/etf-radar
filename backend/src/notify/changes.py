"""会员每日变化摘要——变化计算核心（纯逻辑，无文件 IO）。

触发集 = A + C + D（B 已在 research 阶段剔除）：
- A 象限迁移（per theme）：象限 =（long vs 50, short vs 50）四象限，跨象限则触发。
- C 全市场温度档位切换（全局）：站上率分档边界 30/50/70，同值移植自
  frontend/src/lib/breadthColor.ts 的 breadthTier()；温度数据任一侧缺失 → 跳过 C 不报错。
- D 强度评分跨 50（per theme/etf）：strength.composite 上一交易日/今日分处 50 两侧则触发。

降噪原则：**按标的聚合，不按触发器**。同一自选项当天同时触发 A/D → 合并为一行，
优先级 A > D，取最显著变化描述 + 强度数值。C 单独全局置顶。

阈值一律复用现有分档边界，不引入新魔数。IO（读 snapshot / 查 Supabase / 发信）放阶段 4。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 中线阈值：强度评分 / 象限判定统一以 50 为界（复用现有分档，无新魔数）。
MID_LINE = 50

# 温度分档边界，同值移植自 frontend/src/lib/breadthColor.ts 的 breadthTier()：
#   [0,30) 冰点 / [30,50) 偏冷 / [50,70) 偏暖 / [70,100] 过热。
# 单测钉死这些边界，防与前端漂移。
TEMPERATURE_TIERS: tuple[tuple[int, str], ...] = (
    (70, "过热"),
    (50, "偏暖"),
    (30, "偏冷"),
    (0, "冰点"),
)

ItemType = Literal["theme", "etf"]
ChangeKind = Literal["A", "D"]
Direction = Literal["up", "down"]


@dataclass(frozen=True)
class ItemChange:
    """单个自选标的的聚合变化（同标的 A+D 已合并为一行）。"""

    item_type: ItemType
    item_key: str          # theme id 或 etf code
    name: str              # 展示名
    kind: ChangeKind       # 最显著变化类型（A 优先于 D）
    direction: Direction   # up=转强 / down=转弱
    composite_prev: int
    composite_now: int


@dataclass(frozen=True)
class TemperatureChange:
    """全市场温度档位切换（全局，置顶）。"""

    tier_prev: str
    tier_now: str
    rate_prev: float
    rate_now: float
    direction: Direction   # up=升档 / down=降档


def temperature_tier(rate: float | None) -> str | None:
    """站上率 → 温度档位标签；无数据 → None。边界 30/50/70。"""
    if rate is None:
        return None
    for lower, label in TEMPERATURE_TIERS:
        if rate >= lower:
            return label
    return None  # 理论不可达（最后一档 lower=0）


def _quadrant(long: int | None, short: int | None) -> tuple[bool, bool] | None:
    """象限 =（long≥50, short≥50）；任一维度缺失 → None（无法判定 A）。"""
    if long is None or short is None:
        return None
    return (long >= MID_LINE, short >= MID_LINE)


def _quadrant_moved(
    prev: dict[str, int | None] | None,
    now: dict[str, int | None] | None,
) -> bool:
    """A：象限是否迁移。任一侧强度缺失 → 不触发。"""
    if prev is None or now is None:
        return False
    q_prev = _quadrant(prev.get("long"), prev.get("short"))
    q_now = _quadrant(now.get("long"), now.get("short"))
    if q_prev is None or q_now is None:
        return False
    return q_prev != q_now


def _crossed_mid(prev: int | None, now: int | None) -> Direction | None:
    """D：composite 是否跨越 50 中线；返回方向或 None。

    以 ≥50 为「强侧」，<50 为「弱侧」，两侧不同则视为跨越。
    """
    if prev is None or now is None:
        return None
    prev_strong = prev >= MID_LINE
    now_strong = now >= MID_LINE
    if prev_strong == now_strong:
        return None
    return "up" if now_strong else "down"


def diff_item(
    item_type: ItemType,
    item_key: str,
    name: str,
    prev_strength: dict[str, int | None] | None,
    now_strength: dict[str, int | None] | None,
) -> ItemChange | None:
    """计算单标的的聚合变化（A/D 合并，优先级 A>D）；无变化 → None。

    prev_strength / now_strength：形如 {short,mid,long,composite}，值可为 None。
    方向以 composite 前后值升降判定；composite 缺失时不产出。
    """
    if now_strength is None:
        return None
    comp_prev = prev_strength.get("composite") if prev_strength else None
    comp_now = now_strength.get("composite")

    a_moved = _quadrant_moved(prev_strength, now_strength)
    d_dir = _crossed_mid(comp_prev, comp_now)

    if not a_moved and d_dir is None:
        return None

    # 优先级 A > D：A 触发时归类 A，否则归类 D。
    kind: ChangeKind = "A" if a_moved else "D"

    # 方向：优先按 composite 升降；composite 无法判定时退化为 D 的跨向。
    # 无论哪条分支，产出时 composite 前后值都必须非 None（否则无可靠数值），故此处收窄。
    if comp_prev is not None and comp_now is not None:
        direction: Direction = "up" if comp_now >= comp_prev else "down"
    elif d_dir is not None:
        # d_dir 非 None 蕴含 _crossed_mid 的两参数均非 None。
        direction = d_dir
    else:
        # A 触发但 composite 缺失 → 无可靠数值方向，保守跳过。
        return None

    if comp_prev is None or comp_now is None:
        return None

    return ItemChange(
        item_type=item_type,
        item_key=item_key,
        name=name,
        kind=kind,
        direction=direction,
        composite_prev=comp_prev,
        composite_now=comp_now,
    )


def diff_temperature(
    prev_rate: float | None,
    now_rate: float | None,
) -> TemperatureChange | None:
    """C：全市场温度档位是否切换。任一侧缺失 → None（安全跳过 C）。"""
    tier_prev = temperature_tier(prev_rate)
    tier_now = temperature_tier(now_rate)
    if tier_prev is None or tier_now is None:
        return None
    if tier_prev == tier_now:
        return None
    assert prev_rate is not None and now_rate is not None  # tier 非 None 蕴含
    return TemperatureChange(
        tier_prev=tier_prev,
        tier_now=tier_now,
        rate_prev=prev_rate,
        rate_now=now_rate,
        direction="up" if now_rate >= prev_rate else "down",
    )


def latest_market_rate(temperature: dict[str, object] | None) -> float | None:
    """从 market_temperature snapshot 取全市场 ma20 站上率的最新值。

    结构：{periods: {ma20: {market: [{date, rate}, ...]}}}。
    按序列内最大 date 对应的 rate 取值（非位置末元素），防数据乱序 / 补写历史时
    静默取错值导致 C 全员误报。数据缺失 / 结构不符 / 空序列 → None（安全跳过 C）。
    """
    if not temperature:
        return None
    periods = temperature.get("periods")
    if not isinstance(periods, dict):
        return None
    ma20 = periods.get("ma20")
    if not isinstance(ma20, dict):
        return None
    series = ma20.get("market")
    if not isinstance(series, list) or not series:
        return None
    latest_point: dict[str, object] | None = None
    latest_date: str | None = None
    for point in series:
        if not isinstance(point, dict):
            continue
        d = point.get("date")
        if not isinstance(d, str):
            continue
        if latest_date is None or d > latest_date:
            latest_date = d
            latest_point = point
    if latest_point is None:
        return None
    rate = latest_point.get("rate")
    return float(rate) if isinstance(rate, (int, float)) else None


def index_strength_by_key(
    items: list[dict[str, object]],
    key_field: str,
) -> dict[str, dict[str, int | None]]:
    """把 themes/etfs 列表按标的键索引为 {key: strength dict}。

    key_field：theme 用 'id'，etf 用 'code'。缺 strength 的项映射为空 dict。
    """
    out: dict[str, dict[str, int | None]] = {}
    for it in items:
        key = it.get(key_field)
        if key is None:
            continue
        strength = it.get("strength")
        out[str(key)] = strength if isinstance(strength, dict) else {}
    return out


def build_watchlist_changes(
    watchlist: list[tuple[ItemType, str, str]],
    prev_index: dict[ItemType, dict[str, dict[str, int | None]]],
    now_index: dict[ItemType, dict[str, dict[str, int | None]]],
) -> list[ItemChange]:
    """对一位用户的自选清单逐项算聚合变化，返回有变化的行（无变化自动过滤）。

    watchlist：[(item_type, item_key, name), ...]。
    prev_index/now_index：{item_type: {item_key: strength}}，由 index_strength_by_key 构建。
    空自选 → 空列表。
    """
    changes: list[ItemChange] = []
    for item_type, item_key, name in watchlist:
        prev_strength = prev_index.get(item_type, {}).get(item_key)
        now_strength = now_index.get(item_type, {}).get(item_key)
        ch = diff_item(item_type, item_key, name, prev_strength, now_strength)
        if ch is not None:
            changes.append(ch)
    return changes


def find_prev_snapshot_dir(existing_dirs: list[str], today: str) -> str | None:
    """按实际存在的 snapshot 目录名回溯上一交易日（非目录名减一天）。

    existing_dirs：形如 ['2026-07-02','2026-07-03',...] 的目录名列表（可乱序）。
    返回严格早于 today 的最大目录名；无则 None。
    """
    earlier = sorted(d for d in existing_dirs if d < today)
    return earlier[-1] if earlier else None
