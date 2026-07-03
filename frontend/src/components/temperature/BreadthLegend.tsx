import { TIERS, breadthColor, breadthTextureCss } from '@/lib/breadthColor';

/**
 * 市场温度色阶图例 primitive. 无 props, 4 档全部来自 TIERS 派生.
 * 色块 aria-hidden(装饰), 语义靠文字(档名+区间) -> 屏幕阅读器可朗读, 不只靠颜色.
 */
export const BreadthLegend = () => (
  <ul
    role="list"
    aria-label="市场温度色阶图例"
    className="flex flex-nowrap items-center justify-between gap-x-1 sm:justify-start sm:gap-x-3"
  >
    {TIERS.map((t) => (
      <li
        key={t.key}
        className="flex items-center gap-1 whitespace-nowrap text-[11px] text-gray-600 sm:gap-1.5 sm:text-xs"
      >
        <span
          aria-hidden
          className="h-3 w-4 shrink-0 rounded-sm border border-gray-300"
          style={{ backgroundColor: breadthColor(t.mid), ...breadthTextureCss(t.mid) }}
        />
        <span>
          {t.label} <span className="text-gray-400">{t.min}–{t.max}%</span>
        </span>
      </li>
    ))}
  </ul>
);
