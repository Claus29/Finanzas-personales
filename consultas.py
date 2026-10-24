"""Acceso a la conexión con N26 (cuentas guardadas) y textos comunes.

Desde la v5 el banco solo se consulta en la actualización diaria (actualizacion.py); este módulo
reúne lo que comparten la autenticación, la actualización y el bot.
"""
import html
from pathlib import Path

import config
import contador
from banco import EnableBanking, ErrorBanco
from contador import LimiteAlcanzado  # noqa: F401  (se reexporta)


class PermisoCaducado(Exception):
    """El permiso de N26 no es válido: hay que volver a autenticarse."""


def cliente():
    clave = Path(config.valor("EB_KEY_PATH"))
    return EnableBanking(config.valor("EB_APP_ID"), clave if clave.is_absolute() else config.BASE / clave)


def conexion():
    return config.leer_json(config.CONEXION, {})


def cuentas():
    return conexion().get("cuentas", [])


def formatear_importe(importe, moneda):
    texto = f"{float(importe):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €" if moneda == "EUR" else f"{texto} {moneda}"


def nombre_cuenta(cuenta):
    final = f" ···{cuenta['iban4']}" if cuenta.get("iban4") else ""
    return f"{cuenta['nombre']}{final}"


def pie():
    usadas, limite = contador.estado()
    return f"🔢 Consultas al banco hoy: {usadas}/{limite}"


def texto_error(e):
    """Mensaje de error comprensible para Telegram (HTML)."""
    if isinstance(e, ErrorBanco) and e.demasiadas_consultas:
        return "⏳ El banco ha rechazado la consulta por exceso de consultas hoy. Prueba de nuevo mañana."
    return f"❌ No he podido consultar el banco:\n<code>{html.escape(str(e))[:500]}</code>"
