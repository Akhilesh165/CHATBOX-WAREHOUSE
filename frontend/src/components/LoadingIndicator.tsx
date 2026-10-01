import React from 'react';
import { Database, Sparkles } from 'lucide-react';

export const LoadingIndicator: React.FC = () => {
  return (
    <div className="flex items-start space-x-3 p-4 bg-white rounded-2xl border border-slate-200 shadow-sm max-w-xl animate-pulse">
      <div className="w-9 h-9 rounded-xl bg-sky-500/10 text-sky-600 flex items-center justify-center flex-shrink-0">
        <Sparkles className="w-5 h-5 animate-spin" />
      </div>
      <div className="space-y-2 flex-1">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-600">
          <Database className="w-3.5 h-3.5 text-sky-600" />
          <span>Generating query & querying SQL Server...</span>
        </div>
        <div className="h-3 bg-slate-200 rounded w-3/4"></div>
        <div className="h-3 bg-slate-200 rounded w-1/2"></div>
      </div>
    </div>
  );
};
