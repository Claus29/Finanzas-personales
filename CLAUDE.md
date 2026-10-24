# Reglas del proyecto (léelas antes de cambiar nada)

Bot de Telegram de finanzas personales para Windows. El usuario NO programa: instala con
`INSTALAR.bat` y actualiza con el acceso directo «Bot Finanzas - Actualizar», que descarga el
último `INSTALAR.bat` de la rama `claude/sweet-thompson-41bsdc` y lo ejecuta con `--actualizar`.
Toda actualización debe funcionar con ese doble clic, sin que el usuario toque nada.

## Funcionalidad (v5 + v6 + v7 + v8)

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
- v6 · Deudas con `sentido` («debo» / «me_deben»; columna añadida en `datos.migrar`). Tipos por sentido
  en `deudas.TIPOS_POR_SENTIDO`: debo = fecha, cobro, plazos, fijo, suscripcion; me_deben = fecha,
  plazos, sin_fecha. Lo que te deben NUNCA se suma al saldo neto (se muestra aparte).
- v6 · Recordatorio el día de pago para todo lo que tiene día de pago (debo, me deben, aplazado,
  suscripciones), y cada día si se atrasa (desde la v7, en la franja de deudas; ver abajo).
- v7 · Deudas a plazos llevadas por lo que QUEDA (total − pagos; `deudas.restante`): se crean con total
  + cuota fija o total + nº de cuotas, y lo ya pagado (pago con periodo «inicial»). «Otra cantidad» cubre
  el periodo y la diferencia va al final. `modo`: dia (día fijo, periodo AAAA-MM), cobro (cada salario,
  periodo = fecha del salario), sin (sin día fijo, solo «me_deben»). Una cuota no pagada en su periodo
  NUNCA cuenta como pagada: tabla `saltos` con «pasar» (todo el plan se retrasa) o «juntas» (se paga con
  la siguiente); `si_no_paga` por deuda: preguntar (por defecto) / pasar / juntas.
- v7 · «cobro» = pago único al cobrar (una vez); «fijo» con modo cobro = gasto fijo en cada cobro.
- v7 · Recordatorios de deudas repartidos en `FRANJA_DEUDAS_DESDE`–`HASTA` (08:00–14:00), por prioridad;
  sustituyen a `HORA_AVISO_PAGO` (clave conservada, sin uso). NADA se da por pagado: cada recordatorio
  pide confirmación, «🙈 Ignorar» lo repite al día siguiente, el día del cobro van en «¡Cobrado!» y desde
  el día siguiente uno a uno. La detección en el banco PREGUNTA («¿Es el pago de X?»), no marca.
  Lo que te deben sin día fijo: preguntas los días `DIAS_AVISO_SIN_DIA` (5,15,25).
- v7 · Interfaz de deudas en `bot_deudas.py` (bot.py le delega pasos «deuda_*» y prefijos de PREFIJOS);
  análisis de deudas en `analisis_deudas.py` (semáforo % salario comprometido: <30 % / 30–40 % / >40 %).
- v8 · Metas en sus propias cuentas (`metas.py`): `uid` = cuenta/Espacio de N26 (lo ahorrado es su saldo) o manual.
  Aportación de cada ciclo: `aporte_modo` «necesaria» (calculada al empezar el ciclo) o «fija» (`aporte_fijo`);
  siempre se pide esa, salvo que el usuario elija «otra cantidad» o «este mes no» en ese ciclo (`aportes_ciclo`).
  `recordar`: cobro / cobro1 (por defecto) / dia:N. El recordatorio se repite cada día en la franja de deudas
  hasta confirmar (`mt:ok|otra|no|ig`). El bot NUNCA mueve dinero: calcula, recuerda y comprueba. Si la cuenta de
  una meta sube, PREGUNTA si es la aportación; si llega al objetivo, PREGUNTA si la da por conseguida (`mt:fin`).
- v8 · Al cobrar, plan completo (`analisis.texto_al_cobrar`): atrasado, fijos, cuotas, metas con cuenta destino y
  lo que queda para gastar. La detección de la nómina (`movimientos.candidato_nomina`, `nom:si/no`) no se toca.
- v8 · Colchón de emergencia (`colchon.py`): meta especial (`especial = 'colchon'`), DESACTIVADO por defecto
  (`COLCHON_ACTIVO=0`, `COLCHON_MESES=3`); objetivo = meses × gasto medio (90 días); se activa en Ajustes.
- v8 · Interfaz de metas y colchón en `bot_metas.py` (pasos «meta_*»/«col_*», prefijos en PREFIJOS; los botones
  antiguos g:, gs:, ma:, mo: siguen funcionando). Dinero libre = neto − cuentas de metas − aportaciones pendientes.
- v8 · «🧭 Análisis completo» (`analisis_completo.py`, botones `ac:*`): Ahora, Por meses (ciclos de cobro), Anual,
  Flujo de caja (cascada), Metas, Salud financiera, Trayectoria; cada pantalla con gráfico y «💡 Qué significa».
  Índice de salud 0–100 (`PESOS`: ahorro 25, endeudamiento 20, colchón 20, presupuesto 15, puntualidad 10,
  metas 10), solo con lo que tiene datos (el colchón solo si está activo). Gráficos en `graficos.py`
  (azul #2a78d6 entradas/totales, naranja #eb6834 salidas, verde #1baf7a tercera serie; sin emojis en etiquetas).
- El banco solo se consulta en: actualización diaria, su recuperación si el PC estaba apagado,
  «Actualizar ahora» y tras renovar el permiso (si ese día no había datos). El usuario pidió dejarlo así.

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
  `PRESUPUESTO_CICLO`, `UMBRAL_SALDO_BAJO`, `HORA_AVISO_PAGO`, `FRANJA_DEUDAS_DESDE`, `FRANJA_DEUDAS_HASTA`,
  `DIAS_AVISO_SIN_DIA`, `COLCHON_ACTIVO`, `COLCHON_MESES`, `AVISO_*`).
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
