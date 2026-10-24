@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
title Bot Finanzas
cd /d "%~dp0"

rem Ventana del bot. principal.py garantiza que solo haya un bot: si ya hay otro abierto,
rem trae su ventana al frente y sale con el codigo 4, y esta ventana se cierra.

:bucle
".venv\Scripts\python.exe" principal.py
if "%errorlevel%"=="4" goto :ya_abierto
echo.
echo  El bot se ha detenido. Se vuelve a arrancar en 30 segundos.
echo  Si quieres pararlo del todo, cierra esta ventana.
timeout /t 30 /nobreak >nul
goto bucle

:ya_abierto
timeout /t 3 /nobreak >nul
exit
