'use client';

import React from 'react';
import { PanelLeft, Database, ShieldCheck, Trash2, TableProperties, Sparkles, Sun, Moon } from 'lucide-react';

interface ChatHeaderProps {
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  title?: string;
  isAdmin: boolean;
  onToggleAdmin: () => void;
  onClearChat: () => void;
  onOpenSchema: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  isSidebarOpen,
  onToggleSidebar,
  title,
  isAdmin,
  onToggleAdmin,
  onClearChat,
  onOpenSchema,
  isDarkMode,
  onToggleTheme
}) => {
  return (
    <header className="h-14 bg-white/95 dark:bg-slate-900/95 backdrop-blur border-b border-slate-200/80 dark:border-slate-800 px-4 flex items-center justify-between shadow-2xs flex-shrink-0 z-20 transition-colors">
      {/* Left: Sidebar Toggle & Model Info */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          title={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <PanelLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-100/90 dark:bg-slate-800 rounded-lg text-xs font-semibold text-slate-700 dark:text-slate-200 border border-slate-200/60 dark:border-slate-700/60">
            <Sparkles className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
            <span>Warehouse AI Engine</span>
          </div>

          <span className="text-xs text-slate-300 dark:text-slate-700">|</span>

          <span className="text-xs text-slate-500 dark:text-slate-400 font-medium truncate max-w-[150px] md:max-w-md">
            {title || 'Current Session'}
          </span>
        </div>
      </div>

      {/* Right: Quick actions */}
      <div className="flex items-center space-x-1.5">
        {/* Dark / Light Contrast Mode Toggle */}
        <button
          onClick={onToggleTheme}
          className="flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 transition"
          title={isDarkMode ? 'Switch to Light Contrast Mode' : 'Switch to Dark Contrast Mode'}
        >
          {isDarkMode ? (
            <>
              <Sun className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline">Light Mode</span>
            </>
          ) : (
            <>
              <Moon className="w-3.5 h-3.5 text-sky-600" />
              <span className="hidden sm:inline">Dark Mode</span>
            </>
          )}
        </button>

        <button
          onClick={onOpenSchema}
          className="hidden sm:flex items-center space-x-1 px-2.5 py-1 text-xs text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition"
          title="Schema Reference"
        >
          <TableProperties className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
          <span>Schema</span>
        </button>

        <button
          onClick={onToggleAdmin}
          className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
            isAdmin
              ? 'bg-purple-50 dark:bg-purple-950/80 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700'
              : 'bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
          }`}
          title="Toggle Admin SQL Debug Mode"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Admin SQL:</span>
          <span>{isAdmin ? 'ON' : 'OFF'}</span>
        </button>

        <button
          onClick={onClearChat}
          className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition"
          title="Clear Conversation"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
