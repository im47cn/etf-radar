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


def main() -> None:
    """渠道自检 CLI:`python -m src.notify.alert --test` 发一条测试告警。

    读同一套 env(SERVERCHAN_SENDKEY / ALERT_DRY_RUN),用于验证 secret 配置
    与投递链路。exit 0=已发送, 1=未发送(dry-run/无 key/失败)。
    """
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Server酱 告警渠道自检")
    p.add_argument("--test", action="store_true", help="发送一条测试告警验证渠道")
    args = p.parse_args()
    if not args.test:
        p.error("需指定 --test")
    ok = send_alert(
        "[etf-radar] 告警渠道自检",
        "health-monitor Server酱 通道测试。收到即表示 SENDKEY 配置正确、投递链路正常。",
    )
    print("sent" if ok else "not sent (dry-run / no-key / failure)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
