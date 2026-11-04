'use client';

import React from 'react';
import { Bot } from 'lucide-react';

interface ChatbotLauncherProps {
  onClick: () => void;
  isOpen: boolean;
}

export const ChatbotLauncher: React.FC<ChatbotLauncherProps> = ({ onClick, isOpen }) => {
  if (isOpen) return null;

  return (
    <button
      id="launcher"
      onClick={onClick}
      aria-label="Open chat"
      title="Open Warehouse Assistant"
      className="fixed right-[26px] bottom-[26px] w-16 h-16 rounded-full bg-[#2563eb] hover:bg-[#1d4ed8] text-white border-0 shadow-[0_8px_26px_#2563eb55] cursor-pointer flex items-center justify-center transition-all duration-200 hover:-translate-y-1 hover:scale-[1.04] active:scale-95 z-50 focus:outline-none focus:ring-4 focus:ring-blue-500/30"
    >
      <Bot className="w-7 h-7 text-white stroke-[2.2]" />
    </button>
  );
};
