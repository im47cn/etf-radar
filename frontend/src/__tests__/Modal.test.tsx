import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from '@/components/ui/Modal';

describe('Modal', () => {
  it('open 时渲染标题与内容', () => {
    render(<Modal open onClose={() => {}} title="测试标题"><p>测试内容</p></Modal>);
    expect(screen.getByText('测试标题')).toBeInTheDocument();
    expect(screen.getByText('测试内容')).toBeInTheDocument();
  });

  it('closed 时不渲染', () => {
    render(<Modal open={false} onClose={() => {}} title="标题"><p>内容</p></Modal>);
    expect(screen.queryByText('标题')).toBeNull();
  });

  it('点击背景触发 onClose', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <Modal open onClose={onClose} title="标题"><p>内容</p></Modal>,
    );
    const backdrop = container.querySelector('[class*="bg-black"]');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ESC 触发 onClose 且 open 时锁滚动', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { unmount } = render(<Modal open onClose={onClose} title="标题"><p>内容</p></Modal>);
    expect(document.body.style.overflow).toBe('hidden'); // useEffect 锁滚动
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    expect(document.body.style.overflow).toBe(''); // cleanup 解锁
  });
});
