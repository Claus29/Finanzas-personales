"""Bot de Telegram para ver el saldo de N26.

- Botón «💰 Ver saldo»: consulta el saldo cuando quieras (cuenta en el límite diario).
- Botón «⚙️ Ajustes»: límite de consultas al día, hora del saldo automático y activarlo o no.
- Saldo automático cada día a la hora elegida (00:00 por defecto). Si a esa hora el ordenador
  estaba apagado o sin internet, se envía en cuanto vuelve (una sola vez al día).
Solo habla con TELEGRAM_CHAT_ID. Lo arranca principal.py, que lo vuelve a lanzar tras renovar
el permiso del banco cuando ejecutar() devuelve "reautenticar".
"""
import asyncio
import logging
from datetime import time, timedelta

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import config
import consultas
import contador

# Súbelo y cambia NOVEDADES en cada actualización con cambios visibles: el bot las anuncia una vez.
VERSION = 4
NOVEDADES = ("✨ <b>Bot actualizado</b>\n\n"
             "• «💰 Ver saldo»: tu saldo cuando quieras, con el nombre de cada cuenta.\n"
             "• «⚙️ Ajustes»: límite de consultas al día (4 por defecto), hora del saldo automático "
             "y activarlo o desactivarlo.\n"
             "• Cada respuesta te dice cuántas consultas llevas hoy.")
VERSION_ANUNCIADA = config.BASE / "version_anunciada.txt"

BOTON_SALDO = "💰 Ver saldo"
BOTON_AJUSTES = "⚙️ Ajustes"
TECLADO = ReplyKeyboardMarkup([[KeyboardButton(BOTON_SALDO), KeyboardButton(BOTON_AJUSTES)]],
                              resize_keyboard=True, is_persistent=True)
COMPROBAR_CADA = 30 * 60  # segundos entre comprobaciones de "¿se envió ya el saldo automático de hoy?"
# Si se pulsa «Ver saldo» varias veces seguidas, se repite el último saldo sin gastar consulta.
REUTILIZAR_SALDO = timedelta(minutes=10)
AVISO_PERMISO = ("⚠️ <b>El permiso de N26 ha caducado o se ha desvinculado.</b>\n"
                 "Ve al ordenador: la ventana «Bot Finanzas» te guiará para renovarlo.\n"
                 "(Si desvinculaste la cuenta en Enable Banking, pulsa antes «Link accounts» en tu aplicación.)")

estado = {"chat_id": None, "motivo_parada": None}
candado_banco = asyncio.Lock()       # nunca dos consultas al banco a la vez
candado_automatico = asyncio.Lock()  # la tarea de la hora fija y la de recuperación no se solapan


# ---------- Consultas ----------

async def consultar():
    async with candado_banco:
        return await asyncio.to_thread(consultas.consultar)


async def pedir_reautenticacion(context: ContextTypes.DEFAULT_TYPE):
    if estado["motivo_parada"]:
        return
    estado["motivo_parada"] = "reautenticar"
    logging.warning("El permiso de N26 no es válido: hay que renovarlo")
    await context.bot.send_message(estado["chat_id"], AVISO_PERMISO, parse_mode="HTML")
    context.application.stop_running()


def hace(cuando):
    minutos = int((config.ahora() - cuando).total_seconds() // 60)
    return "hace menos de 1 minuto" if minutos < 1 else f"hace {minutos} min"


async def ver_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    responder = update.message.reply_text
    cuando, cuerpo = consultas.ultimo_saldo()
    if cuando and config.ahora() - cuando < REUTILIZAR_SALDO:
        await responder(f"{cuerpo}\n<i>(Saldo de {hace(cuando)}: no gasta consulta)</i>\n\n{consultas.pie()}",
                        parse_mode="HTML", reply_markup=TECLADO)
        return
    await update.message.chat.send_action("typing")
    try:
        cuerpo = await consultar()
    except consultas.LimiteAlcanzado:
        usadas, limite = contador.estado()
        texto = (f"🚫 Has usado {usadas}/{limite} consultas de hoy. Se renuevan a las 00:00.\n"
                 f"Puedes cambiar el límite en «{BOTON_AJUSTES}».")
        if cuerpo:
            texto += f"\n\nÚltimo saldo conocido ({hace(cuando)}):\n{cuerpo}"
        await responder(texto, parse_mode="HTML", reply_markup=TECLADO)
        logging.info("Límite diario alcanzado (%s/%s)", usadas, limite)
        return
    except consultas.PermisoCaducado:
        await pedir_reautenticacion(context)
        return
    except (requests.ConnectionError, requests.Timeout):
        await responder("📡 No hay conexión con el banco. Prueba en un rato (no ha gastado consulta).",
                        reply_markup=TECLADO)
        return
    except Exception as e:
        logging.getLogger("detalle").exception("Fallo al consultar el saldo")
        logging.warning("No se ha podido consultar el saldo: %s", e)
        await responder(f"{consultas.texto_error(e)}\n\n{consultas.pie()}", parse_mode="HTML", reply_markup=TECLADO)
        return
    await responder(f"{cuerpo}\n\n{consultas.pie()}", parse_mode="HTML", reply_markup=TECLADO)
    logging.info("Saldo enviado (botón) · consultas hoy %s/%s", *contador.estado())


async def saldo_automatico(context: ContextTypes.DEFAULT_TYPE):
    async with candado_automatico:
        if not config.saldo_diario_activo() or estado["motivo_parada"]:
            return
        horas, minutos = config.hora_saldo_diario()
        momento = config.ahora()
        if momento < momento.replace(hour=horas, minute=minutos, second=0, microsecond=0):
            return
        if config.ULTIMO_ENVIO_AUTOMATICO.exists() and \
                config.ULTIMO_ENVIO_AUTOMATICO.read_text().strip() == config.hoy():
            return
        try:
            cuerpo = await consultar()
        except (requests.ConnectionError, requests.Timeout):
            logging.warning("Sin conexión para el saldo automático; reintento en %s min", COMPROBAR_CADA // 60)
            return
        except consultas.PermisoCaducado:
            await pedir_reautenticacion(context)
            return
        except consultas.LimiteAlcanzado:
            texto = "🚫 Saldo automático: ya has usado todas las consultas de hoy."
        except Exception as e:
            logging.getLogger("detalle").exception("Fallo en el saldo automático")
            logging.warning("No se ha podido consultar el saldo automático: %s", e)
            texto = consultas.texto_error(e)
        else:
            texto = f"🕛 <b>Saldo automático</b>\n{cuerpo}"
        config.ULTIMO_ENVIO_AUTOMATICO.write_text(config.hoy())
        await context.bot.send_message(estado["chat_id"], f"{texto}\n\n{consultas.pie()}",
                                       parse_mode="HTML", reply_markup=TECLADO)
        logging.info("Saldo automático enviado")


def programar_saldo_automatico(job_queue):
    for tarea in job_queue.get_jobs_by_name("saldo_automatico"):
        tarea.schedule_removal()
    horas, minutos = config.hora_saldo_diario()
    job_queue.run_daily(saldo_automatico, time=time(horas, minutos, tzinfo=config.zona()), name="saldo_automatico")


# ---------- Ajustes ----------

def boton(texto, datos):
    return InlineKeyboardButton(texto, callback_data=datos)


def texto_ajustes():
    usadas, limite = contador.estado()
    horas, minutos = config.hora_saldo_diario()
    activo = "activado" if config.saldo_diario_activo() else "desactivado"
    texto = (f"⚙️ <b>Ajustes</b>\n\n"
             f"🔢 Consultas hoy: {usadas}/{limite} (se reinician a las 00:00)\n"
             f"📊 Límite diario: {limite} consultas\n"
             f"⏰ Saldo automático: {horas:02d}:{minutos:02d} ({activo})")
    if limite > config.LIMITE_RECOMENDADO:
        texto += (f"\n\n⚠️ Con más de {config.LIMITE_RECOMENDADO} consultas al día, "
                  "N26 podría rechazar algunas.")
    return texto


def teclado_ajustes():
    limite = config.limite_diario()
    horas, minutos = config.hora_saldo_diario()
    activo = config.saldo_diario_activo()
    return InlineKeyboardMarkup([
        [boton("➖", "lim:-"), boton(f"Límite: {limite}/día", "nada"), boton("➕", "lim:+")],
        [boton(f"⏰ Hora: {horas:02d}:{minutos:02d}", "hora"),
         boton("🔔 Automático: sí" if activo else "🔕 Automático: no", "auto")],
        [boton("✖️ Cerrar", "cerrar")],
    ])


def teclado_horas():
    filas = [[boton(f"{h:02d}", f"h:{h:02d}") for h in range(fila, fila + 6)] for fila in range(0, 24, 6)]
    return InlineKeyboardMarkup(filas + [[boton("⬅️ Volver", "volver")]])


def teclado_minutos(horas):
    return InlineKeyboardMarkup([[boton(f"{horas}:{m}", f"m:{horas}:{m}") for m in ("00", "15", "30", "45")],
                                 [boton("⬅️ Volver", "hora")]])


async def ajustes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(texto_ajustes(), parse_mode="HTML", reply_markup=teclado_ajustes())


async def pulsar_ajuste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    consulta = update.callback_query
    if update.effective_chat.id != estado["chat_id"]:
        await consulta.answer()
        return
    datos = consulta.data
    aviso = None
    texto, teclado = texto_ajustes, teclado_ajustes
    if datos in ("lim:-", "lim:+"):
        actual = config.limite_diario()
        nuevo = min(config.LIMITE_MAX, max(config.LIMITE_MIN, actual + (1 if datos == "lim:+" else -1)))
        if nuevo == actual:
            aviso = f"El límite va de {config.LIMITE_MIN} a {config.LIMITE_MAX}"
        else:
            config.guardar("LIMITE_CONSULTAS_DIA", nuevo)
            logging.info("Límite diario cambiado a %s", nuevo)
    elif datos == "auto":
        config.guardar("SALDO_DIARIO_ACTIVO", "0" if config.saldo_diario_activo() else "1")
        logging.info("Saldo automático %s", "activado" if config.saldo_diario_activo() else "desactivado")
    elif datos == "hora":
        texto, teclado = (lambda: "⏰ ¿A qué hora quieres recibir el saldo automático?"), teclado_horas
    elif datos.startswith("h:"):
        horas = datos[2:]
        texto, teclado = (lambda: f"⏰ Elige los minutos ({horas}:..):"), (lambda: teclado_minutos(horas))
    elif datos.startswith("m:"):
        nueva = datos[2:]
        config.guardar("HORA_SALDO_DIARIO", nueva)
        programar_saldo_automatico(context.job_queue)
        aviso = f"Saldo automático a las {nueva}"
        logging.info("Hora del saldo automático cambiada a %s", nueva)
    elif datos == "cerrar":
        await consulta.answer()
        await consulta.message.delete()
        return
    await consulta.answer(aviso)
    if datos == "nada":
        return
    try:
        await consulta.edit_message_text(texto(), parse_mode="HTML", reply_markup=teclado())
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# ---------- Otros ----------

async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ <b>Bot activo</b>\n"
        f"• «{BOTON_SALDO}»: tu saldo cuando quieras.\n"
        f"• «{BOTON_AJUSTES}»: límite diario y saldo automático.\n\n" + consultas.pie(),
        parse_mode="HTML", reply_markup=TECLADO)


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
    logging.getLogger("detalle").error("Error no controlado", exc_info=context.error)
    logging.warning("Error: %s", context.error)


def crear_aplicacion(token):
    return Application.builder().token(token).build()


def ejecutar():
    """Arranca el bot y bloquea hasta que se detiene. Devuelve "reautenticar" si hay que renovar el permiso."""
    config.cargar()
    estado.update(chat_id=int(config.valor("TELEGRAM_CHAT_ID")), motivo_parada=None)
    app = crear_aplicacion(config.valor("TELEGRAM_TOKEN"))
    solo_yo = filters.Chat(chat_id=estado["chat_id"])
    app.add_handler(CommandHandler("start", inicio, filters=solo_yo))
    app.add_handler(CommandHandler("saldo", ver_saldo, filters=solo_yo))
    app.add_handler(CommandHandler("ajustes", ajustes, filters=solo_yo))
    app.add_handler(MessageHandler(solo_yo & filters.Text([BOTON_SALDO]), ver_saldo))
    app.add_handler(MessageHandler(solo_yo & filters.Text([BOTON_AJUSTES]), ajustes))
    app.add_handler(CallbackQueryHandler(pulsar_ajuste))
    app.add_handler(MessageHandler(solo_yo & ~filters.COMMAND, inicio))  # cualquier otra cosa: muestra los botones
    app.add_error_handler(error_no_controlado)
    app.job_queue.run_once(anunciar_novedades, when=3)
    programar_saldo_automatico(app.job_queue)
    app.job_queue.run_repeating(saldo_automatico, interval=COMPROBAR_CADA, first=20, name="recuperar_saldo")

    horas, minutos = config.hora_saldo_diario()
    usadas, limite = contador.estado()
    logging.info("Bot v%s funcionando · consultas hoy %s/%s · saldo automático %02d:%02d (%s)", VERSION,
                 usadas, limite, horas, minutos, "activado" if config.saldo_diario_activo() else "desactivado")
    logging.info("Esperando mensajes de Telegram...")
    app.run_polling(close_loop=False, stop_signals=None)
    return estado["motivo_parada"]


def avisar(texto):
    """Envía un mensaje sin arrancar el bot (p. ej. antes de pedir la autenticación). Nunca falla."""
    try:
        requests.post(f"https://api.telegram.org/bot{config.valor('TELEGRAM_TOKEN')}/sendMessage",
                      json={"chat_id": config.valor("TELEGRAM_CHAT_ID"), "text": texto, "parse_mode": "HTML"},
                      timeout=15)
    except Exception:
        pass
