"""Bot de Telegram: consulta el saldo de N26 una vez al día, a las 00:00, y te lo envía.

Si a las 00:00 el ordenador estaba apagado, dormido o sin internet, lo envía en cuanto
vuelve a estar disponible. Nunca hace más de una consulta al banco al día.
Solo habla con TELEGRAM_CHAT_ID.
    python bot.py
"""
import asyncio
import logging
import os
import sys
from datetime import time
from logging.handlers import RotatingFileHandler
from time import sleep

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from saldo import BASE, cargar_config, consultado_hoy, consultar_saldo, marcar_consulta, zona

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
candado = asyncio.Lock()


async def enviar_saldo(context: ContextTypes.DEFAULT_TYPE):
    async with candado:
        if consultado_hoy():
            return
        try:
            mensaje = await asyncio.to_thread(consultar_saldo)
        except (requests.ConnectionError, requests.Timeout):
            # Sin internet todavía (p. ej. el PC acaba de despertar): se reintenta más tarde.
            logging.warning("Sin conexión; reintento en %s minutos", COMPROBAR_CADA // 60)
            return
        except Exception as e:
            marcar_consulta()
            logging.exception("Fallo al consultar el saldo")
            # Sin Markdown: el texto del error puede traer caracteres que rompen el formato.
            await context.bot.send_message(CHAT_ID, f"❌ No he podido consultar el saldo de hoy:\n{e}")
            return
        marcar_consulta()
        await context.bot.send_message(CHAT_ID, mensaje, parse_mode="Markdown")
        logging.info("Saldo enviado")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == CHAT_ID:
        await update.message.reply_text("✅ Bot activo. Te enviaré tu saldo de N26 cada día a las 00:00.")


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
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_daily(enviar_saldo, time=time(0, 0, tzinfo=zona()), name="saldo_diario")
    app.job_queue.run_repeating(enviar_saldo, interval=COMPROBAR_CADA, first=30, name="recuperar_envio")
    logging.info("Bot iniciado. Saldo programado cada día a las 00:00 (%s)", zona())
    app.run_polling()


if __name__ == "__main__":
    main()
