"""dapanyuntu (大盘云图) 数据源 — 二级行业 MA20 站上率.

直接 WebFetch 会 403, 必须带 Referer/User-Agent 头. 用 stdlib urllib 避免新增依赖.
返回原始稀疏三元组结构, 聚合逻辑在 market_breadth.pipeline 中完成 (单一职责).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .base import EmptyDataError, ProviderError

log = logging.getLogger(__name__)

_ENDPOINT = 'https://sckd.dapanyuntu.com/api/api/industry_ma20_analysis_page?page=0'
_HEADERS = {
    'Referer': 'https://sckd.dapanyuntu.com/',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    ),
}


@dataclass(frozen=True)
class BreadthRaw:
    """dapanyuntu 原始返回.

    data: [[date_idx, industry_idx, value], ...] 稀疏三元组, value=0 表无数据
    dates: 交易日列表 (通常 31~32 个)
    industries: 二级行业名列表 (通常 86 个)
    """

    data: list[list[float]]
    dates: list[str]
    industries: list[str]


class DapanyuntuProvider:
    """大盘云图市场宽度数据源."""

    name = 'dapanyuntu'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0, timeout: float = 20.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout

    def fetch_breadth(self) -> BreadthRaw:
        """拉取二级行业 MA20 站上率原始数据.

        Raises:
            ProviderError: HTTP 失败 (403/超时/非 200/JSON 解析失败), 已重试.
            EmptyDataError: 返回结构缺 data/dates/industries 或为空.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(_ENDPOINT, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        raise ProviderError(f'dapanyuntu HTTP {resp.status}')
                    payload = json.loads(resp.read().decode('utf-8'))
                return _parse(payload)
            except EmptyDataError:
                raise  # 空数据非瞬时错误, 不重试
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
                last_exc = e
                log.warning('dapanyuntu fetch attempt %d/%d failed: %s', attempt + 1, self.max_retries, e)
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (attempt + 1))
        raise ProviderError(f'dapanyuntu fetch failed after {self.max_retries} attempts') from last_exc


def _parse(payload: dict) -> BreadthRaw:
    data = payload.get('data')
    dates = payload.get('dates')
    industries = payload.get('industries')
    if not data or not dates or not industries:
        raise EmptyDataError('dapanyuntu payload missing data/dates/industries')
    return BreadthRaw(data=data, dates=dates, industries=industries)
