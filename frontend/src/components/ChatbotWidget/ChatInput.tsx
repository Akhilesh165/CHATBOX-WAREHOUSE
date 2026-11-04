'use client';

import React, { useState, useRef, useEffect } from 'react';

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
    <footer className="p-[14px_16px_16px] border-t border-[#1b3556] bg-[#071a33] flex-none">
      <form
        id="form"
        onSubmit={handleSubmit}
        className="flex gap-2 p-[7px_8px_7px_13px] border border-[#254566] rounded-[14px] bg-[#0b213d] items-center transition-all focus-within:border-[#3b82f6] focus-within:ring-2 focus-within:ring-[#2563eb33]"
      >
        <input
          ref={inputRef}
          id="input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message..."
          autoComplete="off"
          aria-label="Type your message"
          disabled={isLoading}
          className="flex-1 min-w-0 border-0 outline-none text-[13px] bg-transparent text-[#edf6ff] placeholder-[#7188a5] disabled:opacity-50"
        />

        <button
          type="submit"
          id="send"
          disabled={!input.trim() || isLoading}
          aria-label="Send"
          className="w-9 h-9 border-0 rounded-[10px] bg-[#2563eb] hover:bg-[#1d4ed8] text-white cursor-pointer text-[17px] grid place-items-center transition-all disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
        >
          ➤
        </button>
      </form>

      <p className="text-center text-[#7088a6] text-[10px] mt-2.5 select-none">
        Connected to Live Warehouse Database · SQL Server
      </p>
    </footer>
  );
};
