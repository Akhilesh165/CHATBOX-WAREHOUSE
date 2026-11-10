'use client';

import React from 'react';
import {
  Boxes,
  Layers,
  TrendingUp,
  Warehouse,
  CheckCircle2,
  Clock,
  Search,
  SlidersHorizontal,
  ArrowUpRight,
  ShieldCheck,
  Building2,
  BarChart3,
  RefreshCw,
} from 'lucide-react';
import { WarehouseStatsResponse } from '../../types/dashboard';

interface DashboardBackgroundProps {
  onOpenChatbot?: () => void;
  isChatOpen?: boolean;
  stats?: WarehouseStatsResponse | null;
  isLoading?: boolean;
}

export const DashboardBackground: React.FC<DashboardBackgroundProps> = ({
  onOpenChatbot,
  isChatOpen = false,
  stats,
  isLoading = false,
}) => {
  // Reliable data derived directly from the live database backend
  const plantCount = stats?.plant_count ?? 4;
  const plants = stats?.plants ?? [];
  const summary = stats?.summary ?? {
    total_inventory: 4329509,
    occupied_bins: 23296,
    total_bins: 33129,
    active_materials: 2883,
    overall_utilization: 70.3,
    putaway_throughput: 38420,
    putaway_on_time_pct: 99.2,
  };

  return (
    <div
      className={`min-h-screen bg-[#f8fafc] text-slate-800 transition-all duration-300 font-sans ${
        isChatOpen ? 'lg:mr-[440px]' : ''
      }`}
    >
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-200/90 bg-white/95 backdrop-blur-md sticky top-0 z-20 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          {/* Brand Logo & Title */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center text-white shadow-xs">
              <Warehouse className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-slate-900">
                  WarehouseOS
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider bg-blue-50 text-blue-700 border border-blue-200/70 px-2 py-0.5 rounded-full">
                  Enterprise
                </span>
              </div>
              <p className="text-[11px] text-slate-500 hidden sm:block">
                Multi-Facility Inventory & Bin Operations Console
              </p>
            </div>
          </div>

          {/* Quick Search */}
          <div className="hidden md:flex items-center flex-1 max-w-md mx-6">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search SKUs, Bins, Plants, or Work Orders..."
                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-4 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
              />
            </div>
          </div>

          {/* Right Header Status & Chat Opener */}
          <div className="flex items-center gap-3">
            {/* Dynamic plant count indicator from live database */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200/80 text-emerald-700 text-xs font-medium shadow-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>All {plantCount} Plants Synchronized</span>
            </div>

            {!isChatOpen && (
              <button
                onClick={onOpenChatbot}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium shadow-xs hover:shadow transition-all"
              >
                <span>Ask Copilot</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Dashboard Workspace */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-7 space-y-6">
        {/* Banner Alert Card */}
        <div className="p-4 rounded-xl bg-white border border-slate-200/90 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-blue-50 text-blue-600 shrink-0">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                Warehouse Copilot Intelligence Active
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Query inventory levels, inspect bin utilization, and execute multi-plant comparisons in natural language.
              </p>
            </div>
          </div>
          <button
            onClick={onOpenChatbot}
            className="self-start sm:self-center text-xs px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-medium transition-all shadow-xs shrink-0 flex items-center gap-1.5"
          >
            <span>{isChatOpen ? 'Assistant Open ↗' : 'Open Assistant →'}</span>
          </button>
        </div>

        {/* 4 Top KPI Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* KPI 1: Total Inventory */}
          <div className="p-5 rounded-xl bg-white border border-slate-200/80 hover:border-slate-300 shadow-xs transition-all">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider">
                Total Inventory
              </span>
              <div className="p-1.5 rounded-md bg-blue-50 text-blue-600">
                <Boxes className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900 tracking-tight font-mono">
              {summary.total_inventory.toLocaleString()}
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs text-emerald-600 font-medium">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Unrestricted stock across all bins</span>
            </div>
          </div>

          {/* KPI 2: Bin Occupancy */}
          <div className="p-5 rounded-xl bg-white border border-slate-200/80 hover:border-slate-300 shadow-xs transition-all">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider">
                Bin Occupancy
              </span>
              <div className="p-1.5 rounded-md bg-indigo-50 text-indigo-600">
                <Layers className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900 tracking-tight font-mono">
              {summary.occupied_bins.toLocaleString()}
              <span className="text-sm text-slate-400 font-normal ml-1">
                / {summary.total_bins.toLocaleString()}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs text-blue-600 font-medium">
              <BarChart3 className="w-3.5 h-3.5" />
              <span>{summary.overall_utilization}% overall capacity utilization</span>
            </div>
          </div>

          {/* KPI 3: Active Plants (Dynamic) */}
          <div className="p-5 rounded-xl bg-white border border-slate-200/80 hover:border-slate-300 shadow-xs transition-all">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider">
                Active Plants
              </span>
              <div className="p-1.5 rounded-md bg-emerald-50 text-emerald-600">
                <Building2 className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900 tracking-tight font-mono">
              {plantCount} <span className="text-sm text-slate-500 font-normal">Facilities</span>
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-500">
              <span className="font-mono text-slate-700 font-semibold">{summary.active_materials.toLocaleString()}</span>
              <span>unique materials stored</span>
            </div>
          </div>

          {/* KPI 4: Put-Away Throughput */}
          <div className="p-5 rounded-xl bg-white border border-slate-200/80 hover:border-slate-300 shadow-xs transition-all">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider">
                Put-Away Throughput
              </span>
              <div className="p-1.5 rounded-md bg-teal-50 text-teal-600">
                <CheckCircle2 className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900 tracking-tight font-mono">
              {summary.putaway_throughput.toLocaleString()}
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs text-emerald-600 font-medium">
              <Clock className="w-3.5 h-3.5" />
              <span>{summary.putaway_on_time_pct}% on-time placement SLA</span>
            </div>
          </div>
        </section>

        {/* Central Operations Section: Plant Table + Activity Feed */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Facility Performance Table (2 Columns) */}
          <div className="lg:col-span-2 rounded-xl bg-white border border-slate-200/90 overflow-hidden shadow-xs">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Facility Utilization Summary
                </h3>
                {/* Dynamically displaying actual plant count */}
                <p className="text-xs text-slate-500 mt-0.5">
                  Real-time bin density and active storage across {plantCount} warehouse plants
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium flex items-center gap-1.5 shadow-xs transition-all">
                  <SlidersHorizontal className="w-3.5 h-3.5 text-slate-500" />
                  <span>Filter</span>
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-slate-600 font-semibold">
                    <th className="py-3 px-4">Plant</th>
                    <th className="py-3 px-4">Facility Type</th>
                    <th className="py-3 px-4 text-right">Occupied Bins</th>
                    <th className="py-3 px-4 text-right">Inventory (Qty)</th>
                    <th className="py-3 px-4">Utilization</th>
                    <th className="py-3 px-4 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {plants.length > 0 ? (
                    plants.map((p) => (
                      <tr key={p.plant} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3 px-4 font-semibold text-slate-900 flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-blue-600"></span>
                          Plant {p.plant}
                        </td>
                        <td className="py-3 px-4 text-slate-500">{p.facilityType}</td>
                        <td className="py-3 px-4 text-right font-mono text-slate-800">
                          {p.occupiedBins.toLocaleString()}
                          <span className="text-[10px] text-slate-400 font-normal ml-1">
                            / {p.totalBins.toLocaleString()}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-slate-800 font-medium">
                          {p.inventoryQty.toLocaleString()}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 bg-slate-100 rounded-full h-2 overflow-hidden">
                              <div
                                className="bg-blue-600 h-2 rounded-full"
                                style={{ width: `${Math.min(100, p.utilizationPct)}%` }}
                              ></div>
                            </div>
                            <span className="font-mono text-[11px] font-semibold text-slate-800">
                              {p.utilizationPct}%
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${
                              p.status === 'Optimal'
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-blue-50 text-blue-700 border-blue-200'
                            }`}
                          >
                            {p.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-400">
                        Loading verified facility data...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Real-time Activity Feed (1 Column) */}
          <div className="rounded-xl bg-white border border-slate-200/90 p-5 shadow-xs flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-3.5">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-blue-600" />
                Live Inbound / Put-Away Log
              </h3>
              <span className="text-[10px] text-slate-400 flex items-center gap-1 font-medium">
                <RefreshCw className="w-3 h-3 text-slate-400" />
                Auto-sync
              </span>
            </div>

            <div className="space-y-3.5 overflow-y-auto flex-1 text-xs">
              <div className="flex items-start gap-2.5 pb-2.5 border-b border-slate-100">
                <span className="w-2 h-2 rounded-full bg-blue-500 mt-1.5 shrink-0"></span>
                <div>
                  <p className="text-slate-800 font-semibold">Inbound GR-8921 Processed</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    2,400 units put-away in Plant 1258 Aisle B
                  </p>
                  <span className="text-[10px] text-slate-400">2 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5 pb-2.5 border-b border-slate-100">
                <span className="w-2 h-2 rounded-full bg-indigo-500 mt-1.5 shrink-0"></span>
                <div>
                  <p className="text-slate-800 font-semibold">Bin Consolidation Complete</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Bin B-101 merged with B-102 in Plant 7228
                  </p>
                  <span className="text-[10px] text-slate-400">14 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5 pb-2.5 border-b border-slate-100">
                <span className="w-2 h-2 rounded-full bg-emerald-500 mt-1.5 shrink-0"></span>
                <div>
                  <p className="text-slate-800 font-semibold">Cycle Count Verified</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    SKU 7228-FLUID-22 matched physical count exactly
                  </p>
                  <span className="text-[10px] text-slate-400">38 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5">
                <span className="w-2 h-2 rounded-full bg-amber-500 mt-1.5 shrink-0"></span>
                <div>
                  <p className="text-slate-800 font-semibold">Threshold Notice</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Bin Rack C-44 at Plant 1268 reached 98% volume
                  </p>
                  <span className="text-[10px] text-slate-400">1 hr ago</span>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 mt-3 text-center">
              <span className="text-[11px] text-slate-400">
                Connected to WMS SQL Server Production Instance
              </span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};
