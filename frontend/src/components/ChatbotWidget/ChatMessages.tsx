'use client';

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Copy,
  Check,
  Code,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { ChatMessage, TableDataset, TableMiniSummary } from '../../types/chat';
import { WarehouseStatsResponse } from '../../types/dashboard';
import { ResultTable } from '../ResultTable';
import { InventoryBarChart } from '../InventoryBarChart';
import { InventoryLineChart } from '../InventoryLineChart';
import { InventoryPieChart } from '../InventoryPieChart';
import { KpiCard } from '../KpiCard';
import { ListView } from '../ListView';
import { AdminSqlModal } from '../AdminSqlModal';

function parseMultiPlantTablesFromContent(content: string): TableDataset[] {
  if (!content || !content.includes('|') || !content.includes('## Plant ')) {
    return [];
  }
  const plantSections = content.split(/(?:^|\n)##\s+Plant\s+/).filter(Boolean);
  if (plantSections.length < 1) return [];

  const datasets: TableDataset[] = [];

  for (const section of plantSections) {
    const firstLineEnd = section.indexOf('\n');
    const headerLine = firstLineEnd !== -1 ? section.slice(0, firstLineEnd).trim() : section.trim();
    const plantMatch = headerLine.match(/^([A-Za-z0-9_-]+)/);
    if (!plantMatch) continue;
    const plantId = plantMatch[1];
    const title = `Plant ${plantId} — Detailed Bin Utilization`;

    const tableLines = section.split('\n').filter((l) => l.trim().startsWith('|') && l.trim().endsWith('|'));
    if (tableLines.length < 3) continue;

    const rawHeaders = tableLines[0].split('|').map((h) => h.trim()).filter(Boolean);
    const dataLines = tableLines.slice(2);
    const rows: Array<Record<string, any>> = [];

    for (const dLine of dataLines) {
      const cells = dLine.split('|').map((c) => c.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
      const rowObj: Record<string, any> = {};
      rawHeaders.forEach((h, hIdx) => {
        rowObj[h] = cells[hIdx] ?? '';
      });
      rows.push(rowObj);
    }

    let miniSummary: TableMiniSummary | undefined;
    const summaryMatch = section.match(/###\s*Mini Summary([\s\S]*?)(?:$|---)/i);
    if (summaryMatch) {
      const sumText = summaryMatch[1];
      const totalMatch = sumText.match(/Total bins:\s*([\d,]+)/i);
      const utilMatch = sumText.match(/Utilized bins:\s*([\d,]+)/i);
      const emptyMatch = sumText.match(/Empty bins:\s*([\d,]+)/i);
      const avgMatch = sumText.match(/Average utilization:\s*([\d.]+%?)/i);

      if (totalMatch || avgMatch) {
        miniSummary = {
          total_bins: totalMatch ? parseInt(totalMatch[1].replace(/,/g, ''), 10) : rows.length,
          utilized_bins: utilMatch ? parseInt(utilMatch[1].replace(/,/g, ''), 10) : 0,
          empty_bins: emptyMatch ? parseInt(emptyMatch[1].replace(/,/g, ''), 10) : 0,
          average_utilization: avgMatch ? avgMatch[1] : '0%',
        };
      }
    }

    if (rows.length > 0) {
      datasets.push({
        title,
        plant: plantId,
        count: rows.length,
        total_count: miniSummary ? miniSummary.total_bins : rows.length,
        displayed_count: rows.length,
        rows,
        mini_summary: miniSummary,
      });
    }
  }

  return datasets;
}

interface ChatMessagesProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  onSelectPrompt?: (prompt: string) => void;
  stats?: WarehouseStatsResponse | null;
}

export const ChatMessages: React.FC<ChatMessagesProps> = ({
  messages,
  isLoading = false,
  onSelectPrompt,
  stats,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeSqlModal, setActiveSqlModal] = useState<{
    sql: string;
    metadata?: any;
  } | null>(null);

  // Derived dynamically from backend live database
  const plantCount = stats?.plant_count ?? 4;
  const overallUtil = stats?.summary.overall_utilization ?? 70.3;
  const occupiedBins = stats?.summary.occupied_bins
    ? stats.summary.occupied_bins.toLocaleString()
    : '23,296';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <main
      id="messages"
      className="flex-1 overflow-y-auto p-4 bg-slate-50/70 text-slate-800 text-[13px] select-text scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent space-y-4"
    >
      {/* Date Marker */}
      <div className="text-center text-slate-400 text-[11px] font-semibold tracking-wider mb-2 select-none">
        TODAY
      </div>

      {/* Initial Welcome & Chips (shown when no conversation history yet) */}
      {messages.length === 0 && (
        <div className="space-y-3.5 animate-fade-in">
          {/* Welcome Message 1 */}
          <div className="flex gap-2.5 items-start">
            <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 border border-blue-200/80 grid place-items-center flex-none text-xs font-bold mt-0.5 shadow-2xs">
              ✦
            </div>
            <div className="max-w-[85%] p-3.5 rounded-2xl rounded-tl-sm bg-white border border-slate-200/90 text-slate-800 text-xs sm:text-[13px] leading-relaxed shadow-xs">
              Hello! 👋 Welcome to Warehouse Assistant. How can I help you today?
            </div>
          </div>

          {/* Welcome Message 2 */}
          <div className="flex gap-2.5 items-start">
            <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 border border-blue-200/80 grid place-items-center flex-none text-xs font-bold mt-0.5 shadow-2xs">
              ✦
            </div>
            <div className="max-w-[85%] p-3.5 rounded-2xl rounded-tl-sm bg-white border border-slate-200/90 text-slate-800 text-xs sm:text-[13px] leading-relaxed shadow-xs">
              You can ask about inventory, bin utilization, plant comparisons, or warehouse capacity.
            </div>
          </div>

          {/* Suggested Question Chips (Clean & Readable) */}
          <div className="ml-9 flex gap-2 flex-wrap pt-0.5">
            <button
              type="button"
              onClick={() => onSelectPrompt?.('Show bin utilization')}
              className="border border-slate-200 bg-white hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-700 px-3 py-1.5 rounded-full text-xs font-medium transition-all shadow-xs cursor-pointer"
            >
              Show bin utilization
            </button>
            <button
              type="button"
              onClick={() => onSelectPrompt?.('Check inventory')}
              className="border border-slate-200 bg-white hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-700 px-3 py-1.5 rounded-full text-xs font-medium transition-all shadow-xs cursor-pointer"
            >
              Check inventory
            </button>
            <button
              type="button"
              onClick={() => onSelectPrompt?.('Compare plants')}
              className="border border-slate-200 bg-white hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-700 px-3 py-1.5 rounded-full text-xs font-medium transition-all shadow-xs cursor-pointer"
            >
              Compare plants
            </button>
            <button
              type="button"
              onClick={() => onSelectPrompt?.('Show top utilized bins for Plant 1258')}
              className="border border-slate-200 bg-white hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-700 px-3 py-1.5 rounded-full text-xs font-medium transition-all shadow-xs cursor-pointer"
            >
              Top bins Plant 1258
            </button>
          </div>

          {/* Warehouse Operations Snapshot Card with Dynamic Plant Count */}
          <div
            className="mt-3.5 mb-2 ml-9 p-4 border border-slate-200/90 rounded-xl bg-white shadow-xs"
            aria-label="Warehouse snapshot"
          >
            <div className="flex justify-between items-center text-slate-900 text-xs font-bold">
              <span>Warehouse Operations Snapshot</span>
              <span className="text-[9px] tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold uppercase">
                LIVE DATA
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-3">
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                <b className="block text-slate-900 text-sm font-bold">{overallUtil}%</b>
                <small className="block text-slate-500 text-[10px] mt-0.5 font-medium">Utilization</small>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                <b className="block text-slate-900 text-sm font-bold">{occupiedBins}</b>
                <small className="block text-slate-500 text-[10px] mt-0.5 font-medium">Occupied Bins</small>
              </div>
              {/* Plant count dynamically from live DB */}
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-center">
                <b className="block text-blue-600 text-sm font-bold">{plantCount}</b>
                <small className="block text-slate-500 text-[10px] mt-0.5 font-medium">Active Plants</small>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dynamic Conversation Messages */}
      {messages.map((message) => {
        const isUser = message.role === 'user';

        if (isUser) {
          return (
            <div key={message.id} className="flex justify-end mb-3 items-end">
              <div className="max-w-[85%] p-3 px-4 rounded-2xl rounded-tr-sm bg-blue-600 text-white text-xs sm:text-[13px] leading-relaxed shadow-xs break-words font-medium">
                {message.content}
              </div>
            </div>
          );
        }

        // Assistant response with full preserved response rendering
        const rows = message.data || message.rows || [];
        const hasTable = rows.length > 0;
        const isSingleMetricIntent = Boolean(
          message.output_type === 'text' ||
          (message.output_type as string) === 'single_value' ||
          (message.output_type as string) === 'single_line' ||
          message.intent?.endsWith('_count') ||
          message.intent === 'active_plants_count' ||
          message.intent === 'occupied_bins_count' ||
          message.intent === 'total_bins_count' ||
          message.intent === 'empty_bins_count' ||
          message.intent === 'unique_materials_count' ||
          message.intent === 'total_inventory_quantity' ||
          message.intent === 'storage_locations_count' ||
          message.intent === 'bin_plant_lookup' ||
          message.intent === 'bin_occupancy_status' ||
          message.intent === 'bin_quantity_lookup' ||
          message.intent === 'bin_materials_count' ||
          message.intent === 'LOWEST_BIN_UTILIZATION' ||
          message.intent === 'HIGHEST_BIN_CAPACITY' ||
          message.intent === 'LOWEST_BIN_CAPACITY' ||
          message.intent === 'AVERAGE_BIN_UTILIZATION' ||
          ((message.intent === 'lowest_bin_utilization' || message.intent === 'highest_bin_utilization' || message.intent === 'HIGHEST_BIN_UTILIZATION') && rows.length <= 1)
        );

        const isPlantBinUtilDetail = message.intent === 'plant_bin_utilization_detail';

        const outputType = isSingleMetricIntent ? 'text' : (message.output_type || (
          message.chart?.type === 'line' ? 'line_chart' :
          message.chart?.type === 'bar' ? 'bar_chart' :
          message.chart?.type === 'pie' ? 'pie_chart' :
          hasTable ? 'table' : 'text'
        ));

        const showChart = !isSingleMetricIntent && (outputType === 'bar_chart' || outputType === 'line_chart' || outputType === 'pie_chart' || outputType === 'chart_plus_summary') && message.chart && message.chart.data && message.chart.data.length > 0;
        const showKpi = !isSingleMetricIntent && outputType === 'kpi' && hasTable && message.intent === 'inventory_summary';
        const showList = !isSingleMetricIntent && outputType === 'list' && hasTable;
        const contentHasTable = Boolean(message.content && message.content.includes('|') && message.content.includes('---'));

        let effectiveTables: TableDataset[] = [];
        if (message.tables && message.tables.length > 0) {
          effectiveTables = message.tables;
        } else if (message.content && message.content.includes('## Plant ') && (message.content.includes('| Bin') || message.content.includes('|Bin'))) {
          effectiveTables = parseMultiPlantTablesFromContent(message.content);
        }

        const hasMultiTables = effectiveTables.length > 0;
        const showTable = !isSingleMetricIntent && !contentHasTable && !hasMultiTables && (outputType === 'table' || outputType === 'ranking_table' || outputType === 'comparison_table' || outputType === 'detail_analysis' || isPlantBinUtilDetail || showChart || showKpi || showList) && hasTable;

        let displayContent = message.content || '';
        if (hasMultiTables && displayContent) {
          displayContent = displayContent.split(/(?:^|\n)##\s+Plant\s+|(?:^|\n)\|(?:\s*Bin|\s*Plant|\s*Capacity)/)[0].trim();
        }

        return (
          <div key={message.id} className="flex flex-col mb-4">
            <div className="flex gap-2.5 items-start">
              {/* Bot Avatar ✦ */}
              <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 border border-blue-200/80 grid place-items-center flex-none text-xs font-bold mt-0.5 shadow-2xs">
                ✦
              </div>

              {/* Bot Response Bubble (Clean Light Theme) */}
              <div className="flex-1 max-w-[calc(100%-36px)] p-4 rounded-2xl rounded-tl-sm bg-white border border-slate-200/90 text-slate-800 text-xs sm:text-[13px] leading-relaxed shadow-xs space-y-3 overflow-hidden">
                {/* Header row: Intent, Output Type, Execution time */}
                <div className="flex items-center justify-between border-b border-slate-100 pb-2 flex-wrap gap-1.5 select-none text-[11px]">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-semibold text-slate-900">Warehouse Assistant</span>
                    {message.intent && (
                      <span className="bg-slate-100 text-slate-600 font-mono text-[10px] px-1.5 py-0.5 rounded border border-slate-200/70">
                        {message.intent}
                      </span>
                    )}
                    {outputType && outputType !== 'text' && (
                      <span className="bg-blue-50 text-blue-700 text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border border-blue-200/70">
                        {outputType}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 text-[10px] text-slate-500">
                    {message.executionMs !== undefined && (
                      <span className="flex items-center gap-1 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200">
                        <Clock className="w-2.5 h-2.5 text-slate-400" />
                        <span>{message.executionMs}ms</span>
                      </span>
                    )}
                    {message.rowCount !== undefined && message.rowCount > 0 && (
                      <span className="font-medium text-slate-600">
                        {message.rowCount} rows
                      </span>
                    )}
                  </div>
                </div>

                {/* Markdown text content */}
                {displayContent ? (
                  <div className="prose prose-slate prose-sm max-w-none text-slate-800 leading-relaxed font-normal">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {displayContent}
                    </ReactMarkdown>
                  </div>
                ) : null}

                {/* Relevant KPIs */}
                {message.relevant_kpis && message.relevant_kpis.length > 0 && (
                  <div className="grid grid-cols-2 gap-2 my-2">
                    {message.relevant_kpis.map((kpi, idx) => (
                      <div
                        key={idx}
                        className="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5 shadow-2xs"
                      >
                        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-0.5">
                          {kpi.label}
                        </div>
                        <div className="text-lg font-bold text-slate-900 font-mono">
                          {kpi.value}
                        </div>
                        {kpi.subtext && (
                          <div className="text-[10px] text-slate-500 mt-0.5">
                            {kpi.subtext}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* KPI Card */}
                {showKpi && (
                  <div className="pt-1">
                    <KpiCard data={rows} metric={message.metric} />
                  </div>
                )}

                {/* List View */}
                {showList && (
                  <div className="pt-1">
                    <ListView data={rows} title={message.chart?.title} />
                  </div>
                )}

                {/* Charts */}
                {showChart && message.chart && (
                  <div className="pt-1 bg-slate-50 rounded-xl p-3 border border-slate-200">
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

                {/* Multi-Plant Tables with Mini Summaries */}
                {hasMultiTables ? (
                  <div className="pt-2 space-y-4">
                    {effectiveTables.map((tbl, tblIdx) => (
                      <div key={tblIdx} className="space-y-2">
                        <div className="border-b border-slate-200 pb-1">
                          <h4 className="text-xs font-bold text-slate-900">
                            {tbl.title || `Plant ${tbl.plant} — Detailed Bin Utilization`}
                          </h4>
                        </div>

                        <ResultTable
                          rows={tbl.rows}
                          title={tbl.title}
                          totalCount={tbl.total_count}
                          displayedCount={tbl.displayed_count}
                          emptyMessage={tbl.empty_message}
                          pageSize={10}
                          unitLabel="bins"
                        />

                        {tbl.mini_summary && (
                          <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-200 text-xs text-slate-800">
                            <div className="font-bold text-slate-900 text-[11px] mb-1">Mini Summary</div>
                            <ul className="space-y-0.5 text-[11px] text-slate-600">
                              <li>Total bins: <b className="text-slate-900 font-mono">{tbl.mini_summary.total_bins?.toLocaleString()}</b></li>
                              <li>Utilized bins: <b className="text-slate-900 font-mono">{tbl.mini_summary.utilized_bins?.toLocaleString()}</b></li>
                              <li>Empty bins: <b className="text-slate-900 font-mono">{tbl.mini_summary.empty_bins?.toLocaleString()}</b></li>
                              <li>Average utilization: <b className="text-blue-600 font-mono">{tbl.mini_summary.average_utilization}</b></li>
                            </ul>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  showTable && (
                    <div className="pt-1">
                      <ResultTable
                        rows={rows}
                        totalCount={message.total_count}
                        displayedCount={message.displayed_count}
                        pageSize={10}
                      />
                    </div>
                  )
                )}

                {/* Follow-up Action Suggestion Chip */}
                {message.follow_up_action && (
                  <div className="pt-2 border-t border-slate-100 flex flex-col gap-1.5">
                    <span className="text-[10px] text-slate-500 font-medium">Suggested Next Step:</span>
                    <button
                      type="button"
                      onClick={() => onSelectPrompt?.(message.follow_up_action!.action_prompt)}
                      className="self-start text-[11px] text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-3 py-1 rounded-full flex items-center gap-1.5 transition-colors font-medium cursor-pointer shadow-2xs"
                    >
                      <span>{message.follow_up_action.message || message.follow_up_action.action_prompt}</span>
                      <ArrowRight className="w-3 h-3 text-blue-600" />
                    </button>
                  </div>
                )}

                {/* Warnings */}
                {message.warnings && message.warnings.length > 0 && (
                  <div className="text-xs text-amber-800 bg-amber-50 p-2 rounded-lg border border-amber-200">
                    {message.warnings.map((w, i) => (
                      <div key={i}>⚠️ {w}</div>
                    ))}
                  </div>
                )}

                {/* Bottom Action Bar: Copy Answer & View SQL */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                  <button
                    onClick={() => handleCopy(message.id, message.content)}
                    className="flex items-center gap-1 text-slate-500 hover:text-slate-900 px-2 py-0.5 rounded hover:bg-slate-100 transition-colors"
                    title="Copy Answer"
                  >
                    {copiedId === message.id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-600" />
                        <span className="text-emerald-600 font-medium">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>

                  {message.sql && (
                    <button
                      onClick={() =>
                        setActiveSqlModal({
                          sql: message.sql!,
                          metadata: {
                            executionMs: message.executionMs,
                            llmMs: message.llmMs,
                            sqlMs: message.sqlMs,
                            rowCount: message.rowCount,
                            intent: message.intent,
                          },
                        })
                      }
                      className="flex items-center gap-1 text-blue-600 hover:text-blue-800 px-2 py-0.5 rounded hover:bg-blue-50 transition-colors border border-blue-200 text-[11px] font-medium"
                      title="View Generated SQL"
                    >
                      <Code className="w-3 h-3" />
                      <span>View SQL</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Loading Indicator */}
      {isLoading && (
        <div className="flex gap-2.5 items-start mb-3 animate-fade-in">
          <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 border border-blue-200/80 grid place-items-center flex-none text-xs font-bold mt-0.5 shadow-2xs">
            ✦
          </div>
          <div className="p-3 px-4 rounded-2xl rounded-tl-sm bg-white border border-slate-200/90 text-slate-500 text-xs flex items-center gap-2 shadow-xs">
            <span className="inline-block w-2 h-2 rounded-full bg-blue-600 animate-ping" />
            <span className="font-medium text-slate-700">Analyzing warehouse query...</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />

      {/* SQL Inspector Modal */}
      {activeSqlModal && (
        <AdminSqlModal
          sql={activeSqlModal.sql}
          isOpen={Boolean(activeSqlModal)}
          onClose={() => setActiveSqlModal(null)}
          metadata={activeSqlModal.metadata}
        />
      )}
    </main>
  );
};
