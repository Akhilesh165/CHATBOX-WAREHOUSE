import React from 'react';
import { Boxes, Warehouse, Layers, Activity, Database, CheckCircle2 } from 'lucide-react';

interface KpiCardProps {
  data: Array<Record<string, any>>;
  metric?: string;
}

export const KpiCard: React.FC<KpiCardProps> = ({ data, metric }) => {
  if (!data || data.length === 0) return null;

  const firstRow = data[0] || {};
  
  // Extract key scalar numbers if available
  const totalQty = firstRow.TotalUnrestrictedQuantity ?? firstRow.TotalQuantity ?? firstRow.UnrestrictedQty;
  const uniqueMaterials = firstRow.TotalUniqueMaterials ?? firstRow.MaterialCount;
  const activeBins = firstRow.TotalActiveBins ?? firstRow.OccupiedBins ?? firstRow.BinCount;
  const plantCount = firstRow.PlantCount ?? firstRow.TotalPlants;
  const volumeUtil = firstRow.VolumeUtilizationPct ?? firstRow.BinUtilizationPct;

  return (
    <div className="w-full my-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {totalQty !== undefined && (
          <div className="bg-gradient-to-br from-sky-50 to-white border border-sky-200/80 rounded-xl p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-sky-700 mb-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider">Total Quantity</span>
              <Boxes className="w-4 h-4 text-sky-500" />
            </div>
            <div className="text-xl sm:text-2xl font-bold text-slate-900">
              {Number(totalQty).toLocaleString()}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Unrestricted Units</div>
          </div>
        )}

        {uniqueMaterials !== undefined && (
          <div className="bg-gradient-to-br from-emerald-50 to-white border border-emerald-200/80 rounded-xl p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-emerald-700 mb-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider">Active SKUs</span>
              <Layers className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-xl sm:text-2xl font-bold text-slate-900">
              {Number(uniqueMaterials).toLocaleString()}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Unique Materials</div>
          </div>
        )}

        {activeBins !== undefined && (
          <div className="bg-gradient-to-br from-purple-50 to-white border border-purple-200/80 rounded-xl p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-purple-700 mb-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider">Active Bins</span>
              <Warehouse className="w-4 h-4 text-purple-500" />
            </div>
            <div className="text-xl sm:text-2xl font-bold text-slate-900">
              {Number(activeBins).toLocaleString()}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Occupied Locations</div>
          </div>
        )}

        {plantCount !== undefined && (
          <div className="bg-gradient-to-br from-amber-50 to-white border border-amber-200/80 rounded-xl p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-amber-700 mb-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider">Plants</span>
              <Database className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-xl sm:text-2xl font-bold text-slate-900">
              {Number(plantCount).toLocaleString()}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Operational Facilities</div>
          </div>
        )}

        {volumeUtil !== undefined && (
          <div className="bg-gradient-to-br from-blue-50 to-white border border-blue-200/80 rounded-xl p-3.5 shadow-xs col-span-2 sm:col-span-4">
            <div className="flex items-center justify-between text-blue-700 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wider">Warehouse Utilization</span>
              <Activity className="w-4 h-4 text-blue-500" />
            </div>
            <div className="flex items-baseline space-x-2">
              <span className="text-2xl font-bold text-slate-900">{Number(volumeUtil).toFixed(2)}%</span>
              <span className="text-xs text-slate-500">of total storage capacity</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
