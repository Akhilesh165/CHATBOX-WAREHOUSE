import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Legend
} from 'recharts';

interface InventoryBarChartProps {
  title?: string;
  data: Array<Record<string, any>>;
  xKey?: string;
  yKey?: string;
}

const COLORS = ['#0284c7', '#0ea5e9', '#38bdf8', '#0284c7', '#0369a1', '#075985'];

export const InventoryBarChart: React.FC<InventoryBarChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || data.length === 0) return null;

  const firstRow = data[0] || {};
  const keys = Object.keys(firstRow);
  const effectiveXKey = xKey || keys[0] || 'x';

  // Check if this chart contains bin utilization
  const hasUtilization = 'BinUtilizationPct' in firstRow || 'BinOccupancyPct' in firstRow || 'VolumeUtilizationPct' in firstRow;
  const utilDataKey = 'BinUtilizationPct' in firstRow 
    ? 'BinUtilizationPct' 
    : ('BinOccupancyPct' in firstRow ? 'BinOccupancyPct' : 'VolumeUtilizationPct');

  const effectiveYKey = yKey || (hasUtilization ? utilDataKey : keys.find(k => typeof firstRow[k] === 'number')) || keys[1] || 'y';

  const displayTitle = title 
    ? title.replace(/Warehouse Bin Volume Utilization & Occupancy Percentage/gi, 'Warehouse Bin Utilization')
           .replace(/Volume Utilization & Occupancy Percentage/gi, 'Bin Utilization Percentage')
           .replace(/Volume Utilization/gi, 'Bin Utilization')
    : 'Warehouse Bin Utilization by Plant (%)';

  return (
    <div className="w-full bg-white p-4 rounded-xl border border-slate-200 shadow-sm my-3">
      {displayTitle && (
        <h4 className="text-sm font-semibold text-slate-800 mb-3 border-b border-slate-100 pb-2 flex items-center justify-between">
          <span>{displayTitle}</span>
        </h4>
      )}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis
              dataKey={effectiveXKey}
              tick={{ fontSize: 11, fill: '#64748b' }}
              interval={0}
              angle={-15}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickFormatter={(v) => (hasUtilization || String(effectiveYKey).includes('Pct') ? `${v}%` : v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
              domain={hasUtilization ? [0, 100] : ['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '8px',
                border: 'none',
                color: '#fff',
                fontSize: '12px'
              }}
              formatter={(value: any, name: any) => [
                hasUtilization || String(name).includes('Pct') || String(name).includes('%') 
                  ? `${Number(value).toFixed(2)}%` 
                  : Number(value).toLocaleString(),
                name === 'VolumeUtilizationPct' || name === 'BinUtilizationPct' || name === 'Volume Utilization (%)' 
                  ? 'Bin Utilization (%)' 
                  : name
              ]}
            />
            <Legend
              verticalAlign="top"
              height={36}
              iconType="circle"
              wrapperStyle={{ fontSize: '12px', paddingBottom: '8px' }}
            />
            {hasUtilization ? (
              <Bar
                dataKey={utilDataKey}
                name="Bin Utilization (%)"
                fill="#0284c7"
                radius={[4, 4, 0, 0]}
              />
            ) : (
              <Bar dataKey={effectiveYKey} name={String(effectiveYKey).includes('Pct') ? 'Percentage (%)' : effectiveYKey} radius={[4, 4, 0, 0]}>
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
