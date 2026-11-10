'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isLoading?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  isLoading = false,
}) => {
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input on mount
  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 200);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSendMessage(trimmed);
    setInput('');
  };

  return (
    <footer className="p-3.5 border-t border-slate-200/90 bg-white flex-none">
      <form
        id="form"
        onSubmit={handleSubmit}
        className="flex gap-2 p-1.5 pl-3.5 border border-slate-200 rounded-xl bg-slate-50 items-center transition-all focus-within:bg-white focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 shadow-xs"
      >
        <input
          ref={inputRef}
          id="input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask warehouse assistant (e.g. inventory, bins)..."
          autoComplete="off"
          aria-label="Type your message"
          disabled={isLoading}
          className="flex-1 min-w-0 border-0 outline-none text-xs sm:text-[13px] bg-transparent text-slate-800 placeholder-slate-400 disabled:opacity-50"
        />

        <button
          type="submit"
          id="send"
          disabled={!input.trim() || isLoading}
          aria-label="Send"
          className="w-8 h-8 border-0 rounded-lg bg-blue-600 hover:bg-blue-700 text-white cursor-pointer grid place-items-center transition-all disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0 shadow-xs"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>

      <p className="text-center text-slate-400 text-[10px] mt-2 select-none">
        Connected to Live Warehouse Database · SQL Server
      </p>
    </footer>
  );
};
