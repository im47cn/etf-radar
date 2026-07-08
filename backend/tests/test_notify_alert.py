"""Server酱 告警渠道单测——dry-run 不触网、payload 正确、异常不 raise。"""
from __future__ import annotations

import pytest

from src.notify import alert


def test_send_alert_dry_run_no_network(monkeypatch):
    """dry-run 下不触网、返回 False。"""
    called = {"n": 0}

    def _boom(*a, **k):  # 任何触网即失败
        called["n"] += 1
        raise AssertionError("dry-run 不应触网")

    monkeypatch.setattr(alert.requests, "post", _boom)
    cfg = alert.AlertConfig(sendkey="abc", dry_run=True)
    assert alert.send_alert("t", "d", cfg) is False
    assert called["n"] == 0


def test_send_alert_no_sendkey_no_network(monkeypatch):
    """无 sendkey → 不触网、返回 False（不视为致命）。"""
    monkeypatch.setattr(alert.requests, "post", lambda *a, **k: pytest.fail("不应触网"))
    cfg = alert.AlertConfig(sendkey=None, dry_run=False)
    assert alert.send_alert("t", "d", cfg) is False


def test_send_alert_posts_correct_payload(monkeypatch):
    """真实 path：URL 含 sendkey、data 有 title/desp、200 → True。"""
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"code": 0}

    def _post(url, data=None, timeout=None, **k):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(alert.requests, "post", _post)
    cfg = alert.AlertConfig(sendkey="SENDKEY123", dry_run=False)
    ok = alert.send_alert("标题", "正文\n**md**", cfg)
    assert ok is True
    assert "SENDKEY123" in captured["url"]
    assert captured["url"].endswith(".send")
    assert captured["data"]["title"] == "标题"
    assert captured["data"]["desp"] == "正文\n**md**"


def test_send_alert_network_error_returns_false(monkeypatch):
    """post 抛异常 → 返回 False，绝不 raise。"""
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(alert.requests, "post", _boom)
    cfg = alert.AlertConfig(sendkey="k", dry_run=False)
    assert alert.send_alert("t", "d", cfg) is False


def test_send_alert_non_200_returns_false(monkeypatch):
    """HTTP 非 200 → False。"""
    class _Resp:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr(alert.requests, "post", lambda *a, **k: _Resp())
    cfg = alert.AlertConfig(sendkey="k", dry_run=False)
    assert alert.send_alert("t", "d", cfg) is False


def test_alert_config_from_env(monkeypatch):
    monkeypatch.setenv("SERVERCHAN_SENDKEY", "envkey")
    monkeypatch.setenv("ALERT_DRY_RUN", "1")
    cfg = alert.AlertConfig.from_env()
    assert cfg.sendkey == "envkey"
    assert cfg.dry_run is True

    monkeypatch.delenv("SERVERCHAN_SENDKEY", raising=False)
    monkeypatch.setenv("ALERT_DRY_RUN", "0")
    cfg2 = alert.AlertConfig.from_env()
    assert cfg2.sendkey is None
    assert cfg2.dry_run is False
