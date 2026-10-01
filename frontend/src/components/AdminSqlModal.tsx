import React, { useState } from 'react';
import { Terminal, Copy, Check, X, ShieldAlert } from 'lucide-react';

interface AdminSqlModalProps {
  sql: string;
  isOpen: boolean;
  onClose: () => void;
  metadata?: {
    executionMs?: number;
    llmMs?: number;
    sqlMs?: number;
    rowCount?: number;
    intent?: string;
  };
}

export const AdminSqlModal: React.FC<AdminSqlModalProps> = ({
  sql,
  isOpen,
  onClose,
  metadata
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
      <div className="bg-slate-900 text-slate-100 rounded-2xl border border-slate-700 shadow-2xl max-w-2xl w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 bg-slate-800/80 border-b border-slate-700">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 bg-sky-500/10 text-sky-400 rounded-lg">
              <Terminal className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">Generated SQL Server Query</h3>
              <p className="text-[11px] text-slate-400">Validated with SQLGlot AST</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Query Metadata Badges */}
        {metadata && (
          <div className="flex flex-wrap items-center gap-2 px-5 py-2.5 bg-slate-800/40 border-b border-slate-700/60 text-[11px] text-slate-300">
            {metadata.executionMs !== undefined && (
              <span className="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                Total: <strong className="text-sky-400">{metadata.executionMs}ms</strong>
              </span>
            )}
            {metadata.sqlMs !== undefined && (
              <span className="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                DB Query: <strong className="text-emerald-400">{metadata.sqlMs}ms</strong>
              </span>
            )}
            {metadata.llmMs !== undefined && (
              <span className="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                LLM: <strong className="text-purple-400">{metadata.llmMs}ms</strong>
              </span>
            )}
            {metadata.rowCount !== undefined && (
              <span className="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                Rows: <strong className="text-amber-400">{metadata.rowCount}</strong>
              </span>
            )}
          </div>
        )}

        {/* Code Content */}
        <div className="p-5">
          <div className="relative bg-slate-950 p-4 rounded-xl font-mono text-xs text-sky-300 overflow-x-auto border border-slate-800">
            <button
              onClick={handleCopy}
              className="absolute top-2.5 right-2.5 flex items-center space-x-1 px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-[11px] font-sans transition"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3 text-slate-400" />
                  <span>Copy SQL</span>
                </>
              )}
            </button>
            <pre className="pr-16 whitespace-pre-wrap">{sql}</pre>
          </div>

          <div className="flex items-center space-x-2 mt-3 text-[11px] text-slate-400">
            <ShieldAlert className="w-3.5 h-3.5 text-emerald-500" />
            <span>Executed via read-only SQL Server connection (`wms_chatbot_readonly`).</span>
          </div>
        </div>
      </div>
    </div>
  );
};
