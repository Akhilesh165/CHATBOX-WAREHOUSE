'use client';

import React, { useState } from 'react';

// Simple demo of a floating chatbot button that opens a right‑side panel.
// This page is completely isolated – it does not import any existing API
// or backend logic. All UI is built with Tailwind CSS which is already
// configured in the project.

export default function DemoChatbot() {
  const [open, setOpen] = useState(false);

  const sampleMessages = [
    { role: 'assistant', text: "Hello! I'm your Warehouse Assistant.\nHow can I help you today?" },
    { role: 'user', text: 'Show me the inventory summary.' },
    { role: 'assistant', text: "Sure. I can help you with inventory, materials, bins and warehouse analytics." },
  ];

  return (
    <div className="relative min-h-screen bg-white overflow-hidden">
      {/* Floating chatbot logo */}
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 rounded-full w-14 h-14 flex items-center justify-center bg-blue-600 text-white shadow-lg hover:shadow-xl hover:scale-105 transition-transform"
        aria-label="Open chat"
      >
        {/* Simple robot emoji as placeholder – replace with an icon if desired */}
        🤖
      </button>

      {/* Overlay (optional) when panel is open */}
      {open && (
        <div
          className="fixed inset-0 bg-black bg-opacity-0 transition-opacity duration-300"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Right‑side chat panel */}
      <div
        className={`fixed top-0 right-0 h-full bg-white shadow-lg border-l border-gray-200 transform ${open ? 'translate-x-0' : 'translate-x-full'} transition-transform duration-300 ease-in-out w-96 max-w-full`}
        style={{ maxWidth: '450px' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center space-x-2">
            <span className="text-2xl">🤖</span>
            <span className="font-semibold">Warehouse Assistant</span>
            <span className="text-xs text-green-600">Online</span>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-gray-500 hover:text-gray-700"
            aria-label="Close chat"
          >
            ×
          </button>
        </div>

        {/* Message list */}
        <div className="p-4 flex-1 overflow-y-auto" style={{ height: 'calc(100% - 140px)' }}>
          {sampleMessages.map((msg, idx) => (
            <div
              key={idx}
              className={`mb-4 flex ${msg.role === 'assistant' ? 'justify-start' : 'justify-end'}`}
            >
              <div
                className={`max-w-xs px-3 py-2 rounded-lg ${msg.role === 'assistant' ? 'bg-gray-100 text-gray-800' : 'bg-blue-600 text-white'}`}
              >
                {msg.text.split('\n').map((line, i) => (
                  <p key={i} className="whitespace-pre-wrap">
                    {line}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Input box */}
        <div className="p-4 border-t border-gray-200 bg-gray-50">
          <input
            type="text"
            placeholder="Type your message..."
            className="w-full border rounded-md px-3 py-2 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            disabled // No backend – disabled for demo purposes
          />
        </div>
      </div>
    </div>
  );
}
