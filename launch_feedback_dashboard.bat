@echo off
REM Lancement rapide du dashboard feedback Streamlit
cd /d %~dp0
.\.venv\Scripts\streamlit run ai_autonomous_loop\feedback_dashboard.py