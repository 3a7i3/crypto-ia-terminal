@echo off
REM Lancement rapide du dashboard Dash
cd /d %~dp0
.\.venv\Scripts\python quant-trading-system\dashboard\dash_app.py