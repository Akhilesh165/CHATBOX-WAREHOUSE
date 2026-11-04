'use client';

import React, { useState } from 'react';
import { ChatbotLauncher } from './ChatbotLauncher';
import { ChatPanel } from './ChatPanel';
import { ChatWidgetMessage } from './ChatMessages';

interface ChatbotWidgetProps {
  isOpen?: boolean;
  onToggleOpen?: (open: boolean) => void;
}

const INITIAL_MESSAGES: ChatWidgetMessage[] = [
  {
    id: 'welcome-1',
    sender: 'assistant',
    content: 'Hello! 👋 Welcome to Warehouse Assistant. How can I help you today?',
  },
  {
    id: 'welcome-2',
    sender: 'assistant',
    content: 'You can ask about inventory, bin utilization, plant comparisons, or warehouse capacity.',
    showChips: true,
    showSnapshot: true,
  },
];

export const ChatbotWidget: React.FC<ChatbotWidgetProps> = ({
  isOpen: controlledIsOpen,
  onToggleOpen,
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatWidgetMessage[]>(INITIAL_MESSAGES);
  const [isLoading, setIsLoading] = useState(false);

  const isControlled = controlledIsOpen !== undefined;
  const isOpen = isControlled ? controlledIsOpen : internalIsOpen;

  const setIsOpen = (nextOpen: boolean) => {
    if (onToggleOpen) {
      onToggleOpen(nextOpen);
    }
    if (!isControlled) {
      setInternalIsOpen(nextOpen);
    }
  };

  const handleReset = () => {
    setMessages(INITIAL_MESSAGES);
  };

  const handleSendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    const userMessage: ChatWidgetMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // Connect to the real live warehouse backend API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: 'widget-main',
          is_admin: false,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      const rows = data.data || data.rows || [];

      const botMessage: ChatWidgetMessage = {
        id: `bot-${Date.now()}`,
        sender: 'assistant',
        content: data.answer || 'Information retrieved successfully.',
        rows: rows,
        sql: data.sql,
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err: any) {
      const errorMessage: ChatWidgetMessage = {
        id: `bot-err-${Date.now()}`,
        sender: 'assistant',
        content: `⚠️ ${err.message || 'Unable to connect to warehouse database. Please check your query or server connection.'}`,
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* 1. Clickable circular chatbot logo #launcher */}
      <ChatbotLauncher onClick={() => setIsOpen(true)} isOpen={isOpen} />

      {/* 2. Dark navy right-side chat panel #panel */}
      <ChatPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        messages={messages}
        onSendMessage={handleSendMessage}
        onReset={handleReset}
        isLoading={isLoading}
      />
    </>
  );
};
