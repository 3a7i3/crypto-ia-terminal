@echo off
REM Lancement rapide du dashboard Panel Overview
cd /d %~dp0
.\.venv\Scripts\panel serve quant-trading-system\dashboard\panel_overview.py --show --port 5013