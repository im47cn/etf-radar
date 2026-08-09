import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from '@/components/ui/badge';

describe('Badge', () => {
  it('默认 variant 渲染文本', () => {
    render(<Badge>测试</Badge>);
    expect(screen.getByText('测试')).toBeInTheDocument();
    expect(screen.getByText('测试').tagName).toBe('SPAN');
  });

  it('variant=outline 渲染', () => {
    render(<Badge variant="outline">轮廓</Badge>);
    expect(screen.getByText('轮廓')).toBeInTheDocument();
  });

  it('variant=secondary 渲染', () => {
    render(<Badge variant="secondary">次要</Badge>);
    expect(screen.getByText('次要')).toBeInTheDocument();
  });

  it('支持自定义 className', () => {
    render(<Badge className="custom-cls">自定义</Badge>);
    const el = screen.getByText('自定义');
    expect(el.className).toContain('custom-cls');
  });

  it('支持 render prop 覆盖标签', () => {
    render(
      <Badge render={<a href="/x" data-testid="link" />}>
        链接徽章
      </Badge>,
    );
    const link = screen.getByTestId('link');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/x');
    expect(screen.getByText('链接徽章')).toBeInTheDocument();
  });
});
