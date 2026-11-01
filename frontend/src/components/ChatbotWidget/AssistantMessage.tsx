'use client';

import React, { useState } from 'react';
import { Bot, Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react';
import { ResponseCard, ResponseCardData } from './ResponseCard';

interface AssistantMessageProps {
  content: string;
  timestamp?: string;
  cardData?: ResponseCardData;
}

export const AssistantMessage: React.FC<AssistantMessageProps> = ({
  content,
  timestamp,
  cardData,
}) => {
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState<boolean | null>(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-start gap-2.5 max-w-full pr-4 animate-fade-in">
      {/* Bot Icon */}
      <div className="w-7 h-7 rounded-full bg-slate-800 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-0.5 shadow-sm">
        <Bot className="w-4 h-4" />
      </div>

      <div className="flex flex-col items-start max-w-[calc(100%-2.25rem)]">
        {/* Main message bubble */}
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-slate-900/90 border border-slate-800/80 text-slate-200 text-xs sm:text-[13px] leading-relaxed shadow-sm w-full break-words">
          <p className="whitespace-pre-line">{content}</p>

          {/* Embedded Response Card if present */}
          {cardData && <ResponseCard card={cardData} />}
        </div>

        {/* Message footer & action buttons */}
        <div className="flex items-center gap-3 mt-1.5 ml-1 text-[10px] text-slate-400 select-none">
          {timestamp && <span>{timestamp}</span>}

          <div className="flex items-center gap-1.5">
            <button
              onClick={handleCopy}
              className="p-1 rounded hover:text-slate-300 hover:bg-slate-800/80 transition-colors"
              title="Copy message"
              aria-label="Copy message"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            </button>

            <button
              onClick={() => setLiked(liked === true ? null : true)}
              className={`p-1 rounded hover:bg-slate-800/80 transition-colors ${
                liked === true ? 'text-sky-400' : 'hover:text-slate-300'
              }`}
              title="Helpful"
              aria-label="Helpful"
            >
              <ThumbsUp className="w-3 h-3" />
            </button>

            <button
              onClick={() => setLiked(liked === false ? null : false)}
              className={`p-1 rounded hover:bg-slate-800/80 transition-colors ${
                liked === false ? 'text-rose-400' : 'hover:text-slate-300'
              }`}
              title="Not helpful"
              aria-label="Not helpful"
            >
              <ThumbsDown className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
