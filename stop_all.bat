@echo off
setlocal

echo ============================================================
echo   AI Quant Platform - Stop All
echo   V12 Dashboard (5010) + 3D Evolution Viewer (8501)
echo ============================================================
echo.

REM === Arrêt par port ===
REM 5010 = V12 Dashboard (Panel)
REM 8501 = 3D Evolution Viewer (Streamlit)
REM Anciens ports legacy (V13/V16/V26 dans _old/) : 5011, 5013, 5026 — supprimer la ligne suivante si vous ne voulez plus les checker
for %%P in (5010 8501 5011 5013 5026) do (
    for /f "tokens=5" %%I in ('netstat -ano ^| findstr :%%P ^| findstr LISTENING') do (
        echo [STOP] Port %%P -^> PID %%I
        taskkill /PID %%I /F >nul 2>&1
    )
)

REM === Arrêt par nom de processus Python ===
REM Cible les processus Python qui exécutent les scripts du projet
for %%S in (main_v91.py evolution_3d_view.py streamlit_dashboard.py quant_terminal_v12.py) do (
    for /f "tokens=2 delims== " %%I in ('wmic process where "name='python.exe' and commandline like '%%%%S%%'" get ProcessId /value 2^>nul ^| find "ProcessId="') do (
        echo [STOP] %%S -^> PID %%I
    )
    wmic process where "name='python.exe' and commandline like '%%%%S%%'" call terminate >nul 2>&1
)

echo.
echo Stop requests sent.
timeout /t 2 /nobreak >nul
