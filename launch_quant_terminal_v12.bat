@echo off
REM Lancement rapide du dashboard Panel V12
cd /d %~dp0
.\.venv\Scripts\panel serve quant_hedge_ai\dashboard\quant_terminal_v12.py --show --port 5010