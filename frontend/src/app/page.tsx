'use client';

import React, { useState } from 'react';
import { DashboardBackground, ChatbotWidget } from '../components/ChatbotWidget';
import { ChatWindow } from '../components/ChatWindow';
import { LayoutDashboard, MessageSquare } from 'lucide-react';

export default function Home() {
  const [viewMode, setViewMode] = useState<'prototype' | 'fullscreen'>('prototype');
  const [isChatOpen, setIsChatOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100 overflow-x-hidden">
      {/* Top Floating View Mode Switcher */}
      <div className="fixed top-3 right-4 sm:right-6 z-30 flex items-center bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg p-0.5 shadow-lg">
        <button
          onClick={() => setViewMode('prototype')}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
            viewMode === 'prototype'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="Dark Theme Widget Prototype (Default)"
        >
          <LayoutDashboard className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Prototype UI</span>
        </button>
        <button
          onClick={() => setViewMode('fullscreen')}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
            viewMode === 'fullscreen'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="Legacy Fullscreen Chat"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Fullscreen</span>
        </button>
      </div>

      {viewMode === 'prototype' ? (
        <>
          {/* Dark-Theme Sample Dashboard Background */}
          <DashboardBackground
            onOpenChatbot={() => setIsChatOpen(true)}
            isChatOpen={isChatOpen}
          />

          {/* Interactive Chatbot Widget: Floating Bottom-Right Button + Slide-in Right Panel */}
          <ChatbotWidget
            isOpen={isChatOpen}
            onToggleOpen={(open) => setIsChatOpen(open)}
          />
        </>
      ) : (
        <div className="h-screen w-screen overflow-hidden flex flex-col pt-12 sm:pt-0">
          <ChatWindow />
        </div>
      )}
    </div>
  );
}
