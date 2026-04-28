@echo off
REM Lancement rapide de l'API Monitoring FastAPI
cd /d %~dp0
.\.venv\Scripts\uvicorn supervision.monitoring_api:app --reload --port 8081