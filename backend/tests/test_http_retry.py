"""连接重试注入 — 抵御 eastmoney 间歇性 RemoteDisconnected."""
import requests

from src.providers._http_retry import build_retry_session, install_requests_retry


def test_retry_session_mounts_connect_retries_on_https() -> None:
    s = build_retry_session()
    adapter = s.get_adapter('https://push2his.eastmoney.com')
    retries = adapter.max_retries
    # 关键: 对连接错误 (RemoteDisconnected) 重试, 次数足够扛过坏时段
    assert retries.connect is not None and retries.connect >= 3
    assert retries.read is not None and retries.read >= 3
    assert retries.backoff_factor > 0


def test_install_requests_retry_is_idempotent_and_restorable() -> None:
    # provider 模块导入时已全局安装, 故显式重置为"未安装"态使测试自足.
    import src.providers._http_retry as m
    saved_get = requests.get
    saved_installed = m._installed
    try:
        m._installed = False
        sentinel = object()
        requests.get = sentinel  # type: ignore[assignment]
        install_requests_retry()
        patched = requests.get
        assert patched is not sentinel  # 已替换为带重试的 session.get
        install_requests_retry()
        assert requests.get is patched  # 幂等: 二次调用不再包裹
    finally:
        requests.get = saved_get  # 恢复, 避免污染其他测试
        m._installed = saved_installed
