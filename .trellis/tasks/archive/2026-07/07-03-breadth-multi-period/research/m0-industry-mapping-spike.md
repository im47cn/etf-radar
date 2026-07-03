# M0 Spike — 股票→行业映射源可用性（本机实测）

环境: akshare 1.18.64, 本机出口 IP。CI(GitHub Actions) IP 不同，个别结论需 CI 复验。

## 各候选源实测

| 源 | 接口 | 结果 | 备注 |
|---|---|---|---|
| **东财 EM** | `stock_board_industry_name_em` / `stock_board_industry_cons_em('半导体')` | ❌ **RemoteDisconnected**（重试 3 次全失败） | 与项目当初弃 EM 改新浪同因；**唯一与 dapanyuntu 同源(可对账)** |
| **申万 SW** | `sw_index_first_info`(31 一级) / `sw_index_second_info`(131 二级) | ✅ 稳定, 1.1s, 自带上级行业 | 但成分接口 `sw_index_third_cons` 本版本**列数 bug**；`stock_industry_clf_hist_sw` **SSL 不可达**(swsresearch.com) |
| **同花顺 THS** | `stock_board_industry_name_ths`(90 二级) | ✅ 0.2s | 但本版本**无 cons_ths 成分函数** |
| **巨潮 CNINFO** | `stock_industry_category_cninfo` | ✅ 返回分类标准树(294类,含父子) | 是**分类定义**非**个股成分**；需另找 membership 调用 |
| Sina spot | `stock_zh_a_spot` | ✅(项目已用) | **不含行业列** |

## 关键结论

1. **东财是唯一能与 dapanyuntu apples-to-apples 对账的源**（同为东财体系），但 IP 层面 flaky。
2. **没有本机可验证的"稳定 + 同源 + 有个股成分"的单一源**。申万稳但成分接口在本版本坏/被墙；THS/CNINFO 缺可用的个股成分。
3. **决定性缓解**：股票→行业映射是**月级低频**数据（成分变动慢）。因此对源的 flakiness 容忍度高——**只需每月某次重试成功组装一次全量映射并缓存**即可，日更热路径永不依赖它实时可用。
   - → 东财 cons + 激进重试 + 持久缓存(复用上次 good map)，即使 flaky 也可用。

## 建议路径

- **主：东财 `stock_board_industry_cons_em`** 遍历 86 行业收成分，反转为 stock→二级行业；月级 job，激进重试(如 5×)，成功则写 `stock_industry_map.json` 缓存，失败则保留旧缓存不阻断。
- **对账**：保住，因东财同源。
- **回退(仅当 CI 也完全打不通东财)**：申万(需先修/换 akshare 成分调用)，对账降级为仅全市场。
- **待 CI 复验**：东财在 GitHub Actions IP 的成功率（可选：推一个一次性 probe workflow 实测）。

## CI 实测结论 (probe-industry-source workflow, run 28638443860)

- **东财 board_industry_name: 0/5 失败**（RemoteDisconnected）— **CI 里也彻底不可用**。
- **东财 cons(半导体): 0/5 失败** — 同。
- **申万 second_info: 2/2 成功**（131 二级，5.4s）— CI 可用，但仅"行业列表"，非个股成分。

→ **东财主路径 + dapanyuntu 同源对账 证伪**。

## 个股成分(membership)可靠源二次排查

- 东财 cons: 死（CI+本机）。
- 申万 `sw_index_third_cons`: akshare 1.18.64 **bug**（Length mismatch 18 vs 17），`clf_hist_sw` SSL 被墙。
- **巨潮 `stock_industry_change_cninfo(code)`: 本机可用**，但**逐股**(5531 次)、返回多分类标准多行需筛选，taxonomy 为巨潮/中证。

→ **没有"一次调用拿全市场股票→行业 + CI 可靠 + 与 dapanyuntu 同源"的源。** 行业维度自建的成本/脆弱性远高于预期。

## 重新评估的落地建议 (成本结构已变)

- **全市场 multi-period(MA20/60/120)**: 无需任何行业映射, close_series 直接算, **稳、廉价** → 高价值核心。
- **行业 multi-period**: 卡在可靠的个股→行业源。要么巨潮逐股(重、月级 job)、要么修 akshare 申万 bug, 且 taxonomy 变(非东财)、dapanyuntu 对账降级为仅全市场。
- **推荐 hybrid**: 自建全市场 MA20/60/120 温度计; 行业热力图/排行**沿用现有 dapanyuntu MA20**(已工作); 行业 60/120 暂缺、诚实标注。避开整个脆弱的 stock→industry 问题。

## 对设计的影响

- design 的东财主路径**成立**，但 M2 必须**缓存优先、失败不阻断**（写进 design 已有的"失败降级"，此处强化为"复用上次 good map"）。
- 若走 CI probe 再定，成本 ~几分钟一个临时 workflow。
