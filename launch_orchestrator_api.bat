@echo off
REM Lancement rapide de l'API HTTP orchestrateur (FastAPI exemple)
cd /d %~dp0
.\.venv\Scripts\uvicorn orchestration.api_orchestrator:app --reload --port 8090
