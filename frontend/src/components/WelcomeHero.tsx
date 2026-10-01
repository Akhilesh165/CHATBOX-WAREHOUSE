'use client';

import React from 'react';
import {
  Boxes,
  TrendingUp,
  Layers,
  Building2,
  PackageSearch,
  Sparkles,
  ArrowRight,
  ShieldAlert
} from 'lucide-react';

interface WelcomeHeroProps {
  onSelectPrompt: (prompt: string) => void;
}

const CAPABILITY_CARDS = [
  {
    title: 'Bin Utilization & Capacity',
    desc: 'Calculate overall volume utilization % and bin occupancy across plants',
    prompt: 'What is the overall warehouse bin utilization percentage right now, based on total occupied volume versus total bin capacity?',
    icon: TrendingUp,
    color: 'from-sky-500/10 to-blue-500/10 text-sky-600 border-sky-200/60'
  },
  {
    title: 'Empty Bins for Put-Away',
    desc: 'List unoccupied storage bins with volume and pallet specifications',
    prompt: 'Show me empty bins available for immediate put-away',
    icon: PackageSearch,
    color: 'from-emerald-500/10 to-teal-500/10 text-emerald-600 border-emerald-200/60'
  },
  {
    title: 'Bin Consolidation Moves',
    desc: 'Identify items stored across multiple bins to free up valuable warehouse slots',
    prompt: 'Which materials are stored across multiple bins and can be consolidated?',
    icon: Boxes,
    color: 'from-amber-500/10 to-orange-500/10 text-amber-600 border-amber-200/60'
  },
  {
    title: 'ZWMS vs ZWS Discrepancies',
    desc: 'Highlight materials with the highest stock quantity differences',
    prompt: 'Find materials with highest quantity difference between ZWMS and ZWS',
    icon: Layers,
    color: 'from-rose-500/10 to-red-500/10 text-rose-600 border-rose-200/60'
  },
  {
    title: 'Plant & Location Breakdown',
    desc: 'Compare material counts and quantities across plants and storage locations',
    prompt: 'Show inventory breakdown by plant',
    icon: Building2,
    color: 'from-purple-500/10 to-indigo-500/10 text-purple-600 border-purple-200/60'
  },
  {
    title: 'Top Stock Rankings',
    desc: 'Rank materials by stock level with automatic bar chart visualizations',
    prompt: 'Show top 10 materials by unrestricted quantity',
    icon: TrendingUp,
    color: 'from-indigo-500/10 to-cyan-500/10 text-indigo-600 border-indigo-200/60'
  }
];

export const WelcomeHero: React.FC<WelcomeHeroProps> = ({ onSelectPrompt }) => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 max-w-3xl mx-auto text-center animate-in fade-in zoom-in-95 duration-200">
      {/* Brand Icon */}
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-sky-600 to-sky-400 text-white flex items-center justify-center shadow-lg shadow-sky-500/25 mb-4">
        <Boxes className="w-7 h-7" />
      </div>

      <h2 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
        Warehouse Inventory AI
      </h2>
      <p className="text-xs md:text-sm text-slate-500 max-w-lg mt-1.5 leading-relaxed">
        Query real-time warehouse inventory, bin locations, batches, plants, and material master attributes in natural language.
      </p>

      {/* Grid of Capability Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full mt-8 text-left">
        {CAPABILITY_CARDS.map((card, idx) => {
          const Icon = card.icon;
          return (
            <button
              key={idx}
              onClick={() => onSelectPrompt(card.prompt)}
              className="p-4 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200/80 hover:border-sky-300 shadow-xs hover:shadow-md transition-all duration-150 group flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center space-x-2.5 mb-2">
                  <div className={`p-2 rounded-xl bg-gradient-to-br ${card.color} border flex items-center justify-center`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <h3 className="text-xs font-bold text-slate-800 group-hover:text-sky-600 transition">
                    {card.title}
                  </h3>
                </div>
                <p className="text-[11px] text-slate-500 leading-normal">
                  {card.desc}
                </p>
              </div>

              <div className="mt-3.5 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] text-sky-600 font-medium">
                <span className="truncate pr-2">"{card.prompt}"</span>
                <ArrowRight className="w-3.5 h-3.5 flex-shrink-0 group-hover:translate-x-1 transition-transform" />
              </div>
            </button>
          );
        })}
      </div>

      {/* Security note */}
      <div className="mt-8 inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200/80 text-[11px] text-slate-500">
        <ShieldAlert className="w-3.5 h-3.5 text-emerald-600" />
        <span>Grounded on Authoritative SQL Server • SQLGlot AST Safety Verified</span>
      </div>
    </div>
  );
};
