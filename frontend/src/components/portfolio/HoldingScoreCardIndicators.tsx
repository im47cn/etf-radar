import type { MomentumTag, StrengthTag } from '@/lib/portfolio/types';
import { tagColor } from '@/lib/portfolio/tagColor';

interface Props {
  isUncovered: boolean;
  l2Tag?: StrengthTag;
  momentumTag?: MomentumTag | null;
}

export const HoldingScoreCardIndicators = ({ isUncovered, l2Tag, momentumTag }: Props) => {
  if (isUncovered) {
    return <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600">无信号</span>;
  }
  return (
    <>
      {l2Tag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(l2Tag)}`}>{l2Tag}</span>}
      {momentumTag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(momentumTag)}`}>{momentumTag}</span>}
    </>
  );
};
