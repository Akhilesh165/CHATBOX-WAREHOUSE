# Deployment Instructions

## System Prerequisites
- Python 3.10+ (Tested on Python 3.10, 3.11, 3.12, 3.14)
- Node.js 18+ and npm
- Microsoft SQL Server 2017+ (or Azure SQL Database)
- Microsoft ODBC Driver 18 for SQL Server (or Driver 17)

---

## 1. Database Setup
1. Connect to your SQL Server instance using SSMS, Azure Data Studio, or `sqlcmd`.
2. Execute the DDL script to create the database and tables:
   ```bash
   sqlcmd -S localhost -U sa -P YourSaPassword -i database/01_schema.sql
   ```
3. Create performance indexes:
   ```bash
   sqlcmd -S localhost -d WarehouseDB -U sa -P YourSaPassword -i database/02_indexes.sql
   ```
4. Create the enriched reporting view:
   ```bash
   sqlcmd -S localhost -d WarehouseDB -U sa -P YourSaPassword -i database/03_views.sql
   ```
5. Configure the read-only application user:
   ```bash
   sqlcmd -S localhost -d WarehouseDB -U sa -P YourSaPassword -i database/04_permissions.sql
   ```

---

## 2. Data Ingestion
Run the authoritative Excel data import script:
```bash
python scripts/import_excel.py --inventory "data/Bin Invrntory.xlsx" --masters "data/WMS Bins Data.xlsx" --if-exists replace
```

*Data Contract Rules enforced:*
- Authoritative inventory is sourced ONLY from `Bin Invrntory.xlsx` -> `Sheet1`.
- Bin Master and Material Master are sourced ONLY from `WMS Bins Data.xlsx`.
- The `Inventory` sheet in `WMS Bins Data.xlsx` is strictly ignored.

---

## 3. Backend Deployment
1. Configure environment variables in `.env`:
   ```ini
   SQL_SERVER=your-sql-server-host
   SQL_DATABASE=WarehouseDB
   SQL_USERNAME=wms_chatbot_readonly
   SQL_PASSWORD=YourSecureReadOnlyPassword
   LLM_PROVIDER=gemini
   LLM_API_KEY=your-gemini-or-openai-key
   LLM_MODEL=gemini-1.5-pro
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run test suite:
   ```bash
   pytest
   ```
4. Start production FastAPI server with Uvicorn:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

---

## 4. Frontend Deployment
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   npm install
   ```
2. Build for production:
   ```bash
   npm run build
   ```
3. Start Next.js production server:
   ```bash
   npm run start
   ```
