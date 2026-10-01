'use client';

import React from 'react';
import { ChatWindow } from '../components/ChatWindow';

export default function Home() {
  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col">
      <ChatWindow />
    </div>
  );
}
