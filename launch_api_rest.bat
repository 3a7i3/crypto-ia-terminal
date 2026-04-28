@echo off
REM Lancement rapide de l'API REST BotDoctor FastAPI
cd /d %~dp0
.\.venv\Scripts\uvicorn supervision.api_rest:app --reload --port 8083