'use client';

import React from 'react';
import { RotateCcw, X } from 'lucide-react';

interface ChatHeaderProps {
  onClose: () => void;
  onReset?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ onClose, onReset }) => {
  return (
    <header className="h-16 flex-none border-b border-slate-200/90 bg-white flex items-center px-4 gap-3 select-none">
      {/* ✦ Avatar */}
      <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 border border-blue-200/70 grid place-items-center text-sm font-bold flex-shrink-0">
        ✦
      </div>

      {/* Title & Online Status */}
      <div className="flex-1 min-w-0">
        <strong className="block text-sm font-bold text-slate-900 leading-tight">
          Warehouse Assistant
        </strong>
        <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block shrink-0" />
          <span>Online · Enterprise AI</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1">
        {onReset && (
          <button
            onClick={onReset}
            title="Reset conversation"
            aria-label="Reset conversation"
            className="w-8 h-8 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 grid place-items-center transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        )}

        {/* Close Button */}
        <button
          id="close"
          onClick={onClose}
          aria-label="Close chat"
          title="Close chat"
          className="border-0 bg-transparent text-slate-400 hover:text-slate-800 text-xl cursor-pointer rounded-lg w-8 h-8 grid place-items-center hover:bg-slate-100 transition-colors leading-none"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
};
