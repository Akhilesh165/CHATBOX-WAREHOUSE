'use client';

import React from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  Database,
  ShieldCheck,
  TableProperties,
  ChevronLeft,
  Boxes,
  Sun,
  Moon
} from 'lucide-react';

export interface Session {
  id: string;
  title: string;
  timestamp: Date;
  messageCount: number;
}

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  sessions: Session[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  isAdmin: boolean;
  onToggleAdmin: () => void;
  onOpenSchema: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  isAdmin,
  onToggleAdmin,
  onOpenSchema,
  isDarkMode,
  onToggleTheme
}) => {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 z-30 md:hidden backdrop-blur-xs"
          onClick={onToggle}
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`fixed md:static inset-y-0 left-0 z-40 flex flex-col bg-slate-900 dark:bg-slate-950 text-slate-200 border-r border-slate-800 dark:border-slate-800/80 transition-all duration-250 ease-in-out ${
          isOpen ? 'w-72 translate-x-0' : 'w-0 -translate-x-full md:w-0 md:translate-x-0'
        } overflow-hidden flex-shrink-0 select-none`}
      >
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold shadow-md shadow-sky-600/30 flex-shrink-0">
              <Boxes className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-white tracking-wide truncate">
                WAREHOUSE AI
              </div>
              <div className="text-[10px] text-slate-400 truncate flex items-center space-x-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>SQL Server Live</span>
              </div>
            </div>
          </div>

          <button
            onClick={onToggle}
            className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition md:flex hidden"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        {/* New Chat Action */}
        <div className="p-3">
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-slate-800/90 dark:bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium border border-slate-700/60 dark:border-slate-800 hover:border-slate-600 transition shadow-xs group"
          >
            <div className="flex items-center space-x-2">
              <Plus className="w-4 h-4 text-sky-400 group-hover:rotate-90 transition-transform duration-200" />
              <span>New Warehouse Query</span>
            </div>
            <span className="text-[10px] bg-slate-900/60 dark:bg-slate-950 text-slate-400 px-1.5 py-0.5 rounded border border-slate-750 font-mono">
              Ctrl+K
            </span>
          </button>
        </div>

        {/* Conversation History */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
          <div className="px-2 py-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Recent Queries
          </div>

          {sessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-slate-400">
              No recent conversations
            </div>
          ) : (
            sessions.map((sess) => {
              const isActive = sess.id === activeSessionId;
              return (
                <div
                  key={sess.id}
                  onClick={() => onSelectSession(sess.id)}
                  className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition ${
                    isActive
                      ? 'bg-slate-800 dark:bg-slate-850 text-white font-medium border border-slate-700/70 dark:border-slate-750 shadow-xs'
                      : 'text-slate-300 hover:bg-slate-800/50 hover:text-white'
                  }`}
                >
                  <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                    <MessageSquare
                      className={`w-3.5 h-3.5 flex-shrink-0 ${
                        isActive ? 'text-sky-400' : 'text-slate-400 group-hover:text-slate-300'
                      }`}
                    />
                    <span className="truncate">{sess.title || 'Untitled Query'}</span>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(sess.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-400 hover:bg-slate-700/60 rounded transition"
                    title="Delete Conversation"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Operational Controls & Footer */}
        <div className="p-3 border-t border-slate-800/80 space-y-1 bg-slate-950/40 dark:bg-slate-950/80">
          {/* Theme Toggle in Sidebar */}
          <button
            onClick={onToggleTheme}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800/70 hover:text-white transition"
          >
            <div className="flex items-center space-x-2.5">
              {isDarkMode ? (
                <Sun className="w-4 h-4 text-amber-400" />
              ) : (
                <Moon className="w-4 h-4 text-sky-400" />
              )}
              <span>{isDarkMode ? 'Light Contrast Mode' : 'Dark Contrast Mode'}</span>
            </div>
            <span className="text-[10px] bg-slate-800 dark:bg-slate-900 px-1.5 py-0.5 rounded text-slate-400">
              {isDarkMode ? 'Dark' : 'Light'}
            </span>
          </button>

          {/* Schema Explorer */}
          <button
            onClick={onOpenSchema}
            className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800/70 hover:text-white transition"
          >
            <TableProperties className="w-4 h-4 text-sky-400" />
            <span>Schema Reference</span>
          </button>

          {/* Admin SQL Toggle */}
          <button
            onClick={onToggleAdmin}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition ${
              isAdmin
                ? 'bg-purple-950/60 text-purple-200 border border-purple-800/60'
                : 'text-slate-300 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <ShieldCheck className={`w-4 h-4 ${isAdmin ? 'text-purple-400' : 'text-slate-400'}`} />
              <span>Admin SQL Mode</span>
            </div>
            <span
              className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                isAdmin ? 'bg-purple-600 text-white' : 'bg-slate-800 text-slate-400'
              }`}
            >
              {isAdmin ? 'ON' : 'OFF'}
            </span>
          </button>

          {/* Connection Status Badge */}
          <div className="pt-2 px-3 pb-1 flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center space-x-1.5">
              <Database className="w-3 h-3 text-emerald-400" />
              <span>dbo.ZWMS_INVENTORY</span>
            </span>
            <span className="font-mono text-[10px] text-slate-400">v1.0</span>
          </div>
        </div>
      </aside>
    </>
  );
};
