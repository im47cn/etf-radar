import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChartCard } from '@/components/ChartCard';

describe('ChartCard', () => {
  it('渲染标题/副标题/内容, 初始弹层关闭', () => {
    render(
      <ChartCard title="图标题" subtitle="副标题" helpTitle="帮助标题" help={<p>帮助内容</p>}>
        <div data-testid="chart">图表</div>
      </ChartCard>,
    );
    expect(screen.getByText('图标题')).toBeInTheDocument();
    expect(screen.getByText('副标题')).toBeInTheDocument();
    expect(screen.getByTestId('chart')).toBeInTheDocument();
    expect(screen.queryByText('帮助标题')).toBeNull(); // Modal 初始关
  });

  it('点 ? 按钮打开弹层 (显示 helpTitle + help)', async () => {
    const user = userEvent.setup();
    render(
      <ChartCard title="图标题" subtitle="副标题" helpTitle="帮助标题" help={<p>帮助内容</p>}>
        <div>图表</div>
      </ChartCard>,
    );
    await user.click(screen.getByLabelText('图标题 说明'));
    expect(screen.getByText('帮助标题')).toBeInTheDocument();
    expect(screen.getByText('帮助内容')).toBeInTheDocument();
  });

  it('EmptyCard 渲染占位文本', async () => {
    const { EmptyCard } = await import('@/components/ChartCard');
    render(<EmptyCard text="暂无数据" />);
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });
});
