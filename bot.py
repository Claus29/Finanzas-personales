"""Bot de Telegram: cada día a las 00:00 consulta el saldo de N26 y te lo envía.

Solo hace una petición al banco al día y solo habla con TELEGRAM_CHAT_ID.
    python bot.py
"""
import asyncio
import logging
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from banco import EnableBanking, ErrorBanco, uids_de_cuentas

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"]) if os.environ.get("TELEGRAM_CHAT_ID") else None
ZONA = ZoneInfo(os.environ.get("ZONA_HORARIA", "Europe/Madrid"))
DIAS_AVISO_CADUCIDAD = 15


def formatear_importe(importe, moneda):
    texto = f"{float(importe):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €" if moneda == "EUR" else f"{texto} {moneda}"


def consultar_saldo():
    """Hace la consulta al banco (bloqueante) y devuelve el mensaje para Telegram."""
    eb = EnableBanking(os.environ["EB_APP_ID"], os.environ["EB_KEY_PATH"])
    sesion = eb.sesion(os.environ["EB_SESSION_ID"])
    if sesion.get("status") != "AUTHORIZED":
        return (f"⚠️ El permiso de acceso a N26 no está activo (estado: {sesion.get('status')}).\n"
                "Ejecuta `python conectar_banco.py` para volver a conectarlo.")

    lineas = [f"💰 *Saldo N26* — {datetime.now(ZONA):%d/%m/%Y}"]
    for uid in uids_de_cuentas(sesion):
        importe, moneda, _ = eb.saldo_actual(uid)
        lineas.append(formatear_importe(importe, moneda))

    caduca = sesion.get("access", {}).get("valid_until")
    if caduca:
        dias = (datetime.fromisoformat(caduca.replace("Z", "+00:00")) - datetime.now(ZONA)).days
        if dias <= DIAS_AVISO_CADUCIDAD:
            lineas.append(f"\n⏳ El permiso del banco caduca en {dias} días. "
                          "Ejecuta `python conectar_banco.py` para renovarlo.")
    return "\n".join(lineas)


async def enviar_saldo_diario(context: ContextTypes.DEFAULT_TYPE):
    try:
        mensaje = await asyncio.to_thread(consultar_saldo)
    except (ErrorBanco, OSError, KeyError) as e:
        logging.exception("Fallo al consultar el saldo")
        # Sin Markdown: el texto del error puede traer caracteres que rompen el formato.
        await context.bot.send_message(CHAT_ID, f"❌ No he podido consultar el saldo de hoy:\n{e}")
        return
    await context.bot.send_message(CHAT_ID, mensaje, parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if CHAT_ID is None:
        await update.message.reply_text(
            f"Tu chat ID es {update.effective_chat.id}. Ponlo en TELEGRAM_CHAT_ID en el .env y reinicia el bot.")
    elif update.effective_chat.id == CHAT_ID:
        await update.message.reply_text("✅ Bot activo. Te enviaré tu saldo de N26 cada día a las 00:00.")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    if CHAT_ID is not None:
        app.job_queue.run_daily(enviar_saldo_diario, time=time(0, 0, tzinfo=ZONA), name="saldo_diario")
        logging.info("Saldo programado cada día a las 00:00 (%s)", ZONA)
    else:
        logging.warning("Falta TELEGRAM_CHAT_ID: escribe /start al bot para conocerlo.")
    app.run_polling()


if __name__ == "__main__":
    main()
