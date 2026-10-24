# Reglas del proyecto (léelas antes de cambiar nada)

Bot de Telegram de finanzas personales para Windows. El usuario NO programa: instala con
`INSTALAR.bat` y actualiza con el acceso directo «Bot Finanzas - Actualizar», que descarga el
último `INSTALAR.bat` de la rama `claude/sweet-thompson-41bsdc` y lo ejecuta con `--actualizar`.
Toda actualización debe funcionar con ese doble clic, sin que el usuario toque nada.

## Compatibilidad con instalaciones existentes

- Nunca renombres ni elimines claves del `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `EB_APP_ID`,
  `EB_KEY_PATH`, `EB_SESSION_ID`, `EB_COUNTRY`, `EB_REDIRECT_URL`, `ZONA_HORARIA`).
  Una clave nueva debe tener valor por defecto en el código o pedirse en `configurar.py` solo si falta.
- La actualización copia los archivos del repositorio encima de `%LOCALAPPDATA%\FinanzasBot` con
  robocopy (sin borrar nada). Los archivos que genera el bot (`.env`, `*.pem`, `bot.log`,
  `ultima_consulta.txt`, `version_anunciada.txt`, `version.txt`, bases de datos) van en `.gitignore`
  y nunca en el repositorio, o se sobrescribirían los del usuario.
- Si un archivo deja de usarse, el código nuevo no debe depender de que haya desaparecido.
- Dependencias en `requirements.txt` con límite de versión mayor (`<N`).
- Cambios visibles en Telegram: sube `VERSION` y reescribe `NOVEDADES` en `bot.py`
  (el bot las anuncia una vez por Telegram tras actualizar).

## Archivos .bat y .ps1

- Solo ASCII (sin tildes ni ñ). Los `.bat` con finales de línea CRLF (`.gitattributes` los marca
  `-text`; al editarlos, conserva el CRLF).
- `INSTALAR.bat` es idempotente: instala, repara y actualiza. Si se ejecuta desde la carpeta de
  instalación se copia a TEMP antes de seguir (la actualización lo sobrescribe).
- `ACTUALIZAR.bat` debe seguir siendo mínimo: solo descarga `INSTALAR.bat` y lo ejecuta.
- El bot funciona en una ventana visible (`BOT.bat`, el usuario quiere verla abierta), que arranca
  con Windows y desde el acceso directo «Bot Finanzas». `BOT.bat` cierra cualquier otra instancia
  al abrirse; `INSTALAR.bat` (`:parar_bot`) cierra la ventana y el bot antes de actualizar.

## Comportamiento que hay que respetar

- El bot solo habla con `TELEGRAM_CHAT_ID`.
- Saldo automático: una única consulta al banco al día (00:00, o al volver la conexión).
- Banco solo lectura (AIS). Nada de pagos (PIS).

## Antes de subir

- `python -m py_compile *.py` y pruebas con el banco y Telegram simulados
  (este entorno no tiene acceso a api.enablebanking.com ni a Windows).
- Comprueba que el ZIP de la rama y el `INSTALAR.bat` en raw se descargan, y que el .bat llega en CRLF.
