'use client';

import React, { useState, useEffect } from 'react';
import { ChatWindow } from '../components/ChatWindow';
import { DashboardBackground, ChatbotWidget } from '../components/ChatbotWidget';
import { CHATBOT_UI_PROTOTYPE } from '../config/uiConfig';
import { WarehouseStatsResponse } from '../types/dashboard';

export default function Home() {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [stats, setStats] = useState<WarehouseStatsResponse | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  // Fetch actual distinct plant count and live summary directly from backend
  useEffect(() => {
    let isMounted = true;
    async function fetchStats() {
      try {
        const res = await fetch('/api/dashboard/stats');
        if (res.ok) {
          const data: WarehouseStatsResponse = await res.json();
          if (isMounted) {
            setStats(data);
          }
        }
      } catch (err) {
        console.error('Failed to load live warehouse stats:', err);
      } finally {
        if (isMounted) {
          setIsLoadingStats(false);
        }
      }
    }

    fetchStats();
    return () => {
      isMounted = false;
    };
  }, []);

  // When CHATBOT_UI_PROTOTYPE is false: Renders original standalone chat testing interface
  if (!CHATBOT_UI_PROTOTYPE) {
    return (
      <div className="h-screen w-screen overflow-hidden flex flex-col">
        <ChatWindow />
      </div>
    );
  }

  // When CHATBOT_UI_PROTOTYPE is true: Clean, modern enterprise light dashboard & chatbot
  return (
    <div className="relative min-h-screen bg-[#f8fafc] text-slate-800 overflow-x-hidden selection:bg-blue-100 selection:text-blue-900">
      <DashboardBackground
        onOpenChatbot={() => setIsChatOpen(true)}
        isChatOpen={isChatOpen}
        stats={stats}
        isLoading={isLoadingStats}
      />
      <ChatbotWidget
        isOpen={isChatOpen}
        onToggleOpen={(open) => setIsChatOpen(open)}
        stats={stats}
      />
    </div>
  );
}
