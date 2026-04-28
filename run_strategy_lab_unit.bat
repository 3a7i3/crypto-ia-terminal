@echo off
REM Script pour lancer uniquement les tests du dossier strategy_lab (exclusion des tests globaux)
cd /d %~dp0\quant-hedge-ai
c:\Users\WINDOWS\crypto_ai_terminal\.venv\Scripts\python.exe -m unittest discover -s strategy_lab -p "test_*.py" %*
