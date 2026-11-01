'use client';

import React from 'react';
import { Layers, CheckCircle2, TrendingUp, AlertTriangle } from 'lucide-react';

export type ResponseCardType = 'table' | 'summary' | 'detail' | 'comparison';

export interface ResponseCardData {
  type: ResponseCardType;
  title?: string;
  subtitle?: string;
  summaryText?: string;
  tableData?: Array<{ [key: string]: any }>;
  kpis?: Array<{ label: string; value: string | number; change?: string; hint?: string }>;
  comparisonData?: {
    plantA: { name: string; qty: string; materials: string; bins: string; util: string };
    plantB: { name: string; qty: string; materials: string; bins: string; util: string };
    highlight?: string;
  };
}

interface ResponseCardProps {
  card: ResponseCardData;
}

export const ResponseCard: React.FC<ResponseCardProps> = ({ card }) => {
  // 1. SUMMARY CARD
  if (card.type === 'summary') {
    return (
      <div className="mt-2.5 rounded-xl bg-slate-950/90 border border-slate-800/80 p-3.5 shadow-md shadow-black/20 text-slate-200">
        <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-sky-500/10 text-sky-400">
              <Layers className="w-4 h-4" />
            </div>
            <span className="font-semibold text-xs text-slate-200 tracking-wide">
              {card.title || 'Inventory Summary'}
            </span>
          </div>
          <span className="text-[10px] font-medium text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
            Network Overview
          </span>
        </div>

        {card.summaryText && (
          <p className="text-xs text-slate-400 mb-3 leading-relaxed">
            {card.summaryText}
          </p>
        )}

        <div className="grid grid-cols-3 gap-2">
          {(card.kpis || [
            { label: 'Total Quantity', value: '1,933,031', hint: 'units' },
            { label: 'Unique Materials', value: '974', hint: 'SKUs' },
            { label: 'Occupied Bins', value: '7,525', hint: 'active' },
          ]).map((kpi, idx) => (
            <div
              key={idx}
              className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/60 flex flex-col items-start"
            >
              <span className="text-[10px] text-slate-400 font-medium truncate w-full">
                {kpi.label}
              </span>
              <span className="text-sm font-bold text-white mt-0.5 font-mono">
                {kpi.value}
              </span>
              {kpi.hint && (
                <span className="text-[9px] text-slate-400 mt-0.5">
                  {kpi.hint}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // 2. TABLE CARD
  if (card.type === 'table') {
    const rows = card.tableData || [
      { rank: 1, bin: 'BIN-1024', plant: '7228', util: '98.7%' },
      { rank: 2, bin: 'BIN-1842', plant: '1258', util: '97.9%' },
      { rank: 3, bin: 'BIN-2145', plant: '7228', util: '97.4%' },
      { rank: 4, bin: 'BIN-0891', plant: '1268', util: '96.8%' },
      { rank: 5, bin: 'BIN-1102', plant: '1266', util: '95.2%' },
    ];

    return (
      <div className="mt-2.5 rounded-xl bg-slate-950/90 border border-slate-800/80 overflow-hidden shadow-md shadow-black/20 text-slate-200">
        <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/80 border-b border-slate-800/80">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-400"></span>
            <span className="font-semibold text-xs text-slate-200">
              {card.title || 'Top Utilized Bins'}
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
            {rows.length} rows
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800/80 bg-slate-900/40 text-[11px] text-slate-400">
                <th className="py-2 px-3 font-semibold text-center w-12">Rank</th>
                <th className="py-2 px-3 font-semibold">Bin Location</th>
                <th className="py-2 px-3 font-semibold text-center">Plant</th>
                <th className="py-2 px-3 font-semibold text-right">Utilization</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40 font-mono">
              {rows.map((row, idx) => (
                <tr
                  key={idx}
                  className="hover:bg-slate-900/50 transition-colors group"
                >
                  <td className="py-2 px-3 text-center text-slate-400 text-[11px]">
                    {row.rank ?? idx + 1}
                  </td>
                  <td className="py-2 px-3 text-sky-400 font-medium group-hover:text-sky-300 transition-colors">
                    {row.bin}
                  </td>
                  <td className="py-2 px-3 text-center text-slate-300">
                    <span className="px-1.5 py-0.5 bg-slate-800 text-[10px] rounded text-slate-300 border border-slate-700/60">
                      {row.plant}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="inline-flex items-center gap-1 font-semibold text-emerald-400">
                      {row.util}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-3.5 py-2 bg-slate-900/60 border-t border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400">
          <span>Sort: Utilization (DESC)</span>
          <span className="text-sky-400 font-medium">Real-time mock dataset</span>
        </div>
      </div>
    );
  }

  // 3. COMPARISON CARD
  if (card.type === 'comparison') {
    const comp = card.comparisonData || {
      plantA: { name: 'Plant 1258', qty: '498,504 Qty', materials: '1,453 Materials', bins: '3,769 Bins', util: '60.8%' },
      plantB: { name: 'Plant 7228', qty: '1,933,031 Qty', materials: '974 Materials', bins: '7,525 Bins', util: '79.1%' },
      highlight: 'Plant 7228 holds 271% higher inventory volume with 7,525 active bins.'
    };

    return (
      <div className="mt-2.5 rounded-xl bg-slate-950/90 border border-slate-800/80 p-3.5 shadow-md shadow-black/20 text-slate-200">
        <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-amber-500/10 text-amber-400">
              <TrendingUp className="w-4 h-4" />
            </div>
            <span className="font-semibold text-xs text-slate-200">
              {card.title || 'Plant Inventory Comparison'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
            Multi-Plant
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          {/* Plant A */}
          <div className="p-3 rounded-lg bg-slate-900/70 border border-slate-800/70">
            <div className="flex items-center justify-between mb-2 pb-1 border-b border-slate-800/50">
              <span className="font-bold text-xs text-slate-200">
                {comp.plantA.name}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">{comp.plantA.util} fill</span>
            </div>
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-400 font-sans">Stock:</span>
                <span className="font-semibold">{comp.plantA.qty}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-400 font-sans">SKUs:</span>
                <span>{comp.plantA.materials}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-400 font-sans">Bins:</span>
                <span>{comp.plantA.bins}</span>
              </div>
            </div>
          </div>

          {/* Plant B */}
          <div className="p-3 rounded-lg bg-sky-950/20 border border-sky-500/30 relative overflow-hidden">
            <div className="absolute top-0 right-0 bg-sky-500 text-slate-950 font-bold text-[8px] px-1.5 py-0.5 rounded-bl">
              LEADER
            </div>
            <div className="flex items-center justify-between mb-2 pb-1 border-b border-sky-500/20">
              <span className="font-bold text-xs text-sky-200">
                {comp.plantB.name}
              </span>
              <span className="text-[10px] text-sky-400 font-mono font-semibold">{comp.plantB.util} fill</span>
            </div>
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between text-sky-100">
                <span className="text-slate-400 font-sans">Stock:</span>
                <span className="font-semibold text-white">{comp.plantB.qty}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-400 font-sans">SKUs:</span>
                <span>{comp.plantB.materials}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-400 font-sans">Bins:</span>
                <span>{comp.plantB.bins}</span>
              </div>
            </div>
          </div>
        </div>

        {comp.highlight && (
          <div className="mt-2.5 p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] text-slate-300 flex items-start gap-1.5">
            <span className="text-amber-400 text-xs">💡</span>
            <span>{comp.highlight}</span>
          </div>
        )}
      </div>
    );
  }

  // 4. DETAIL CARD
  return (
    <div className="mt-2.5 rounded-xl bg-slate-950/90 border border-slate-800/80 p-3.5 shadow-md shadow-black/20 text-slate-200">
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-sky-500/10 text-sky-400">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <span className="font-semibold text-xs text-slate-200">
            {card.title || 'Plant 1258 Detailed Inventory'}
          </span>
        </div>
        <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
          60.8% Occupied
        </span>
      </div>

      <p className="text-xs text-slate-300 mb-2.5 leading-relaxed">
        {card.summaryText || 'Total stock quantity is 498,504 units with 1,453 unique materials across 3,762 active bins, leaving 2,425 empty bins.'}
      </p>

      {/* Metric badges */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="p-2 rounded bg-slate-900 border border-slate-800/60 text-center">
          <div className="text-[10px] text-slate-400">Highest SKU</div>
          <div className="text-xs font-mono font-bold text-sky-400 truncate">BV430100002</div>
          <div className="text-[10px] text-slate-400">14,336 EA (47 bins)</div>
        </div>
        <div className="p-2 rounded bg-slate-900 border border-slate-800/60 text-center">
          <div className="text-[10px] text-slate-400">Available Space</div>
          <div className="text-xs font-mono font-bold text-emerald-400">2,425 Bins</div>
          <div className="text-[10px] text-slate-400">Ready for put-away</div>
        </div>
      </div>

      {/* Mini top items */}
      <div className="text-[11px] font-medium text-slate-400 mb-1">Top Materials:</div>
      <div className="space-y-1 font-mono text-[10px]">
        <div className="flex justify-between p-1.5 rounded bg-slate-900/60 border border-slate-800/50">
          <span className="text-sky-400">1. BV430100002 (VISION GLASS)</span>
          <span className="text-white font-semibold">14,336 EA</span>
        </div>
        <div className="flex justify-between p-1.5 rounded bg-slate-900/60 border border-slate-800/50">
          <span className="text-sky-400">2. BV430100001 (WATER TUMBLER)</span>
          <span className="text-white font-semibold">11,280 EA</span>
        </div>
      </div>
    </div>
  );
};
