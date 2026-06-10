import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  PolarAngleAxis,
} from 'recharts';

export const StrengthRing = ({ value, label }: { value: number; label: string }) => {
  const data = [{ name: label, value, fill: '#2563EB' }];
  return (
    <div className="relative w-32 h-32">
      <ResponsiveContainer>
        <RadialBarChart
          innerRadius="65%"
          outerRadius="95%"
          data={data}
          startAngle={90}
          endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={6} background />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
};
