@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
title Bot Finanzas - Diagnostico

rem Muestra todo lo que devuelve el banco de cada cuenta. No envia nada a Telegram.

"%~dp0.venv\Scripts\python.exe" "%~dp0diagnostico.py"
echo.
echo  El resultado se ha guardado en: %~dp0diagnostico.txt
echo  Copialo y pegaselo a Claude (los IBAN salen ocultos).
echo.
pause
