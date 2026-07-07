"""会员每日变化摘要——编排 + Supabase 查询 + 发信（IO 层）。

阶段 4：串起阶段 3 的纯变化计算与真实数据/发信。流程：
  1. 读今日 + 上一交易日 snapshot（themes/etfs/market_temperature）。
  2. 查 Supabase（service_role REST）：生效会员、各自 watchlist、notify_prefs、邮箱。
  3. 逐会员套用 build_watchlist_changes（A/D）+ diff_temperature（C，全局置顶）；
     无任何变化 → 跳过；有变化 → 拼邮件 → Resend 发送 → 写 digest_log。
  4. 幂等：digest_log UNIQUE(run_date,user_id)，已有记录当天不重复处理。
  5. 边界安全：无会员/无自选/prev 缺失/温度缺失/单用户发信失败——逐用户 try 隔离，不中断整体。

依赖仅 stdlib（urllib/json）+ 阶段 3 的 changes.py，零新增第三方依赖（与 dapanyuntu_provider 一致）。
所有密钥从 env 读取，绝不硬编码。合规：邮件文案零操作动词。
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .changes import (
    ItemChange,
    ItemType,
    TemperatureChange,
    build_watchlist_changes,
    diff_temperature,
    index_strength_by_key,
    latest_market_rate,
    find_prev_snapshot_dir,
)

log = logging.getLogger(__name__)

# digest_log.outcome 枚举常量（防拼写漂移；与 004_notify.sql 注释一致）。
OUTCOME_SENT = "sent"
OUTCOME_SKIPPED_NO_CHANGE = "skipped_no_change"
OUTCOME_SKIPPED_UNSUB = "skipped_unsub"
OUTCOME_FAILED = "failed"

_RESEND_ENDPOINT = "https://api.resend.com/emails"
# 发件地址：可 env 覆盖，默认占位（联调前需在 Resend 验证域名）。
_DEFAULT_FROM = "ETF Radar <digest@etf-radar.app>"


# ============================================================
# 数据结构
# ============================================================
@dataclass(frozen=True)
class Member:
    """一位生效会员及其推送上下文。"""

    user_id: str
    email: str
    unsub_token: str
    watchlist: list[tuple[ItemType, str, str]]  # (item_type, item_key, name)


@dataclass
class DigestConfig:
    """运行配置（全部从 env 读取）。"""

    supabase_url: str
    service_role_key: str
    resend_api_key: str | None
    mail_from: str
    supabase_ref: str
    dry_run: bool

    @classmethod
    def from_env(cls, *, dry_run_override: bool | None = None) -> DigestConfig:
        supabase_url = _require_env("SUPABASE_URL").rstrip("/")
        # 从 https://<ref>.supabase.co 解析 ref，用于拼退订链接。
        ref = supabase_url.replace("https://", "").replace("http://", "").split(".")[0]
        env_dry = os.getenv("NOTIFY_DRY_RUN", "").strip() in ("1", "true", "True")
        dry_run = env_dry if dry_run_override is None else dry_run_override
        return cls(
            supabase_url=supabase_url,
            service_role_key=_require_env("SUPABASE_SERVICE_ROLE_KEY"),
            # dry-run 下允许无 Resend key（不真发）。
            resend_api_key=os.getenv("RESEND_API_KEY") or None,
            mail_from=os.getenv("NOTIFY_MAIL_FROM") or _DEFAULT_FROM,
            supabase_ref=ref,
            dry_run=dry_run,
        )


@dataclass
class RunResult:
    """整体运行统计（便于 CI 日志与断言）。"""

    run_date: str
    sent: int = 0
    skipped_no_change: int = 0
    skipped_unsub: int = 0
    skipped_idempotent: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)


def _require_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"缺少环境变量: {key}")
    return v


# ============================================================
# Supabase REST 客户端（stdlib urllib，service_role 绕过 RLS）
# ============================================================
class SupabaseRest:
    """极简 Supabase REST/Auth Admin 封装，仅覆盖本任务用到的读写。

    用 service_role key，绕过 RLS。所有方法失败抛异常（供上层逐用户/整体隔离）。
    便于 mock：单测替换本类实例即可。
    """

    def __init__(self, base_url: str, service_role_key: str) -> None:
        self._base = base_url.rstrip("/")
        self._key = service_role_key

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> Any:
        url = f"{self._base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method, headers=self._headers(headers)
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"Supabase {method} {path} 失败 {e.code}: {detail}") from e
        return json.loads(raw) if raw else None

    # ---- REST (PostgREST) ----
    def select(self, table: str, query: str = "") -> list[dict[str, Any]]:
        sep = "?" if query and not query.startswith("?") else ""
        result = self._request("GET", f"/rest/v1/{table}{sep}{query}")
        return result if isinstance(result, list) else []

    def insert(self, table: str, row: dict[str, Any]) -> None:
        # Prefer resolution=ignore-duplicates：幂等 UNIQUE 冲突不报错。
        self._request(
            "POST",
            f"/rest/v1/{table}",
            headers={"Prefer": "return=minimal,resolution=ignore-duplicates"},
            body=[row],
        )

    def update(self, table: str, query: str, patch: dict[str, Any]) -> None:
        self._request(
            "PATCH",
            f"/rest/v1/{table}?{query}",
            headers={"Prefer": "return=minimal"},
            body=patch,
        )

    def digest_log_exists(self, run_date: str, user_id: str) -> bool:
        """当日该用户是否已有 digest_log 记录（幂等：重跑当天不重复发信/落表）。"""
        rows = self.select(
            "digest_log",
            f"select=id&run_date=eq.{run_date}&user_id=eq.{user_id}&limit=1",
        )
        return bool(rows)

    # ---- Auth Admin：取用户邮箱 ----
    def get_user_email(self, user_id: str) -> str | None:
        """service_role 经 Auth Admin REST 取邮箱（auth.users.email）。"""
        try:
            result = self._request("GET", f"/auth/v1/admin/users/{user_id}")
        except RuntimeError as e:
            log.warning("取用户 %s 邮箱失败: %s", user_id, e)
            return None
        if isinstance(result, dict):
            email = result.get("email")
            return email if isinstance(email, str) and email else None
        return None


# ============================================================
# Supabase 查询：生效会员 + watchlist + notify_prefs
# ============================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_active_members(
    rest: SupabaseRest,
    name_resolver: dict[ItemType, dict[str, str]],
) -> list[Member]:
    """查生效会员（active 且未过期）→ 附 watchlist（已含展示名）、notify_prefs、邮箱。

    未退订判定：无 notify_prefs 行视为默认可发；有行且 email_enabled=false → 退订（此处过滤）。
    退订用户不进返回列表（由上层记 skipped_unsub 时另查，见 run 主流程）。
    name_resolver：{item_type: {item_key: name}}，来自今日 snapshot，为 watchlist 补展示名。
    """
    now = _now_iso()
    subs = rest.select(
        "subscriptions",
        f"select=user_id&status=eq.active&current_period_end=gt.{now}",
    )
    members: list[Member] = []
    for sub in subs:
        user_id = sub.get("user_id")
        if not isinstance(user_id, str):
            continue
        # notify_prefs：确保存在并拿 unsub_token；退订的在上层单独处理。
        pref = _ensure_notify_prefs(rest, user_id)
        if not pref["email_enabled"]:
            continue  # 退订，跳过（skipped_unsub 由上层 run 处理）
        email = rest.get_user_email(user_id)
        if not email:
            continue
        watchlist = _load_watchlist(rest, user_id, name_resolver)
        members.append(
            Member(
                user_id=user_id,
                email=email,
                unsub_token=pref["unsub_token"],
                watchlist=watchlist,
            )
        )
    return members


def load_unsubscribed_user_ids(rest: SupabaseRest) -> set[str]:
    """查生效会员中已退订（email_enabled=false）的 user_id，供记 skipped_unsub。"""
    now = _now_iso()
    subs = rest.select(
        "subscriptions",
        f"select=user_id&status=eq.active&current_period_end=gt.{now}",
    )
    active_ids = {s["user_id"] for s in subs if isinstance(s.get("user_id"), str)}
    if not active_ids:
        return set()
    prefs = rest.select("notify_prefs", "select=user_id,email_enabled&email_enabled=eq.false")
    return {p["user_id"] for p in prefs if p.get("user_id") in active_ids}


def _ensure_notify_prefs(rest: SupabaseRest, user_id: str) -> dict[str, Any]:
    """取用户 notify_prefs；不存在则创建（含随机 unsub_token）。返回 {email_enabled, unsub_token}。"""
    rows = rest.select(
        "notify_prefs",
        f"select=email_enabled,unsub_token&user_id=eq.{user_id}",
    )
    if rows:
        row = rows[0]
        token = row.get("unsub_token")
        if not token:
            # 兜底：历史行缺 token → 补一个。
            token = secrets.token_urlsafe(24)
            rest.update("notify_prefs", f"user_id=eq.{user_id}", {"unsub_token": token})
        return {"email_enabled": bool(row.get("email_enabled", True)), "unsub_token": token}
    # 无行：默认可发，创建带 token 的行。
    token = secrets.token_urlsafe(24)
    rest.insert(
        "notify_prefs",
        {"user_id": user_id, "email_enabled": True, "unsub_token": token},
    )
    return {"email_enabled": True, "unsub_token": token}


def _load_watchlist(
    rest: SupabaseRest,
    user_id: str,
    name_resolver: dict[ItemType, dict[str, str]],
) -> list[tuple[ItemType, str, str]]:
    rows = rest.select(
        "watchlist",
        f"select=item_type,item_key&user_id=eq.{user_id}",
    )
    out: list[tuple[ItemType, str, str]] = []
    for r in rows:
        it = r.get("item_type")
        key = r.get("item_key")
        if it not in ("theme", "etf") or not isinstance(key, str):
            continue
        item_type: ItemType = it
        name = name_resolver.get(item_type, {}).get(key, key)
        out.append((item_type, key, name))
    return out


# ============================================================
# Snapshot 读取（IO；纯计算在 changes.py）
# ============================================================
@dataclass(frozen=True)
class SnapshotData:
    date: str
    strength_index: dict[ItemType, dict[str, dict[str, int | None]]]
    name_index: dict[ItemType, dict[str, str]]
    market_rate: float | None


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_snapshot(snapshots_root: Path, date: str) -> SnapshotData:
    """读一天 snapshot → 强度索引 + 名称索引 + 全市场温度站上率。缺文件视作空。"""
    day = snapshots_root / date
    themes = _list_of(day / "themes.json", "themes")
    etfs = _list_of(day / "etfs.json", "etfs")
    temperature = _dict_or_none(day / "market_temperature.json")

    strength_index: dict[ItemType, dict[str, dict[str, int | None]]] = {
        "theme": index_strength_by_key(themes, "id"),
        "etf": index_strength_by_key(etfs, "code"),
    }
    name_index: dict[ItemType, dict[str, str]] = {
        "theme": _name_map(themes, "id"),
        "etf": _name_map(etfs, "code"),
    }
    return SnapshotData(
        date=date,
        strength_index=strength_index,
        name_index=name_index,
        market_rate=latest_market_rate(temperature),
    )


def _list_of(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = _read_json(path)
    if isinstance(data, dict):
        items = data.get(key)
        return items if isinstance(items, list) else []
    return data if isinstance(data, list) else []


def _dict_or_none(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = _read_json(path)
    return data if isinstance(data, dict) else None


def _name_map(items: list[dict[str, Any]], key_field: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for it in items:
        key = it.get(key_field)
        if key is None:
            continue
        name = it.get("name")
        out[str(key)] = str(name) if name else str(key)
    return out


# ============================================================
# 邮件文案（合规：零操作动词）
# ============================================================
def _item_line(ch: ItemChange) -> str:
    """单标的一行客观状态描述。禁买入/加仓/看涨等操作动词。"""
    if ch.kind == "A":
        verb = "进入强势象限" if ch.direction == "up" else "退出强势象限"
    else:  # D
        verb = "强度上穿 50" if ch.direction == "up" else "强度下穿 50"
    return f"• [{ch.name}] {verb}，强度 {ch.composite_prev}→{ch.composite_now}"


def _temperature_line(tc: TemperatureChange) -> str:
    trend = "升温" if tc.direction == "up" else "降温"
    return (
        f"全市场温度{trend}：{tc.tier_prev} → {tc.tier_now}"
        f"（站上率 {tc.rate_prev:g}%→{tc.rate_now:g}%）"
    )


def build_email(
    run_date: str,
    item_changes: list[ItemChange],
    temperature: TemperatureChange | None,
    unsub_url: str,
) -> tuple[str, str, str]:
    """拼邮件 → (subject, text, html)。C 置顶，随后每标的一行。合规文案零操作动词。"""
    subject = f"你的自选变化摘要 · {run_date}"

    lines: list[str] = []
    if temperature is not None:
        lines.append(_temperature_line(temperature))
        lines.append("")
    for ch in item_changes:
        lines.append(_item_line(ch))

    disclaimer = "本邮件仅供参考，非投资建议。"
    text = (
        f"{subject}\n\n"
        + "\n".join(lines)
        + f"\n\n---\n{disclaimer}\n退订：{unsub_url}\n"
    )

    top_html = (
        f"<p style='padding:8px 12px;background:#f2f4f8;border-radius:6px'>"
        f"{_temperature_line(temperature)}</p>"
        if temperature is not None
        else ""
    )
    items_html = "".join(f"<li>{_item_line(ch)[2:]}</li>" for ch in item_changes)
    html = (
        f"<h2 style='font-size:18px'>{subject}</h2>"
        f"{top_html}"
        f"<ul style='line-height:1.8'>{items_html}</ul>"
        f"<hr><p style='color:#888;font-size:12px'>{disclaimer}<br>"
        f"<a href='{unsub_url}'>退订此邮件</a></p>"
    )
    return subject, text, html


def unsub_url(supabase_ref: str, token: str) -> str:
    return f"https://{supabase_ref}.supabase.co/functions/v1/notify-unsub?token={token}"


# ============================================================
# 发信（Resend）
# ============================================================
def send_email(
    api_key: str,
    mail_from: str,
    to: str,
    subject: str,
    text: str,
    html: str,
) -> None:
    """POST Resend /emails。失败抛异常（供上层记 failed）。"""
    body = json.dumps(
        {"from": mail_from, "to": [to], "subject": subject, "text": text, "html": html}
    ).encode("utf-8")
    req = urllib.request.Request(
        _RESEND_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Resend 发信失败 {e.code}: {detail}") from e


# ============================================================
# 主编排
# ============================================================
def run(
    snapshots_root: Path,
    run_date: str,
    rest: SupabaseRest,
    config: DigestConfig,
    *,
    sender: Any = send_email,
) -> RunResult:
    """执行一次每日摘要。逐用户 try 隔离；返回统计。

    snapshots_root：data/snapshots 目录。run_date：今日目录名（YYYY-MM-DD）。
    sender：发信函数（便于注入 mock）；dry-run 下不调用。
    """
    result = RunResult(run_date=run_date)

    # 1. 上一交易日目录（按实际存在目录回溯）。
    existing = [p.name for p in snapshots_root.iterdir() if p.is_dir()] if snapshots_root.exists() else []
    prev_date = find_prev_snapshot_dir(existing, run_date)
    if prev_date is None:
        result.notes.append("无上一交易日 snapshot，跳过本次运行")
        log.warning("run_date=%s 无 prev snapshot，安全跳过", run_date)
        return result

    # 2. 读今日/昨日 snapshot（各自全市场序列按最大 date 取该日最新 rate）。
    today = load_snapshot(snapshots_root, run_date)
    prev = load_snapshot(snapshots_root, prev_date)

    # 3. 全局 C（温度档位切换），全员共享置顶。
    temperature = diff_temperature(prev.market_rate, today.market_rate)

    # 4. 会员（含 watchlist 名称解析自今日 snapshot）。
    members = load_active_members(rest, today.name_index)
    unsub_ids = load_unsubscribed_user_ids(rest)

    # 5. 已退订会员：记 skipped_unsub（当日已处理则跳过，幂等）。
    for uid in unsub_ids:
        if rest.digest_log_exists(run_date, uid):
            continue
        if _record_idempotent(rest, run_date, uid, OUTCOME_SKIPPED_UNSUB, "unsubscribed"):
            result.skipped_unsub += 1

    # 6. 逐会员处理，try 隔离。当日已处理（发过/跳过）→ 幂等跳过，不再发信。
    for m in members:
        if rest.digest_log_exists(run_date, m.user_id):
            result.skipped_idempotent += 1
            continue
        try:
            _process_member(m, run_date, today, prev, temperature, rest, config, sender, result)
        except Exception as e:  # noqa: BLE001 单用户失败不中断整体
            log.exception("用户 %s 处理异常", m.user_id)
            if _record_idempotent(rest, run_date, m.user_id, OUTCOME_FAILED, str(e)[:500]):
                result.failed += 1

    return result


def _process_member(
    m: Member,
    run_date: str,
    today: SnapshotData,
    prev: SnapshotData,
    temperature: TemperatureChange | None,
    rest: SupabaseRest,
    config: DigestConfig,
    sender: Any,
    result: RunResult,
) -> None:
    item_changes = build_watchlist_changes(m.watchlist, prev.strength_index, today.strength_index)

    # 无任何变化（含无温度切换）→ 跳过。
    if not item_changes and temperature is None:
        if _record_idempotent(rest, run_date, m.user_id, OUTCOME_SKIPPED_NO_CHANGE, "no change"):
            result.skipped_no_change += 1
        return

    link = unsub_url(config.supabase_ref, m.unsub_token)
    subject, text, html = build_email(run_date, item_changes, temperature, link)

    if config.dry_run:
        log.info("[dry-run] 将发给 %s <%s>:\n%s", m.user_id, m.email, text)
        if _record_idempotent(rest, run_date, m.user_id, OUTCOME_SENT, "dry-run"):
            result.sent += 1
        return

    if not config.resend_api_key:
        raise RuntimeError("非 dry-run 但缺 RESEND_API_KEY")
    sender(config.resend_api_key, config.mail_from, m.email, subject, text, html)
    if _record_idempotent(rest, run_date, m.user_id, OUTCOME_SENT, None):
        result.sent += 1


def _record_idempotent(
    rest: SupabaseRest,
    run_date: str,
    user_id: str,
    outcome: str,
    note: str | None,
) -> bool:
    """写 digest_log（UNIQUE(run_date,user_id) 幂等，冲突静默忽略）。返回是否计入统计。

    用 ignore-duplicates：重跑当天已处理用户不重复。写审计失败不应中断主流程。
    """
    try:
        rest.insert(
            "digest_log",
            {"run_date": run_date, "user_id": user_id, "outcome": outcome, "note": note},
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("digest_log 写入失败 user=%s: %s", user_id, e)
        return True  # 统计仍计入：动作已发生，审计缺失不改变事实


# ============================================================
# CLI 入口
# ============================================================
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="会员每日变化摘要邮件推送")
    parser.add_argument(
        "--snapshots-root",
        default=os.getenv("SNAPSHOTS_ROOT", "data/snapshots"),
        help="snapshots 根目录（默认 data/snapshots 或 env SNAPSHOTS_ROOT）",
    )
    parser.add_argument("--run-date", default=None, help="今日目录名 YYYY-MM-DD（默认取最新目录）")
    parser.add_argument("--dry-run", action="store_true", help="不真发，仅打印将发内容")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    root = Path(args.snapshots_root)
    run_date = args.run_date
    if run_date is None:
        dirs = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []
        if not dirs:
            log.error("snapshots 目录为空: %s", root)
            return 1
        run_date = dirs[-1]

    config = DigestConfig.from_env(dry_run_override=True if args.dry_run else None)
    rest = SupabaseRest(config.supabase_url, config.service_role_key)
    result = run(root, run_date, rest, config)

    log.info(
        "完成 run_date=%s sent=%d no_change=%d unsub=%d failed=%d",
        result.run_date,
        result.sent,
        result.skipped_no_change,
        result.skipped_unsub,
        result.failed,
    )
    for note in result.notes:
        log.info("note: %s", note)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
