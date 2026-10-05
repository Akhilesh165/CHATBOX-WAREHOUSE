import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown, Check } from 'lucide-react';

interface FeedbackButtonsProps {
  conversationId: string;
  sql?: string | null;
  onFeedbackSubmit?: (rating: 'up' | 'down') => void;
}

export const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({
  conversationId,
  sql,
  onFeedbackSubmit
}) => {
  const [voted, setVoted] = useState<'up' | 'down' | null>(null);

  const handleVote = async (rating: 'up' | 'down') => {
    if (voted) return;
    setVoted(rating);
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          rating,
          sql: sql || null
        })
      });
      if (onFeedbackSubmit) onFeedbackSubmit(rating);
    } catch (err) {
      console.error('Failed to submit feedback', err);
    }
  };

  return (
    <div className="flex items-center space-x-1.5 text-xs text-slate-500 dark:text-slate-400">
      {voted ? (
        <span className="flex items-center space-x-1 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/80 px-2 py-0.5 rounded text-[11px] font-medium border border-emerald-200/60 dark:border-emerald-800">
          <Check className="w-3 h-3" />
          <span>Feedback received</span>
        </span>
      ) : (
        <>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">Was this helpful?</span>
          <button
            onClick={() => handleVote('up')}
            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400 dark:text-slate-500 hover:text-emerald-600 dark:hover:text-emerald-400 transition"
            title="Helpful"
          >
            <ThumbsUp className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleVote('down')}
            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400 dark:text-slate-500 hover:text-rose-600 dark:hover:text-rose-400 transition"
            title="Not helpful"
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </button>
        </>
      )}
    </div>
  );
};
