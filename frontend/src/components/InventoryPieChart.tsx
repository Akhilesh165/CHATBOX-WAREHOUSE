import React from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Tooltip,
  Cell,
  Legend
} from 'recharts';

interface InventoryPieChartProps {
  title?: string;
  data: Array<Record<string, any>>;
  xKey?: string;
  yKey?: string;
}

const PIE_COLORS = ['#0284c7', '#10b981', '#f59e0b', '#6366f1', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316'];

export const InventoryPieChart: React.FC<InventoryPieChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || data.length === 0) return null;

  const keys = Object.keys(data[0] || {});
  const nameKey = xKey || keys[0] || 'name';
  const valKey = yKey || keys.find(k => typeof data[0][k] === 'number') || keys[1] || 'value';

  return (
    <div className="w-full bg-white p-4 rounded-xl border border-slate-200 shadow-sm my-3">
      {title && (
        <h4 className="text-sm font-semibold text-slate-800 mb-3 border-b border-slate-100 pb-2">
          {title}
        </h4>
      )}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey={valKey}
              nameKey={nameKey}
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
              labelLine={false}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '8px',
                border: 'none',
                color: '#fff',
                fontSize: '12px'
              }}
              formatter={(value: any) => [Number(value).toLocaleString(), valKey]}
            />
            <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: '11px' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
