'use client';

import React, { useState } from 'react';
import { ChatWindow } from '../components/ChatWindow';
import { DashboardBackground, ChatbotWidget } from '../components/ChatbotWidget';
import { CHATBOT_UI_PROTOTYPE } from '../config/uiConfig';

export default function Home() {
  const [isChatOpen, setIsChatOpen] = useState(false);

  // When CHATBOT_UI_PROTOTYPE is false (HOLD / DISABLED):
  // Renders the original, clean testing interface directly without any prototype dashboard,
  // banner, launcher button, or right-side panel.
  if (!CHATBOT_UI_PROTOTYPE) {
    return (
      <div className="h-screen w-screen overflow-hidden flex flex-col">
        <ChatWindow />
      </div>
    );
  }

  // When CHATBOT_UI_PROTOTYPE is true:
  // Renders the new dark dashboard with floating launcher & slide-over assistant panel.
  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100 overflow-x-hidden">
      <DashboardBackground
        onOpenChatbot={() => setIsChatOpen(true)}
        isChatOpen={isChatOpen}
      />
      <ChatbotWidget
        isOpen={isChatOpen}
        onToggleOpen={(open) => setIsChatOpen(open)}
      />
    </div>
  );
}
