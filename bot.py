"""Bot de Telegram para ver el saldo de N26.

- Cada día a las 00:00 te envía el saldo. Si a esa hora el ordenador estaba apagado, dormido
  o sin internet, lo envía en cuanto vuelve a estar disponible (una sola vez al día).
- Botón «💰 Ver saldo» para consultarlo cuando quieras.
Solo habla con TELEGRAM_CHAT_ID.
    python bot.py
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, time, timedelta
from logging.handlers import RotatingFileHandler
from time import sleep

import requests
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from saldo import BASE, cargar_config, consultado_hoy, consultar_saldo, marcar_consulta, texto_error, zona

# Súbelo y cambia NOVEDADES en cada actualización con cambios visibles: el bot las anuncia una vez.
VERSION = 2
NOVEDADES = ("✨ *Bot actualizado*\n\n"
             "Nuevo: botón «💰 Ver saldo» abajo del chat para consultar tu saldo cuando quieras.")

cargar_config()
logging.basicConfig(
    handlers=[RotatingFileHandler(BASE / "bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
# httpx registra cada petición a Telegram con el token en la URL: no queremos eso en el log.
logging.getLogger("httpx").setLevel(logging.WARNING)
# Con pythonw no hay consola: cualquier error fatal tiene que quedar en bot.log.
sys.excepthook = lambda *error: logging.critical("Error fatal", exc_info=error)

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
COMPROBAR_CADA = 30 * 60  # segundos entre comprobaciones de "¿se envió ya el saldo de hoy?"
# Los bancos limitan las consultas diarias: si se pulsa el botón varias veces seguidas,
# se reutiliza el último saldo durante unos minutos en vez de volver a preguntar al banco.
REUTILIZAR_SALDO = timedelta(minutes=10)
VERSION_ANUNCIADA = BASE / "version_anunciada.txt"

BOTON_SALDO = "💰 Ver saldo"
TECLADO = ReplyKeyboardMarkup([[KeyboardButton(BOTON_SALDO)]], resize_keyboard=True, is_persistent=True)

candado = asyncio.Lock()
candado_diario = asyncio.Lock()  # la tarea de las 00:00 y la de recuperación no deben solaparse
ultimo_saldo = {"cuando": None, "mensaje": None}


async def pedir_saldo():
    """Consulta el banco y recuerda el resultado. Las excepciones se propagan."""
    async with candado:
        mensaje = await asyncio.to_thread(consultar_saldo)
        ultimo_saldo.update(cuando=datetime.now(zona()), mensaje=mensaje)
        return mensaje


async def enviar_saldo_diario(context: ContextTypes.DEFAULT_TYPE):
    async with candado_diario:
        if consultado_hoy():
            return
        try:
            mensaje = await pedir_saldo()
        except (requests.ConnectionError, requests.Timeout):
            # Sin internet todavía (p. ej. el PC acaba de despertar): se reintenta más tarde.
            logging.warning("Sin conexión; reintento en %s minutos", COMPROBAR_CADA // 60)
            return
        except Exception as e:
            marcar_consulta()
            logging.exception("Fallo al consultar el saldo diario")
            # Sin Markdown: el texto del error puede traer caracteres que rompen el formato.
            await context.bot.send_message(CHAT_ID, texto_error(e), reply_markup=TECLADO)
            return
        marcar_consulta()
        await context.bot.send_message(CHAT_ID, mensaje, parse_mode="Markdown", reply_markup=TECLADO)
        logging.info("Saldo diario enviado")


async def ver_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cuando = ultimo_saldo["cuando"]
    if cuando and datetime.now(zona()) - cuando < REUTILIZAR_SALDO:
        await update.message.reply_text(ultimo_saldo["mensaje"], parse_mode="Markdown", reply_markup=TECLADO)
        return
    await update.message.chat.send_action("typing")
    try:
        mensaje = await pedir_saldo()
    except (requests.ConnectionError, requests.Timeout):
        await update.message.reply_text("📡 No hay conexión con el banco. Prueba en un rato.", reply_markup=TECLADO)
        return
    except Exception as e:
        logging.exception("Fallo al consultar el saldo desde el botón")
        await update.message.reply_text(texto_error(e), reply_markup=TECLADO)
        return
    await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=TECLADO)
    logging.info("Saldo enviado desde el botón")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot activo.\n• Cada día a las 00:00 te envío tu saldo de N26.\n"
        f"• Pulsa «{BOTON_SALDO}» cuando quieras verlo.", reply_markup=TECLADO)


async def anunciar_novedades(context: ContextTypes.DEFAULT_TYPE):
    """Tras instalar o actualizar, avisa una vez de lo nuevo y muestra el botón."""
    try:
        anunciada = int(VERSION_ANUNCIADA.read_text().strip())
    except (FileNotFoundError, ValueError):
        anunciada = 0
    if anunciada >= VERSION:
        return
    await context.bot.send_message(CHAT_ID, NOVEDADES, parse_mode="Markdown", reply_markup=TECLADO)
    VERSION_ANUNCIADA.write_text(str(VERSION))


def esperar_internet():
    """Al arrancar con Windows puede no haber red todavía; sin esto el bot se cerraría."""
    while True:
        try:
            requests.get("https://api.telegram.org", timeout=10)
            return
        except requests.RequestException:
            logging.warning("Sin conexión con Telegram; reintento en 30 segundos")
            sleep(30)


def main():
    esperar_internet()
    app = Application.builder().token(TOKEN).build()
    solo_yo = filters.Chat(chat_id=CHAT_ID)
    app.add_handler(CommandHandler("start", start, filters=solo_yo))
    app.add_handler(CommandHandler("saldo", ver_saldo, filters=solo_yo))
    app.add_handler(MessageHandler(solo_yo & filters.Text([BOTON_SALDO]), ver_saldo))
    app.add_handler(MessageHandler(solo_yo & ~filters.COMMAND, start))  # cualquier otro mensaje: vuelve a mostrar el botón
    app.job_queue.run_once(anunciar_novedades, when=5)
    app.job_queue.run_daily(enviar_saldo_diario, time=time(0, 0, tzinfo=zona()), name="saldo_diario")
    app.job_queue.run_repeating(enviar_saldo_diario, interval=COMPROBAR_CADA, first=30, name="recuperar_envio")
    logging.info("Bot v%s iniciado. Saldo programado cada día a las 00:00 (%s)", VERSION, zona())
    app.run_polling()


if __name__ == "__main__":
    main()
