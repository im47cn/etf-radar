import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

const sections: HelpSection[] = [
  { title: '理论基础', children: <p>理论正文</p> },
  { title: '使用方法', children: <p>方法正文</p> },
];

describe('PageHelp', () => {
  it('默认仅渲染按钮, 弹窗内容不显示', () => {
    render(<PageHelp title="测试页" sections={sections} />);
    expect(screen.getByText('📖 使用说明')).toBeInTheDocument();
    expect(screen.queryByText('测试页 · 使用说明')).toBeNull();
    expect(screen.queryByText('理论基础')).toBeNull();
  });

  it('点按钮打开弹窗: 渲染标题 + 各 Section 标题与正文', async () => {
    const user = userEvent.setup();
    render(<PageHelp title="测试页" sections={sections} />);
    await user.click(screen.getByText('📖 使用说明'));
    expect(screen.getByText('测试页 · 使用说明')).toBeInTheDocument();
    expect(screen.getByText('理论基础')).toBeInTheDocument();
    expect(screen.getByText('理论正文')).toBeInTheDocument();
    expect(screen.getByText('使用方法')).toBeInTheDocument();
    expect(screen.getByText('方法正文')).toBeInTheDocument();
  });

  it('渲染 footer 口径说明', async () => {
    const user = userEvent.setup();
    render(
      <PageHelp
        title="测试页"
        sections={sections}
        footer={<p>口径说明正文</p>}
      />,
    );
    await user.click(screen.getByText('📖 使用说明'));
    expect(screen.getByText('口径说明正文')).toBeInTheDocument();
  });

  it('点背景关闭弹窗', async () => {
    const user = userEvent.setup();
    render(<PageHelp title="测试页" sections={sections} />);
    await user.click(screen.getByText('📖 使用说明'));
    expect(screen.getByText('理论基础')).toBeInTheDocument();
    const backdrop = document.body.querySelector('[class*="bg-black"]');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop!);
    expect(screen.queryByText('理论基础')).toBeNull();
  });

  it('buttonClassName 透传到按钮', () => {
    render(<PageHelp title="测试页" sections={sections} buttonClassName="custom-cls" />);
    const btn = screen.getByText('📖 使用说明').closest('button');
    expect(btn?.className).toContain('custom-cls');
  });
});
