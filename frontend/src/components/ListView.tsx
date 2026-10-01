import React from 'react';
import { CheckCircle, AlertTriangle, ArrowRight, Package, MapPin } from 'lucide-react';

interface ListViewProps {
  data: Array<Record<string, any>>;
  title?: string;
}

export const ListView: React.FC<ListViewProps> = ({ data, title }) => {
  if (!data || data.length === 0) return null;

  return (
    <div className="w-full bg-white rounded-xl border border-slate-200 shadow-xs p-4 my-3 space-y-2.5">
      {title && (
        <div className="text-xs font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2 flex items-center justify-between">
          <span>{title}</span>
          <span className="text-[11px] font-normal text-slate-500">{data.length} priority items</span>
        </div>
      )}
      <div className="divide-y divide-slate-100 space-y-1">
        {data.slice(0, 10).map((item, idx) => {
          const mat = item.Material || item.MaterialCode || item.BinLocation || `Item #${idx + 1}`;
          const desc = item.MaterialDescription || item.Description || '';
          const qty = item.TotalQuantity ?? item.UnrestrictedQty ?? item.QuantityDifference;
          const bins = item.ActiveBinCount ?? item.BinsOccupied ?? item.BinCount;
          const uom = item.UOM || item.BaseUnitOfMeasure || '';

          return (
            <div key={idx} className="pt-2 pb-1.5 flex items-start justify-between space-x-3 hover:bg-slate-50/80 px-2 rounded-lg transition">
              <div className="flex items-start space-x-2.5 min-w-0">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-sky-100 text-sky-700 text-[11px] font-bold flex items-center justify-center mt-0.5">
                  {idx + 1}
                </span>
                <div className="min-w-0">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-bold text-slate-900 font-mono">{mat}</span>
                    {bins !== undefined && (
                      <span className="inline-flex items-center space-x-1 text-[10px] font-medium bg-amber-50 text-amber-700 px-1.5 py-0.2 rounded border border-amber-200/60">
                        <MapPin className="w-2.5 h-2.5" />
                        <span>{bins} bins</span>
                      </span>
                    )}
                  </div>
                  {desc && <div className="text-xs text-slate-600 truncate mt-0.5">{desc}</div>}
                </div>
              </div>

              {qty !== undefined && (
                <div className="text-right flex-shrink-0">
                  <div className="text-xs font-bold text-slate-900 font-mono">
                    {Number(qty).toLocaleString()} {uom}
                  </div>
                  <div className="text-[10px] text-slate-400">Total Units</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
