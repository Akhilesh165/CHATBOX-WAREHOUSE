'use client';

import React from 'react';
import {
  Boxes,
  Layers,
  TrendingUp,
  Activity,
  Warehouse,
  CheckCircle2,
  AlertCircle,
  Clock,
  Search,
  SlidersHorizontal,
  ArrowUpRight,
  ShieldCheck,
} from 'lucide-react';

interface DashboardBackgroundProps {
  onOpenChatbot?: () => void;
  isChatOpen?: boolean;
}

export const DashboardBackground: React.FC<DashboardBackgroundProps> = ({
  onOpenChatbot,
  isChatOpen = false,
}) => {
  return (
    <div
      className={`min-h-screen bg-slate-950 text-slate-100 transition-all duration-300 ${
        isChatOpen ? 'lg:mr-[430px]' : ''
      }`}
    >
      {/* Top Navigation */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-sky-950/50">
              <Warehouse className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-white">
                  WarehouseOS
                </span>
                <span className="text-[10px] uppercase font-mono font-bold tracking-widest bg-sky-500/10 text-sky-400 border border-sky-500/20 px-1.5 py-0.5 rounded">
                  Live
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                Multi-Facility Inventory & Bin Operations Console
              </p>
            </div>
          </div>

          {/* Quick Search */}
          <div className="hidden md:flex items-center flex-1 max-w-md mx-6">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search SKUs, Bins, Plants, or Work Orders..."
                className="w-full bg-slate-950/70 border border-slate-800 rounded-lg pl-9 pr-4 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50"
              />
            </div>
          </div>

          {/* Right Header Status & Chat Opener */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              All 5 Plants Synchronized
            </div>

            {!isChatOpen && (
              <button
                onClick={onOpenChatbot}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-sky-600/20 border border-sky-500/40 text-sky-300 hover:bg-sky-600/30 text-xs font-medium transition-all"
              >
                <span>Ask Copilot</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Dashboard Workspace */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Banner Alert */}
        <div className="p-4 rounded-xl bg-gradient-to-r from-sky-950/40 via-indigo-950/30 to-slate-900 border border-sky-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg shadow-sky-950/20">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-sky-500/20 text-sky-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-100">
                Interactive Assistant UI Prototype
              </h2>
              <p className="text-xs text-slate-400">
                The chatbot operates from the bottom-right launcher and slides open seamlessly without interrupting warehouse workflows.
              </p>
            </div>
          </div>
          <button
            onClick={onOpenChatbot}
            className="self-start sm:self-center text-xs px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-medium transition-all shadow-md shrink-0"
          >
            {isChatOpen ? 'Chat Panel Open ↗' : 'Open Assistant →'}
          </button>
        </div>

        {/* 4 Top KPI Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* KPI 1 */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-all shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">
                Total Inventory
              </span>
              <Boxes className="w-4 h-4 text-sky-400" />
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              1,933,031
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-[11px] text-emerald-400">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>+4.2% from previous cycle</span>
            </div>
          </div>

          {/* KPI 2 */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-all shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">
                Bin Occupancy
              </span>
              <Layers className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              7,525 <span className="text-sm text-slate-400 font-normal">/ 8,940</span>
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-[11px] text-sky-400">
              <Activity className="w-3.5 h-3.5" />
              <span>84.17% overall utilization</span>
            </div>
          </div>

          {/* KPI 3 */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-all shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">
                Active Materials
              </span>
              <Warehouse className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              974 <span className="text-sm text-slate-400 font-normal">SKUs</span>
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-[11px] text-amber-400">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>12 SKUs nearing safety threshold</span>
            </div>
          </div>

          {/* KPI 4 */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-all shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">
                Put-Away Throughput
              </span>
              <CheckCircle2 className="w-4 h-4 text-teal-400" />
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              38,420
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-[11px] text-slate-400">
              <Clock className="w-3.5 h-3.5" />
              <span>99.2% on-time placement</span>
            </div>
          </div>
        </section>

        {/* Central Operations Section: Plant Table + Activity Feed */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Facility Performance Table (2 Columns) */}
          <div className="lg:col-span-2 rounded-xl bg-slate-900/70 border border-slate-800/90 overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">
                  Facility Utilization Summary
                </h3>
                <p className="text-xs text-slate-400">
                  Real-time bin density and active storage across 5 warehouse plants
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1">
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                  <span>Filter</span>
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/50 text-slate-400 font-medium">
                    <th className="py-2.5 px-4">Plant</th>
                    <th className="py-2.5 px-4">Facility Type</th>
                    <th className="py-2.5 px-4 text-right">Occupied Bins</th>
                    <th className="py-2.5 px-4 text-right">Inventory (Qty)</th>
                    <th className="py-2.5 px-4">Utilization</th>
                    <th className="py-2.5 px-4 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  <tr className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      Plant 1258
                    </td>
                    <td className="py-3 px-4 text-slate-400">North Central Hub</td>
                    <td className="py-3 px-4 text-right font-mono">2,840</td>
                    <td className="py-3 px-4 text-right font-mono">742,100</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-sky-500 h-1.5 rounded-full"
                            style={{ width: '88.5%' }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-sky-400">88.5%</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Optimal
                      </span>
                    </td>
                  </tr>

                  <tr className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      Plant 7228
                    </td>
                    <td className="py-3 px-4 text-slate-400">Eastern Distribution</td>
                    <td className="py-3 px-4 text-right font-mono">1,950</td>
                    <td className="py-3 px-4 text-right font-mono">518,430</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-indigo-500 h-1.5 rounded-full"
                            style={{ width: '76.2%' }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-indigo-400">76.2%</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Optimal
                      </span>
                    </td>
                  </tr>

                  <tr className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      Plant 1268
                    </td>
                    <td className="py-3 px-4 text-slate-400">Southern Terminal</td>
                    <td className="py-3 px-4 text-right font-mono">2,100</td>
                    <td className="py-3 px-4 text-right font-mono">489,200</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-amber-500 h-1.5 rounded-full"
                            style={{ width: '82.4%' }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-amber-400">82.4%</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Optimal
                      </span>
                    </td>
                  </tr>

                  <tr className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-sky-400"></span>
                      Plant 1266
                    </td>
                    <td className="py-3 px-4 text-slate-400">Western Fulfillment</td>
                    <td className="py-3 px-4 text-right font-mono">1,210</td>
                    <td className="py-3 px-4 text-right font-mono">183,301</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-emerald-500 h-1.5 rounded-full"
                            style={{ width: '69.8%' }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-emerald-400">69.8%</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20">
                        Available
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Real-time Activity Feed (1 Column) */}
          <div className="rounded-xl bg-slate-900/70 border border-slate-800/90 p-4 shadow-sm flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <Activity className="w-4 h-4 text-sky-400" />
                Live Inbound / Put-Away Log
              </h3>
              <span className="text-[10px] text-slate-500">Auto-refresh</span>
            </div>

            <div className="space-y-3.5 overflow-y-auto flex-1 text-xs">
              <div className="flex items-start gap-2.5 pb-2 border-b border-slate-800/40">
                <span className="w-2 h-2 rounded-full bg-sky-400 mt-1 shrink-0"></span>
                <div>
                  <p className="text-slate-200 font-medium">Inbound GR-8921 Processed</p>
                  <p className="text-[11px] text-slate-400">
                    2,400 units put-away in Plant 1258 Aisle B
                  </p>
                  <span className="text-[10px] text-slate-500">2 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5 pb-2 border-b border-slate-800/40">
                <span className="w-2 h-2 rounded-full bg-indigo-400 mt-1 shrink-0"></span>
                <div>
                  <p className="text-slate-200 font-medium">Bin Consolidation Complete</p>
                  <p className="text-[11px] text-slate-400">
                    Bin B-101 merged with B-102 in Plant 7228
                  </p>
                  <span className="text-[10px] text-slate-500">14 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5 pb-2 border-b border-slate-800/40">
                <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1 shrink-0"></span>
                <div>
                  <p className="text-slate-200 font-medium">Cycle Count Verified</p>
                  <p className="text-[11px] text-slate-400">
                    SKU 7228-FLUID-22 matched physical count exactly
                  </p>
                  <span className="text-[10px] text-slate-500">38 mins ago</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5">
                <span className="w-2 h-2 rounded-full bg-amber-400 mt-1 shrink-0"></span>
                <div>
                  <p className="text-slate-200 font-medium">Threshold Notice</p>
                  <p className="text-[11px] text-slate-400">
                    Bin Rack C-44 at Plant 1268 reached 98% volume
                  </p>
                  <span className="text-[10px] text-slate-500">1 hr ago</span>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800 mt-3 text-center">
              <span className="text-[11px] text-slate-500">
                Telemetry connected to WMS Event Stream
              </span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};
