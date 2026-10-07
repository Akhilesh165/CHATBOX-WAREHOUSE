'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  User,
  Boxes,
  Copy,
  Check,
  Code,
  Clock,
  Sparkles
} from 'lucide-react';
import { ChatMessage } from '../types/chat';
import { ResultTable } from './ResultTable';
import { InventoryBarChart } from './InventoryBarChart';
import { InventoryLineChart } from './InventoryLineChart';
import { InventoryPieChart } from './InventoryPieChart';
import { KpiCard } from './KpiCard';
import { ListView } from './ListView';
import { FeedbackButtons } from './FeedbackButtons';
import { AdminSqlModal } from './AdminSqlModal';

interface MessageBubbleProps {
  message: ChatMessage;
  conversationId: string;
  isAdmin?: boolean;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  conversationId,
  isAdmin = false
}) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [isSqlModalOpen, setIsSqlModalOpen] = useState(false);

  const handleCopyText = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const rows = message.data || message.rows || [];
  const hasTable = rows.length > 0;
  const isSingleMetricIntent = (
    message.output_type === 'text' ||
    message.output_type === 'single_value' ||
    message.intent?.endsWith('_count') ||
    message.intent === 'SINGLE_METRIC' ||
    message.intent === 'active_plants_count' ||
    message.intent === 'occupied_bins_count' ||
    message.intent === 'total_bins_count' ||
    message.intent === 'empty_bins_count' ||
    message.intent === 'unique_materials_count' ||
    message.intent === 'total_inventory_quantity' ||
    message.intent === 'storage_locations_count'
  );

  const outputType = isSingleMetricIntent ? 'text' : (message.output_type || (
    message.chart?.type === 'line' ? 'line_chart' :
    message.chart?.type === 'bar' ? 'bar_chart' :
    message.chart?.type === 'pie' ? 'pie_chart' :
    hasTable ? 'table' : 'text'
  ));

  const showChart = !isSingleMetricIntent && (outputType === 'bar_chart' || outputType === 'line_chart' || outputType === 'pie_chart') && message.chart && message.chart.data && message.chart.data.length > 0;
  const showKpi = !isSingleMetricIntent && outputType === 'kpi' && hasTable && message.intent === 'inventory_summary';
  const showList = !isSingleMetricIntent && outputType === 'list' && hasTable;
  const showTable = !isSingleMetricIntent && (outputType === 'table' || showChart || showKpi || showList) && hasTable;

  if (isUser) {
    return (
      <div className="flex justify-end my-4 animate-in fade-in slide-in-from-bottom-2 duration-150">
        <div className="flex items-start space-x-3 flex-row-reverse space-x-reverse max-w-2xl">
          <div className="w-8 h-8 rounded-full bg-slate-800 dark:bg-sky-600 text-slate-200 dark:text-white flex items-center justify-center flex-shrink-0 shadow-xs">
            <User className="w-4 h-4" />
          </div>
          <div className="bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-4 py-3 rounded-2xl rounded-tr-xs shadow-xs text-sm font-normal leading-relaxed border border-slate-200/60 dark:border-slate-750">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start my-4 w-full animate-in fade-in slide-in-from-bottom-2 duration-150">
      <div className="flex items-start space-x-3.5 max-w-4xl w-full">
        {/* Assistant Avatar */}
        <div className="w-8 h-8 rounded-xl bg-sky-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm shadow-sky-600/20 mt-0.5">
          <Boxes className="w-4 h-4" />
        </div>

        {/* Assistant Response Box */}
        <div className="flex-1 bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl rounded-tl-xs p-4 md:p-5 shadow-xs text-sm text-slate-800 dark:text-slate-100 space-y-3 overflow-hidden transition-colors">
          {/* Top Bar: Title & Dynamic Output Type Badges */}
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 pb-2.5 flex-wrap gap-2">
            <div className="flex items-center space-x-2 flex-wrap gap-1">
              <span className="text-xs font-bold text-slate-800 dark:text-slate-200">Warehouse Assistant</span>
              {message.intent && (
                <span className="text-[11px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/60">
                  {message.intent}
                </span>
              )}
              {outputType && (
                <span className="text-[10px] uppercase font-bold tracking-wider bg-sky-50 dark:bg-sky-950/80 text-sky-700 dark:text-sky-300 px-1.5 py-0.5 rounded border border-sky-200/60 dark:border-sky-800">
                  {outputType}
                </span>
              )}
              {message.time_range && (
                <span className="hidden sm:inline-block text-[10px] text-slate-400 dark:text-slate-500">
                  • {message.time_range}
                </span>
              )}
            </div>

            <div className="flex items-center space-x-2 text-[11px] text-slate-400 dark:text-slate-500">
              {message.executionMs !== undefined && (
                <span className="flex items-center space-x-1 bg-slate-50 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-750">
                  <Clock className="w-3 h-3 text-slate-400" />
                  <span>{message.executionMs}ms</span>
                </span>
              )}
              {message.rowCount !== undefined && message.rowCount > 0 && (
                <span className="bg-sky-50 dark:bg-sky-950/80 text-sky-700 dark:text-sky-300 px-2 py-0.5 rounded font-medium border border-sky-200/60 dark:border-sky-800">
                  {message.rowCount} rows
                </span>
              )}
            </div>
          </div>

          {/* 1. Summary / Theory Content */}
          {message.content && (
            <div className="prose prose-sm max-w-none text-slate-700 dark:text-slate-300 leading-relaxed font-normal">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* 2. KPI Cards (if output_type = 'kpi') */}
          {showKpi && (
            <div className="pt-1">
              <KpiCard data={rows} metric={message.metric} />
            </div>
          )}

          {/* 3. List View (if output_type = 'list') */}
          {showList && (
            <div className="pt-1">
              <ListView data={rows} title={message.chart?.title} />
            </div>
          )}

          {/* 4. Chart Views (if output_type = 'bar_chart' | 'line_chart' | 'pie_chart') */}
          {showChart && message.chart && (
            <div className="pt-2">
              {(outputType === 'bar_chart' || message.chart.type === 'bar') && (
                <InventoryBarChart
                  title={message.chart.title}
                  data={message.chart.data}
                  xKey={message.chart.xAxis || message.chart.x_key}
                  yKey={message.chart.yAxis || message.chart.y_key}
                />
              )}
              {(outputType === 'line_chart' || message.chart.type === 'line') && (
                <InventoryLineChart
                  title={message.chart.title}
                  data={message.chart.data}
                  xKey={message.chart.xAxis || message.chart.x_key}
                  yKey={message.chart.yAxis || message.chart.y_key}
                />
              )}
              {(outputType === 'pie_chart' || message.chart.type === 'pie') && (
                <InventoryPieChart
                  title={message.chart.title}
                  data={message.chart.data}
                  xKey={message.chart.xAxis || message.chart.x_key}
                  yKey={message.chart.yAxis || message.chart.y_key}
                />
              )}
            </div>
          )}

          {/* 5. Data Table View (if output_type = 'table' or under chart/kpi/list) */}
          {showTable && (
            <div className="pt-2">
              <ResultTable rows={rows} pageSize={8} />
            </div>
          )}

          {/* Warnings */}
          {message.warnings && message.warnings.length > 0 && (
            <div className="text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/60 p-2.5 rounded-xl border border-amber-200 dark:border-amber-800/80">
              {message.warnings.map((w, i) => (
                <div key={i}>⚠️ {w}</div>
              ))}
            </div>
          )}

          {/* Bottom Action Bar */}
          <div className="flex items-center justify-between pt-2.5 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400 dark:text-slate-500">
            <FeedbackButtons conversationId={conversationId} sql={message.sql} />

            <div className="flex items-center space-x-2">
              <button
                onClick={handleCopyText}
                className="flex items-center space-x-1 px-2.5 py-1 text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition text-[11px] font-medium"
                title="Copy Answer"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span className="text-emerald-600 dark:text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>

              {(isAdmin || message.sql) && (
                <button
                  onClick={() => setIsSqlModalOpen(true)}
                  className="flex items-center space-x-1 px-2.5 py-1 text-slate-600 dark:text-slate-300 hover:text-sky-700 dark:hover:text-sky-400 hover:bg-sky-50 dark:hover:bg-sky-950/60 rounded-lg transition text-[11px] font-semibold border border-slate-200/80 dark:border-slate-750"
                  title="View Generated SQL"
                >
                  <Code className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
                  <span>View SQL</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* SQL Inspector Modal */}
      {message.sql && (
        <AdminSqlModal
          sql={message.sql}
          isOpen={isSqlModalOpen}
          onClose={() => setIsSqlModalOpen(false)}
          metadata={{
            executionMs: message.executionMs,
            llmMs: message.llmMs,
            sqlMs: message.sqlMs,
            rowCount: message.rowCount,
            intent: message.intent
          }}
        />
      )}
    </div>
  );
};
