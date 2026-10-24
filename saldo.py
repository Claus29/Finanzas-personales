"""Consulta del saldo y registro de la última consulta (como máximo una al día)."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from banco import EnableBanking

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
ULTIMA_CONSULTA = BASE / "ultima_consulta.txt"
DIAS_AVISO_CADUCIDAD = 15
AVISO_RECONECTAR = "Abre el acceso directo «Bot Finanzas - Reconectar banco» del escritorio."


def cargar_config():
    # override=True: si se reconecta el banco, el bot usa la sesión nueva sin reiniciarse.
    load_dotenv(ENV, override=True)


def zona():
    return ZoneInfo(os.environ.get("ZONA_HORARIA") or "Europe/Madrid")


def hoy():
    return datetime.now(zona()).date().isoformat()


def consultado_hoy():
    return ULTIMA_CONSULTA.exists() and ULTIMA_CONSULTA.read_text().strip() == hoy()


def marcar_consulta():
    ULTIMA_CONSULTA.write_text(hoy())


def cliente():
    clave = Path(os.environ["EB_KEY_PATH"])
    return EnableBanking(os.environ["EB_APP_ID"], clave if clave.is_absolute() else BASE / clave)


def formatear_importe(importe, moneda):
    texto = f"{float(importe):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €" if moneda == "EUR" else f"{texto} {moneda}"


def mensaje_saldo(eb, sesion):
    if sesion.get("status") != "AUTHORIZED":
        return f"⚠️ El permiso de acceso a N26 no está activo (estado: {sesion.get('status')}).\n{AVISO_RECONECTAR}"

    lineas = [f"💰 *Saldo N26* — {datetime.now(zona()):%d/%m/%Y %H:%M}"]
    cuentas = [c if isinstance(c, str) else c["uid"] for c in sesion.get("accounts", [])]
    for n, uid in enumerate(cuentas, 1):
        importe, moneda, _ = eb.saldo_actual(uid)
        prefijo = f"Cuenta {n}: " if len(cuentas) > 1 else ""
        lineas.append(prefijo + formatear_importe(importe, moneda))

    caduca = sesion.get("access", {}).get("valid_until")
    if caduca:
        dias = (datetime.fromisoformat(caduca.replace("Z", "+00:00")) - datetime.now(zona())).days
        if dias <= DIAS_AVISO_CADUCIDAD:
            lineas.append(f"\n⏳ El permiso del banco caduca en {dias} días. {AVISO_RECONECTAR}")
    return "\n".join(lineas)


def texto_error(e):
    """Mensaje de error comprensible para Telegram (sin Markdown)."""
    if "Error 429" in str(e):
        return "⏳ El banco limita el número de consultas al día. Prueba de nuevo más tarde."
    return f"❌ No he podido consultar el saldo:\n{e}"


def consultar_saldo():
    """Hace la consulta al banco (bloqueante) y devuelve el mensaje para Telegram."""
    cargar_config()
    eb = cliente()
    return mensaje_saldo(eb, eb.sesion(os.environ["EB_SESSION_ID"]))
