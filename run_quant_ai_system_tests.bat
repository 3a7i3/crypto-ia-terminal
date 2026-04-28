@echo off
REM Script pour lancer les tests pytest dans quant-ai-system avec la bonne structure d'import
cd /d %~dp0quant-ai-system
python -m pytest %*
cd /d %~dp0
