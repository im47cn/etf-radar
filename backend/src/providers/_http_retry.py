"""为 akshare 的裸 requests.get 注入连接层重试.

根因: akshare 内部用 `requests.get(url, timeout=15, params=params)` (无 session、
default adapter max_retries=0)。eastmoney (push2his) 会间歇性掐断初始连接
(RemoteDisconnected)，单次请求即失败。实测 urllib3 的连接层重试可将成功率从
~20% 提升到接近 100% (见调查记录)。

方案: 全局把 `requests.get` 指到一个挂了 Retry 适配器的 Session。数据管道进程
只做抓数, GET 幂等, 该增强是安全超集。em / sina 都走 akshare 的 requests.get,
一处修复同时覆盖两者。
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# connect/read 均重试, backoff 0.8 → ~0/0.8/1.6/3.2/6.4s, 足够扛过 eastmoney 坏时段
_RETRY = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=0.8,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=frozenset(['GET']),
)

_installed = False


def build_retry_session() -> requests.Session:
    """带连接重试适配器的 Session (https + http)."""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def install_requests_retry() -> None:
    """把 requests.get 换成带重试的 session.get (幂等)。"""
    global _installed
    if _installed:
        return
    session = build_retry_session()
    requests.get = session.get
    _installed = True
