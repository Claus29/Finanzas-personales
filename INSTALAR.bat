@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"

rem ============================================================
rem  Bot Finanzas - Instalador y actualizador (tambien repara)
rem  Todo ocurre en ESTA ventana: instala o actualiza y, al terminar,
rem  esta misma ventana pasa a ser la del bot. No se abre ninguna otra.
rem  Se conservan .env, la clave .pem y la conexion con el banco.
rem ============================================================

set "REPO=Claus29/Finanzas-personales"
set "RAMA=claude/sweet-thompson-41bsdc"
set "DIR=%LOCALAPPDATA%\FinanzasBot"
set "PYVER=3.12.10"
set "VPY=%DIR%\.venv\Scripts\python.exe"
set "NUEVO=%TEMP%\FinanzasBot_nuevo_%RANDOM%%RANDOM%"
set "COPIA=%TEMP%\FinanzasBot_instalar_%RANDOM%%RANDOM%.bat"

rem Si se ejecuta desde la carpeta del bot, se copia a TEMP: la actualizacion sobrescribe ese archivo.
if /i "%~dp0"=="%DIR%\" (
    copy /y "%~f0" "%COPIA%" >nul
    "%COPIA%" %*
)

if /i "%~1"=="--actualizar" (set "ACCION=Actualizando") else (set "ACCION=Instalando")
title Bot Finanzas - %ACCION%
echo.
echo  ==========================================================
echo     BOT FINANZAS - %ACCION%
echo  ==========================================================
set "ANTES=ninguna"
if exist "%DIR%\version.txt" set /p ANTES=<"%DIR%\version.txt"
echo   Version instalada: %ANTES%
echo.

rem ---------- 1. Python ----------
echo [1/6] Comprobando Python...
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

rem ---------- 2. Descargar y comprobar la version nueva (sin tocar nada todavia) ----------
echo [2/6] Descargando la ultima version del bot desde GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $zip=Join-Path $env:TEMP 'FinanzasBot.zip'; $tmp=Join-Path $env:TEMP 'FinanzasBot_extraido'; $nuevo='%NUEVO%'; foreach ($p in $zip, $tmp, $nuevo) { if (Test-Path $p) { Remove-Item $p -Recurse -Force } }; Invoke-WebRequest 'https://github.com/%REPO%/archive/refs/heads/%RAMA%.zip' -OutFile $zip; Expand-Archive $zip $tmp -Force; Move-Item (Get-ChildItem $tmp -Directory)[0].FullName $nuevo; Remove-Item $zip, $tmp -Recurse -Force; foreach ($f in 'principal.py', 'bot.py', 'bot_deudas.py', 'datos.py', 'actualizacion.py', 'avisos.py', 'lanzador.py', 'BOT.bat', 'requirements.txt', 'parar_bot.ps1', 'accesos_directos.ps1') { if (-not (Test-Path (Join-Path $nuevo $f))) { throw ('Descarga incompleta: falta ' + $f) } }; try { $c=(Invoke-RestMethod 'https://api.github.com/repos/%REPO%/commits?sha=%RAMA%&per_page=1')[0]; $v=$c.commit.committer.date + ' ' + $c.sha.Substring(0,7); Set-Content (Join-Path $nuevo 'version.txt') $v; Write-Host ('      Version nueva:     ' + $v) } catch { Write-Host '      Version nueva: (no disponible)' }" || goto :error
set "DESPUES="
if exist "%NUEVO%\version.txt" set /p DESPUES=<"%NUEVO%\version.txt"
if defined DESPUES if "%DESPUES%"=="%ANTES%" echo       Ya tenias la ultima version: se reinstala igualmente.

rem ---------- 3. Cerrar el bot que este funcionando (y su ventana) ----------
echo [3/6] Cerrando el bot si estaba abierto...
powershell -NoProfile -ExecutionPolicy Bypass -File "%NUEVO%\parar_bot.ps1"

rem ---------- 4. Copiar archivos ----------
rem Solo se copian los archivos del programa: .env, la clave .pem y los datos no se tocan.
echo [4/6] Copiando archivos...
robocopy "%NUEVO%" "%DIR%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :error
rmdir /s /q "%NUEVO%" >nul 2>&1
rem Archivos de versiones anteriores que ya no se usan.
for %%F in (RECONECTAR_BANCO.bat DIAGNOSTICO.bat diagnostico.py diagnostico.txt conectar_banco.py saldo.py) do (
    if exist "%DIR%\%%F" del /q "%DIR%\%%F" >nul 2>&1
)

rem ---------- 5. Dependencias ----------
echo [5/6] Instalando lo que necesita el bot (la primera vez puede tardar unos minutos)...
if not exist "%VPY%" (
    "%PY%" -m venv "%DIR%\.venv" || goto :error
)
"%VPY%" -m pip install --upgrade pip -q --disable-pip-version-check >nul 2>&1
"%VPY%" -m pip install -r "%DIR%\requirements.txt" -q --disable-pip-version-check || goto :error

rem ---------- 6. Accesos directos ----------
echo [6/6] Creando accesos directos...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%\accesos_directos.ps1" || goto :error

echo.
echo  ==========================================================
echo     TODO LISTO
echo  ==========================================================
echo   - Esta ventana es ahora la del bot. No la cierres, puedes minimizarla.
echo   - Si es la primera vez o el permiso de N26 caduco, aqui mismo se te pedira.
echo   - En Telegram: Saldo, Analisis, Deudas, Metas, Recordatorios y Ajustes.
echo   - El banco se consulta una vez al dia (00:00) en silencio. Tus datos estan en datos.db.
echo   - En el escritorio: "Bot Finanzas" y "Bot Finanzas - Actualizar".
echo.
call "%DIR%\BOT.bat"
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

:error
echo.
echo  [ERROR] Algo ha fallado. Haz una captura de esta ventana y enviasela a Claude.
if exist "%DIR%\BOT.bat" if exist "%VPY%" (
    echo  El bot arrancara en 30 segundos con lo que haya instalado.
    timeout /t 30 >nul
    call "%DIR%\BOT.bat"
    exit /b 1
)
echo.
pause
exit /b 1
