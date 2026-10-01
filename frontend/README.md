# Warehouse Inventory AI Frontend

Next.js + TypeScript + Tailwind CSS chat interface for warehouse operations.

## Features
- **Conversational Chat Interface:** Multi-turn conversational memory with markdown answer rendering.
- **Dynamic Charts:** Automatic rendering of Bar, Line, and Pie charts using Recharts based on LLM query intent.
- **Data Table:** Paginated results table with search filtering and one-click CSV export.
- **Admin SQL View:** Toggleable inspection modal allowing authorized users to inspect the generated SQL and execution metrics.
- **Feedback Controls:** Thumbs up / down rating on assistant answers.
- **Quick Suggested Chips:** Pre-built starter questions for quick operations.

## Running Locally

```bash
npm install
npm run dev
```

The application runs on `http://localhost:3000` and proxies `/api/*` requests to the FastAPI backend on `http://localhost:8000`.
