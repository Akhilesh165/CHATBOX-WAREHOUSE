'use client';

import React, { useRef, useEffect } from 'react';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { ResponseCardData } from './ResponseCard';
import { Bot, Sparkles } from 'lucide-react';

export interface ChatWidgetMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  cardData?: ResponseCardData;
}

interface ChatMessagesProps {
  messages: ChatWidgetMessage[];
  isLoading?: boolean;
}

export const ChatMessages: React.FC<ChatMessagesProps> = ({ messages, isLoading = false }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-sky-500/20 to-indigo-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 mb-3 shadow-lg shadow-sky-950/50">
            <Bot className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-200 mb-1">
            Warehouse Assistant Active
          </h3>
          <p className="text-xs text-slate-500 max-w-[260px] leading-relaxed">
            Ask about bin utilization, inventory summaries, multi-plant comparisons, or material listings across plants.
          </p>
        </div>
      ) : (
        messages.map((msg) =>
          msg.sender === 'user' ? (
            <UserMessage
              key={msg.id}
              content={msg.content}
              timestamp={msg.timestamp}
            />
          ) : (
            <AssistantMessage
              key={msg.id}
              content={msg.content}
              timestamp={msg.timestamp}
              cardData={msg.cardData}
            />
          )
        )
      )}

      {/* Typing / Generating Indicator */}
      {isLoading && (
        <div className="flex items-center gap-2.5 max-w-full animate-fade-in pl-1">
          <div className="w-7 h-7 rounded-full bg-slate-800 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0">
            <Bot className="w-4 h-4" />
          </div>
          <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-sm bg-slate-900/90 border border-slate-800 text-slate-400 text-xs flex items-center gap-1.5 shadow-sm">
            <Sparkles className="w-3.5 h-3.5 text-sky-400 animate-spin" />
            <span className="text-[12px] font-medium text-slate-300">Analyzing warehouse data</span>
            <span className="flex gap-1 ml-1">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '0ms' }}></span>
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '150ms' }}></span>
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '300ms' }}></span>
            </span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
};
