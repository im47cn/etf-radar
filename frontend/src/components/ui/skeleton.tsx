import { cn } from '@/lib/utils';

// 统一骨架屏基元：加载态占位块，pulse 呼吸动画。
// prefers-reduced-motion 下由 Tailwind 的 motion-reduce 变体自动关闭动画。
export const Skeleton = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn('animate-pulse rounded bg-gray-100 motion-reduce:animate-none', className)}
    {...props}
  />
);
