@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
title Bot Finanzas - Reconectar banco

rem Vuelve a autorizar el acceso de solo lectura a N26 (cuando caduca el permiso).
rem No hace falta reiniciar el bot: usara la conexion nueva automaticamente.

"%~dp0.venv\Scripts\python.exe" "%~dp0configurar.py" --reconectar
pause
