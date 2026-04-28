@echo off
REM Lancement rapide du dashboard Panel V16
cd /d %~dp0
.\.venv\Scripts\panel serve crypto_quant_v16\ui\quant_dashboard.py --show --port 5012