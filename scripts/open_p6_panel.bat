@echo off
title P6 Behavioral Health — Tunnel SSH
echo Ouverture du tunnel SSH vers le VPS...
echo Laissez cette fenetre ouverte pendant que vous utilisez le panel.
echo.
echo Fermez cette fenetre pour couper le tunnel.
echo.

:: Ouvrir le navigateur apres 4 secondes
start "" /B cmd /c "timeout /t 4 /nobreak > nul && start http://localhost:8501"

:: Tunnel SSH (bloquant — maintient la connexion)
"C:\Program Files\Git\usr\bin\ssh.exe" -L 8501:localhost:8501 -N -i "C:\Users\WINDOWS\.ssh\gcp_key" mathieuhasard111@34.171.188.99

echo.
echo Tunnel ferme.
pause
