import { Slider } from '@base-ui/react/slider';
import { MAX_TRAIL_DAYS, type TrailRange } from '@/hooks/useTrailRange';

interface Props {
  range: TrailRange;
  onChange: (range: TrailRange) => void;
  maxDays: number;
}

export const TrailRangeSlider = ({ range, onChange, maxDays }: Props) => {
  // 当 maxDays===0 (无数据) 时, min 必须为 0 才能让 Base-UI 接受 disabled slider; 否则
  // min=-1 与 max=0 会让 Thumb 视觉偏移. 同时所有派生值 (startValue/endValue) 被钳进 [min,max].
  const min = maxDays === 0 ? 0 : -Math.min(MAX_TRAIL_DAYS, Math.max(1, maxDays));
  const max = 0;
  // Clamp display value into [min, max] so the Thumb never escapes the track
  // when range.startOffset < min (e.g., default -10 still safe with only 10 prefetched frames).
  const startValue = Math.max(min, Math.min(max, range.startOffset));
  const endValue = Math.max(min, Math.min(max, range.endOffset));
  const days = endValue - startValue;
  const disabled = maxDays === 0;

  return (
    <div className="px-4 py-2 flex items-center gap-4">
      <span className="text-xs text-gray-600 whitespace-nowrap">
        轨迹长度: <strong>{days} 天</strong>
      </span>
      <Slider.Root
        value={[startValue, endValue]}
        onValueChange={(v: number[]) => {
          if (v.length === 2) {
            onChange({ startOffset: v[0], endOffset: v[1] });
          }
        }}
        min={min}
        max={max}
        step={1}
        disabled={disabled}
        className="relative flex-1 flex items-center select-none touch-none h-6"
      >
        <Slider.Control className="relative flex-1 h-2 bg-gray-200 rounded-full">
          <Slider.Track>
            <Slider.Indicator className="absolute h-2 bg-blue-500 rounded-full" />
          </Slider.Track>
          <Slider.Thumb
            className="block w-4 h-4 bg-white border-2 border-blue-500 rounded-full focus:outline-none"
            aria-label="起始日"
          />
          <Slider.Thumb
            className="block w-4 h-4 bg-white border-2 border-blue-500 rounded-full focus:outline-none"
            aria-label="终止日"
          />
        </Slider.Control>
      </Slider.Root>
      <span className="text-xs text-gray-500 whitespace-nowrap">
        {range.startOffset} ~ {range.endOffset}
      </span>
    </div>
  );
};
