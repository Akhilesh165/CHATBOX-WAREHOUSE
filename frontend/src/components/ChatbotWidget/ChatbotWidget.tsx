'use client';

import React, { useState } from 'react';
import { ChatbotLauncher } from './ChatbotLauncher';
import { ChatPanel } from './ChatPanel';
import { ChatWidgetMessage } from './ChatMessages';
import { ResponseCardData } from './ResponseCard';

interface ChatbotWidgetProps {
  isOpen?: boolean;
  onToggleOpen?: (open: boolean) => void;
}

const INITIAL_MESSAGES: ChatWidgetMessage[] = [
  {
    id: 'msg-1',
    sender: 'user',
    content: 'Compare the bin utilization of plant 1258 and 7228 in detail',
    timestamp: '10:42 AM',
  },
  {
    id: 'msg-2',
    sender: 'assistant',
    content:
      'Here is the multi-plant bin utilization comparison between Plant 1258 and Plant 7228. Plant 1258 currently operates at higher overall density.',
    timestamp: '10:42 AM',
    cardData: {
      type: 'comparison',
      title: 'Facility Comparison: Plant 1258 vs Plant 7228',
      comparisonData: {
        plantA: {
          name: 'Plant 1258',
          qty: '742,100 Qty',
          materials: '1,453 SKUs',
          bins: '2,840 Bins',
          util: '88.5%',
        },
        plantB: {
          name: 'Plant 7228',
          qty: '518,430 Qty',
          materials: '974 SKUs',
          bins: '1,950 Bins',
          util: '76.2%',
        },
        highlight:
          'Plant 1258 demonstrates +12.3% higher capacity utilization with 2,513 active bins versus 1,485 in Plant 7228.',
      },
    },
  },
  {
    id: 'msg-3',
    sender: 'user',
    content: 'Show top utilized bins for Plant 1258',
    timestamp: '10:44 AM',
  },
  {
    id: 'msg-4',
    sender: 'assistant',
    content:
      'Retrieved the top 5 highest-density storage locations in Plant 1258. Bins BIN-1258-A01 and BIN-1258-A04 are near maximum capacity.',
    timestamp: '10:44 AM',
    cardData: {
      type: 'table',
      title: 'Top Utilized Bins — Plant 1258',
      tableData: [
        { rank: 1, bin: 'BIN-1258-A01', plant: '1258', util: '98.4%' },
        { rank: 2, bin: 'BIN-1258-B14', plant: '1258', util: '96.1%' },
        { rank: 3, bin: 'BIN-1258-A04', plant: '1258', util: '94.7%' },
        { rank: 4, bin: 'BIN-1258-C09', plant: '1258', util: '91.2%' },
        { rank: 5, bin: 'BIN-1258-D22', plant: '1258', util: '89.8%' },
      ],
    },
  },
];

export const ChatbotWidget: React.FC<ChatbotWidgetProps> = ({
  isOpen: controlledIsOpen,
  onToggleOpen,
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatWidgetMessage[]>(INITIAL_MESSAGES);
  const [isLoading, setIsLoading] = useState(false);

  const isControlled = controlledIsOpen !== undefined;
  const isOpen = isControlled ? controlledIsOpen : internalIsOpen;

  const setIsOpen = (nextOpen: boolean) => {
    if (onToggleOpen) {
      onToggleOpen(nextOpen);
    }
    if (!isControlled) {
      setInternalIsOpen(nextOpen);
    }
  };

  const handleReset = () => {
    setMessages(INITIAL_MESSAGES);
  };

  const handleSendMessage = (text: string) => {
    const userMsgId = `user-${Date.now()}`;
    const nowTime = new Date().toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });

    const userMessage: ChatWidgetMessage = {
      id: userMsgId,
      sender: 'user',
      content: text,
      timestamp: nowTime,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    // Mock intelligent response generator based on query semantics
    setTimeout(() => {
      const lower = text.toLowerCase();
      let replyContent = '';
      let replyCard: ResponseCardData | undefined;

      if (lower.includes('compare') || lower.includes('vs') || lower.includes('versus')) {
        replyContent =
          'Multi-plant comparative analysis completed across requested facilities. Metric evaluation shows stable load distribution.';
        replyCard = {
          type: 'comparison',
          title: 'Comparative Utilization Analysis',
          comparisonData: {
            plantA: {
              name: 'Plant 1258',
              qty: '742,100 Qty',
              materials: '1,453 SKUs',
              bins: '2,840 Bins',
              util: '88.5%',
            },
            plantB: {
              name: 'Plant 7228',
              qty: '518,430 Qty',
              materials: '974 SKUs',
              bins: '1,950 Bins',
              util: '76.2%',
            },
            highlight:
              'Plant 1258 holds higher storage density (+12.3%) across high-velocity fast-moving goods aisles.',
          },
        };
      } else if (
        lower.includes('material') ||
        lower.includes('items') ||
        lower.includes('available') ||
        lower.includes('stock')
      ) {
        replyContent =
          'Found 148 active materials stored in Plant 7228. Showing top volume SKUs and storage locations:';
        replyCard = {
          type: 'table',
          title: 'Available Materials in Plant 7228',
          tableData: [
            { rank: 1, bin: 'MAT-7228-091', plant: '7228', util: '94.5%' },
            { rank: 2, bin: 'MAT-7228-104', plant: '7228', util: '88.0%' },
            { rank: 3, bin: 'MAT-7228-312', plant: '7228', util: '82.3%' },
            { rank: 4, bin: 'MAT-7228-044', plant: '7228', util: '79.1%' },
          ],
        };
      } else if (lower.includes('detail') || lower.includes('metric')) {
        replyContent =
          'Detailed operational breakdown for the requested facility. Turnover index and cubic volume metrics:';
        replyCard = {
          type: 'detail',
          title: 'Plant 1258 Detailed Logistics Breakdown',
          summaryText:
            'Total stock quantity is 498,504 units with 1,453 unique materials across 3,762 active bins, leaving 2,425 empty bins.',
        };
      } else if (
        lower.includes('summary') ||
        lower.includes('total') ||
        lower.includes('inventory')
      ) {
        replyContent =
          'Network-wide inventory and bin capacity summary aggregated across all 5 warehouse plants:';
        replyCard = {
          type: 'summary',
          title: 'Total Network Inventory Summary',
          summaryText:
            'Current active storage footprint across all designated warehouse plants.',
          kpis: [
            { label: 'Total Inventory', value: '1,933,031', hint: 'units' },
            { label: 'Unique Materials', value: '974', hint: 'SKUs' },
            { label: 'Occupied Bins', value: '7,525', hint: '84.1% fill' },
          ],
        };
      } else {
        replyContent = `Analyzed your query: "${text}". Storage telemetry is nominal across designated facilities. You can request multi-plant comparisons, top bin rankings, or material lookups.`;
        replyCard = {
          type: 'summary',
          title: 'Quick Operations Snapshot',
          summaryText:
            'Warehouse operations snapshot across North and Eastern distribution hubs.',
          kpis: [
            { label: 'Total Inventory', value: '1,933,031', hint: 'units' },
            { label: 'Unique Materials', value: '974', hint: 'SKUs' },
            { label: 'Occupied Bins', value: '7,525', hint: '84.1% fill' },
          ],
        };
      }

      const botMessage: ChatWidgetMessage = {
        id: `bot-${Date.now()}`,
        sender: 'assistant',
        content: replyContent,
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
        cardData: replyCard,
      };

      setMessages((prev) => [...prev, botMessage]);
      setIsLoading(false);
    }, 600);
  };

  return (
    <>
      {/* State 1: Floating Launcher Button at Bottom-Right */}
      <ChatbotLauncher onClick={() => setIsOpen(true)} isOpen={isOpen} />

      {/* State 2: Slide-in Panel from the Right */}
      <ChatPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        messages={messages}
        onSendMessage={handleSendMessage}
        onReset={handleReset}
        isLoading={isLoading}
      />
    </>
  );
};
