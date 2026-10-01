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

const PIE_COLORS = ['#0284c7', '#10b981', '#f59e0b', '#6366f1', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316', '#38bdf8', '#84cc16'];

function parseNumber(val: any): number | null {
  if (val === null || val === undefined || val === '') return null;
  if (typeof val === 'number') return isNaN(val) ? null : val;
  if (typeof val === 'string') {
    const clean = val.replace(/%/g, '').replace(/,/g, '').replace(/[a-zA-Z]+/g, '').trim();
    const num = parseFloat(clean);
    return isNaN(num) ? null : num;
  }
  return null;
}

export const InventoryPieChart: React.FC<InventoryPieChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || !Array.isArray(data) || data.length === 0) return null;

  const rawKeys = Object.keys(data[0] || {});
  if (rawKeys.length === 0) return null;

  const nameKey = xKey || rawKeys.find(k => typeof data[0][k] === 'string' && !['Rank', 'Quality Issue'].includes(k)) || rawKeys[0] || 'name';
  const valKey = yKey || rawKeys.find(k => k !== nameKey && parseNumber(data[0][k]) !== null) || rawKeys[1] || 'value';

  const chartData = data.map(item => {
    const row: Record<string, any> = { ...item };
    for (const k of Object.keys(item)) {
      const parsed = parseNumber(item[k]);
      if (parsed !== null) {
        row[`__num_${k}`] = parsed;
        if (k === valKey) {
          row[k] = parsed;
        }
      }
    }
    return row;
  }).filter(item => (parseNumber(item[valKey]) || 0) > 0);

  if (chartData.length === 0) return null;

  return (
    <div className="w-full bg-white p-4 md:p-5 rounded-2xl border border-slate-200 shadow-xs my-3">
      {title && (
        <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 mb-3.5">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-500 inline-block"></span>
            <span>{title}</span>
          </h4>
          <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
            {chartData.length} slices
          </span>
        </div>
      )}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey={valKey}
              nameKey={nameKey}
              cx="50%"
              cy="50%"
              outerRadius={85}
              innerRadius={35}
              paddingAngle={2}
              label={({ name, percent }) => `${String(name).slice(0, 10)} (${(percent * 100).toFixed(0)}%)`}
              labelLine={false}
            >
              {chartData.map((_, index) => (
                <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '10px',
                border: 'none',
                color: '#fff',
                fontSize: '12px'
              }}
              formatter={(value: any) => [Number(value).toLocaleString(), valKey]}
            />
            <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: '11px', color: '#64748b' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
