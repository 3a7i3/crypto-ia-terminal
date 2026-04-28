@echo off
REM Lancement rapide du dashboard BotDoctor Streamlit
cd /d %~dp0
.\.venv\Scripts\streamlit run supervision\botdoctor_dashboard.py