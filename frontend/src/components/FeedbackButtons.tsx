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
    <div className="flex items-center space-x-1.5 text-xs text-slate-500">
      {voted ? (
        <span className="flex items-center space-x-1 text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium">
          <Check className="w-3 h-3" />
          <span>Feedback received</span>
        </span>
      ) : (
        <>
          <span className="text-[11px] text-slate-400">Was this helpful?</span>
          <button
            onClick={() => handleVote('up')}
            className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-emerald-600 transition"
            title="Helpful"
          >
            <ThumbsUp className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleVote('down')}
            className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-rose-600 transition"
            title="Not helpful"
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </button>
        </>
      )}
    </div>
  );
};
