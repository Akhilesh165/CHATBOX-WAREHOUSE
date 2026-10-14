import React from 'react';
import './globals.css';

export const metadata = {
  title: 'Warehouse Inventory AI Chatbot',
  description: 'Production Warehouse AI assistant for inventory, bins, materials, and plants.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="h-full antialiased bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-200">
        {children}
      </body>
    </html>
  );
}
