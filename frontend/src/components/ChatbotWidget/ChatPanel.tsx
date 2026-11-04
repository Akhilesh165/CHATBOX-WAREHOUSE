'use client';

import React, { useEffect } from 'react';
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
  // Listen for Escape key to close panel (matching user JS specification)
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
      {/* Optional backdrop on mobile view */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-xs z-40 sm:hidden transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Right-Side Chat Panel matching #panel */}
      <aside
        id="panel"
        role="dialog"
        aria-label="Warehouse Assistant"
        aria-modal="true"
        className={`fixed right-0 top-0 h-[100dvh] w-[min(430px,100vw)] bg-[#071a33] border-l border-[#1b3556] shadow-[-12px_0_36px_#02081766] flex flex-col z-50 transition-all duration-[320ms] ease-out ${
          isOpen
            ? 'translate-x-0 visible opacity-100 open'
            : 'translate-x-[105%] invisible opacity-0 pointer-events-none'
        }`}
      >
        <ChatHeader onClose={onClose} onReset={onReset} />

        <ChatMessages
          messages={messages}
          isLoading={isLoading}
          onSelectChip={(query) => onSendMessage(query)}
        />

        <ChatInput onSendMessage={onSendMessage} isLoading={isLoading} />
      </aside>
    </>
  );
};
