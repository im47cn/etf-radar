import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthOptional } from '@/hooks/useAuth';
import { useWatchlist } from '@/lib/watchlist/useWatchlist';
import { NotAMemberError, type WatchItemType } from '@/lib/watchlist/types';

// 「加自选」按钮：会员可点，非会员点击后引导去 /membership。
// 依赖 add_watchlist RPC 服务端会员校验，前端仅做提示，非安全边界。
export const AddWatchButton = ({
  itemType, itemKey, className,
}: { itemType: WatchItemType; itemKey: string; className?: string }) => {
  const status = useAuthOptional()?.status ?? 'unconfigured';
  const { add } = useWatchlist();
  const navigate = useNavigate();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleClick = async () => {
    if (status !== 'authenticated') {
      navigate('/membership');
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await add(itemType, itemKey);
      setMsg(r.error ? `失败：${r.error}` : '已加入自选');
    } catch (e) {
      if (e instanceof NotAMemberError) {
        setMsg('自选为会员功能');
        navigate('/membership');
      } else {
        setMsg('操作失败');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={busy}
        className={className ?? 'text-xs px-2 py-0.5 border rounded text-gray-600 hover:bg-gray-50 disabled:opacity-50'}
      >
        {busy ? '...' : '＋自选'}
      </button>
      {msg && <span className="text-xs text-gray-500">{msg}</span>}
    </span>
  );
};
