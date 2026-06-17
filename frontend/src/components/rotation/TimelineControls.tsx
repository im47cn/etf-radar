import { Play, Pause, Square } from 'lucide-react';
import type { PlaySpeed } from '@/hooks/useTimelinePlayer';

export interface TimelineControlsProps {
  dates: string[];
  currentDate: string;
  onDateChange: (date: string) => void;

  playing: boolean;
  speed: PlaySpeed;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  onSpeedChange: (s: PlaySpeed) => void;

  showTrails: boolean;
  onToggleTrails: (v: boolean) => void;

  disabled?: boolean;
}

const SPEEDS: PlaySpeed[] = [1, 2, 4];

export const TimelineControls = (props: TimelineControlsProps) => {
  const {
    dates, currentDate, onDateChange,
    playing, speed, onPlay, onPause, onStop, onSpeedChange,
    showTrails, onToggleTrails,
    disabled = false,
  } = props;

  const currentIdx = Math.max(0, dates.indexOf(currentDate));
  const maxIdx = Math.max(0, dates.length - 1);

  return (
    <div className="flex flex-col gap-2 p-3 border-t bg-background md:flex-row md:items-center md:gap-4">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <button
          type="button"
          aria-label="停止"
          disabled={disabled}
          onClick={onStop}
          className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
        >
          <Square size={16} />
        </button>
        <button
          type="button"
          aria-label={playing ? '暂停' : '播放'}
          disabled={disabled}
          onClick={playing ? onPause : onPlay}
          className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <input
          type="range"
          min={0}
          max={maxIdx}
          value={currentIdx}
          disabled={disabled}
          onChange={(e) => {
            const idx = Number(e.target.value);
            if (dates[idx]) onDateChange(dates[idx]);
          }}
          className="flex-1 min-w-0"
        />
        <span className="text-sm tabular-nums text-muted-foreground whitespace-nowrap">
          {currentDate}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex rounded border overflow-hidden" role="group" aria-label="速度">
          {SPEEDS.map(s => (
            <button
              key={s}
              type="button"
              disabled={disabled}
              onClick={() => onSpeedChange(s)}
              className={`px-2 py-1 text-xs ${s === speed ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-muted'} disabled:opacity-40`}
            >
              {s}x
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs select-none">
          <input
            type="checkbox"
            checked={showTrails}
            disabled={disabled}
            onChange={(e) => onToggleTrails(e.target.checked)}
            aria-label="显示尾迹"
          />
          显示尾迹
        </label>
      </div>
    </div>
  );
};
