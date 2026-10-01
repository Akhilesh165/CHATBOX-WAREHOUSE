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

const BAR_COLORS = [
  '#0284c7', // Sky blue
  '#0ea5e9', // Light sky
  '#38bdf8', // Cyan
  '#06b6d4', // Teal cyan
  '#0d9488', // Emerald teal
  '#10b981', // Emerald
  '#6366f1', // Indigo
  '#8b5cf6', // Violet
  '#a855f7', // Purple
  '#ec4899'  // Pink
];

// Robust numeric parser for values like "3.421%", "1,250", "45.2 FT3", 85.5
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

export const InventoryBarChart: React.FC<InventoryBarChartProps> = ({
  title,
  data,
  xKey,
  yKey
}) => {
  if (!data || !Array.isArray(data) || data.length === 0) return null;

  const rawKeys = Object.keys(data[0] || {});
  if (rawKeys.length === 0) return null;

  // Identify dimension (X) key
  const preferredXKeys = [
    'Material', 'MaterialCode', 'Plant', 'StorageLocation',
    'Bin', 'BinLocation', 'Ranking Group', 'Division', 'Category', 'Month', 'Date'
  ];
  let effectiveXKey = xKey;
  if (!effectiveXKey || !rawKeys.includes(effectiveXKey)) {
    effectiveXKey = preferredXKeys.find(k => rawKeys.includes(k)) || 
      rawKeys.find(k => typeof data[0][k] === 'string' && !['Rank', 'Quality Issue'].includes(k)) || 
      rawKeys[0];
  }

  // Identify measure (Y) key
  const preferredYKeys = [
    '% of Total Bin Volume', 'BinUtilizationPct', 'VolumeUtilizationPct', 'BinOccupancyPct',
    'Total Material Volume', 'Total Quantity', 'TotalOccupiedVolume', 'UnrestrictedQty',
    'TotalUnrestrictedQuantity', 'AvgInventoryPerOccupiedBin', 'TotalBins', 'OccupiedBins'
  ];
  let effectiveYKey = yKey;
  if (!effectiveYKey || !rawKeys.includes(effectiveYKey)) {
    effectiveYKey = preferredYKeys.find(k => rawKeys.includes(k)) ||
      rawKeys.find(k => {
        if (['Rank', 'Id', 'id', 'RowNumber'].includes(k) || k === effectiveXKey) return false;
        return parseNumber(data[0][k]) !== null;
      }) ||
      rawKeys[1] || 'value';
  }

  // Clean & Normalize dataset so Recharts receives real float numbers
  const chartData = data.map(item => {
    const row: Record<string, any> = { ...item };
    for (const k of Object.keys(item)) {
      const parsed = parseNumber(item[k]);
      if (parsed !== null) {
        row[`__num_${k}`] = parsed;
        // If it's the Y key and was a string with % or units, overwrite with numeric
        if (k === effectiveYKey) {
          row[k] = parsed;
        }
      }
    }
    return row;
  });

  const isPercentage = 
    String(effectiveYKey).includes('%') ||
    String(effectiveYKey).toLowerCase().includes('pct') ||
    String(effectiveYKey).toLowerCase().includes('percent') ||
    String(effectiveYKey).toLowerCase().includes('utiliz') ||
    String(effectiveYKey).toLowerCase().includes('occupan') ||
    String(effectiveYKey).toLowerCase().includes('share');

  // Compute dynamic max value for domain
  const maxVal = Math.max(...chartData.map(d => parseNumber(d[effectiveYKey]) || 0), 1);
  const yDomain: [number, number | string] = isPercentage 
    ? (maxVal <= 100 ? [0, Math.min(100, Math.ceil(maxVal > 20 ? 100 : maxVal * 1.3))] : [0, 'auto'])
    : [0, 'auto'];

  const displayTitle = title 
    ? title.replace(/Warehouse Bin Volume Utilization & Occupancy Percentage/gi, 'Warehouse Bin Utilization')
           .replace(/Volume Utilization & Occupancy Percentage/gi, 'Bin Utilization Percentage')
           .replace(/Volume Utilization/gi, 'Bin Utilization')
    : 'Warehouse Inventory & Utilization Distribution';

  return (
    <div className="w-full bg-white p-4 md:p-5 rounded-2xl border border-slate-200 shadow-xs my-3 transition-all duration-200">
      {displayTitle && (
        <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 mb-3.5">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-500 inline-block"></span>
            <span>{displayTitle}</span>
          </h4>
          <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
            {chartData.length} records
          </span>
        </div>
      )}

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 12, right: 24, left: 10, bottom: 28 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis
              dataKey={effectiveXKey}
              tick={{ fontSize: 11, fill: '#64748b' }}
              interval={0}
              angle={-20}
              textAnchor="end"
              tickFormatter={(val) => {
                const str = String(val || '');
                return str.length > 15 ? `${str.slice(0, 13)}…` : str;
              }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#64748b' }}
              domain={yDomain}
              tickFormatter={(v) => {
                if (isPercentage) return `${Number(v).toFixed(0)}%`;
                if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
                if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
                return `${v}`;
              }}
            />
            <Tooltip
              cursor={{ fill: '#f8fafc' }}
              contentStyle={{
                backgroundColor: '#0f172a',
                borderRadius: '10px',
                border: 'none',
                color: '#fff',
                fontSize: '12px',
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)'
              }}
              formatter={(value: any, name: any) => {
                const num = parseNumber(value) ?? 0;
                const formattedVal = isPercentage ? `${num.toFixed(3)}%` : num.toLocaleString();
                const displayMetricName = String(name || effectiveYKey)
                  .replace(/BinUtilizationPct/gi, 'Bin Utilization (%)')
                  .replace(/VolumeUtilizationPct/gi, 'Volume Utilization (%)')
                  .replace(/BinOccupancyPct/gi, 'Bin Occupancy (%)');
                return [formattedVal, displayMetricName];
              }}
              labelFormatter={(label) => `${effectiveXKey}: ${label}`}
            />
            <Legend
              verticalAlign="top"
              height={36}
              iconType="circle"
              wrapperStyle={{ fontSize: '11px', paddingBottom: '10px', color: '#64748b' }}
              formatter={(val) => {
                return String(val || effectiveYKey)
                  .replace(/BinUtilizationPct/gi, 'Bin Utilization (%)')
                  .replace(/VolumeUtilizationPct/gi, 'Volume Utilization (%)')
                  .replace(/BinOccupancyPct/gi, 'Bin Occupancy (%)');
              }}
            />
            <Bar
              dataKey={effectiveYKey}
              name={String(effectiveYKey)}
              radius={[6, 6, 0, 0]}
              maxBarSize={48}
            >
              {chartData.map((_, index) => (
                <Cell 
                  key={`cell-${index}`} 
                  fill={BAR_COLORS[index % BAR_COLORS.length]} 
                  className="transition-all duration-300 hover:opacity-80"
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
