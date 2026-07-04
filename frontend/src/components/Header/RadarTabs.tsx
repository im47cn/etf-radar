import { Link, useLocation } from 'react-router-dom';

const linkClass = (active: boolean): string =>
  active
    ? 'shrink-0 px-3 py-1 rounded bg-blue-600 text-white'
    : 'shrink-0 px-3 py-1 rounded text-gray-700 hover:bg-gray-100';

export const RadarTabs = () => {
  const { pathname } = useLocation();
  return (
    <div className="flex gap-1 text-sm overflow-x-auto whitespace-nowrap -mx-1 px-1">
      <Link to="/" className={linkClass(pathname === '/' || pathname === '/temperature')}>温度</Link>
      <Link to="/rotation" className={linkClass(pathname === '/rotation')}>轮动</Link>
      <Link to="/radar" className={linkClass(pathname === '/radar')}>雷达</Link>
      <Link to="/portfolio" className={linkClass(pathname === '/portfolio')}>持仓</Link>
      <Link to="/watchlist" className={linkClass(pathname === '/watchlist')}>自选</Link>
      <Link to="/membership" className={linkClass(pathname === '/membership')}>会员</Link>
    </div>
  );
};
