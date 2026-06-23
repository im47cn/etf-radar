import type { HealthGrade, HealthScore } from '@/types/rotation';

const GRADE_LABEL: Record<HealthGrade, string> = {
  healthy: '健康',
  caution: '警示',
  imbalanced: '失衡',
  insufficient: '数据不足',
};

const GRADE_BADGE_CLASS: Record<HealthGrade, string> = {
  healthy: 'bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs',
  caution: 'bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-xs',
  imbalanced: 'bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs',
  insufficient: 'bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs',
};

const TOOLTIP: Record<'coverage' | 'robustness', string> = {
  coverage:
    '四象限主题数的香农熵。100=四象限均匀，0=全部挤在一个象限。低分意味分类信号集中，需结合大盘环境理解。',
  robustness:
    '远离边界线 (x=50 或 y=50) 超过 10 单位的主题占比。低分意味多数主题贴近边界，小幅波动就会跨象限，分类信号脆弱；高分意味分类对噪声有抗扰动能力。',
};

interface HealthCellProps {
  label: string;
  score: number;
  grade: HealthGrade;
  tooltip: string;
}

const HealthCell = ({ label, score, grade, tooltip }: HealthCellProps) => {
  const display = grade === 'insufficient' ? '—' : score.toString();
  const ariaLabel = `${label} ${display}${grade === 'insufficient' ? '' : ' 分'} ${GRADE_LABEL[grade]}`;
  return (
    // 窄屏 padding/字号同步压缩, 释放垂直空间给象限图
    <div
      className="bg-white px-2 py-1 sm:px-4 sm:py-2 flex items-center justify-between gap-1"
      role="status"
      aria-label={ariaLabel}
      title={tooltip}
    >
      <span className="text-xs text-gray-600 shrink-0">{label}</span>
      <div className="flex items-center gap-1 sm:gap-2 min-w-0">
        <span className="text-base sm:text-lg font-semibold tabular-nums">{display}</span>
        <span className={GRADE_BADGE_CLASS[grade]}>{GRADE_LABEL[grade]}</span>
      </div>
    </div>
  );
};

export interface RotationHealthBarProps {
  health: HealthScore;
}

export const RotationHealthBar = ({ health }: RotationHealthBarProps) => (
  // 始终两列: 移动端窄屏下也并排展示, 避免吃掉一整行高度.
  // 窄屏空间够用: 每 cell 约 160px (=320/2), 容纳 label+score+badge 无溢出.
  <div
    className="grid grid-cols-2 gap-px bg-gray-200 border rounded overflow-hidden mb-4"
    role="region"
    aria-label="分布健康度"
  >
    <HealthCell
      label="覆盖度"
      score={health.coverage.score}
      grade={health.coverage.grade}
      tooltip={TOOLTIP.coverage}
    />
    <HealthCell
      label="鲁棒度"
      score={health.robustness.score}
      grade={health.robustness.grade}
      tooltip={TOOLTIP.robustness}
    />
  </div>
);
