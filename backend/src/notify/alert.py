"""Server酱 失败告警渠道——薄封装,发信失败绝不拖垮巡检。

风格对齐 digest.py 的 dataclass + from_env。与 digest.py（urllib）不同,
这里用 requests（已在 pyproject 显式声明为依赖）以贴合 Server酱 简单表单 POST。

关键契约:任何失败（无 key / dry-run / 网络异常 / 非 200）→ 返回 False 且不 raise,
因为"告警失败"不应中断哨兵巡检本身。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

_ENDPOINT_TMPL = "https://sctapi.ftqq.com/{sendkey}.send"
_TIMEOUT = 10  # 秒


@dataclass
class AlertConfig:
    """告警配置（从 env 读取）。"""

    sendkey: str | None
    dry_run: bool

    @classmethod
    def from_env(cls) -> "AlertConfig":
        dry = os.getenv("ALERT_DRY_RUN", "").strip() in ("1", "true", "True")
        return cls(sendkey=os.getenv("SERVERCHAN_SENDKEY") or None, dry_run=dry)


def send_alert(title: str, desp: str, cfg: AlertConfig | None = None) -> bool:
    """经 Server酱 推送告警。成功返回 True,其余一律 False（不 raise）。

    desp 支持 markdown。dry-run 或无 sendkey 只打印。
    """
    cfg = cfg or AlertConfig.from_env()
    if cfg.dry_run or not cfg.sendkey:
        reason = "dry-run" if cfg.dry_run else "无 SENDKEY"
        log.info("[alert:%s] %s\n%s", reason, title, desp)
        return False

    url = _ENDPOINT_TMPL.format(sendkey=cfg.sendkey)
    try:
        resp = requests.post(url, data={"title": title, "desp": desp}, timeout=_TIMEOUT)
    except Exception as exc:  # 网络/连接异常——告警失败不致命
        log.error("send_alert 请求异常: %s", exc)
        return False
    if resp.status_code != 200:
        log.error("send_alert HTTP %s", resp.status_code)
        return False
    return True
