import { Link, useLocation } from 'react-router-dom';

const linkClass = (active: boolean): string =>
  active
    ? 'px-3 py-1 rounded bg-blue-600 text-white'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100';

export const RadarTabs = () => {
  const { pathname } = useLocation();
  return (
    <div className="flex gap-1 text-sm">
      <Link to="/" className={linkClass(pathname === '/' || pathname === '/rotation')}>主题轮动</Link>
      <Link to="/radar" className={linkClass(pathname === '/radar')}>跨市雷达</Link>
      <Link to="/portfolio" className={linkClass(pathname === '/portfolio')}>
        我的持仓
      </Link>
    </div>
  );
};
