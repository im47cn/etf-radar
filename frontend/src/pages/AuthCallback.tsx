import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export const AuthCallback = () => {
  const { status } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === 'authenticated') {
      navigate('/portfolio', { replace: true });
    } else if (status === 'anonymous') {
      // session 解析后仍未登录，回登录页
      navigate('/portfolio', { replace: true });
    }
    // status === 'loading' / 'unconfigured' 时不动
  }, [status, navigate]);

  return (
    <div className="flex items-center justify-center min-h-[40vh] text-gray-600">
      <div className="text-center space-y-2">
        <div className="text-2xl">🔐</div>
        <div>正在完成登录...</div>
      </div>
    </div>
  );
};
