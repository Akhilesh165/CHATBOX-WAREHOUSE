'use client';

import React, { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface ChatWidgetMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  showChips?: boolean;
  showSnapshot?: boolean;
  rows?: Array<Record<string, any>>;
  sql?: string;
}

interface ChatMessagesProps {
  messages: ChatWidgetMessage[];
  isLoading?: boolean;
  onSelectChip?: (chipText: string) => void;
}

export const ChatMessages: React.FC<ChatMessagesProps> = ({
  messages,
  isLoading = false,
  onSelectChip,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <main
      id="messages"
      className="flex-1 overflow-y-auto p-[22px_18px] bg-[#071a33] text-[#eaf2fb] text-[13px] select-text scrollbar-thin scrollbar-thumb-[#1b3556] scrollbar-track-transparent"
    >
      {/* Date Divider */}
      <div className="text-center text-[#7088a6] text-[10px] font-semibold tracking-wider mb-[22px] select-none">
        TODAY
      </div>

      {/* Message stream */}
      {messages.map((msg) => {
        const isUser = msg.sender === 'user';

        if (isUser) {
          return (
            <div key={msg.id} className="flex justify-end mb-[17px] items-end">
              <div className="max-w-[85%] p-[12px_14px] rounded-[15px_15px_5px_15px] bg-[#1d4ed8] border border-[#2563eb] text-white text-[13px] leading-[1.55] shadow-sm break-words">
                {msg.content}
              </div>
            </div>
          );
        }

        return (
          <div key={msg.id} className="flex flex-col mb-[17px]">
            {/* Bot message row */}
            <div className="flex gap-[9px] items-start">
              <div className="w-[27px] h-[27px] rounded-[9px] bg-[#102b4d] text-[#7dd3fc] grid place-items-center flex-none text-[14px] font-semibold mt-0.5">
                ✦
              </div>

              <div className="max-w-[85%] p-[12px_14px] rounded-[15px_15px_15px_5px] bg-[#102b4d] border border-[#1b3556] text-[#eaf2fb] text-[13px] leading-[1.55] shadow-sm break-words space-y-2">
                <div className="prose prose-invert prose-sm max-w-none text-[#eaf2fb] leading-[1.55] text-[13px]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>

                {/* Structured data table if returned by query */}
                {msg.rows && msg.rows.length > 0 && (
                  <div className="mt-2.5 rounded-lg border border-[#1b3556] bg-[#091f3a] overflow-hidden">
                    <div className="px-2.5 py-1.5 bg-[#0d2442] border-b border-[#1b3556] text-[11px] font-semibold text-[#7dd3fc] flex justify-between items-center">
                      <span>Query Results</span>
                      <span className="font-mono text-[10px] text-[#93c5fd]">
                        {msg.rows.length} rows
                      </span>
                    </div>
                    <div className="overflow-x-auto max-h-56">
                      <table className="w-full text-left text-[11px] border-collapse">
                        <thead>
                          <tr className="bg-[#0b213d] text-[#9fb3cc] border-b border-[#1b3556]">
                            {Object.keys(msg.rows[0]).map((colKey) => (
                              <th key={colKey} className="py-1.5 px-2 font-medium capitalize truncate">
                                {colKey.replace(/_/g, ' ')}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#1b3556]/60">
                          {msg.rows.slice(0, 10).map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-[#102b4d]/70 transition-colors">
                              {Object.values(row).map((val: any, cIdx) => (
                                <td key={cIdx} className="py-1.5 px-2 text-[#dbeafe] whitespace-nowrap">
                                  {val !== null && val !== undefined ? String(val) : '-'}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Quick Suggestion Chips */}
            {msg.showChips && (
              <div className="ml-[36px] mt-2.5 flex gap-[7px] flex-wrap">
                <button
                  type="button"
                  onClick={() => onSelectChip?.('Show bin utilization')}
                  className="border border-[#254566] bg-[#0d2442] text-[#b9dcff] hover:bg-[#14365f] hover:border-[#3b82f6] px-2.5 py-1.5 rounded-[18px] text-[11px] cursor-pointer transition-colors"
                >
                  Show bin utilization
                </button>
                <button
                  type="button"
                  onClick={() => onSelectChip?.('Check inventory')}
                  className="border border-[#254566] bg-[#0d2442] text-[#b9dcff] hover:bg-[#14365f] hover:border-[#3b82f6] px-2.5 py-1.5 rounded-[18px] text-[11px] cursor-pointer transition-colors"
                >
                  Check inventory
                </button>
                <button
                  type="button"
                  onClick={() => onSelectChip?.('Compare plants')}
                  className="border border-[#254566] bg-[#0d2442] text-[#b9dcff] hover:bg-[#14365f] hover:border-[#3b82f6] px-2.5 py-1.5 rounded-[18px] text-[11px] cursor-pointer transition-colors"
                >
                  Compare plants
                </button>
              </div>
            )}

            {/* Warehouse Snapshot Card */}
            {msg.showSnapshot && (
              <div
                className="mt-3.5 mb-1 ml-[36px] p-[14px] border border-[#1f4268] rounded-[16px] bg-gradient-to-br from-[#0c2949] to-[#091f3a] shadow-[0_10px_24px_#02081744]"
                aria-label="Warehouse analytics snapshot"
              >
                <div className="flex justify-between items-center text-[#eaf2fb] text-[12px] font-bold">
                  <span>Warehouse Snapshot</span>
                  <span className="text-[8px] tracking-[.08em] text-[#67e8f9] bg-[#123d5f] px-1.5 py-1 rounded-full font-semibold uppercase">
                    LIVE DATA
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-[13px]">
                  <div className="p-[10px_7px] rounded-[10px] bg-[#071a33] border border-[#183857] text-center">
                    <b className="block text-[#7dd3fc] text-[14px] font-bold">84.2%</b>
                    <small className="block text-[#7891ad] text-[9px] mt-1">Utilization</small>
                  </div>
                  <div className="p-[10px_7px] rounded-[10px] bg-[#071a33] border border-[#183857] text-center">
                    <b className="block text-[#7dd3fc] text-[14px] font-bold">7,525</b>
                    <small className="block text-[#7891ad] text-[9px] mt-1">Occupied Bins</small>
                  </div>
                  <div className="p-[10px_7px] rounded-[10px] bg-[#071a33] border border-[#183857] text-center">
                    <b className="block text-[#7dd3fc] text-[14px] font-bold">5</b>
                    <small className="block text-[#7891ad] text-[9px] mt-1">Plants</small>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Loading Indicator */}
      {isLoading && (
        <div className="flex gap-[9px] items-start mb-[17px] animate-fade-in">
          <div className="w-[27px] h-[27px] rounded-[9px] bg-[#102b4d] text-[#7dd3fc] grid place-items-center flex-none text-[14px] font-semibold mt-0.5">
            ✦
          </div>
          <div className="p-[10px_14px] rounded-[15px_15px_15px_5px] bg-[#102b4d] border border-[#1b3556] text-[#9fb3cc] text-[12px] flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-[#7dd3fc] animate-ping" />
            <span>Analyzing warehouse query...</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  );
};
