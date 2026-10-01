'use client';

import React from 'react';
import { PanelLeft, Database, ShieldCheck, Trash2, TableProperties, Sparkles } from 'lucide-react';

interface ChatHeaderProps {
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  title?: string;
  isAdmin: boolean;
  onToggleAdmin: () => void;
  onClearChat: () => void;
  onOpenSchema: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  isSidebarOpen,
  onToggleSidebar,
  title,
  isAdmin,
  onToggleAdmin,
  onClearChat,
  onOpenSchema
}) => {
  return (
    <header className="h-14 bg-white/95 backdrop-blur border-b border-slate-200/80 px-4 flex items-center justify-between shadow-2xs flex-shrink-0 z-20">
      {/* Left: Sidebar Toggle & Model Info */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition"
          title={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <PanelLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-100/90 rounded-lg text-xs font-semibold text-slate-700 border border-slate-200/60">
            <Sparkles className="w-3.5 h-3.5 text-sky-600" />
            <span>Warehouse AI Engine</span>
          </div>

          <span className="text-xs text-slate-300">|</span>

          <span className="text-xs text-slate-500 font-medium truncate max-w-[200px] md:max-w-md">
            {title || 'Current Session'}
          </span>
        </div>
      </div>

      {/* Right: Quick actions */}
      <div className="flex items-center space-x-1.5">
        <button
          onClick={onOpenSchema}
          className="hidden sm:flex items-center space-x-1 px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition"
          title="Schema Reference"
        >
          <TableProperties className="w-3.5 h-3.5 text-sky-600" />
          <span>Schema</span>
        </button>

        <button
          onClick={onToggleAdmin}
          className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
            isAdmin
              ? 'bg-purple-50 text-purple-700 border-purple-300'
              : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
          }`}
          title="Toggle Admin SQL Debug Mode"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Admin SQL:</span>
          <span>{isAdmin ? 'ON' : 'OFF'}</span>
        </button>

        <button
          onClick={onClearChat}
          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
          title="Clear Conversation"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
