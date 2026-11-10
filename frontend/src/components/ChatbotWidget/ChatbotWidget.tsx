'use client';

import React, { useState } from 'react';
import { ChatbotLauncher } from './ChatbotLauncher';
import { ChatPanel } from './ChatPanel';
import { ChatMessage, ChatResponsePayload } from '../../types/chat';
import { WarehouseStatsResponse } from '../../types/dashboard';

interface ChatbotWidgetProps {
  isOpen?: boolean;
  onToggleOpen?: (open: boolean) => void;
  stats?: WarehouseStatsResponse | null;
}

export const ChatbotWidget: React.FC<ChatbotWidgetProps> = ({
  isOpen: controlledIsOpen,
  onToggleOpen,
  stats,
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => `widget-${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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
    setMessages([]);
    setSessionId(`widget-${Date.now()}`);
  };

  const handleSendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    // User message preserving conversation stream
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // Connect to the real live warehouse backend API with conversation session ID
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: sessionId,
          is_admin: false,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const data: ChatResponsePayload = await response.json();
      const rows = data.data || data.rows || [];

      // Preserving all existing response metadata, charts, tables, rankings and KPIs
      const botMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.answer || 'Information retrieved successfully.',
        sql: data.sql,
        rows: rows,
        data: rows,
        tables: data.tables,
        chart: data.chart,
        meta: data.meta,
        rowCount: data.meta?.rowCount ?? data.row_count ?? rows.length,
        total_count: data.meta?.total_count ?? data.total_count,
        displayed_count: data.meta?.displayed_count ?? data.displayed_count ?? rows.length,
        executionMs: data.meta?.executionMs ?? data.execution_ms,
        llmMs: data.meta?.llmMs ?? data.llm_ms,
        sqlMs: data.meta?.sqlMs ?? data.sql_ms,
        warnings: data.warnings,
        intent: data.intent,
        output_type: data.output_type,
        metric: data.metric,
        filters: data.filters,
        time_range: data.time_range,
        follow_up_action: data.follow_up_action,
        relevant_kpis: data.relevant_kpis,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `assistant-err-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${err.message || 'Unable to connect to warehouse database. Please check your query or server connection.'}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* 1. Clickable circular chatbot logo fixed at bottom-right */}
      <ChatbotLauncher onClick={() => setIsOpen(true)} isOpen={isOpen} />

      {/* 2. Slide-in right-side chat panel in clean light theme */}
      <ChatPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        messages={messages}
        onSendMessage={handleSendMessage}
        onReset={handleReset}
        isLoading={isLoading}
        stats={stats}
      />
    </>
  );
};
