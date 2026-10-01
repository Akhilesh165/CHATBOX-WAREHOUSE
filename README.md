# Warehouse Inventory AI Chatbot

A production-ready AI chatbot for warehouse inventory management that translates natural-language questions into safe, read-only SQL Server queries, validates them using SQLGlot AST, executes them against SQL Server / warehouse database, and presents grounded answers with charts and interactive data tables.

---

## 🏗️ Architecture Flow
```
User Question
     │
     ▼
Next.js / React UI (ChatWindow, FilterChips, Recharts, Pagination)
     │
     ▼
FastAPI Gateway (CORS, Health, Logging, Rate Limits)
     │
     ▼
Query Intent & Context Manager (Multi-turn History Window)
     │
     ▼
LLM SQL Generator (Schema-aware System Prompts, Structured JSON)
     │
     ▼
SQLGlot AST Validator (Read-only check, Table & Column Allowlist, No DDL/DML, No comments)
     │
     ▼
SQL Server Read-Only Connection (wms_chatbot_readonly, Timeouts, Row Capping)
     │
     ▼
Grounded Answer Generator (Summarizes actual DB rows, Never invents figures)
     │
     ▼
Frontend Render (Markdown Answer + Bar/Line/Pie Recharts + Paginated Table + Admin SQL View)
```

---

## 📊 Data Source Contract Compliance
| Target SQL Table | Authoritative Excel Workbook & Sheet | Columns |
|---|---|---|
| `dbo.ZWMS_INVENTORY` | `Bin Invrntory.xlsx` -> `Sheet1` | 18 Columns |
| `dbo.ZWMS_BIN_MASTER` | `WMS Bins Data.xlsx` -> `Bin Master` | 15 Columns |
| `dbo.ZWMS_MATERIAL_MASTER` | `WMS Bins Data.xlsx` -> `Material Master` | 23 Columns |
| *Ignored* | `WMS Bins Data.xlsx` -> `Inventory` | **Explicitly Ignored** |

---

## 📂 Deliverables Directory Structure
```
CHATBOX WAREHOUSE/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic environment configuration
│   │   ├── models.py           # Request / Response schemas & Chart models
│   │   ├── validator.py        # SQLGlot AST security validator
│   │   ├── db.py               # SQLAlchemy pool & read-only execution
│   │   ├── llm.py              # Multi-provider LLM adapter (Gemini / OpenAI)
│   │   └── main.py             # FastAPI router & chat endpoint
│   └── requirements.txt
├── database/
│   ├── 01_schema.sql           # Table creation DDL
│   ├── 02_indexes.sql          # Nonclustered performance indexes
│   ├── 03_views.sql            # Semantic enriched reporting view
│   ├── 04_permissions.sql      # Read-only least-privilege user grants
│   └── 05_seed_queries.sql     # Canonical sample SQL queries
├── data/
│   ├── Bin Invrntory.xlsx      # Authoritative inventory data
│   └── WMS Bins Data.xlsx      # Bin Master & Material Master
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   │   ├── components/
│   │   │   ├── AdminSqlModal.tsx
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── ErrorBanner.tsx
│   │   │   ├── FeedbackButtons.tsx
│   │   │   ├── FilterChips.tsx
│   │   │   ├── InventoryBarChart.tsx
│   │   │   ├── InventoryLineChart.tsx
│   │   │   ├── InventoryPieChart.tsx
│   │   │   ├── LoadingIndicator.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   └── ResultTable.tsx
│   │   └── types/
│   │       └── chat.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── next.config.js
├── prompts/
│   ├── sql_prompt.txt          # Schema-grounded SQL generation prompt
│   ├── answer_prompt.txt       # Grounded conversational answer prompt
│   └── validation_retry_prompt.txt # 1-retry error reflection template
├── scripts/
│   └── import_excel.py         # Authoritative bulk Excel ETL script
├── tests/
│   ├── test_api.py             # FastAPI endpoints test
│   ├── test_data_import.py     # Data schema & column cleaning tests
│   └── test_validator.py       # SQL AST security & allowlist tests
├── docs/
│   ├── API.md                  # Complete API contracts
│   ├── DEPLOYMENT.md           # Step-by-step production deployment guide
│   ├── SAMPLE_QUERIES.md       # Natural language & SQL query mapping
│   ├── SECURITY_CHECKLIST.md   # Production security controls
│   └── PERFORMANCE_CHECKLIST.md # Performance optimizations & indexing
├── .env.example
└── README.md
```

---

## 🚀 Quick Start

### 1. Ingest Data
```bash
python scripts/import_excel.py --inventory "data/Bin Invrntory.xlsx" --masters "data/WMS Bins Data.xlsx"
```

### 2. Run Backend Tests
```bash
pytest
```

### 3. Start Backend Server
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to interact with the Warehouse AI Chatbot.
