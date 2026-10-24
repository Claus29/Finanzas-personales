@echo off
setlocal EnableExtensions
title Bot Finanzas - Actualizando

rem Descarga el ultimo instalador y lo ejecuta en ESTA MISMA ventana.
rem Al terminar, esta ventana pasa a ser la del bot (no se abre ninguna otra).
rem Tu configuracion (.env), tu clave .pem y la conexion con el banco se conservan.

set "REPO=Claus29/Finanzas-personales"
set "RAMA=claude/sweet-thompson-41bsdc"
set "INSTALADOR=%TEMP%\FinanzasBot_instalar_%RANDOM%%RANDOM%.bat"

echo Buscando la ultima version en GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest ('https://raw.githubusercontent.com/%REPO%/refs/heads/%RAMA%/INSTALAR.bat?t=' + [guid]::NewGuid()) -OutFile '%INSTALADOR%'"
if errorlevel 1 goto :sin_conexion
"%INSTALADOR%" --actualizar

:sin_conexion
echo.
echo  [ERROR] No he podido conectar con GitHub. Revisa tu conexion a internet.
echo  El bot sigue con la version actual. Arrancando en 10 segundos...
timeout /t 10 >nul
if exist "%~dp0BOT.bat" call "%~dp0BOT.bat"
