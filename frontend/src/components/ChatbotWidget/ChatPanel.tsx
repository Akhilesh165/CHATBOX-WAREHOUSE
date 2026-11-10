'use client';

import React, { useEffect } from 'react';
import { ChatMessage } from '../../types/chat';
import { WarehouseStatsResponse } from '../../types/dashboard';
import { ChatHeader } from './ChatHeader';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  onSendMessage: (query: string) => void;
  onReset: () => void;
  isLoading?: boolean;
  stats?: WarehouseStatsResponse | null;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  isOpen,
  onClose,
  messages,
  onSendMessage,
  onReset,
  isLoading = false,
  stats,
}) => {
  // Listen for Escape key to close panel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <>
      {/* Backdrop overlay on mobile & tablet */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/30 backdrop-blur-2xs z-40 sm:hidden transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Slide-in Right-Side Panel (Clean Enterprise Light Theme) */}
      <aside
        id="panel"
        role="dialog"
        aria-label="Warehouse Assistant"
        aria-modal="true"
        className={`fixed right-0 top-0 h-[100dvh] w-full sm:w-[440px] md:w-[460px] lg:w-[470px] bg-white border-l border-slate-200/90 shadow-[-10px_0_30px_rgba(15,23,42,0.08)] flex flex-col z-50 transition-all duration-[320ms] ease-out ${
          isOpen
            ? 'translate-x-0 visible opacity-100 open'
            : 'translate-x-[105%] invisible opacity-0 pointer-events-none'
        }`}
      >
        {/* Compact Header */}
        <ChatHeader onClose={onClose} onReset={onReset} />

        {/* Scrollable Conversation Stream */}
        <ChatMessages
          messages={messages}
          isLoading={isLoading}
          onSelectPrompt={(prompt) => onSendMessage(prompt)}
          stats={stats}
        />

        {/* Modern Clean Input Composer */}
        <ChatInput onSendMessage={onSendMessage} isLoading={isLoading} />
      </aside>
    </>
  );
};
