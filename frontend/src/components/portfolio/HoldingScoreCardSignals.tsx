import type { Strength } from '@/lib/portfolio/types';

interface SecondaryTheme {
  id: string;
  name: string;
}

interface Props {
  themeName?: string;
  secondaryThemes?: SecondaryTheme[];
  selfStrength?: Strength;
  themeUsStrength?: Strength;
  themeCnStrength?: Strength;
  narrative?: string;
}

// covered 持仓的信号区：主题归属 → 次要归属 chip → 双轨/自身强度 → narrative，任一段缺省即跳过
export const HoldingScoreCardSignals = ({
  themeName,
  secondaryThemes,
  selfStrength,
  themeUsStrength,
  themeCnStrength,
  narrative,
}: Props) => (
  <div className="mt-3 pt-2 border-t text-sm space-y-2">
    {themeName ? (
      <div className="text-gray-600">归属主题：<span className="font-medium text-gray-900">{themeName}</span></div>
    ) : (
      <div className="text-xs text-gray-400">ⓘ 未归入主题分组（暂无双轨信号）</div>
    )}

    {secondaryThemes && secondaryThemes.length > 0 && (
      <div className="text-xs text-gray-500 flex flex-wrap items-center gap-1">
        <span>也属于</span>
        {secondaryThemes.slice(0, 3).map(t => (
          <span key={t.id} className="bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">
            {t.name}
          </span>
        ))}
        {secondaryThemes.length > 3 && (
          <span className="text-gray-400">+{secondaryThemes.length - 3}</span>
        )}
        <span className="text-gray-400">· 百分位仅基于主归属计算</span>
      </div>
    )}

    {selfStrength && (
      <div className={`grid ${themeUsStrength ? 'grid-cols-2' : 'grid-cols-1'} gap-2 text-xs`}>
        {themeUsStrength && (
          <div className="border rounded p-2">
            <div className="text-gray-500 mb-1">双轨强度（美/A）</div>
            <div>美 短{themeUsStrength.short} 中{themeUsStrength.mid} 长{themeUsStrength.long}</div>
            {themeCnStrength && (
              <div>A 短{themeCnStrength.short} 中{themeCnStrength.mid} 长{themeCnStrength.long}</div>
            )}
          </div>
        )}
        <div className="border rounded p-2">
          <div className="text-gray-500 mb-1">ETF 自身百分位</div>
          <div>短 {selfStrength.short}</div>
          <div>中 {selfStrength.mid}</div>
          <div>长 {selfStrength.long}</div>
          <div>综合 {selfStrength.composite}</div>
        </div>
      </div>
    )}

    {narrative && (
      <div className="text-gray-700 text-xs leading-relaxed bg-gray-50 p-2 rounded">
        {narrative}
      </div>
    )}
  </div>
);
