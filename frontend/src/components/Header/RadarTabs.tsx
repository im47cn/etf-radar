export const RadarTabs = () => (
  <div className="flex gap-1 text-sm">
    <button className="px-3 py-1 rounded bg-blue-600 text-white">跨市雷达</button>
    <button
      className="px-3 py-1 rounded text-gray-400 cursor-not-allowed"
      disabled
    >
      主题轮动 (v2)
    </button>
    <button
      className="px-3 py-1 rounded text-gray-400 cursor-not-allowed"
      disabled
    >
      持仓监控 (v3)
    </button>
  </div>
);
