@echo off
REM Lancement rapide de l'API BotDoctor FastAPI
cd /d %~dp0
.\.venv\Scripts\uvicorn supervision.botdoctor_api:app --reload --port 8082