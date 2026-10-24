# Reglas del proyecto (léelas antes de cambiar nada)

Bot de Telegram de finanzas personales para Windows. El usuario NO programa: instala con
`INSTALAR.bat` y actualiza con el acceso directo «Bot Finanzas - Actualizar», que descarga el
último `INSTALAR.bat` de la rama `claude/sweet-thompson-41bsdc` y lo ejecuta con `--actualizar`.
Toda actualización debe funcionar con ese doble clic, sin que el usuario toque nada.

## Funcionalidad (v5)

- El banco se consulta UNA vez al día (`actualizacion.py`, hora `HORA_SALDO_DIARIO`, 00:00 por
  defecto) o con «🔄 Actualizar ahora» (Ajustes, con confirmación). Descarga saldos y movimientos
  de todas las cuentas. Es silenciosa: NUNCA envía mensajes. Ningún otro botón consulta al banco.
- Lo que se descubre de madrugada (pagos detectados, gastos grandes) va a `cola_avisos` y se envía
  desde las 09:00. Ningún aviso automático a las 00:00 (`avisos.py`).
- Saldo = suma de las cuentas. Saldo neto = saldo − pendiente del ciclo (`deudas.pendientes`):
  de las deudas a plazos solo la cuota del ciclo; lo pagado no se resta; «al cobrar» se resta
  desde que se registra el salario; «me deben» nunca.
- Ciclo = del último salario registrado al siguiente (`ciclo.py`); cobro esperado entre
  `DIA_COBRO_DESDE` y `DIA_COBRO_HASTA` (3–7). El recordatorio del cobro insiste hasta registrarlo.
- Teclado: Saldo, Análisis, Deudas, Metas, Recordatorios, Ajustes (`bot.py`). Pasos guiados con
  `context.user_data["espera"]`; botones con prefijos en `callback_data` (máx. 64 bytes: usar ids
  numéricos, p. ej. `rowid` de movimientos).
- Datos del usuario en `datos.db` (SQLite, `datos.py`), copia diaria en `copias/`. El esquema solo
  se amplía con `CREATE TABLE IF NOT EXISTS` / columnas nuevas con valor por defecto: nunca borrar
  ni renombrar tablas o columnas.
- Si el permiso de N26 caduca, el bot sigue funcionando y la autenticación se pide en la misma
  ventana en segundo plano (`autenticacion.en_segundo_plano`).

## Una sola ventana, un solo bot

- `principal.py` reserva un puerto local (`instancia.py`): si ya hay un bot, trae su ventana al
  frente y sale con código 4 (`BOT.bat` cierra esa ventana).
- Configuración, autenticación con N26 y bot ocurren en el mismo proceso y ventana.
- Accesos directos y arranque con Windows usan `lanzador.py` (pythonw), que nunca abre una segunda
  ventana.
- `INSTALAR.bat` y `ACTUALIZAR.bat` no abren ventanas nuevas: al terminar hacen `call BOT.bat` en la
  misma. `parar_bot.ps1` cierra el bot y su ventana (de cualquier versión) sin cerrar la propia.

## Compatibilidad con instalaciones existentes

- Nunca renombres ni elimines claves del `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `EB_APP_ID`,
  `EB_KEY_PATH`, `EB_SESSION_ID`, `EB_COUNTRY`, `EB_REDIRECT_URL`, `ZONA_HORARIA`,
  `LIMITE_CONSULTAS_DIA`, `HORA_SALDO_DIARIO`, `SALDO_DIARIO_ACTIVO`, `DIA_COBRO_DESDE`, `DIA_COBRO_HASTA`,
  `PRESUPUESTO_CICLO`, `UMBRAL_SALDO_BAJO`, `AVISO_*`).
  Una clave nueva debe tener valor por defecto (`config.POR_DEFECTO`) o pedirse solo si falta.
- La actualización copia los archivos del repositorio encima de `%LOCALAPPDATA%\FinanzasBot` con
  robocopy y borra una lista fija de archivos obsoletos (en `INSTALAR.bat`). Los archivos que genera
  el bot (`.env`, `*.pem`, `bot.log`, `datos.db`, `copias/`, `conexion.json`, `contador_api.json`,
  `ultimo_saldo.json`, `ultima_consulta.txt`, `version*.txt`) van en `.gitignore` y nunca en el repositorio.
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
