# Hook 约定

## 命名与位置

- `use*` 前缀，放 `src/hooks/`（跨功能）或就近 feature（少数）。测试在 `hooks/__tests__/`。

## 数据 hook 模式（SWR）

- 数据获取用 **SWR** + **zod 校验**，标准形态：
  ```ts
  const fetcher = async (url: string): Promise<T> => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`... ${res.status}`);
    return SomeSchema.parse(await res.json()); // zod 校验
  };
  export function useX() {
    const { data, error, isLoading } = useSWR(URL, fetcher, {
      revalidateOnFocus: false, errorRetryInterval: 5000,
    });
    return { data, error: error as Error | undefined, isLoading };
  }
  ```
  真实示例：`hooks/useMarketTemperature.ts`, `hooks/useEventsSnapshot.ts`。
- **URL 来自 `lib/dataUrls.ts`**（`LATEST_URLS.*` / `frameUrl(...)`），不在 hook 里硬编码。
- **返回归一化数据**：hook 内把原始 JSON 归一化成组件友好结构（如 `useMarketTemperature` 归一 schema 1.0/2.0 → `{dates, periods, available}`），组件不碰原始格式。
- **缺失优雅降级**：文件不存在/解析失败 → `data=undefined`，由页面显示"暂无数据"，不崩。

## 派生 hook

- 纯派生（从 context 数据算 Map/过滤）用 `useMemo`，如 `useThemeSignalsMap`。
- 遵守 react-hooks/recommended lint（依赖数组完整）。
