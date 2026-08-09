import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Alert, AlertTitle, AlertDescription, AlertAction } from '@/components/ui/alert';

describe('Alert', () => {
  it('default variant 渲染 + role=alert', () => {
    render(<Alert>内容</Alert>);
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toBe('内容');
  });

  it('warning variant 渲染', () => {
    render(<Alert variant="warning">警告</Alert>);
    expect(screen.getByRole('alert').textContent).toBe('警告');
  });

  it('destructive variant 渲染', () => {
    render(<Alert variant="destructive">严重</Alert>);
    expect(screen.getByRole('alert').textContent).toBe('严重');
  });

  it('AlertTitle 渲染标题', () => {
    render(<Alert><AlertTitle>标题</AlertTitle></Alert>);
    expect(screen.getByText('标题')).toBeInTheDocument();
  });

  it('AlertDescription 渲染描述', () => {
    render(<Alert><AlertDescription>描述文本</AlertDescription></Alert>);
    expect(screen.getByText('描述文本')).toBeInTheDocument();
  });

  it('AlertAction 渲染操作区', () => {
    render(<Alert><AlertAction><button>操作</button></AlertAction></Alert>);
    expect(screen.getByText('操作')).toBeInTheDocument();
  });

  it('支持自定义 className', () => {
    render(<Alert className="my-alert">内容</Alert>);
    expect(screen.getByRole('alert').className).toContain('my-alert');
  });
});
