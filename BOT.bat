@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
title Bot Finanzas
cd /d "%~dp0"

rem Si el bot ya estaba en marcha (en otra ventana o en segundo plano), se cierra para que no haya dos.
powershell -NoProfile -Command "$yo = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID)).ParentProcessId; $p = Get-CimInstance Win32_Process; $p | Where-Object { $_.Name -eq 'cmd.exe' -and $_.ProcessId -ne $yo -and $_.CommandLine -like '*FinanzasBot*\BOT.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; $p | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*FinanzasBot*\bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo  ==========================================================
echo     BOT FINANZAS - funcionando
echo  ==========================================================
echo   No cierres esta ventana: si la cierras, el bot se detiene.
echo   Puedes minimizarla. Para volver a abrirla: "Bot Finanzas" en el escritorio.
echo.

:bucle
".venv\Scripts\python.exe" bot.py
echo.
echo  El bot se ha detenido. Se vuelve a arrancar en 30 segundos.
echo  Si quieres pararlo del todo, cierra esta ventana.
timeout /t 30 /nobreak >nul
goto bucle
