import React from 'react';
import { Database, Sparkles } from 'lucide-react';

export const LoadingIndicator: React.FC = () => {
  return (
    <div className="flex items-start space-x-3 p-4 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm max-w-xl animate-pulse transition-colors">
      <div className="w-9 h-9 rounded-xl bg-sky-500/10 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 flex items-center justify-center flex-shrink-0">
        <Sparkles className="w-5 h-5 animate-spin" />
      </div>
      <div className="space-y-2 flex-1">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
          <Database className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
          <span>Generating query & querying SQL Server...</span>
        </div>
        <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-3/4"></div>
        <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-1/2"></div>
      </div>
    </div>
  );
};
