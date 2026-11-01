'use client';

import React from 'react';
import { Bot, X, RotateCcw } from 'lucide-react';

interface ChatHeaderProps {
  onClose: () => void;
  onReset: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ onClose, onReset }) => {
  return (
    <div className="flex items-center justify-between px-5 py-4 bg-slate-900/95 border-b border-slate-800/80 backdrop-blur-md select-none shrink-0">
      {/* Left branding */}
      <div className="flex items-center gap-3">
        <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500/20 to-cyan-500/10 border border-sky-500/30 text-sky-400 shadow-inner">
          <Bot className="w-5 h-5" />
          <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 border border-slate-900"></span>
          </span>
        </div>

        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-sm text-slate-100 tracking-tight">
              Warehouse Assistant
            </h3>
            <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-sky-500/15 text-sky-400 border border-sky-500/20 rounded">
              AI
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span className="text-[11px] font-medium text-emerald-400">Online</span>
            <span className="text-slate-600">•</span>
            <span className="text-[11px] text-slate-400">Inventory & Bins</span>
          </div>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-1 text-slate-400">
        <button
          onClick={onReset}
          title="Reset sample conversation"
          className="p-1.5 rounded-lg hover:text-slate-200 hover:bg-slate-800/80 transition-colors focus:outline-none focus:ring-1 focus:ring-slate-700"
          aria-label="Reset Conversation"
        >
          <RotateCcw className="w-4 h-4" />
        </button>

        <button
          onClick={onClose}
          title="Close Warehouse Assistant"
          className="p-1.5 rounded-lg hover:text-rose-400 hover:bg-rose-500/10 transition-colors focus:outline-none focus:ring-1 focus:ring-rose-500/30 ml-1"
          aria-label="Close Assistant"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
};
