import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from 'recharts';

interface InventoryLineChartProps {
  title?: string;
  data: Array<Record<string, any>>;
  xKey?: string;
  yKey?: string;
}

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

export const InventoryLineChart: React.FC<InventoryLineChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || !Array.isArray(data) || data.length === 0) return null;

  const rawKeys = Object.keys(data[0] || {});
  if (rawKeys.length === 0) return null;

  const preferredXKeys = ['Date', 'Month', 'Year', 'ChangedAt', 'INSERT_TIMESTAMP', 'CreatedDate', 'Plant', 'Material'];
  let effectiveXKey = xKey;
  if (!effectiveXKey || !rawKeys.includes(effectiveXKey)) {
    effectiveXKey = preferredXKeys.find(k => rawKeys.includes(k)) || rawKeys[0];
  }

  let effectiveYKey = yKey;
  if (!effectiveYKey || !rawKeys.includes(effectiveYKey)) {
    effectiveYKey = rawKeys.find(k => k !== effectiveXKey && parseNumber(data[0][k]) !== null) || rawKeys[1] || 'value';
  }

  const chartData = data.map(item => {
    const row: Record<string, any> = { ...item };
    for (const k of Object.keys(item)) {
      const parsed = parseNumber(item[k]);
      if (parsed !== null) {
        row[`__num_${k}`] = parsed;
        if (k === effectiveYKey) {
          row[k] = parsed;
        }
      }
    }
    return row;
  });

  const isPercentage = String(effectiveYKey).includes('%') || String(effectiveYKey).toLowerCase().includes('pct');

  return (
    <div className="w-full bg-white dark:bg-slate-900 p-4 md:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs my-3 transition-colors">
      {title && (
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5 mb-3.5">
          <h4 className="text-xs font-bold text-slate-800 dark:text-slate-100 uppercase tracking-wider flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-500 inline-block"></span>
            <span>{title}</span>
          </h4>
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
            {chartData.length} data points
          </span>
        </div>
      )}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 24, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#94a3b8" strokeOpacity={0.2} />
            <XAxis
              dataKey={effectiveXKey}
              tick={{ fontSize: 11, fill: '#64748b' }}
              interval="preserveStartEnd"
              angle={-20}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickFormatter={(v) => {
                if (isPercentage) return `${Number(v).toFixed(0)}%`;
                if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
                if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
                return `${v}`;
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '10px',
                border: '1px solid #334155',
                color: '#fff',
                fontSize: '12px',
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3)'
              }}
              formatter={(value: any) => {
                const num = parseNumber(value) ?? 0;
                return [isPercentage ? `${num.toFixed(2)}%` : num.toLocaleString(), effectiveYKey];
              }}
            />
            <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: '11px', color: '#64748b' }} />
            <Line
              type="monotone"
              dataKey={effectiveYKey}
              name={String(effectiveYKey)}
              stroke="#0284c7"
              strokeWidth={3}
              dot={{ r: 4, fill: '#0284c7' }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
