@echo off
REM Lancement rapide du dashboard Streamlit equity curve
cd /d %~dp0
.\.venv\Scripts\streamlit run results\equity_curve_streamlit.py