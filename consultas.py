"""Consulta del saldo de las cuentas elegidas, con contador diario y memoria del último saldo."""
import html
import logging
from datetime import datetime
from pathlib import Path

import requests

import config
import contador
from banco import EnableBanking, ErrorBanco, elegir_saldo
from contador import LimiteAlcanzado  # noqa: F401  (se reexporta para quien consulta)

DIAS_AVISO_CADUCIDAD = 15


class PermisoCaducado(Exception):
    """El permiso de N26 no es válido: hay que volver a autenticarse."""


def cliente():
    clave = Path(config.valor("EB_KEY_PATH"))
    return EnableBanking(config.valor("EB_APP_ID"), clave if clave.is_absolute() else config.BASE / clave)


def conexion():
    return config.leer_json(config.CONEXION, {})


def formatear_importe(importe, moneda):
    texto = f"{float(importe):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €" if moneda == "EUR" else f"{texto} {moneda}"


def nombre_cuenta(cuenta):
    final = f" ···{cuenta['iban4']}" if cuenta.get("iban4") else ""
    return f"{cuenta['nombre']}{final}"


def pie():
    usadas, limite = contador.estado()
    return f"🔢 Consultas hoy: {usadas}/{limite}"


def aviso_caducidad():
    caduca = conexion().get("valido_hasta")
    if not caduca:
        return ""
    dias = (datetime.fromisoformat(caduca.replace("Z", "+00:00")) - config.ahora()).days
    if dias > DIAS_AVISO_CADUCIDAD:
        return ""
    return (f"\n⏳ El permiso de N26 caduca en {max(dias, 0)} días. Cuando caduque, "
            "la ventana del bot te pedirá renovarlo.")


def consultar():
    """Pregunta el saldo al banco (bloqueante) y devuelve el mensaje en HTML, sin el pie.

    Gasta una consulta del día. Si la consulta no llega al banco (sin internet o permiso caducado),
    la consulta se devuelve al contador.
    """
    cuentas = conexion().get("cuentas")
    if not cuentas or not config.valor("EB_SESSION_ID"):
        raise PermisoCaducado("No hay ninguna cuenta conectada.")
    contador.usar()
    try:
        eb = cliente()
        lineas = [f"💰 <b>Saldo N26</b> — {config.ahora():%d/%m/%Y %H:%M}"]
        for cuenta in cuentas:
            saldos = eb.saldos(cuenta["uid"])
            logging.getLogger("detalle").info("Saldos de %s: %s", nombre_cuenta(cuenta), "; ".join(
                f"{b.get('balance_type')}={b.get('balance_amount', {}).get('amount')} "
                f"{b.get('balance_amount', {}).get('currency')}" for b in saldos) or "ninguno")
            elegido = elegir_saldo(saldos)
            importe = formatear_importe(elegido[0], elegido[1]) if elegido else "sin datos"
            lineas.append(f"{html.escape(nombre_cuenta(cuenta))}: <b>{importe}</b>")
    except (requests.ConnectionError, requests.Timeout):
        contador.devolver()
        raise
    except ErrorBanco as e:
        if e.permiso_caducado:
            contador.devolver()
            raise PermisoCaducado(str(e)) from e
        raise
    except Exception:
        contador.devolver()  # fallo nuestro (p. ej. la clave .pem): no ha llegado al banco
        raise
    cuerpo = "\n".join(lineas) + aviso_caducidad()
    config.escribir_json(config.ULTIMO_SALDO, {"cuando": config.ahora().isoformat(), "cuerpo": cuerpo})
    return cuerpo


def ultimo_saldo():
    """(cuándo, cuerpo HTML) del último saldo obtenido, o (None, None)."""
    datos = config.leer_json(config.ULTIMO_SALDO, {})
    if not datos.get("cuando"):
        return None, None
    return datetime.fromisoformat(datos["cuando"]), datos["cuerpo"]


def texto_error(e):
    """Mensaje de error comprensible para Telegram (HTML)."""
    if isinstance(e, ErrorBanco) and e.demasiadas_consultas:
        return "⏳ El banco ha rechazado la consulta por exceso de consultas hoy. Prueba de nuevo mañana."
    return f"❌ No he podido consultar el saldo:\n<code>{html.escape(str(e))[:500]}</code>"
