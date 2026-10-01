@echo off
title Warehouse Inventory AI - Launcher
color 0b
echo ======================================================
echo   WAREHOUSE INVENTORY AI - STARTING SERVICES
echo ======================================================
echo.

echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
start "Warehouse Backend (Port 8000)" cmd /k "title Warehouse Backend & python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 >nul

echo [2/2] Starting Next.js Frontend on http://localhost:3000 ...
start "Warehouse Frontend (Port 3000)" cmd /k "title Warehouse Frontend & cd frontend & npm run dev"

timeout /t 3 >nul

echo.
echo ======================================================
echo   ALL SERVICES ARE LIVE!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000/docs
echo ======================================================
echo.
pause
