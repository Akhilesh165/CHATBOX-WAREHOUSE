'use client';

import React from 'react';
import { ChatHeader } from './ChatHeader';
import { ChatMessages, ChatWidgetMessage } from './ChatMessages';
import { ChatInput } from './ChatInput';

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  messages: ChatWidgetMessage[];
  onSendMessage: (query: string) => void;
  onReset: () => void;
  isLoading?: boolean;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  isOpen,
  onClose,
  messages,
  onSendMessage,
  onReset,
  isLoading = false,
}) => {
  return (
    <>
      {/* Mobile backdrop overlay: click outside to dismiss on mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 sm:hidden transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Slide-in Right Panel */}
      <aside
        className={`fixed top-0 right-0 h-screen w-full sm:w-[460px] md:w-[480px] z-50 bg-slate-950/95 backdrop-blur-xl border-l border-slate-800/90 shadow-2xl shadow-black/80 flex flex-col transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'
        }`}
        aria-label="Warehouse Assistant Chatbot"
        role="dialog"
        aria-modal="true"
      >
        {/* Top Header */}
        <ChatHeader onClose={onClose} onReset={onReset} />

        {/* Scrollable Conversation Content */}
        <ChatMessages messages={messages} isLoading={isLoading} />

        {/* Fixed Bottom Input Area */}
        <ChatInput onSendMessage={onSendMessage} isLoading={isLoading} />
      </aside>
    </>
  );
};
