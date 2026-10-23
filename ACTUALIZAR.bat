@echo off
setlocal EnableExtensions
title Bot Finanzas - Actualizar

rem Descarga la ultima version del instalador y la ejecuta en modo actualizacion.
rem Tu configuracion (.env), tu clave .pem y la conexion con el banco se conservan.

set "REPO=Claus29/Finanzas-personales"
set "RAMA=claude/sweet-thompson-41bsdc"

echo Buscando la ultima version en GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest ('https://raw.githubusercontent.com/%REPO%/refs/heads/%RAMA%/INSTALAR.bat?t=' + [guid]::NewGuid()) -OutFile (Join-Path $env:TEMP 'FinanzasBot_instalar.bat')"
if errorlevel 1 (
    echo.
    echo  [ERROR] No he podido conectar con GitHub. Revisa tu conexion a internet.
    pause
    exit /b 1
)
"%TEMP%\FinanzasBot_instalar.bat" --actualizar
