"""编排层单测：会员过滤、退订跳过、无变化跳过、幂等、发信失败隔离、文案零操作动词、C 置顶。

用 FakeRest 替 Supabase REST；用 in-memory snapshot 目录（tmp_path）；发信用可控 sender。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.notify.digest import (
    OUTCOME_FAILED,
    OUTCOME_SENT,
    OUTCOME_SKIPPED_NO_CHANGE,
    OUTCOME_SKIPPED_UNSUB,
    DigestConfig,
    build_email,
    run,
    unsub_url,
)

# 未来时间戳，保证订阅"未过期"。
_FUTURE = "2099-01-01T00:00:00Z"


# ============================================================
# FakeRest：内存版 Supabase，仅覆盖被调用的查询
# ============================================================
class FakeRest:
    def __init__(
        self,
        *,
        subscriptions: list[dict[str, Any]],
        watchlists: dict[str, list[dict[str, Any]]],
        prefs: dict[str, dict[str, Any]],
        emails: dict[str, str],
    ) -> None:
        self.subscriptions = subscriptions
        self.watchlists = watchlists
        self.prefs = prefs  # user_id -> {email_enabled, unsub_token}
        self.emails = emails
        self.digest_log: list[dict[str, Any]] = []

    # --- select 路由（按 table + 简单解析 query）---
    def select(self, table: str, query: str = "") -> list[dict[str, Any]]:
        if table == "subscriptions":
            return [{"user_id": s["user_id"]} for s in self.subscriptions
                    if s.get("status") == "active"]
        if table == "notify_prefs":
            uid = _extract_eq(query, "user_id")
            if "email_enabled=eq.false" in query:
                return [{"user_id": u, "email_enabled": False}
                        for u, p in self.prefs.items() if not p["email_enabled"]]
            if uid is None:
                return []
            p = self.prefs.get(uid)
            return [{"email_enabled": p["email_enabled"], "unsub_token": p["unsub_token"]}] if p else []
        if table == "watchlist":
            uid = _extract_eq(query, "user_id")
            return list(self.watchlists.get(uid or "", []))
        return []

    def insert(self, table: str, row: dict[str, Any]) -> None:
        if table == "digest_log":
            # 幂等：UNIQUE(run_date,user_id)。
            for existing in self.digest_log:
                if (existing["run_date"], existing["user_id"]) == (row["run_date"], row["user_id"]):
                    return  # ignore-duplicates
            self.digest_log.append(row)
        elif table == "notify_prefs":
            self.prefs[row["user_id"]] = {
                "email_enabled": row["email_enabled"],
                "unsub_token": row["unsub_token"],
            }

    def update(self, table: str, query: str, patch: dict[str, Any]) -> None:
        if table == "notify_prefs":
            uid = _extract_eq(query, "user_id")
            if uid and uid in self.prefs:
                self.prefs[uid].update(patch)

    def digest_log_exists(self, run_date: str, user_id: str) -> bool:
        return any(
            (r["run_date"], r["user_id"]) == (run_date, user_id) for r in self.digest_log
        )

    def get_user_email(self, user_id: str) -> str | None:
        return self.emails.get(user_id)


def _extract_eq(query: str, field: str) -> str | None:
    marker = f"{field}=eq."
    idx = query.find(marker)
    if idx < 0:
        return None
    rest = query[idx + len(marker):]
    return rest.split("&")[0]


# ============================================================
# snapshot 夹具
# ============================================================
def _write_snapshot(
    root: Path,
    date: str,
    themes: list[dict[str, Any]],
    etfs: list[dict[str, Any]] | None = None,
    market_rate: float | None = None,
) -> None:
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "themes.json").write_text(json.dumps({"themes": themes}), encoding="utf-8")
    (d / "etfs.json").write_text(json.dumps({"etfs": etfs or []}), encoding="utf-8")
    if market_rate is not None:
        mt = {"periods": {"ma20": {"market": [{"date": date, "rate": market_rate}]}}}
        (d / "market_temperature.json").write_text(json.dumps(mt), encoding="utf-8")


def _theme(tid: str, name: str, short: int, long: int, composite: int) -> dict[str, Any]:
    return {"id": tid, "name": name,
            "strength": {"short": short, "mid": 50, "long": long, "composite": composite}}


def _config(dry_run: bool = False) -> DigestConfig:
    return DigestConfig(
        supabase_url="https://ref123.supabase.co",
        service_role_key="svc",
        resend_api_key="re_key",
        mail_from="ETF Radar <d@x.app>",
        supabase_ref="ref123",
        dry_run=dry_run,
    )


class _Sender:
    """记录发信调用；可配置抛异常模拟失败。"""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.fail_for = fail_for or set()

    def __call__(self, api_key: str, mail_from: str, to: str,
                 subject: str, text: str, html: str) -> None:
        if to in self.fail_for:
            raise RuntimeError("boom")
        self.calls.append({"to": to, "subject": subject, "text": text, "html": html})


# ============================================================
# 测试
# ============================================================
def _base_snapshots(root: Path) -> None:
    """昨日弱、今日强：theme t1 composite 40→60（D 上穿 + A 迁移）。"""
    _write_snapshot(root, "2026-07-06", [_theme("t1", "半导体", 30, 30, 40)], market_rate=40.0)
    _write_snapshot(root, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)


def test_active_member_with_change_gets_email(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)

    assert result.sent == 1
    assert len(sender.calls) == 1
    assert sender.calls[0]["to"] == "u1@example.com"
    assert any(r["outcome"] == OUTCOME_SENT for r in rest.digest_log)


def test_no_change_skips(tmp_path: Path) -> None:
    # 今昨相同、温度不变 → 无变化。
    _write_snapshot(tmp_path, "2026-07-06", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)
    _write_snapshot(tmp_path, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert result.sent == 0
    assert result.skipped_no_change == 1
    assert not sender.calls
    assert rest.digest_log[0]["outcome"] == OUTCOME_SKIPPED_NO_CHANGE


def test_unsubscribed_member_skipped(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": False, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert not sender.calls
    assert result.skipped_unsub == 1
    assert result.sent == 0
    assert rest.digest_log[0]["outcome"] == OUTCOME_SKIPPED_UNSUB


def test_non_member_gets_nothing(tmp_path: Path) -> None:
    # 订阅 inactive → 不算生效会员。
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "inactive"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert not sender.calls
    assert result.sent == 0
    assert not rest.digest_log


def test_idempotent_rerun_no_duplicate(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender1 = _Sender()
    run(tmp_path, "2026-07-07", rest, _config(), sender=sender1)
    assert len(sender1.calls) == 1  # 首次发信一次

    sender2 = _Sender()
    result2 = run(tmp_path, "2026-07-07", rest, _config(), sender=sender2)
    # 第二次：当日已有 digest_log → 幂等跳过，不再发信、不重复落表。
    assert len(sender2.calls) == 0
    assert result2.skipped_idempotent == 1
    assert result2.sent == 0
    logs_for_u1 = [r for r in rest.digest_log if r["user_id"] == "u1"]
    assert len(logs_for_u1) == 1


def test_send_failure_isolated(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    # u1 发信失败，u2 正常。
    _write_snapshot(tmp_path, "2026-07-06", [_theme("t1", "半导体", 30, 30, 40)], market_rate=40.0)
    _write_snapshot(tmp_path, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}, {"user_id": "u2", "status": "active"}],
        watchlists={
            "u1": [{"item_type": "theme", "item_key": "t1"}],
            "u2": [{"item_type": "theme", "item_key": "t1"}],
        },
        prefs={
            "u1": {"email_enabled": True, "unsub_token": "tok1"},
            "u2": {"email_enabled": True, "unsub_token": "tok2"},
        },
        emails={"u1": "u1@example.com", "u2": "u2@example.com"},
    )
    sender = _Sender(fail_for={"u1@example.com"})
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert result.failed == 1
    assert result.sent == 1
    outcomes = {r["user_id"]: r["outcome"] for r in rest.digest_log}
    assert outcomes["u1"] == OUTCOME_FAILED
    assert outcomes["u2"] == OUTCOME_SENT


def test_prev_snapshot_missing_safe_skip(tmp_path: Path) -> None:
    # 只有今日，无昨日 → 安全跳过整体。
    _write_snapshot(tmp_path, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert not sender.calls
    assert result.sent == 0
    assert result.notes


def test_temperature_missing_skips_C_no_error(tmp_path: Path) -> None:
    # 无 market_temperature → C 跳过；无 item 变化 → 无邮件，但不报错。
    _write_snapshot(tmp_path, "2026-07-06", [_theme("t1", "半导体", 60, 60, 60)])
    _write_snapshot(tmp_path, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)])
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=_Sender())
    assert result.skipped_no_change == 1


def test_temperature_change_broadcast_top(tmp_path: Path) -> None:
    # 温度 40→60 跨档（偏冷→偏暖），theme 无变化：仍发邮件且 C 置顶。
    _write_snapshot(tmp_path, "2026-07-06", [_theme("t1", "半导体", 60, 60, 60)], market_rate=40.0)
    _write_snapshot(tmp_path, "2026-07-07", [_theme("t1", "半导体", 60, 60, 60)], market_rate=60.0)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert len(sender.calls) == 1
    text = sender.calls[0]["text"]
    # C 置顶：温度行出现在 theme 行之前（此处无 theme 行）。
    assert "全市场温度" in text
    assert "偏冷 → 偏暖" in text


def test_dry_run_does_not_send_but_logs(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={"u1": {"email_enabled": True, "unsub_token": "tok1"}},
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(dry_run=True), sender=sender)
    assert not sender.calls           # dry-run 不真发
    assert result.sent == 1           # 仍计入
    assert rest.digest_log[0]["note"] == "dry-run"


def test_creates_notify_prefs_when_missing(tmp_path: Path) -> None:
    _base_snapshots(tmp_path)
    rest = FakeRest(
        subscriptions=[{"user_id": "u1", "status": "active"}],
        watchlists={"u1": [{"item_type": "theme", "item_key": "t1"}]},
        prefs={},  # 无 notify_prefs 行 → 默认可发，自动创建
        emails={"u1": "u1@example.com"},
    )
    sender = _Sender()
    result = run(tmp_path, "2026-07-07", rest, _config(), sender=sender)
    assert result.sent == 1
    assert "u1" in rest.prefs
    assert rest.prefs["u1"]["unsub_token"]  # 生成了 token


# ---- 合规：邮件文案零操作动词 ----
# 注：「建议」仅作为固定免责声明「非投资建议」出现，检查前剔除该句再断言。
_FORBIDDEN = ["买入", "加仓", "卖出", "减仓", "看涨", "看跌", "抄底", "止盈", "止损"]


def test_email_text_no_action_verbs(tmp_path: Path) -> None:
    from src.notify.changes import ItemChange, TemperatureChange

    changes = [
        ItemChange("theme", "t1", "半导体", "A", "up", 40, 61),
        ItemChange("etf", "512480", "半导体ETF", "D", "down", 55, 42),
    ]
    tc = TemperatureChange("偏冷", "偏暖", 40.0, 60.0, "up")
    subject, text, html = build_email(
        "2026-07-07", changes, tc, unsub_url("ref123", "tok1")
    )
    body_text = text.replace("仅供参考，非投资建议", "")
    body_html = html.replace("仅供参考，非投资建议", "")
    for verb in _FORBIDDEN:
        assert verb not in body_text, f"文案含操作动词: {verb}"
        assert verb not in body_html, f"HTML 含操作动词: {verb}"
    assert "仅供参考，非投资建议" in text
    assert "notify-unsub?token=tok1" in text


def test_c_pinned_before_items(tmp_path: Path) -> None:
    from src.notify.changes import ItemChange, TemperatureChange

    changes = [ItemChange("theme", "t1", "半导体", "A", "up", 40, 61)]
    tc = TemperatureChange("偏冷", "偏暖", 40.0, 60.0, "up")
    _, text, _ = build_email("2026-07-07", changes, tc, "http://x")
    assert text.index("全市场温度") < text.index("半导体")
