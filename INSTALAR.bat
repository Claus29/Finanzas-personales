@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"

rem ============================================================
rem  Bot Finanzas - Instalador (tambien sirve para reparar)
rem  Descarga Python si hace falta, descarga el bot de GitHub,
rem  instala todo, te guia en la configuracion y deja el bot
rem  funcionando y arrancando solo con Windows.
rem ============================================================

set "REPO=Claus29/Finanzas-personales"
set "RAMA=claude/sweet-thompson-41bsdc"
set "DIR=%LOCALAPPDATA%\FinanzasBot"
set "PYVER=3.12.10"
set "VPY=%DIR%\.venv\Scripts\python.exe"

rem Si se ejecuta desde la carpeta del bot, se copia a TEMP: la actualizacion sobrescribe ese archivo.
if /i "%~dp0"=="%DIR%\" (
    copy /y "%~f0" "%TEMP%\FinanzasBot_instalar.bat" >nul
    "%TEMP%\FinanzasBot_instalar.bat" %*
)

if /i "%~1"=="--actualizar" (set "ACCION=Actualizando") else (set "ACCION=Instalando")
title Bot Finanzas - %ACCION%
echo.
echo  ==========================================================
echo     BOT FINANZAS - %ACCION%
echo  ==========================================================
echo.

rem ---------- 1. Python ----------
echo [1/7] Comprobando Python...
call :buscar_python
if not defined PY (
    echo       Python no esta instalado. Instalandolo, espera unos minutos...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    call :buscar_python
)
if not defined PY (
    echo       Descargando Python desde python.org...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile (Join-Path $env:TEMP 'python-instalador.exe')" || goto :error
    "%TEMP%\python-instalador.exe" /quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 || goto :error
    call :buscar_python
)
if not defined PY (
    echo       No he podido instalar Python.
    goto :error
)
echo       OK: %PY%

rem ---------- 2. Descargar el bot ----------
rem Se descarga y se comprueba en TEMP antes de tocar nada de la instalacion actual.
echo [2/7] Descargando la ultima version del bot desde GitHub...
set "NUEVO=%TEMP%\FinanzasBot_nuevo"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $zip=Join-Path $env:TEMP 'FinanzasBot.zip'; $tmp=Join-Path $env:TEMP 'FinanzasBot_extraido'; $nuevo='%NUEVO%'; foreach ($p in $tmp, $nuevo) { if (Test-Path $p) { Remove-Item $p -Recurse -Force } }; Invoke-WebRequest 'https://github.com/%REPO%/archive/refs/heads/%RAMA%.zip' -OutFile $zip; Expand-Archive $zip $tmp -Force; Move-Item (Get-ChildItem $tmp -Directory)[0].FullName $nuevo; Remove-Item $zip, $tmp -Recurse -Force; foreach ($f in 'bot.py', 'configurar.py', 'requirements.txt', 'accesos_directos.ps1') { if (-not (Test-Path (Join-Path $nuevo $f))) { throw ('Descarga incompleta: falta ' + $f) } }; try { $c=(Invoke-RestMethod 'https://api.github.com/repos/%REPO%/commits?sha=%RAMA%&per_page=1')[0]; $v=$c.commit.committer.date + ' ' + $c.sha.Substring(0,7); Set-Content (Join-Path $nuevo 'version.txt') $v; Write-Host ('      Version: ' + $v) } catch {}" || goto :error

rem ---------- 3. Parar el bot si estaba en marcha ----------
echo [3/7] Parando el bot si estaba en marcha...
call :parar_bot

rem ---------- 4. Copiar archivos ----------
rem Solo se copian los archivos del programa: .env, la clave .pem y los datos no se tocan.
echo [4/7] Copiando archivos...
robocopy "%NUEVO%" "%DIR%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :error
rmdir /s /q "%NUEVO%" >nul 2>&1

rem ---------- 5. Dependencias ----------
echo [5/7] Instalando lo que necesita el bot (puede tardar un par de minutos)...
if not exist "%VPY%" (
    "%PY%" -m venv "%DIR%\.venv" || goto :error
)
"%VPY%" -m pip install --upgrade pip -q --disable-pip-version-check >nul 2>&1
"%VPY%" -m pip install -r "%DIR%\requirements.txt" -q --disable-pip-version-check || goto :error

rem ---------- 6. Configuracion ----------
rem Solo pregunta lo que falte en el .env: en una actualizacion normal no pregunta nada.
echo [6/7] Configuracion...
"%VPY%" "%DIR%\configurar.py" || goto :error

rem ---------- 7. Arranque automatico y puesta en marcha ----------
echo [7/7] Creando accesos directos y abriendo la ventana del bot...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%\accesos_directos.ps1" || goto :error
start "" "%DIR%\BOT.bat"
timeout /t 8 /nobreak >nul
call :bot_en_marcha
if errorlevel 1 (
    echo.
    echo  [ERROR] El bot no ha arrancado. Ultimas lineas del registro:
    powershell -NoProfile -Command "if (Test-Path '%DIR%\bot.log') { Get-Content '%DIR%\bot.log' -Tail 15 }"
    goto :error
)

echo.
echo  ==========================================================
echo     TODO LISTO. El bot esta funcionando.
echo  ==========================================================
echo   - Se ha abierto la ventana "Bot Finanzas": ahi ves lo que hace el bot.
echo     No la cierres, puedes minimizarla. Se abre sola al encender el PC.
echo   - Cada dia a las 00:00 recibiras tu saldo de N26 en Telegram.
echo   - Si el PC estaba apagado a las 00:00, te lo envia al encenderlo.
echo   - En el chat del bot tienes el boton "Ver saldo" para verlo cuando quieras.
echo   - En el escritorio tienes:
echo       "Bot Finanzas"                     para volver a abrir la ventana del bot
echo       "Bot Finanzas - Actualizar"        para instalar novedades
echo       "Bot Finanzas - Reconectar banco"  cuando caduque el permiso de N26
echo       "Bot Finanzas - Diagnostico"       si el saldo no cuadra
echo.
pause
exit /b 0

rem ============================================================
:buscar_python
set "PY="
for %%C in ("py -3" "python") do (
    if not defined PY (
        for /f "delims=" %%E in ('%%~C -c "import sys; print(sys.executable) if sys.version_info >= (3, 10) else None" 2^>nul') do set "PY=%%E"
    )
)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b 0

:parar_bot
rem Cierra la ventana del bot (BOT.bat) y el propio bot, este en ventana o en segundo plano.
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process; $p | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*FinanzasBot*\BOT.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; $p | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*FinanzasBot*\bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
exit /b 0

:bot_en_marcha
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*FinanzasBot*\bot.py*' }) { exit 0 } else { exit 1 }"
exit /b %errorlevel%

:error
echo.
echo  [ERROR] Algo ha fallado. Haz una captura de esta ventana y enviasela a Claude.
rem Si el bot ya estaba instalado, se vuelve a arrancar para no dejarte sin el.
if exist "%DIR%\.env" if exist "%DIR%\BOT.bat" if exist "%VPY%" (
    call :bot_en_marcha || start "" "%DIR%\BOT.bat"
)
echo.
pause
exit /b 1
