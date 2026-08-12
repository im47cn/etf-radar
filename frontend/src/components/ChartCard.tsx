import { useState, type ReactNode } from 'react';
import { Modal } from '@/components/ui/Modal';

interface ChartCardProps {
  title: string;
  subtitle: string;
  helpTitle: string;
  help: ReactNode;
  children: ReactNode;
}

/** 证据图统一卡片: 标题 + 副标题 + 右上角 ? 弹层(该图读法+案例) + 图表内容. */
export const ChartCard = ({ title, subtitle, helpTitle, help, children }: ChartCardProps) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
          <span className="text-[10px] text-gray-400">{subtitle}</span>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="shrink-0 rounded-full border border-gray-200 px-1.5 text-xs text-gray-400 hover:bg-gray-50 hover:text-gray-600"
          aria-label={`${title} 说明`}
        >
          ?
        </button>
      </div>
      {children}
      <Modal open={open} onClose={() => setOpen(false)} title={helpTitle}>
        {help}
      </Modal>
    </div>
  );
};

/** 无数据时的占位卡片. */
export const EmptyCard = ({ text }: { text: string }) => (
  <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">{text}</div>
);
