@echo off
REM Lancement rapide du dashboard Panel Quant Terminal
cd /d %~dp0
.\.venv\Scripts\panel serve quant_hedge_ai\dashboard\dashboard_quant_terminal.py --show --port 5011