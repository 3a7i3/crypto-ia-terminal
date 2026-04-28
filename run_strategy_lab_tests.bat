@echo off
REM Script pour lancer les tests strategy_lab depuis le bon dossier
cd /d %~dp0\quant-hedge-ai
c:\Users\WINDOWS\crypto_ai_terminal\.venv\Scripts\python.exe -m unittest %*
