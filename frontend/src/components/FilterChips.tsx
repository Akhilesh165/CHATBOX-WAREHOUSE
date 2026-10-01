import React from 'react';
import { Sparkles, TrendingUp, Box, Layers, Building2 } from 'lucide-react';

interface FilterChipsProps {
  onSelectQuery: (query: string) => void;
  disabled?: boolean;
}

const SAMPLE_QUESTIONS = [
  { text: 'Total warehouse inventory', icon: Layers },
  { text: 'Top 10 materials by quantity', icon: TrendingUp },
  { text: 'Inventory breakdown by plant', icon: Building2 },
  { text: 'Show inventory by storage location', icon: Box },
  { text: 'Recently updated inventory records', icon: Sparkles },
];

export const FilterChips: React.FC<FilterChipsProps> = ({ onSelectQuery, disabled }) => {
  return (
    <div className="flex items-center space-x-2 overflow-x-auto py-2 px-1 scrollbar-thin">
      <span className="text-xs font-medium text-slate-400 whitespace-nowrap">Suggested:</span>
      {SAMPLE_QUESTIONS.map((q, idx) => {
        const Icon = q.icon;
        return (
          <button
            key={idx}
            disabled={disabled}
            onClick={() => onSelectQuery(q.text)}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-slate-100 hover:bg-sky-50 hover:text-sky-700 hover:border-sky-300 text-slate-700 border border-slate-200 text-xs font-medium transition whitespace-nowrap disabled:opacity-50"
          >
            <Icon className="w-3.5 h-3.5 text-sky-600" />
            <span>{q.text}</span>
          </button>
        );
      })}
    </div>
  );
};
