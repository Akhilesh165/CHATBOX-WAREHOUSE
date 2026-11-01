'use client';

import React from 'react';
import { Bot, Sparkles } from 'lucide-react';

interface ChatbotLauncherProps {
  onClick: () => void;
  isOpen: boolean;
}

export const ChatbotLauncher: React.FC<ChatbotLauncherProps> = ({ onClick, isOpen }) => {
  if (isOpen) return null;

  return (
    <div className="fixed bottom-6 right-6 z-40 animate-fade-in">
      <button
        onClick={onClick}
        aria-label="Open Warehouse Assistant"
        className="group relative flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-slate-900 via-slate-850 to-slate-900 hover:from-slate-850 hover:to-slate-800 text-white rounded-full border border-sky-500/40 hover:border-sky-400 shadow-2xl shadow-sky-950/60 hover:shadow-sky-500/20 backdrop-blur-md transition-all duration-300 hover:scale-[1.03] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-sky-500/50"
      >
        {/* Glowing ring behind the icon */}
        <div className="relative flex items-center justify-center w-9 h-9 rounded-full bg-gradient-to-tr from-sky-600 to-cyan-400 text-white shadow-md shadow-sky-500/30 group-hover:shadow-sky-400/50 transition-all duration-300">
          <Bot className="w-5 h-5 transition-transform duration-300 group-hover:rotate-6" />
          
          {/* Active online green pulse badge */}
          <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500 border-2 border-slate-950"></span>
          </span>
        </div>

        {/* Button Label */}
        <div className="flex flex-col text-left">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-sm tracking-wide text-slate-100 group-hover:text-white transition-colors">
              Warehouse Assistant
            </span>
            <Sparkles className="w-3.5 h-3.5 text-sky-400 opacity-80 group-hover:opacity-100 transition-opacity" />
          </div>
          <span className="text-[11px] font-medium text-slate-400 group-hover:text-slate-300 flex items-center gap-1 transition-colors">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            Online • Ask inventory & bins
          </span>
        </div>
      </button>
    </div>
  );
};
