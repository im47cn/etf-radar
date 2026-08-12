import { useState, type ReactNode } from 'react';
import { Modal } from '@/components/ui/Modal';

/** 帮助弹窗内一节: 标题 + 正文 (正文通常是若干 <p>). */
export interface HelpSection {
  title: string;
  children: ReactNode;
}

interface PageHelpProps {
  /** 页面名, 弹窗标题渲染为 "{title} · 使用说明". */
  title: string;
  sections: HelpSection[];
  /** 可选末端口径说明 (如 TemperaturePage 的分母口径 <p>). */
  footer?: ReactNode;
  /** 按钮额外类名 (对齐微调). */
  buttonClassName?: string;
}

const Section = ({ title, children }: HelpSection) => (
  <div className="space-y-1">
    <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
    <div className="space-y-1 text-xs">{children}</div>
  </div>
);

/**
 * 页面级"使用说明"帮助按钮 + 弹窗. 仿 EvidencePage 模式抽出的共享组件:
 * 一个 📖 按钮 + Modal(分层 Section + 可选口径 footer). 调用方只传 title/sections 数据,
 * 不重复写 state/按钮/Modal. 样式与原 EvidencePage 完全一致.
 */
export const PageHelp = ({ title, sections, footer, buttonClassName }: PageHelpProps) => {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`shrink-0 rounded border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50 ${
          buttonClassName ?? ''
        }`}
      >
        📖 使用说明
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={`${title} · 使用说明`}>
        {sections.map((s) => (
          <Section key={s.title} title={s.title}>
            {s.children}
          </Section>
        ))}
        {footer}
      </Modal>
    </>
  );
};
