'use client';

import React from 'react';
import { User } from 'lucide-react';

interface UserMessageProps {
  content: string;
  timestamp?: string;
}

export const UserMessage: React.FC<UserMessageProps> = ({ content, timestamp }) => {
  return (
    <div className="flex items-start justify-end gap-2.5 max-w-full pl-6">
      <div className="flex flex-col items-end">
        <div className="px-4 py-2.5 rounded-2xl rounded-tr-sm bg-gradient-to-r from-sky-600 to-sky-700 text-white text-xs sm:text-[13px] leading-relaxed shadow-md shadow-sky-950/40 border border-sky-400/20 max-w-full break-words">
          {content}
        </div>
        {timestamp && (
          <span className="text-[10px] text-slate-400 mt-1 mr-1">
            {timestamp}
          </span>
        )}
      </div>

      <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700/80 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
        <User className="w-3.5 h-3.5" />
      </div>
    </div>
  );
};
