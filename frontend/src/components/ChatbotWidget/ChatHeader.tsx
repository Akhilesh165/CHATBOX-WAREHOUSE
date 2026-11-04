'use client';

import React from 'react';
import { RotateCcw } from 'lucide-react';

interface ChatHeaderProps {
  onClose: () => void;
  onReset?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ onClose, onReset }) => {
  return (
    <header className="h-[76px] flex-none border-b border-[#1b3556] bg-[#071a33] flex items-center px-[18px] gap-3 text-[#f8fbff] select-none">
      {/* ✦ Avatar */}
      <div className="w-[42px] h-[42px] rounded-[13px] bg-[#102b4d] text-[#7dd3fc] grid place-items-center text-[22px] flex-shrink-0 font-medium">
        ✦
      </div>

      {/* Title & Online Status */}
      <div className="flex-1 min-w-0">
        <strong className="block text-[15px] font-bold text-[#f8fbff] leading-snug">
          Warehouse Assistant
        </strong>
        <div className="text-[12px] text-[#9fb3cc] mt-0.5 flex items-center">
          <span className="inline-block w-[7px] h-[7px] bg-[#22c55e] rounded-full mr-[6px] shrink-0" />
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
            className="w-[34px] h-[34px] rounded-[9px] text-[#a9bbd0] hover:text-white hover:bg-[#102b4d] grid place-items-center transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        )}

        {/* Close Button matching #close */}
        <button
          id="close"
          onClick={onClose}
          aria-label="Close chat"
          title="Close chat"
          className="border-0 bg-transparent text-[#a9bbd0] hover:text-white text-[26px] cursor-pointer rounded-[9px] w-[36px] h-[36px] grid place-items-center hover:bg-[#102b4d] transition-colors leading-none"
        >
          ×
        </button>
      </div>
    </header>
  );
};
