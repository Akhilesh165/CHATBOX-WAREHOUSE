'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, CornerDownLeft } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isLoading?: boolean;
}

const SUGGESTIONS = [
  { label: '📊 Top utilized bins', query: 'Show top utilized bins in plant 1258' },
  { label: '⚖️ Plant 1258 vs 7228', query: 'Compare the bin utilization of plant 1258 and 7228 in detail' },
  { label: '📦 Inventory summary', query: 'Show total warehouse inventory summary' },
  { label: '🔍 Materials in 7228', query: 'Which materials are available in Plant 7228?' },
  { label: '🏭 Plant 1258 detail', query: 'Show plant 1258 detail inventory metrics' },
];

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  isLoading = false,
}) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea as user types
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        120
      )}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSuggestionClick = (query: string) => {
    if (isLoading) return;
    onSendMessage(query);
  };

  return (
    <div className="border-t border-slate-800/80 bg-slate-950/95 backdrop-blur-md px-3.5 pt-2.5 pb-3">
      {/* Quick Suggestion Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
        <span className="flex items-center gap-1 text-[10px] uppercase font-semibold text-sky-400 tracking-wider shrink-0 pl-0.5 pr-1">
          <Sparkles className="w-3 h-3 text-sky-400 animate-pulse" />
          Suggestions:
        </span>
        {SUGGESTIONS.map((item, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => handleSuggestionClick(item.query)}
            disabled={isLoading}
            className="shrink-0 text-[11px] px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-300 hover:text-sky-300 hover:border-sky-500/40 hover:bg-slate-800/70 transition-all duration-150 disabled:opacity-50 disabled:pointer-events-none"
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Input container */}
      <form
        onSubmit={handleSubmit}
        className="relative flex items-center bg-slate-900/90 border border-slate-800 rounded-xl focus-within:border-sky-500/60 focus-within:ring-1 focus-within:ring-sky-500/30 transition-all shadow-inner"
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask warehouse assistant (e.g., bin utilization, comparisons)..."
          disabled={isLoading}
          rows={1}
          className="w-full bg-transparent text-slate-100 placeholder-slate-500 text-xs sm:text-[13px] px-3.5 py-2.5 resize-none focus:outline-none max-h-32 leading-relaxed"
        />

        <div className="flex items-center gap-1 pr-2">
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="p-1.5 rounded-lg bg-sky-600 text-white hover:bg-sky-500 disabled:opacity-30 disabled:pointer-events-none transition-all duration-150 shadow-sm"
            aria-label="Send message"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>

      {/* Subtle Hint Footer */}
      <div className="flex items-center justify-between mt-1.5 px-1 text-[10px] text-slate-500 select-none">
        <span className="flex items-center gap-1">
          <CornerDownLeft className="w-2.5 h-2.5 text-slate-600" />
          Press <kbd className="px-1 py-0.2 rounded bg-slate-900 border border-slate-800 text-slate-400 font-mono text-[9px]">Enter</kbd> to send
        </span>
        <span className="text-[9px] text-slate-600 tracking-wider uppercase font-semibold">
          Warehouse Copilot
        </span>
      </div>
    </div>
  );
};
