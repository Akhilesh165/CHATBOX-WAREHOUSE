'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage, ChatResponsePayload } from '../types/chat';
import { Sidebar, Session } from './Sidebar';
import { ChatHeader } from './ChatHeader';
import { WelcomeHero } from './WelcomeHero';
import { MessageBubble } from './MessageBubble';
import { LoadingIndicator } from './LoadingIndicator';
import { ErrorBanner } from './ErrorBanner';
import { PromptComposer } from './PromptComposer';
import { SchemaModal } from './SchemaModal';

export const ChatWindow: React.FC = () => {
  // Session management state
  const [sessions, setSessions] = useState<Session[]>([
    {
      id: 'session-main',
      title: 'Current Warehouse Session',
      timestamp: new Date(),
      messageCount: 0,
    },
  ]);
  const [activeSessionId, setActiveSessionId] = useState<string>('session-main');
  const [sessionMessages, setSessionMessages] = useState<Record<string, ChatMessage[]>>({
    'session-main': [],
  });

  // UI state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAdminMode, setIsAdminMode] = useState(false);
  const [isSchemaModalOpen, setIsSchemaModalOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messages = sessionMessages[activeSessionId] || [];

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Keyboard shortcut: Ctrl+K for new chat
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  const handleNewChat = () => {
    const newId = `session-${Date.now()}`;
    const newSession: Session = {
      id: newId,
      title: 'New Query',
      timestamp: new Date(),
      messageCount: 0,
    };
    setSessions((prev) => [newSession, ...prev]);
    setSessionMessages((prev) => ({ ...prev, [newId]: [] }));
    setActiveSessionId(newId);
    setErrorMessage(null);
  };

  const handleDeleteSession = (id: string) => {
    setSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== id);
      if (filtered.length === 0) {
        const resetId = `session-${Date.now()}`;
        setActiveSessionId(resetId);
        setSessionMessages({ [resetId]: [] });
        return [{ id: resetId, title: 'Current Session', timestamp: new Date(), messageCount: 0 }];
      }
      if (activeSessionId === id) {
        setActiveSessionId(filtered[0].id);
      }
      return filtered;
    });

    setSessionMessages((prev) => {
      const copy = { ...prev };
      delete copy[id];
      return copy;
    });
  };

  const handleSendMessage = async (textToSend?: string) => {
    const messageText = (textToSend || input).trim();
    if (!messageText || isLoading) return;

    setErrorMessage(null);
    setInput('');

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };

    // Update active session messages
    setSessionMessages((prev) => ({
      ...prev,
      [activeSessionId]: [...(prev[activeSessionId] || []), userMsg],
    }));

    // Update session title if first query
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === activeSessionId && (s.messageCount === 0 || s.title === 'New Query' || s.title === 'Current Warehouse Session')) {
          return {
            ...s,
            title: messageText.length > 28 ? messageText.slice(0, 28) + '...' : messageText,
            messageCount: s.messageCount + 1,
          };
        }
        return s;
      })
    );

    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          conversation_id: activeSessionId,
          is_admin: isAdminMode,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const data: ChatResponsePayload = await response.json();
      const rows = data.data || data.rows || [];

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.answer,
        sql: data.sql,
        rows: rows,
        data: rows,
        chart: data.chart,
        meta: data.meta,
        rowCount: data.meta?.rowCount ?? data.row_count ?? rows.length,
        executionMs: data.meta?.executionMs ?? data.execution_ms,
        llmMs: data.meta?.llmMs ?? data.llm_ms,
        sqlMs: data.meta?.sqlMs ?? data.sql_ms,
        warnings: data.warnings,
        intent: data.intent,
        output_type: data.output_type,
        metric: data.metric,
        filters: data.filters,
        time_range: data.time_range,
        timestamp: new Date(),
      };

      setSessionMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), assistantMsg],
      }));
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected error occurred.');
    } finally {
      setIsLoading(false);
    }
  };

  const activeTitle = sessions.find((s) => s.id === activeSessionId)?.title;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-100">
      {/* ChatGPT-style Left Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => {
          setActiveSessionId(id);
          setErrorMessage(null);
        }}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        isAdmin={isAdminMode}
        onToggleAdmin={() => setIsAdminMode(!isAdminMode)}
        onOpenSchema={() => setIsSchemaModalOpen(true)}
      />

      {/* Main Chat Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-slate-50/80">
        {/* Minimal Top Header */}
        <ChatHeader
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          title={activeTitle}
          isAdmin={isAdminMode}
          onToggleAdmin={() => setIsAdminMode(!isAdminMode)}
          onClearChat={() => {
            setSessionMessages((prev) => ({ ...prev, [activeSessionId]: [] }));
            setErrorMessage(null);
          }}
          onOpenSchema={() => setIsSchemaModalOpen(true)}
        />

        {/* Message Stream Area */}
        <main className="flex-1 overflow-y-auto px-4 md:px-6">
          {messages.length === 0 ? (
            <WelcomeHero onSelectPrompt={(p) => handleSendMessage(p)} />
          ) : (
            <div className="max-w-3xl mx-auto py-6 space-y-4">
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  conversationId={activeSessionId}
                  isAdmin={isAdminMode}
                />
              ))}

              {isLoading && <LoadingIndicator />}

              {errorMessage && (
                <ErrorBanner
                  message={errorMessage}
                  onRetry={() => handleSendMessage()}
                />
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </main>

        {/* Sticky Prompt Composer Input */}
        <PromptComposer
          input={input}
          onInputChange={setInput}
          onSubmit={() => handleSendMessage()}
          isLoading={isLoading}
          onSelectPrompt={(p) => handleSendMessage(p)}
        />
      </div>

      {/* Schema Reference Explorer Modal */}
      <SchemaModal
        isOpen={isSchemaModalOpen}
        onClose={() => setIsSchemaModalOpen(false)}
      />
    </div>
  );
};
