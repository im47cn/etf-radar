import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export const UserMenu = () => {
  const { status, user, signOut } = useAuth();
  const [open, setOpen] = useState(false);

  if (status === 'loading') return null;
  if (status === 'unconfigured') return null;

  if (status === 'anonymous') {
    return (
      <Link to="/portfolio" className="text-sm px-3 py-1 border rounded hover:bg-gray-50">
        登录
      </Link>
    );
  }

  const email = user?.email ?? '';
  const truncated = email.length > 20 ? email.slice(0, 17) + '...' : email;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="text-sm px-3 py-1 border rounded hover:bg-gray-50 flex items-center gap-1"
      >
        <span>📧 <span className="hidden md:inline">{truncated}</span><span className="md:hidden">已登录</span></span>
        <span className="text-xs">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 min-w-[160px] bg-white border rounded shadow-lg z-50">
          <div className="hidden md:block px-3 py-2 text-xs text-gray-500 border-b">{email}</div>
          <button
            onClick={() => { signOut(); setOpen(false); }}
            className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100"
          >
            退出登录
          </button>
        </div>
      )}
    </div>
  );
};
