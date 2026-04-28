@echo off
REM Lancement rapide de l'API Dashboard FastAPI
cd /d %~dp0
.\.venv\Scripts\uvicorn crypto_quant_v16.supervision.dashboard_api:app --reload --port 8084