"""Bot de Telegram de finanzas personales (v8).

- El banco solo se consulta en la actualización diaria (00:00 por defecto, en silencio) o con
  «Actualizar ahora» en Ajustes. Todos los botones calculan al momento con esos datos.
- Teclado: 💰 Saldo · 📊 Análisis · 💳 Deudas · 🎯 Metas · ⏰ Recordatorios · ⚙️ Ajustes.
- Avisos (avisos.py) revisados cada minuto; nunca a las 00:00.
- Si el permiso de N26 caduca, el bot sigue funcionando con los últimos datos y la ventana pide
  renovarlo en segundo plano.
Solo habla con TELEGRAM_CHAT_ID. Lo arranca principal.py.
"""
import asyncio
import html
import logging
from datetime import date, time, timedelta

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import actualizacion
import analisis
import analisis_completo
import autenticacion
import avisos
import bot_deudas
import bot_metas
import bot_proyeccion
import ciclo
import colchon
import config
import consultas
import contador
import datos
import deudas
import exportar
import graficos
import metas
import movimientos
from formato import (DIAS_SEMANA, euros, euros_cortos, leer_entero, leer_fecha, leer_hora, leer_importe,
                     sumar_meses)
from movimientos import CATEGORIAS

# Súbelo y cambia NOVEDADES en cada actualización con cambios visibles: el bot las anuncia una vez.
VERSION = 9
NOVEDADES = ("✨ <b>Bot actualizado: versión 9</b>\n\n"
             "• 📈 <b>Nuevo botón «Proyección»</b> (junto a Saldo): cómo se reparte tu salario en cada cobro hasta el mes "
             "que elijas. Gastos fijos, suscripciones, cuotas, pagos únicos, metas y lo que te devuelven. "
             "<b>Cuánto te queda libre en cada cobro</b> y con cuánto dinero acabas.\n"
             "• 🟢🟡🔴 Te dice si tu configuración es <b>sostenible</b>, cuál es el cobro más justo y cuánto podrías "
             "destinar como máximo a tus metas.\n"
             "• 📅 Mes a mes, 🗓️ calendario (cuándo terminas cada deuda y consigues cada meta), 🎯 metas y "
             "🧪 «¿y si…?» (cobrar más o menos, sin lo que te deben, sin metas).\n"
             "• ⚖️ <b>Ajustar</b>: propuestas para que sea sostenible (recortar, alargar fechas, priorizar) o para "
             "acelerar tus metas. Las aplicas con un toque (y se pueden deshacer) o las ignoras. Y un simulador para "
             "probar cambios en cada meta.\n"
             "• 💶 Usa tu último salario o uno estimado que escribas tú.\n"
             "• 🖤 Gráficos nuevos en negro, más detallados.")
VERSION_ANUNCIADA = config.BASE / "version_anunciada.txt"

B_SALDO, B_ANALISIS, B_DEUDAS, B_METAS, B_RECORDATORIOS, B_AJUSTES, B_PROYECCION = (
    "💰 Saldo", "📊 Análisis", "💳 Deudas", "🎯 Metas", "⏰ Recordatorios", "⚙️ Ajustes", "📈 Proyección")
BOTONES_VIEJOS = {"💰 Ver saldo": B_SALDO}  # teclados de versiones anteriores que aún tenga el móvil
TECLADO = ReplyKeyboardMarkup([[KeyboardButton(B_SALDO), KeyboardButton(B_PROYECCION)],
                               [KeyboardButton(B_ANALISIS), KeyboardButton(B_DEUDAS)],
                               [KeyboardButton(B_METAS), KeyboardButton(B_RECORDATORIOS)],
                               [KeyboardButton(B_AJUSTES)]],
                              resize_keyboard=True, is_persistent=True)
AVISOS_CONFIGURABLES = [
    ("AVISO_DEUDAS", "💳 Lo que debes (deudas, cuotas, fijos, suscripciones)"),
    ("AVISO_ME_DEBEN", "🤝 Lo que te deben"),
    ("AVISO_METAS", "🎯 Apartar para las metas"),
    ("AVISO_RESUMEN_SEMANAL", "📅 Resumen semanal (domingo 20:00)"),
    ("AVISO_RESUMEN_CICLO", "📆 Resumen del ciclo al cobrar"),
    ("AVISO_SALDO_BAJO", "⚠️ Saldo neto bajo"),
    ("AVISO_RITMO", "📉 Ritmo de gasto"),
    ("AVISO_GASTO_GRANDE", "💸 Gasto grande"),
    ("AVISO_SUSCRIPCIONES", "🔍 Revisar suscripciones (día 1)"),
]
COMPROBAR_ACTUALIZACION = 10 * 60
COMPROBAR_PERMISO = 60 * 60

estado = {"chat_id": None}
candado_banco = asyncio.Lock()
detalle = logging.getLogger("detalle")


def e(texto):
    return html.escape(str(texto))


def teclado(filas):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in fila] for fila in filas])


CANCELAR = [("❌ Cancelar", "cancelar")]


async def mostrar(update: Update, context, texto, filas=None, nuevo=False):
    """Edita el mensaje del botón pulsado (si se puede) o envía uno nuevo."""
    marcado = teclado(filas) if filas else None
    consulta = update.callback_query
    if consulta and not nuevo and consulta.message and consulta.message.text:
        try:
            await consulta.edit_message_text(texto, parse_mode="HTML", reply_markup=marcado)
            return
        except BadRequest as error:
            if "not modified" in str(error).lower():
                return
    await context.bot.send_message(estado["chat_id"], texto, parse_mode="HTML",
                                   reply_markup=marcado or (TECLADO if not filas else None))


async def enviar(context, texto, filas=None):
    await context.bot.send_message(estado["chat_id"], texto, parse_mode="HTML",
                                   reply_markup=teclado(filas) if filas else None)


def esperar(context, paso, **datos_paso):
    context.user_data["espera"] = {"paso": paso, **datos_paso}


async def avisar_proyeccion(context):
    """Tras apuntar una deuda o una meta: si algún cobro futuro deja de llegar, lo avisa."""
    import proyeccion
    try:
        aviso = await asyncio.to_thread(proyeccion.aviso_si_insostenible)
    except Exception:
        detalle.exception("No se pudo calcular la proyección")
        return
    if aviso:
        await enviar(context, aviso, [[("📈 Ver proyección", "pr:res"), ("⚖️ Ajustar", "pr:aju")]])


def con_deshacer(accion_id, filas=None):
    return (filas or []) + [[("↩️ Deshacer", f"des:{accion_id}")]]


# =====================================================================
# Pantallas
# =====================================================================

async def pantalla_saldo(update, context, nuevo=False):
    await mostrar(update, context, analisis.texto_saldo(),
                  [[("🧮 Saldo neto", "m:neto"), ("💶 Registrar cobro", "cobro:nuevo")],
                   [("🧾 Movimientos", "m:movs"), ("📈 Evolución", "a:evo:30")]], nuevo)


async def pantalla_analisis(update, context, nuevo=False):
    await mostrar(update, context, "📊 <b>Análisis</b>\nTodo calculado con tus datos de "
                                   f"{analisis.texto_actualizado().lower().replace('actualizado ', '')}. ¿Qué quieres ver?",
                  [[("🧭 Análisis completo", "ac:menu")],
                   [("📆 Ciclo actual", "a:ciclo"), ("🎯 Presupuesto", "a:pres")],
                   [("🧩 Categorías", "a:cat:ciclo"), ("📈 Evolución", "a:evo:30")],
                   [("📅 Semana", "a:sem"), ("🔁 Suscripciones", "a:subs")],
                   [("💳 Deudas", "ad:res"), ("🏷️ Corregir categoría", "a:corregir")]], nuevo)


async def pantalla_deudas(update, context, nuevo=False):
    await bot_deudas.pantalla(update, context, nuevo)


async def pantalla_metas(update, context, nuevo=False):
    await bot_metas.pantalla(update, context, nuevo)


async def pantalla_recordatorios(update, context, nuevo=False):
    propios = datos.todos("SELECT * FROM recordatorios WHERE activo >= 0 AND (activo = 1 OR frecuencia != 'una') ORDER BY id")
    desde, hasta = config.dias_cobro()
    lineas = ["⏰ <b>Recordatorios</b>", "",
              f"💶 Cobro: desde el día {desde}, insistiendo hasta que lo registres (siempre activo)"]
    lineas += [f"{'🔔' if config.aviso_activo(c) else '🔕'} {n}" for c, n in AVISOS_CONFIGURABLES]
    lineas.append(f"<i>Los de deudas se reparten entre las {texto_franja()} y piden confirmación.\n"
                  "Los avisos se activan o desactivan en ⚙️ Ajustes › Avisos.</i>")
    lineas += ["", "<b>Tus recordatorios:</b>"]
    if propios:
        lineas += [f"{'🔔' if r['activo'] else '🔕'} {e(r['texto'])} · {avisos.describir_recordatorio(r)}" for r in propios]
    else:
        lineas.append("Aún no tienes. Crea uno con «➕ Nuevo» (por ejemplo: «Pagar la tarjeta» el día 25).")
    filas = [[("➕ Nuevo", "r:nuevo")]]
    filas += [[(f"{'🔕 Pausar' if r['activo'] else '🔔 Activar'} «{r['texto'][:15]}»", f"r:tog:{r['id']}"),
               ("🗑️", f"r:bo:{r['id']}")] for r in propios]
    await mostrar(update, context, "\n".join(lineas), filas, nuevo)


def texto_franja():
    (h1, m1), (h2, m2) = config.franja_deudas()
    return f"{h1:02d}:{m1:02d}–{h2:02d}:{m2:02d}"


def texto_ajustes():
    usadas, limite = contador.estado()
    horas, minutos = config.hora_saldo_diario()
    desde, hasta = config.dias_cobro()
    presupuesto = config.importe("PRESUPUESTO_CICLO")
    umbral = config.importe("UMBRAL_SALDO_BAJO")
    texto = ("⚙️ <b>Ajustes</b>\n\n"
             f"🔄 Actualización con el banco: cada día a las <b>{horas:02d}:{minutos:02d}</b> (en silencio)\n"
             f"🔢 Consultas al banco hoy: {usadas}/{limite} (límite diario, también para «Actualizar ahora»)\n"
             f"💶 Cobro: entre el día <b>{desde}</b> y el <b>{hasta}</b>\n"
             f"🔔 Recordatorios de deudas: entre las <b>{texto_franja()}</b>\n"
             f"🤝 Lo que te deben sin día fijo: te pregunto los días {', '.join(map(str, config.dias_aviso_sin_dia()))}\n"
             f"🎯 Presupuesto por ciclo: {euros_cortos(presupuesto) if presupuesto else 'sin límite'}\n"
             f"⚠️ Aviso de saldo neto bajo: {('por debajo de ' + euros_cortos(umbral)) if umbral else 'desactivado'}\n"
             f"{bot_metas.linea_ajustes()}")
    if limite > config.LIMITE_RECOMENDADO:
        texto += f"\n\n⚠️ Con más de {config.LIMITE_RECOMENDADO} consultas al día, N26 podría rechazar algunas."
    return texto


def filas_ajustes():
    horas, minutos = config.hora_saldo_diario()
    desde, hasta = config.dias_cobro()
    return [[("➖", "aj:lim:-"), (f"Límite: {config.limite_diario()}/día", "nada"), ("➕", "aj:lim:+")],
            [(f"⏰ Hora de actualización: {horas:02d}:{minutos:02d}", "aj:hora")],
            [(f"💶 Días de cobro: {desde}–{hasta}", "aj:cobro")],
            [(f"🔔 Recordatorios de deudas: {texto_franja()}", "aj:fr")],
            [(f"🤝 Sin día fijo: días {'·'.join(map(str, config.dias_aviso_sin_dia()))}", "aj:ds")],
            [("🎯 Presupuesto", "aj:pres"), ("⚠️ Saldo bajo", "aj:umbral")],
            [(bot_metas.linea_ajustes(), "col:ver")],
            [("🔔 Avisos", "aj:avisos"), ("🔄 Actualizar ahora", "aj:act")],
            [("📤 Exportar a Excel", "aj:exp"), ("✖️ Cerrar", "aj:cerrar")]]


async def pantalla_ajustes(update, context, nuevo=False):
    await mostrar(update, context, texto_ajustes(), filas_ajustes(), nuevo)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE, boton):
    context.user_data.pop("espera", None)
    pantallas = {B_SALDO: pantalla_saldo, B_ANALISIS: pantalla_analisis, B_DEUDAS: pantalla_deudas,
                 B_METAS: pantalla_metas, B_RECORDATORIOS: pantalla_recordatorios, B_AJUSTES: pantalla_ajustes,
                 B_PROYECCION: bot_proyeccion.pantalla}
    await pantallas[boton](update, context, nuevo=True)


async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("espera", None)
    await update.message.reply_text(
        "✅ <b>Bot activo</b>\nUsa los botones de abajo. Tus datos se actualizan con el banco cada día a las "
        f"{config.valor('HORA_SALDO_DIARIO')} en silencio; todo lo demás se calcula al momento.",
        parse_mode="HTML", reply_markup=TECLADO)


# =====================================================================
# Mensajes de texto (botones del teclado y respuestas a preguntas)
# =====================================================================

async def texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    escrito = update.message.text.strip()
    boton = BOTONES_VIEJOS.get(escrito, escrito)
    if boton in (B_SALDO, B_ANALISIS, B_DEUDAS, B_METAS, B_RECORDATORIOS, B_AJUSTES, B_PROYECCION):
        await menu(update, context, boton)
        return
    espera = context.user_data.get("espera")
    if not espera:
        await inicio(update, context)
        return
    await responder_pregunta(update, context, espera, escrito)


async def repetir(update, mensaje):
    await update.message.reply_text(f"❌ {mensaje}", parse_mode="HTML", reply_markup=teclado([CANCELAR]))


async def responder_pregunta(update, context, espera, escrito):
    paso = espera["paso"]
    hoy = config.ahora().date()

    # --- Cobro
    if paso == "cobro_importe":
        importe = leer_importe(escrito)
        if not importe:
            return await repetir(update, "Escribe solo el importe, por ejemplo <b>1850</b> o <b>1.850,50</b>.")
        esperar(context, "cobro_tipo", importe=importe)
        return await enviar(context, f"💶 {euros(importe)}. ¿Qué es?",
                            [[("💶 Mi salario", "cobro:t:salario"), ("💰 Otro ingreso", "cobro:t:otro")], CANCELAR])
    if paso == "cobro_fecha":
        fecha = leer_fecha(escrito, hoy)
        if not fecha or fecha > hoy:
            return await repetir(update, "Escribe la fecha como <b>05/11</b> (no puede ser futura).")
        return await guardar_cobro(update, context, espera["importe"], espera["tipo"], fecha)

    # --- Deudas
    if paso.startswith("deuda_") and await bot_deudas.responder(update, context, espera, escrito):
        return None

    # --- Proyección
    if paso.startswith("proy_") and await bot_proyeccion.responder(update, context, espera, escrito):
        return None

    # --- Metas y colchón
    if paso.startswith(("meta_", "col_")) and await bot_metas.responder(update, context, espera, escrito):
        return None

    # --- Recordatorios
    if paso == "rec_texto":
        esperar(context, "rec_frecuencia", texto=escrito[:120])
        return await enviar(context, "¿Cada cuánto?", [[("Una vez", "rf:una"), ("Cada día", "rf:diaria")],
                                                       [("Cada semana", "rf:semanal"), ("Cada mes", "rf:mensual")], CANCELAR])
    if paso == "rec_fecha":
        fecha = leer_fecha(escrito, hoy)
        if not fecha or fecha < hoy:
            return await repetir(update, "Escribe la fecha como <b>25/11</b>.")
        esperar(context, "rec_hora", **{**{k: v for k, v in espera.items() if k != "paso"}, "fecha": fecha.isoformat()})
        return await preguntar_hora(context, "rh")
    if paso == "rec_dia_mes":
        dia = leer_entero(escrito, 1, 31)
        if not dia:
            return await repetir(update, "Escribe un día del 1 al 31.")
        esperar(context, "rec_hora", **{**{k: v for k, v in espera.items() if k != "paso"}, "dia_mes": dia})
        return await preguntar_hora(context, "rh")
    if paso == "rec_hora":
        hora = leer_hora(escrito)
        if not hora:
            return await repetir(update, "Escribe la hora como <b>09:30</b>, o elige un botón.")
        return await crear_recordatorio(context, espera, hora)

    # --- Ajustes
    if paso == "aj_dias_sin":
        dias = sorted({n for n in (leer_entero(x, 1, 31) for x in escrito.replace(" ", "").split(",")) if n})
        if not dias:
            return await repetir(update, "Escribe días del 1 al 31 separados por comas, por ejemplo <b>1, 10, 20</b>.")
        context.user_data.pop("espera", None)
        config.guardar("DIAS_AVISO_SIN_DIA", ",".join(map(str, dias)))
        await enviar(context, "✅ Guardado.")
        return await pantalla_ajustes(update, context, nuevo=True)
    if paso in ("aj_pres", "aj_umbral"):
        importe = 0.0 if escrito.strip() == "0" else leer_importe(escrito)
        if importe is None:
            return await repetir(update, "Escribe un importe (0 para quitarlo).")
        context.user_data.pop("espera", None)
        config.guardar("PRESUPUESTO_CICLO" if paso == "aj_pres" else "UMBRAL_SALDO_BAJO", importe)
        await enviar(context, "✅ Guardado.")
        return await pantalla_ajustes(update, context, nuevo=True)

    context.user_data.pop("espera", None)
    await inicio(update, context)


async def preguntar_hora(context, prefijo, texto="¿A qué hora? Elige o escribe (ej. <b>09:30</b>):"):
    horas = [7, 8, 9, 10, 12, 14, 16, 18, 19, 20, 21, 22]
    filas = [[(f"{h:02d}:00", f"{prefijo}:{h:02d}:00") for h in horas[n:n + 4]] for n in range(0, 12, 4)]
    await enviar(context, texto, filas + [CANCELAR])


# =====================================================================
# Acciones
# =====================================================================

async def guardar_cobro(update, context, importe, tipo, fecha, movimiento_id=None):
    context.user_data.pop("espera", None)
    if not movimiento_id and tipo == "salario":
        # Si el banco ya trajo ese ingreso, se enlaza para no proponerlo como nómina.
        parecido = datos.uno("SELECT id FROM movimientos WHERE interno = 0 AND importe > 0 AND ABS(importe - ?) <= 1 "
                             "AND fecha >= ? AND fecha <= ? ORDER BY fecha DESC LIMIT 1", importe,
                             (fecha - timedelta(days=4)).isoformat(), (fecha + timedelta(days=4)).isoformat())
        movimiento_id = parecido["id"] if parecido else None
    anterior = ciclo.inicio(fecha - timedelta(days=1))
    ingreso = datos.ejecutar("INSERT INTO ingresos (fecha, importe, tipo, movimiento_id, creado) VALUES (?, ?, ?, ?, ?)",
                             fecha.isoformat(), importe, tipo, movimiento_id, config.ahora().isoformat())
    accion = datos.registrar_accion("ingresos", ingreso, "DELETE FROM ingresos WHERE id = ?1",
                                    f"Cobro de {euros(importe)}")
    nombre = "Salario" if tipo == "salario" else "Ingreso"
    await enviar(context, f"✅ {nombre} de <b>{euros(importe)}</b> registrado ({fecha:%d/%m}).", con_deshacer(accion))
    logging.info("%s registrado: %s", nombre, euros(importe))
    if tipo == "salario":
        datos.ejecutar("DELETE FROM pospuestos WHERE clave = 'cobro'")
        if config.aviso_activo("AVISO_RESUMEN_CICLO") and anterior < fecha:
            await enviar(context, analisis.texto_resumen_ciclo_cerrado(anterior, fecha))
        colchon.actualizar_objetivo()
        filas = []
        if deudas.pendientes():
            filas.append([("✅ Marcar pagos hechos", "d:pagar")])
        if any(metas.pendiente_ciclo(m) > 0 for m in metas.activas()):
            filas.append([("🎯 Marcar dinero movido", "mt:lista")])
        await enviar(context, analisis.texto_al_cobrar(), filas or None)


async def crear_recordatorio(context, espera, hora):
    context.user_data.pop("espera", None)
    rec_id = datos.ejecutar("INSERT INTO recordatorios (texto, frecuencia, fecha, dia_semana, dia_mes, hora, creado) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)", espera["texto"], espera["frecuencia"], espera.get("fecha"),
                            espera.get("dia_semana"), espera.get("dia_mes"), hora, config.ahora().isoformat())
    accion = datos.registrar_accion("recordatorios", rec_id, "DELETE FROM recordatorios WHERE id = ?1", "Recordatorio")
    r = datos.uno("SELECT * FROM recordatorios WHERE id = ?", rec_id)
    await enviar(context, f"✅ Te recordaré «{e(r['texto'])}» {avisos.describir_recordatorio(r)}.",
                 con_deshacer(accion, [[("⏰ Ver recordatorios", "m:rec")]]))


# =====================================================================
# Botones (callback)
# =====================================================================

async def pulsar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    consulta = update.callback_query
    if update.effective_chat.id != estado["chat_id"]:
        await consulta.answer()
        return
    dato = consulta.data
    aviso = None
    try:
        aviso = await atender_boton(update, context, dato)
    finally:
        try:
            await consulta.answer(aviso)
        except BadRequest:
            pass


async def atender_boton(update, context, dato):  # noqa: C901  (enrutador de botones)
    partes = dato.split(":")
    clave = partes[0]
    hoy = config.ahora().date()

    if dato == "nada":
        return None
    if dato == "borrar":
        await update.callback_query.message.delete()
        return None
    if dato == "cancelar":
        context.user_data.pop("espera", None)
        await mostrar(update, context, "Cancelado.")
        return None
    if clave in ("des", "desl"):
        descripcion = datos.deshacer(int(partes[1]), minutos=10 if clave == "des" else 4320)
        if descripcion:
            await mostrar(update, context, f"↩️ Deshecho: {e(descripcion)}.")
            return "Deshecho"
        return "Ya no se puede deshacer"

    # --- Menús
    if clave == "m":
        pantallas = {"saldo": pantalla_saldo, "deudas": pantalla_deudas, "metas": pantalla_metas,
                     "rec": pantalla_recordatorios, "ajustes": pantalla_ajustes, "analisis": pantalla_analisis}
        if partes[1] in pantallas:
            await pantallas[partes[1]](update, context)
        elif partes[1] == "neto":
            await mostrar(update, context, analisis.texto_neto(), [[("⬅️ Saldo", "m:saldo")]])
        elif partes[1] == "movs":
            await mostrar(update, context, analisis.texto_movimientos(12),
                          [[("🏷️ Corregir una categoría", "a:corregir")], [("⬅️ Saldo", "m:saldo")]])
        return None

    # --- Análisis
    if clave == "a":
        volver = [[("⬅️ Análisis", "m:analisis")]]
        if partes[1] == "ciclo":
            await mostrar(update, context, analisis.texto_ciclo(), volver)
        elif partes[1] == "pres":
            await mostrar(update, context, analisis.texto_presupuesto(), [[("✏️ Cambiar presupuesto", "aj:pres")]] + volver)
        elif partes[1] == "sem":
            await mostrar(update, context, analisis.texto_semana(), volver)
        elif partes[1] == "subs":
            filas = [[(f"➕ Apuntar {x['nombre'][:20]} ({euros_cortos(x['importe'])})", f"sub:{n}")]
                     for n, x in enumerate(analisis.suscripciones_sin_apuntar())]
            await mostrar(update, context, analisis.texto_suscripciones(), filas + volver)
        elif partes[1] == "cat":
            dias = None if partes[2] == "ciclo" else int(partes[2])
            await enviar_categorias(context, dias)
        elif partes[1] == "evo":
            await enviar_evolucion(context, int(partes[2]))
        elif partes[1] == "corregir":
            filas = [[(f"{m['fecha'][8:10]}/{m['fecha'][5:7]} {(m['contraparte'] or m['descripcion'] or '—')[:20]} "
                       f"{euros_cortos(-m['importe'])}", f"cc:{m['fila']}")]
                     for m in datos.todos("SELECT rowid AS fila, * FROM movimientos WHERE interno = 0 AND importe < 0 "
                                          "ORDER BY fecha DESC, importado DESC LIMIT 8")]
            await mostrar(update, context, "🏷️ ¿Qué gasto quieres cambiar de categoría?\n"
                                           "<i>Lo recordaré para los gastos parecidos.</i>", filas + volver, nuevo=True)
        return None
    if clave == "cc":
        m = datos.uno("SELECT rowid AS fila, * FROM movimientos WHERE rowid = ?", int(partes[1]))
        cats = list(CATEGORIAS.items())
        filas = [[(n, f"ccs:{partes[1]}:{c}") for c, n in cats[i:i + 2]] for i in range(0, len(cats), 2)]
        await mostrar(update, context, f"🏷️ «{e(m['contraparte'] or m['descripcion'])}» ({euros(m['importe'])}) "
                                       f"ahora está en {CATEGORIAS.get(m['categoria'], m['categoria'])}.\n¿Cuál es su categoría?",
                      filas + [CANCELAR])
        return None
    if clave == "ccs":
        m = datos.uno("SELECT * FROM movimientos WHERE rowid = ?", int(partes[1]))
        cambiados = movimientos.cambiar_categoria(m["id"], partes[2])
        await mostrar(update, context, f"✅ «{e(m['contraparte'] or m['descripcion'])}» ahora es {CATEGORIAS[partes[2]]}"
                                       f"{f' (y {cambiados - 1} gastos parecidos)' if cambiados > 1 else ''}.")
        return None

    if clave == "sub":
        detectadas = analisis.suscripciones_sin_apuntar()
        n = int(partes[1])
        if n >= len(detectadas):
            return "Ya estaba apuntada"
        sub = detectadas[n]
        ultimo = date.fromisoformat(sub["ultimo"])
        dia = ultimo.day
        ya_cobrada = (ultimo.year, ultimo.month) == (hoy.year, hoy.month) or dia < hoy.day
        desde = sumar_meses(hoy, 1, 1) if ya_cobrada else hoy
        deuda_id, accion = deudas.crear(sub["nombre"][:40], "suscripcion", sub["importe"], cuota=sub["importe"],
                                        dia=dia, desde=f"{desde:%Y-%m}")
        await mostrar(update, context, f"✅ Apuntada: {analisis.linea_deuda(deudas.obtener(deuda_id))}\n"
                                       f"🔔 Te recordaré el cobro cada día {dia} a las {config.hora_aviso_pago()}.",
                      con_deshacer(accion, [[("🔁 Suscripciones", "a:subs")]]))
        return None

    # --- Cobro
    if clave == "cobro":
        if partes[1] == "nuevo":
            esperar(context, "cobro_importe")
            await mostrar(update, context, "💶 ¿Cuánto has cobrado? Escribe el importe (ej. <b>1850</b>).", [CANCELAR], nuevo=True)
        elif partes[1] == "aun":
            datos.posponer("cobro", config.ahora() + timedelta(hours=3))
            await mostrar(update, context, "⏰ Vale, te lo vuelvo a preguntar en 3 horas.")
        elif partes[1] == "t":
            espera = context.user_data.get("espera") or {}
            if "importe" not in espera:
                return "Empieza otra vez con «Registrar cobro»"
            esperar(context, "cobro_fecha", importe=espera["importe"], tipo=partes[2])
            await mostrar(update, context, "¿Cuándo lo cobraste?",
                          [[("Hoy", "cobro:f:0"), ("Ayer", "cobro:f:1"), ("Anteayer", "cobro:f:2")],
                           [("✍️ Otra fecha (escríbela)", "nada")], CANCELAR])
        elif partes[1] == "f":
            espera = context.user_data.get("espera") or {}
            if "importe" not in espera:
                return "Empieza otra vez con «Registrar cobro»"
            await guardar_cobro(update, context, espera["importe"], espera["tipo"], hoy - timedelta(days=int(partes[2])))
        return None
    if clave == "nom":
        m = datos.uno("SELECT * FROM movimientos WHERE rowid = ?", int(partes[2]))
        if not m:
            return "Ese movimiento ya no existe"
        if partes[1] == "si":
            await guardar_cobro(update, context, m["importe"], "salario", date.fromisoformat(m["fecha"]), m["id"])
        else:
            datos.marcar_enviado(f"nomina_no:{m['id']}")
            await mostrar(update, context, "Vale, no lo cuento como nómina. ¿Quieres registrar tu cobro a mano?",
                          [[("💶 Registrar cobro", "cobro:nuevo")]])
        return None

    # --- Deudas
    if clave in bot_deudas.PREFIJOS:
        return await bot_deudas.boton(update, context, partes)

    # --- Proyección
    if clave in bot_proyeccion.PREFIJOS:
        return await bot_proyeccion.boton(update, context, partes)

    # --- Metas y colchón
    if clave in bot_metas.PREFIJOS:
        return await bot_metas.boton(update, context, partes)

    # --- Análisis completo
    if clave == "ac":
        await enviar_analisis_completo(context, partes[1], partes[2] if len(partes) > 2 else 0)
        return None

    # --- Recordatorios
    if clave == "r":
        if partes[1] == "nuevo":
            esperar(context, "rec_texto")
            await mostrar(update, context, "⏰ ¿Qué te recuerdo? (ej. <b>Pagar la tarjeta</b>)", [CANCELAR], nuevo=True)
        elif partes[1] == "tog":
            datos.ejecutar("UPDATE recordatorios SET activo = 1 - activo WHERE id = ?", int(partes[2]))
            await pantalla_recordatorios(update, context)
        elif partes[1] == "bo":
            datos.ejecutar("UPDATE recordatorios SET activo = -1 WHERE id = ?", int(partes[2]))
            await pantalla_recordatorios(update, context)
        return None
    if clave == "rf":
        espera = context.user_data.get("espera") or {}
        if "texto" not in espera:
            return "Empieza otra vez"
        base = {"texto": espera["texto"], "frecuencia": partes[1]}
        if partes[1] == "una":
            esperar(context, "rec_fecha", **base)
            await mostrar(update, context, "¿Qué día? (ej. <b>25/11</b>)", [CANCELAR])
        elif partes[1] == "semanal":
            esperar(context, "rec_dia_semana", **base)
            filas = [[(DIAS_SEMANA[n].capitalize(), f"rd:{n}") for n in range(i, min(i + 4, 7))] for i in (0, 4)]
            await mostrar(update, context, "¿Qué día de la semana?", filas + [CANCELAR])
        elif partes[1] == "mensual":
            esperar(context, "rec_dia_mes", **base)
            await mostrar(update, context, "¿Qué día del mes? (1-31)", [CANCELAR])
        else:
            esperar(context, "rec_hora", **base)
            await preguntar_hora(context, "rh")
        return None
    if clave == "rd":
        espera = context.user_data.get("espera") or {}
        esperar(context, "rec_hora", texto=espera.get("texto", ""), frecuencia="semanal", dia_semana=int(partes[1]))
        await preguntar_hora(context, "rh")
        return None
    if clave == "rh":
        espera = context.user_data.get("espera") or {}
        if espera.get("paso") != "rec_hora":
            return "Empieza otra vez"
        await crear_recordatorio(context, espera, f"{partes[1]}:{partes[2]}")
        return None

    # --- Ajustes
    if clave == "aj":
        return await atender_ajuste(update, context, partes)
    return None


async def atender_ajuste(update, context, partes):
    opcion = partes[1]
    if opcion == "lim":
        actual = config.limite_diario()
        nuevo = min(config.LIMITE_MAX, max(config.LIMITE_MIN, actual + (1 if partes[2] == "+" else -1)))
        if nuevo == actual:
            return f"El límite va de {config.LIMITE_MIN} a {config.LIMITE_MAX}"
        config.guardar("LIMITE_CONSULTAS_DIA", nuevo)
        await pantalla_ajustes(update, context)
    elif opcion == "hora":
        filas = [[(f"{h:02d}:00", f"aj:h:{h:02d}") for h in range(fila, fila + 6)] for fila in range(0, 24, 6)]
        await mostrar(update, context, "⏰ ¿A qué hora actualizo tus datos con el banco cada día? (en silencio)",
                      filas + [[("⬅️ Ajustes", "m:ajustes")]])
    elif opcion == "h":
        await mostrar(update, context, f"⏰ Elige los minutos ({partes[2]}:..):",
                      [[(f"{partes[2]}:{m}", f"aj:m:{partes[2]}:{m}") for m in ("00", "15", "30", "45")],
                       [("⬅️ Volver", "aj:hora")]])
    elif opcion == "m":
        config.guardar("HORA_SALDO_DIARIO", f"{partes[2]}:{partes[3]}")
        programar_actualizacion(context.job_queue)
        logging.info("Hora de actualización cambiada a %s:%s", partes[2], partes[3])
        await pantalla_ajustes(update, context)
        return f"Actualización a las {partes[2]}:{partes[3]}"
    elif opcion == "fr":
        filas = [[(f"{h:02d}:00", f"aj:fd:{h:02d}") for h in range(fila, fila + 4)] for fila in range(6, 22, 4)]
        await mostrar(update, context, "🔔 Los recordatorios de deudas se reparten en una franja del día.\n"
                                       "¿Desde qué hora?", filas + [[("⬅️ Ajustes", "m:ajustes")]])
    elif opcion == "fd":
        desde = int(partes[2])
        filas = [[(f"{h:02d}:00", f"aj:fh:{desde:02d}:{h:02d}") for h in range(fila, min(fila + 4, 24))]
                 for fila in range(desde + 1, 24, 4)]
        await mostrar(update, context, f"🔔 Desde las {desde:02d}:00. ¿Hasta qué hora?", filas + [[("⬅️ Volver", "aj:fr")]])
    elif opcion == "fh":
        config.guardar("FRANJA_DEUDAS_DESDE", f"{partes[2]}:00")
        config.guardar("FRANJA_DEUDAS_HASTA", f"{partes[3]}:00")
        logging.info("Franja de recordatorios de deudas: %s:00–%s:00", partes[2], partes[3])
        await pantalla_ajustes(update, context)
        return f"Recordatorios entre las {partes[2]}:00 y las {partes[3]}:00"
    elif opcion == "ds":
        esperar(context, "aj_dias_sin")
        await mostrar(update, context, "🤝 Para lo que te deben <b>sin día fijo</b>, ¿qué días del mes te pregunto si te han pagado?\n"
                                       "Elige o escribe los días separados por comas (ej. <b>1, 10, 20</b>):",
                      [[("5 · 15 · 25", "aj:dsp:5,15,25"), ("1 · 10 · 20", "aj:dsp:1,10,20")],
                       [("10 · 20 · 30", "aj:dsp:10,20,30"), ("1 · 15", "aj:dsp:1,15")], CANCELAR], nuevo=True)
    elif opcion == "dsp":
        context.user_data.pop("espera", None)
        config.guardar("DIAS_AVISO_SIN_DIA", partes[2])
        await pantalla_ajustes(update, context)
        return f"Días {partes[2].replace(',', ', ')}"
    elif opcion == "cobro":
        filas = [[(str(n), f"aj:cd:{n}") for n in range(i, i + 5)] for i in (1, 6, 11, 16, 21)]
        await mostrar(update, context, "💶 ¿Desde qué día del mes sueles cobrar? (el más pronto)",
                      filas + [[("⬅️ Ajustes", "m:ajustes")]])
    elif opcion == "cd":
        desde = int(partes[2])
        filas = [[(str(n), f"aj:ch:{desde}:{n}") for n in range(i, min(i + 5, 29))] for i in range(desde, 29, 5)]
        await mostrar(update, context, f"💶 Desde el día {desde}. ¿Y como muy tarde?", filas[:4] + [[("⬅️ Volver", "aj:cobro")]])
    elif opcion == "ch":
        config.guardar("DIA_COBRO_DESDE", partes[2])
        config.guardar("DIA_COBRO_HASTA", partes[3])
        await pantalla_ajustes(update, context)
        return f"Cobro entre el día {partes[2]} y el {partes[3]}"
    elif opcion in ("pres", "umbral"):
        esperar(context, f"aj_{opcion}")
        pregunta = ("🎯 ¿Cuánto quieres gastar como máximo en cada ciclo (de cobro a cobro)? (0 para quitarlo)"
                    if opcion == "pres" else "⚠️ ¿Por debajo de qué saldo neto te aviso? (0 para no avisar)")
        await mostrar(update, context, pregunta, [CANCELAR], nuevo=True)
    elif opcion == "avisos":
        filas = [[(f"{'🔔' if config.aviso_activo(c) else '🔕'} {n}", f"aj:av:{c}")] for c, n in AVISOS_CONFIGURABLES]
        await mostrar(update, context, "🔔 <b>Avisos automáticos</b>\nPulsa para activar o desactivar.\n"
                                       "<i>El del cobro está siempre activo.</i>", filas + [[("⬅️ Ajustes", "m:ajustes")]])
    elif opcion == "av":
        config.guardar(partes[2], "0" if config.aviso_activo(partes[2]) else "1")
        return await atender_ajuste(update, context, ["aj", "avisos"])
    elif opcion == "act":
        usadas, limite = contador.estado()
        await mostrar(update, context, f"🔄 ¿Actualizar ahora tus datos con el banco?\nGasta 1 consulta de hoy "
                                       f"(llevas {usadas}/{limite}).",
                      [[("✅ Sí, actualizar", "aj:act_si"), ("❌ No", "m:ajustes")]])
    elif opcion == "act_si":
        await actualizar_ahora(update, context)
    elif opcion == "exp":
        archivo, nombre = exportar.excel()
        await context.bot.send_document(estado["chat_id"], document=archivo, filename=nombre,
                                        caption="📤 Todos tus datos: saldos, movimientos, cobros, deudas, pagos y metas.")
    elif opcion == "cerrar":
        await update.callback_query.message.delete()
    return None


async def actualizar_ahora(update, context):
    await mostrar(update, context, "🔄 Actualizando con el banco...")
    async with candado_banco:
        try:
            resultado = await asyncio.to_thread(actualizacion.actualizar)
        except consultas.LimiteAlcanzado:
            usadas, limite = contador.estado()
            return await mostrar(update, context, f"🚫 Ya has usado {usadas}/{limite} consultas de hoy. "
                                                  "Puedes subir el límite en Ajustes.", [[("⬅️ Ajustes", "m:ajustes")]])
        except consultas.PermisoCaducado:
            await permiso_caducado(context.application)
            return await mostrar(update, context, "⚠️ El permiso de N26 no es válido. Ve al ordenador: la ventana del bot "
                                                  "te guía para renovarlo.")
        except (requests.ConnectionError, requests.Timeout):
            return await mostrar(update, context, "📡 No hay conexión con el banco. Prueba en un rato (no ha gastado consulta).")
        except Exception as error:
            detalle.exception("Fallo al actualizar")
            return await mostrar(update, context, consultas.texto_error(error))
    await mostrar(update, context, f"✅ Actualizado: {euros(resultado['total'])} en {resultado['cuentas']} cuentas · "
                                   f"{resultado['movimientos_nuevos']} movimientos nuevos.\n{consultas.pie()}",
                  [[("💰 Ver saldo", "m:saldo")]])


async def enviar_categorias(context, dias):
    texto = analisis.texto_categorias(dias)
    desde = config.ahora().date() - timedelta(days=dias - 1) if dias else ciclo.inicio()
    lista = movimientos.por_categoria(desde, config.ahora().date() + timedelta(days=1))
    filas = teclado([[("Este ciclo", "a:cat:ciclo"), ("30 días", "a:cat:30"), ("90 días", "a:cat:90")],
                     [("🏷️ Corregir una categoría", "a:corregir"), ("⬅️ Análisis", "m:analisis")]])
    if lista:
        titulo = "Gastos por categoría · " + (f"últimos {dias} días" if dias else "este ciclo")
        imagen = await asyncio.to_thread(graficos.categorias, [(CATEGORIAS.get(c, c), t) for c, t in lista], titulo)
        await context.bot.send_photo(estado["chat_id"], photo=imagen, caption=texto[:1024], parse_mode="HTML",
                                     reply_markup=filas)
    else:
        await context.bot.send_message(estado["chat_id"], texto, parse_mode="HTML", reply_markup=filas)


async def enviar_evolucion(context, dias):
    texto = analisis.texto_evolucion(dias)
    serie = analisis.serie_saldo(dias)
    filas = teclado([[("30 días", "a:evo:30"), ("90 días", "a:evo:90")], [("⬅️ Análisis", "m:analisis")]])
    if len(serie) >= 2:
        imagen = await asyncio.to_thread(graficos.evolucion, serie, f"Saldo total · últimos {dias} días")
        await context.bot.send_photo(estado["chat_id"], photo=imagen, caption=texto, parse_mode="HTML", reply_markup=filas)
    else:
        await context.bot.send_message(estado["chat_id"], texto, parse_mode="HTML", reply_markup=filas)


MENU_COMPLETO = [[("📌 Ahora", "ac:ahora"), ("📅 Por meses", "ac:meses"), ("📆 Anual", "ac:anual")],
                 [("💧 Flujo de caja", "ac:flujo:0"), ("🎯 Metas", "ac:metas")],
                 [("🩺 Salud financiera", "ac:salud"), ("🔮 Trayectoria", "ac:tray")],
                 [("⬅️ Análisis", "m:analisis")]]


async def enviar_analisis_completo(context, nombre, arg=0):
    """Pantallas del 🧭 Análisis completo: primero el gráfico (o los gráficos) y después el texto con los botones."""
    texto, imagenes = await asyncio.to_thread(analisis_completo.pantalla, nombre, arg)
    filas = [fila[:] for fila in MENU_COMPLETO]
    if nombre == "flujo":
        atras = int(arg or 0)
        navegar = [] if "No hay datos" in texto else [("◀️ Ciclo anterior", f"ac:flujo:{atras + 1}")]
        if atras > 0:
            navegar.append(("Siguiente ▶️", f"ac:flujo:{atras - 1}"))
        if navegar:
            filas.insert(0, navegar)
    for imagen in imagenes:
        await context.bot.send_photo(estado["chat_id"], photo=imagen)
    await context.bot.send_message(estado["chat_id"], texto, parse_mode="HTML", reply_markup=teclado(filas))


# =====================================================================
# Tareas programadas
# =====================================================================

async def tarea_actualizacion(context: ContextTypes.DEFAULT_TYPE):
    """Actualización diaria con el banco. Silenciosa: nunca envía mensajes."""
    if candado_banco.locked() or not actualizacion.toca():
        return
    async with candado_banco:
        try:
            await asyncio.to_thread(actualizacion.actualizar)
        except consultas.PermisoCaducado:
            await permiso_caducado(context.application)
        except consultas.LimiteAlcanzado:
            logging.warning("Actualización diaria: no quedan consultas hoy")
            datos.marcar_enviado(f"actualizacion_sin_consultas:{config.hoy()}")
        except (requests.ConnectionError, requests.Timeout):
            logging.warning("Actualización diaria: sin conexión, reintento en %s min", COMPROBAR_ACTUALIZACION // 60)
        except Exception as error:
            detalle.exception("Fallo en la actualización diaria")
            logging.warning("Actualización diaria fallida: %s", error)


def programar_actualizacion(job_queue):
    for tarea in job_queue.get_jobs_by_name("actualizacion"):
        tarea.schedule_removal()
    horas, minutos = config.hora_saldo_diario()
    job_queue.run_daily(tarea_actualizacion, time=time(horas, minutos, 20, tzinfo=config.zona()), name="actualizacion")


async def tarea_avisos(context: ContextTypes.DEFAULT_TYPE):
    try:
        pendientes = await asyncio.to_thread(avisos.calcular)
    except Exception:
        detalle.exception("Fallo calculando avisos")
        return
    for clave, texto_aviso, filas in pendientes:
        try:
            await enviar(context, texto_aviso, [[tuple(b) for b in fila] for fila in filas] or None)
            avisos.enviado(clave)
            logging.info("Aviso enviado: %s", clave.split(":")[0])
        except Exception:
            detalle.exception("No se ha podido enviar el aviso %s", clave)


async def permiso_caducado(app):
    datos.marcar_enviado("permiso_caducado")

    def al_terminar(exito):
        if exito:
            datos.ejecutar("DELETE FROM enviados WHERE clave = 'permiso_caducado'")
            avisar("✅ <b>N26 conectado de nuevo.</b> Tus datos ya se actualizan con normalidad.")

    if autenticacion.en_segundo_plano(al_terminar):
        logging.warning("El permiso de N26 no es válido: la ventana te guía para renovarlo")


async def tarea_permiso(context: ContextTypes.DEFAULT_TYPE):
    """Al arrancar y cada hora: si el permiso no es válido, pedir renovarlo (sin parar el bot)."""
    if autenticacion.en_marcha():
        return
    try:
        valido = await asyncio.to_thread(autenticacion.permiso_valido)
    except Exception as error:
        logging.warning("No he podido comprobar el permiso de N26: %s", error)
        return
    if not valido:
        await permiso_caducado(context.application)


async def anunciar_novedades(context: ContextTypes.DEFAULT_TYPE):
    """Tras instalar o actualizar, avisa una vez de lo nuevo y muestra los botones."""
    try:
        anunciada = int(VERSION_ANUNCIADA.read_text().strip())
    except (FileNotFoundError, ValueError):
        anunciada = 0
    if anunciada >= VERSION:
        return
    await context.bot.send_message(estado["chat_id"], NOVEDADES, parse_mode="HTML", reply_markup=TECLADO)
    VERSION_ANUNCIADA.write_text(str(VERSION))


async def error_no_controlado(update, context: ContextTypes.DEFAULT_TYPE):
    detalle.error("Error no controlado", exc_info=context.error)
    logging.warning("Error: %s", context.error)


def crear_aplicacion(token):
    return Application.builder().token(token).build()


def ejecutar():
    """Arranca el bot y bloquea hasta que se detiene."""
    config.cargar()
    datos.iniciar()
    colchon.actualizar_objetivo()
    estado["chat_id"] = int(config.valor("TELEGRAM_CHAT_ID"))
    app = crear_aplicacion(config.valor("TELEGRAM_TOKEN"))
    solo_yo = filters.Chat(chat_id=estado["chat_id"])
    app.add_handler(CommandHandler("start", inicio, filters=solo_yo))
    app.add_handler(CommandHandler("cancelar", inicio, filters=solo_yo))
    app.add_handler(CommandHandler("saldo", lambda u, c: menu(u, c, B_SALDO), filters=solo_yo))
    app.add_handler(CommandHandler("ajustes", lambda u, c: menu(u, c, B_AJUSTES), filters=solo_yo))
    app.add_handler(MessageHandler(solo_yo & filters.TEXT & ~filters.COMMAND, texto))
    app.add_handler(CallbackQueryHandler(pulsar))
    app.add_error_handler(error_no_controlado)
    cola = app.job_queue
    cola.run_once(anunciar_novedades, when=3)
    cola.run_once(tarea_permiso, when=5)
    cola.run_repeating(tarea_permiso, interval=COMPROBAR_PERMISO, first=COMPROBAR_PERMISO, name="permiso")
    programar_actualizacion(cola)
    cola.run_repeating(tarea_actualizacion, interval=COMPROBAR_ACTUALIZACION, first=40, name="recuperar_actualizacion")
    cola.run_repeating(tarea_avisos, interval=60, first=15, name="avisos")

    horas, minutos = config.hora_saldo_diario()
    usadas, limite = contador.estado()
    logging.info("Bot v%s funcionando · actualización diaria %02d:%02d (en silencio) · consultas hoy %s/%s",
                 VERSION, horas, minutos, usadas, limite)
    logging.info("Esperando mensajes de Telegram...")
    app.run_polling(close_loop=False, stop_signals=None)


def avisar(texto_aviso):
    """Envía un mensaje sin pasar por el bot (desde otro hilo o antes de arrancarlo). Nunca falla."""
    try:
        requests.post(f"https://api.telegram.org/bot{config.valor('TELEGRAM_TOKEN')}/sendMessage",
                      json={"chat_id": config.valor("TELEGRAM_CHAT_ID"), "text": texto_aviso, "parse_mode": "HTML"},
                      timeout=15)
    except Exception:
        pass
