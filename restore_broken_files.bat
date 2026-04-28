@echo off
REM ============================================================
REM   Wrapper pour restore_broken_files.ps1
REM   Usage : restore_broken_files.bat [-DryRun]
REM ============================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore_broken_files.ps1" %*
