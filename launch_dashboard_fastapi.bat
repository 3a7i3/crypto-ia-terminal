@echo off
REM Lancement rapide du dashboard FastAPI
cd /d %~dp0
.\.venv\Scripts\uvicorn my_trading_system.ui.dashboard_fastapi:app --reload --port 8080