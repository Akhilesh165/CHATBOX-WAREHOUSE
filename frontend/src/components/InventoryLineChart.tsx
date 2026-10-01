import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from 'recharts';

interface InventoryLineChartProps {
  title?: string;
  data: Array<Record<string, any>>;
  xKey?: string;
  yKey?: string;
}

export const InventoryLineChart: React.FC<InventoryLineChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || data.length === 0) return null;

  const keys = Object.keys(data[0] || {});
  const effectiveXKey = xKey || keys[0] || 'x';
  const effectiveYKey = yKey || keys.find(k => typeof data[0][k] === 'number') || keys[1] || 'y';

  return (
    <div className="w-full bg-white p-4 rounded-xl border border-slate-200 shadow-sm my-3">
      {title && (
        <h4 className="text-sm font-semibold text-slate-800 mb-3 border-b border-slate-100 pb-2">
          {title}
        </h4>
      )}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis
              dataKey={effectiveXKey}
              tick={{ fontSize: 11, fill: '#64748b' }}
              interval="preserveStartEnd"
              angle={-20}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '8px',
                border: 'none',
                color: '#fff',
                fontSize: '12px'
              }}
              formatter={(value: any) => [Number(value).toLocaleString(), effectiveYKey]}
            />
            <Line
              type="monotone"
              dataKey={effectiveYKey}
              stroke="#0284c7"
              strokeWidth={2.5}
              dot={{ r: 4, fill: '#0284c7' }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
