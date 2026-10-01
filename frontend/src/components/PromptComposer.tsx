'use client';

import React, { useRef, useEffect } from 'react';
import { Send, Sparkles, CornerDownLeft, ShieldCheck } from 'lucide-react';
import { FilterChips } from './FilterChips';

interface PromptComposerProps {
  input: string;
  onInputChange: (val: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
  onSelectPrompt: (prompt: string) => void;
}

export const PromptComposer: React.FC<PromptComposerProps> = ({
  input,
  onInputChange,
  onSubmit,
  isLoading,
  onSelectPrompt
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea as user types
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && input.trim()) {
        onSubmit();
      }
    }
  };

  return (
    <div className="bg-gradient-to-t from-slate-100 via-slate-100/90 to-transparent p-4 pb-5 flex-shrink-0">
      <div className="max-w-3xl mx-auto space-y-2">
        {/* Quick Suggestion Chips */}
        <FilterChips disabled={isLoading} onSelectQuery={onSelectPrompt} />

        {/* Input Box Card */}
        <div className="relative bg-white border border-slate-300/80 rounded-2xl shadow-md shadow-slate-200/50 focus-within:ring-2 focus-within:ring-sky-500/20 focus-within:border-sky-500 transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Ask about warehouse inventory, material codes, bin occupancy, plant totals..."
            className="w-full pl-4 pr-14 py-3.5 bg-transparent resize-none outline-none text-sm text-slate-800 placeholder:text-slate-400 max-h-44 scrollbar-thin"
          />

          <button
            type="button"
            onClick={onSubmit}
            disabled={isLoading || !input.trim()}
            className="absolute right-2.5 bottom-2.5 w-9 h-9 rounded-xl bg-sky-600 hover:bg-sky-700 disabled:bg-slate-200 text-white disabled:text-slate-400 flex items-center justify-center transition shadow-xs disabled:cursor-not-allowed"
            title="Send query (Enter)"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-white/60 border-t-transparent rounded-full animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Security / Model footer disclaimer */}
        <div className="flex items-center justify-center space-x-1.5 text-[11px] text-slate-400 text-center pt-0.5">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
          <span>Warehouse AI queries are verified via SQLGlot AST on read-only database connections.</span>
        </div>
      </div>
    </div>
  );
};
