@echo off
REM Script de lancement rapide pour le dashboard Streamlit
cd /d %~dp0
.\.venv\Scripts\streamlit run dashboard\alert_dashboard.py