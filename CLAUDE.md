# Reglas del proyecto (léelas antes de cambiar nada)

Bot de Telegram de finanzas personales para Windows. El usuario NO programa: instala con
`INSTALAR.bat` y actualiza con el acceso directo «Bot Finanzas - Actualizar», que descarga el
último `INSTALAR.bat` de la rama `claude/sweet-thompson-41bsdc` y lo ejecuta con `--actualizar`.
Toda actualización debe funcionar con ese doble clic, sin que el usuario toque nada.

## Funcionalidad (v4)

- Teclado de Telegram con dos botones: «💰 Ver saldo» y «⚙️ Ajustes».
- Ajustes (botones en línea): límite diario de consultas (1–20, 4 por defecto, aviso si > 4),
  hora del saldo automático (00:00 por defecto) y activarlo/desactivarlo.
- Contador de consultas al banco (`contador.py`): una consulta = una lectura de saldos de todas las
  cuentas elegidas. Se reinicia a las 00:00. Lo que no llega al banco (sin red, permiso caducado)
  se devuelve. Pulsar de nuevo en 10 minutos repite el último saldo sin gastar consulta.
- Saldo automático a la hora elegida, una vez al día; si el PC estaba apagado, en cuanto vuelve.

## Una sola ventana, un solo bot

- `principal.py` reserva un puerto local (`instancia.py`): si ya hay un bot, trae su ventana al
  frente y sale con código 4 (`BOT.bat` cierra esa ventana).
- Configuración, autenticación con N26 y bot ocurren en el mismo proceso y ventana. Si el permiso
  caduca mientras funciona, `bot.ejecutar()` devuelve "reautenticar" y `principal.py` pide la
  autenticación en la misma ventana y vuelve a arrancar el bot.
- Accesos directos y arranque con Windows usan `lanzador.py` (pythonw), que nunca abre una segunda
  ventana.
- `INSTALAR.bat` y `ACTUALIZAR.bat` no abren ventanas nuevas: al terminar hacen `call BOT.bat` en la
  misma. `parar_bot.ps1` cierra el bot y su ventana (de cualquier versión) sin cerrar la propia.

## Compatibilidad con instalaciones existentes

- Nunca renombres ni elimines claves del `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `EB_APP_ID`,
  `EB_KEY_PATH`, `EB_SESSION_ID`, `EB_COUNTRY`, `EB_REDIRECT_URL`, `ZONA_HORARIA`,
  `LIMITE_CONSULTAS_DIA`, `HORA_SALDO_DIARIO`, `SALDO_DIARIO_ACTIVO`).
  Una clave nueva debe tener valor por defecto (`config.POR_DEFECTO`) o pedirse solo si falta.
- La actualización copia los archivos del repositorio encima de `%LOCALAPPDATA%\FinanzasBot` con
  robocopy y borra una lista fija de archivos obsoletos (en `INSTALAR.bat`). Los archivos que genera
  el bot (`.env`, `*.pem`, `bot.log`, `conexion.json`, `contador_api.json`, `ultimo_saldo.json`,
  `ultima_consulta.txt`, `version*.txt`) van en `.gitignore` y nunca en el repositorio.
- Si un archivo deja de usarse, añádelo a la lista de obsoletos de `INSTALAR.bat`.
- Dependencias en `requirements.txt` con límite de versión mayor (`<N`).
- Cambios visibles en Telegram: sube `VERSION` y reescribe `NOVEDADES` en `bot.py`
  (el bot las anuncia una vez por Telegram tras actualizar).

## Archivos .bat y .ps1

- Solo ASCII (sin tildes ni ñ). Los `.bat` con finales de línea CRLF (`.gitattributes` los marca
  `-text`; al editarlos, conserva el CRLF).
- `INSTALAR.bat` es idempotente: instala, repara y actualiza. Si se ejecuta desde la carpeta de
  instalación se copia a TEMP antes de seguir. Descarga y verifica en TEMP antes de cerrar el bot.
- `ACTUALIZAR.bat` debe seguir siendo mínimo: solo descarga `INSTALAR.bat` y lo ejecuta.

## Comportamiento que hay que respetar

- El bot solo habla con `TELEGRAM_CHAT_ID` (mensajes y botones de Ajustes).
- Banco solo lectura (AIS). Nada de pagos (PIS).
- Mensajes de Telegram en HTML (`parse_mode="HTML"`), escapando los textos que vienen del banco.

## Antes de subir

- `python -m py_compile *.py` y pruebas con el banco y Telegram simulados (servidor HTTP local
  con `Application.builder().base_url(...)`): este entorno no tiene acceso a
  api.enablebanking.com, a api.telegram.org ni a Windows.
- Comprueba que el ZIP de la rama y el `INSTALAR.bat` en raw se descargan, y que el .bat llega en CRLF.
