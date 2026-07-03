"""个股→巨潮行业映射管线 (月级低频).

遍历 close_series 的全市场 code, 逐股拉巨潮行业(大类/中类), 并发 + 单股容错.
韧性: 与上次 good map 合并 (断点续跑)——本次失败的 code 保留上次归属,
永不产出空 map、不阻断下游. 覆盖率不足阈值仅告警.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..output.writer import atomic_write_json
from ..providers.stock_industry_provider import StockIndustryFetchError, fetch_stock_industry

log = logging.getLogger(__name__)

SCHEMA_VERSION = '1.0'
MIN_COVERAGE = 0.95


@dataclass
class MapReport:
    fetched: int = 0
    failed: list[str] = field(default_factory=list)
    from_cache: int = 0


def _load_codes(close_series_path: Path) -> list[str]:
    data = json.loads(close_series_path.read_text(encoding='utf-8'))
    return list(data['stocks'].keys())


def _load_existing_map(out_path: Path) -> dict[str, dict[str, str]]:
    if not out_path.exists():
        return {}
    try:
        doc = json.loads(out_path.read_text(encoding='utf-8'))
        m = doc.get('map', {})
        return m if isinstance(m, dict) else {}
    except (json.JSONDecodeError, KeyError):
        return {}


def build_map(
    codes: list[str],
    existing: dict[str, dict[str, str]],
    *,
    max_workers: int = 8,
    fetch: Any = fetch_stock_industry,
) -> tuple[dict[str, dict[str, str]], list[str], MapReport]:
    """并发拉映射, 与 existing 合并. 返回 (map, unmapped, report).

    - 拉取成功且有巨潮归属 → 更新 map。
    - 拉取失败 → 保留 existing[code] (若有), 否则计入本轮 failed。
    - 拉取成功但无巨潮归属 → unmapped。
    """
    result = dict(existing)  # 以旧 map 为底
    report = MapReport()
    unmapped: list[str] = []

    def one(code: str) -> tuple[str, dict[str, str] | None, str | None]:
        try:
            return code, fetch(code), None
        except StockIndustryFetchError as e:
            return code, None, str(e)
        except Exception as e:  # noqa: BLE001
            return code, None, f'unexpected: {e}'

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(one, c): c for c in codes}
        for fut in as_completed(futures):
            code, ind, err = fut.result()
            if err is not None:
                if code in existing:
                    report.from_cache += 1  # 保留旧值
                else:
                    report.failed.append(code)
                continue
            if ind is None:
                unmapped.append(code)
                result.pop(code, None)  # 明确无巨潮归属, 清掉旧值
                continue
            result[code] = ind
            report.fetched += 1

    # 只保留当前 universe 内的 code (剔除已退市)
    universe = set(codes)
    result = {c: v for c, v in result.items() if c in universe}
    return result, sorted(unmapped), report


def run(data_root: Path, *, max_workers: int = 8, fetch: Any = fetch_stock_industry) -> Path:
    stocks_dir = Path(data_root) / 'stocks'
    close_path = stocks_dir / 'close_series.json'
    out_path = stocks_dir / 'stock_industry_map.json'

    codes = _load_codes(close_path)
    existing = _load_existing_map(out_path)
    mapping, unmapped, report = build_map(codes, existing, max_workers=max_workers, fetch=fetch)

    coverage = len(mapping) / len(codes) if codes else 0.0
    if coverage < MIN_COVERAGE:
        log.warning('巨潮行业映射覆盖率 %.1f%% < %.0f%% (fetched=%d, cache=%d, failed=%d); 仍写出(含旧值)',
                    coverage * 100, MIN_COVERAGE * 100, report.fetched, report.from_cache, len(report.failed))
    else:
        log.info('巨潮行业映射 覆盖率 %.1f%% (fetched=%d, cache=%d, unmapped=%d, failed=%d)',
                 coverage * 100, report.fetched, report.from_cache, len(unmapped), len(report.failed))

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    atomic_write_json(out_path, {
        'schema_version': SCHEMA_VERSION,
        'generated_at': now,
        'source': 'cninfo',
        'coverage': round(coverage, 4),
        'map': mapping,
        'unmapped': unmapped,
    })
    return out_path


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    p = argparse.ArgumentParser(description='个股→巨潮行业映射管线')
    p.add_argument('--data-root', type=Path, default=Path('data'))
    p.add_argument('--max-workers', type=int, default=8)
    args = p.parse_args()
    run(args.data_root, max_workers=args.max_workers)


if __name__ == '__main__':
    main()
