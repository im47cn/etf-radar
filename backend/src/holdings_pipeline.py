"""ETF 持仓季度抓取管道。

入口:
- `python -m src.holdings_pipeline --data-root=./data --config-dir=./config`
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config_loader import load_themes
from .providers.holdings_provider import HoldingsFetchError, HoldingsProvider

log = logging.getLogger(__name__)


QUARTER_ENDS = [(3, 31), (6, 30), (9, 30), (12, 31)]


def candidate_quarters(today: date) -> list[date]:
    """生成最近 4 个季末日期（按降序），用于回退抓取。"""
    candidates: list[date] = []
    year = today.year
    while len(candidates) < 4:
        for m, d in reversed(QUARTER_ENDS):
            q = date(year, m, d)
            if q <= today:
                candidates.append(q)
                if len(candidates) >= 4:
                    break
        year -= 1
    return candidates


@dataclass
class HoldingsPipelineReport:
    success: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def run_holdings_pipeline(
    themes_yaml: Path,
    output_dir: Path,
    today: date | None = None,
    provider: HoldingsProvider | None = None,
) -> HoldingsPipelineReport:
    """读取 themes.yaml，逐 ETF 拉持仓，写入 output_dir。

    每个 ETF 独立按候选季度回退；单个失败不影响其他。
    最后写 index.json 列表。
    """
    today = today or date.today()
    provider = provider or HoldingsProvider()
    output_dir.mkdir(parents=True, exist_ok=True)

    themes = load_themes(themes_yaml)

    etf_targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for t in themes:
        if not t.primary_cn:
            continue
        if t.primary_cn in seen:
            continue
        seen.add(t.primary_cn)
        name_match = next((cn.name for cn in t.cn_etfs if cn.code == t.primary_cn),
                          t.primary_cn)
        etf_targets.append((t.primary_cn, name_match))

    quarters = candidate_quarters(today)
    report = HoldingsPipelineReport()

    for code, name in etf_targets:
        snap = None
        for q in quarters:
            try:
                snap = provider.fetch(etf_code=code, etf_name=name, quarter=q)
                break
            except HoldingsFetchError as e:
                log.info(f'holdings fallback: {code} @ {q} → {e}')
                continue
        if snap is None:
            log.warning(f'holdings failed for {code} across {quarters}')
            report.failed.append(code)
            continue

        out_path = output_dir / f'{code}.json'
        out_path.write_text(
            json.dumps(snap.model_dump(mode='json'), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        report.success.append(code)

    _write_index(output_dir, report.success)
    return report


def _write_index(output_dir: Path, etf_codes: list[str]) -> None:
    """写 index.json，列出所有成功抓取的 ETF 及其披露日期。"""
    from datetime import datetime, timezone
    entries = []
    for code in etf_codes:
        snap_path = output_dir / f'{code}.json'
        data = json.loads(snap_path.read_text())
        entries.append({'code': code, 'disclosure_date': data['disclosure_date']})
    index = {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'etfs': entries,
    }
    (output_dir / 'index.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    report = run_holdings_pipeline(
        themes_yaml=args.config_dir / 'themes.yml',
        output_dir=args.data_root / 'holdings',
    )
    log.info(f'holdings pipeline: success={len(report.success)} failed={len(report.failed)}')


if __name__ == '__main__':
    main()
