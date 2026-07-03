"""市场宽度 (个股 MA20 站上率) 数据管线.

数据源: dapanyuntu.com (大盘云图), 已按个股计算好二级行业 MA20 站上率.
本包负责: 拉取 -> 二级/一级聚合 -> 全市场均值 -> 产出快照 market_temperature.json.
"""
